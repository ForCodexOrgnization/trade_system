from tempfile import TemporaryDirectory
from pathlib import Path
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext

from django.test import SimpleTestCase, override_settings

from .ibkr_client import IBKRClient
from .services import IBKRSyncService


FLEX_XML = '''<FlexQueryResponse><FlexStatements><FlexStatement><Trades>
<Trade ibExecID="exec-1" ibOrderID="order-1" accountId="DU123" symbol="MCLN6" description="MCL Jul26" conid="123" assetCategory="FUT" currency="USD" exchange="NYMEX" buySell="BUY" quantity="6" tradePrice="90" ibCommission="-1.25" fifoPnlRealized="0" dateTime="20260306;142202" multiplier="100" tradeID="trade-1" orderType="LMT" proceeds="0" netCash="0" />
</Trades></FlexStatement></FlexStatements></FlexQueryResponse>'''


class IBKRClientLocalCacheTests(SimpleTestCase):
    @override_settings(
        IBKR_FLEX_TOKEN='token',
        IBKR_FLEX_QUERY_ID='query',
        IBKR_FLEX_SEND_REQUEST_URL='https://example.test/send',
        IBKR_FLEX_GET_STATEMENT_URL='https://example.test/get',
    )
    @patch('apps.brokers.ibkr_client.requests.get')
    def test_unavailable_explicit_history_range_is_an_empty_chunk(self, get):
        get.return_value = SimpleNamespace(
            text='''<FlexStatementResponse><Status>Fail</Status><ErrorCode>1003</ErrorCode>
            <ErrorMessage>Statement is not available.</ErrorMessage></FlexStatementResponse>''',
            raise_for_status=lambda: None,
        )

        xml_text = IBKRClient().fetch_flex_statement_xml(
            from_date=date(2022, 1, 1),
            to_date=date(2022, 12, 31),
        )

        self.assertEqual(IBKRClient().parse_flex_xml(xml_text), [])
        get.assert_called_once()

    @override_settings(
        IBKR_FLEX_TOKEN='token',
        IBKR_FLEX_QUERY_ID='query',
        IBKR_FLEX_SEND_REQUEST_URL='https://example.test/send',
        IBKR_FLEX_GET_STATEMENT_URL='https://example.test/get',
    )
    @patch('apps.brokers.ibkr_client.requests.get')
    def test_1025_stops_without_retrying_and_explains_token_recovery(self, get):
        get.return_value = SimpleNamespace(
            text='''<FlexStatementResponse><Status>Fail</Status><ErrorCode>1025</ErrorCode>
            <ErrorMessage>Too many failed attempts.</ErrorMessage></FlexStatementResponse>''',
            raise_for_status=lambda: None,
        )

        with self.assertRaisesRegex(RuntimeError, 'account/service-level state'):
            IBKRClient().fetch_flex_statement_xml()

        get.assert_called_once()

    def test_incomplete_statement_response_is_not_treated_as_ready(self):
        incomplete_xml = '''<FlexStatementResponse>
        <Status>Fail</Status><ErrorCode>1004</ErrorCode>
        <ErrorMessage>Statement is incomplete at this time.</ErrorMessage>
        </FlexStatementResponse>'''

        self.assertFalse(IBKRClient()._is_flex_statement_ready(incomplete_xml))
        self.assertTrue(IBKRClient()._is_flex_statement_ready(FLEX_XML))

    def test_real_fetch_caches_flex_xml(self):
        with TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir), IBKR_FLEX_HISTORY_YEARS=None):
            client = IBKRClient()
            client.fetch_flex_statement_xml = Mock(return_value=FLEX_XML)

            rows = client.fetch_all_executions()

            cache_path = Path(tmpdir) / 'data' / 'ibkr_last_flex_statement.xml'
            self.assertTrue(cache_path.exists())
            self.assertEqual(len(client.parse_flex_xml(cache_path.read_text(encoding='utf-8'))), 1)
            self.assertEqual(rows[0]['execution_id'], 'exec-1')
            self.assertEqual(client.last_fetch_metadata['source'], 'ibkr_query_period')
            client.fetch_flex_statement_xml.assert_called_once_with()

    def test_local_fetch_reads_cached_flex_xml_without_requesting_ibkr(self):
        with TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            cache_path = Path(tmpdir) / 'data' / 'ibkr_last_flex_statement.xml'
            cache_path.parent.mkdir(parents=True)
            cache_path.write_text(FLEX_XML, encoding='utf-8')
            client = IBKRClient(use_local_flex_xml=True)
            client.fetch_flex_statement_xml = lambda: self.fail('local sync should not call IBKR')

            rows = client.fetch_all_executions()

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['order_id'], 'order-1')

    def test_local_cache_existence_is_reported_before_reading(self):
        with TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            client = IBKRClient(use_local_flex_xml=True)

            self.assertFalse(client.has_flex_statement_cache)
            with self.assertRaises(FileNotFoundError):
                client.fetch_all_executions()

    @override_settings(IBKR_FLEX_HISTORY_YEARS=1)
    def test_full_history_is_split_into_at_most_365_day_ranges(self):
        ranges = IBKRClient().full_history_ranges(today=date(2026, 7, 31))

        self.assertEqual(ranges[0][0], date(2025, 1, 1))
        self.assertEqual(ranges[-1][1], date(2026, 7, 31))
        self.assertTrue(all((end - start).days <= 364 for start, end in ranges))
        self.assertTrue(all(
            ranges[index][1] + timedelta(days=1) == ranges[index + 1][0]
            for index in range(len(ranges) - 1)
        ))

    def test_combined_cache_contains_trades_from_every_chunk(self):
        client = IBKRClient()
        combined = client.combine_flex_documents([FLEX_XML, FLEX_XML.replace('exec-1', 'exec-2')])

        rows = client.parse_flex_xml(combined)

        self.assertEqual([row['execution_id'] for row in rows], ['exec-1', 'exec-2'])


class IBKRSyncServiceTests(SimpleTestCase):
    def test_account_sync_rejects_a_query_containing_another_account(self):
        class Client:
            last_fetch_metadata = {'reported_accounts': ['DU-EXPECTED', 'DU-OTHER']}

            def fetch_all_executions(self):
                return []

        job = SimpleNamespace(metadata={}, save=lambda **kwargs: None)
        target = SimpleNamespace(account_code='DU-EXPECTED')

        with patch.object(IBKRSyncService, '_build_pre_sync_snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'also returned other accounts'):
                IBKRSyncService(client=Client()).run_full_sync(job, target_account=target)

    def test_sync_records_accounts_returned_by_the_flex_report(self):
        class Client:
            def fetch_all_executions(self):
                return [
                    {
                        'execution_id': 'exec-1',
                        'account': 'DU456',
                        'symbol': 'MCLN6',
                        'sec_type': 'FUT',
                        'side': 'BUY',
                        'quantity': '1',
                        'price': '90',
                        'commission': '1',
                        'executed_at': '20260306;142202',
                    },
                    {
                        'execution_id': 'exec-2',
                        'account': 'DU123',
                        'symbol': 'MCLN6',
                        'sec_type': 'FUT',
                        'side': 'SELL',
                        'quantity': '1',
                        'price': '91',
                        'commission': '1',
                        'executed_at': '20260306;142203',
                    },
                ]

        job = SimpleNamespace(
            metadata={},
            raw_count=0,
            error_count=0,
            error_message=None,
            inserted_count=0,
            duplicate_count=0,
            status='running',
            save=lambda **kwargs: None,
        )
        raw_execution = SimpleNamespace(trade_date=None)

        with (
            patch.object(IBKRSyncService, '_build_pre_sync_snapshot', return_value={}),
            patch('apps.brokers.services.transaction.atomic', side_effect=nullcontext),
            patch(
                'apps.brokers.services.BrokerAccount.objects.update_or_create',
                side_effect=[
                    (SimpleNamespace(account_code='DU123'), False),
                    (SimpleNamespace(account_code='DU456'), False),
                ],
            ),
            patch('apps.brokers.services.RawIBKRExecution.objects.create', return_value=raw_execution),
            patch('apps.brokers.services.create_fill_from_raw'),
            patch('apps.brokers.services.rebuild_trade_groups_for_dates'),
        ):
            result = IBKRSyncService(client=Client()).run_full_sync(job)

        self.assertEqual(job.metadata['accounts'], ['DU123', 'DU456'])
        self.assertEqual(result['accounts'], ['DU123', 'DU456'])
