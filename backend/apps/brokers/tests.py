from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import nullcontext

from django.test import SimpleTestCase, override_settings

from .ibkr_client import IBKRClient
from .services import IBKRSyncService


FLEX_XML = '''<FlexQueryResponse><FlexStatements><FlexStatement><Trades>
<Trade ibExecID="exec-1" ibOrderID="order-1" accountId="DU123" symbol="MCLN6" description="MCL Jul26" conid="123" assetCategory="FUT" currency="USD" exchange="NYMEX" buySell="BUY" quantity="6" tradePrice="90" ibCommission="-1.25" fifoPnlRealized="0" dateTime="20260306;142202" multiplier="100" tradeID="trade-1" orderType="LMT" proceeds="0" netCash="0" />
</Trades></FlexStatement></FlexStatements></FlexQueryResponse>'''


class IBKRClientLocalCacheTests(SimpleTestCase):
    def test_real_fetch_caches_flex_xml(self):
        with TemporaryDirectory() as tmpdir, override_settings(BASE_DIR=Path(tmpdir)):
            client = IBKRClient()
            client.fetch_flex_statement_xml = lambda: FLEX_XML

            rows = client.fetch_all_executions()

            cache_path = Path(tmpdir) / 'data' / 'ibkr_last_flex_statement.xml'
            self.assertTrue(cache_path.exists())
            self.assertEqual(cache_path.read_text(encoding='utf-8'), FLEX_XML)
            self.assertEqual(rows[0]['execution_id'], 'exec-1')

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


class IBKRSyncServiceTests(SimpleTestCase):
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
            patch('apps.brokers.services.RawIBKRExecution.objects.create', return_value=raw_execution),
            patch('apps.brokers.services.create_fill_from_raw'),
            patch('apps.brokers.services.rebuild_trade_groups_for_dates'),
        ):
            result = IBKRSyncService(client=Client()).run_full_sync(job)

        self.assertEqual(job.metadata['accounts'], ['DU123', 'DU456'])
        self.assertEqual(result['accounts'], ['DU123', 'DU456'])
