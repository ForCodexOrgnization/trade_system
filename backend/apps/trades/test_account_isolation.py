from datetime import datetime, timezone

from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.models import BrokerAccount
from apps.trades.models import RawIBKRExecution, TradeGroup
from apps.trades.services import create_fill_from_raw, rebuild_all_trade_groups


class AccountIsolationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.account_a = BrokerAccount.objects.create(account_code='DU-A', display_name='Account A')
        self.account_b = BrokerAccount.objects.create(account_code='DU-B', display_name='Account B')

    def _raw(self, *, account, execution_id, side, price, second, realized_pnl):
        raw = RawIBKRExecution.objects.create(
            account=account,
            execution_id=execution_id,
            symbol='MESU6',
            sec_type='FUT',
            side=side,
            quantity='1',
            price=price,
            commission='0.50',
            realized_pnl=realized_pnl,
            executed_at=datetime(2026, 8, 3, 14, 30, second, tzinfo=timezone.utc),
            trade_date='2026-08-03',
            dedupe_key=f'{account}-{execution_id}',
        )
        create_fill_from_raw(raw)
        return raw

    def _group(self, account, *, pnl='10'):
        return TradeGroup.objects.create(
            account=account,
            symbol='MESU6',
            trade_date='2026-08-03',
            status='closed',
            direction='long',
            realized_pnl=pnl,
            opened_at=datetime(2026, 8, 3, 14, 30, tzinfo=timezone.utc),
            closed_at=datetime(2026, 8, 3, 14, 31, tzinfo=timezone.utc),
        )

    def test_same_symbol_and_time_build_separate_account_groups(self):
        self._raw(account='DU-A', execution_id='a-buy', side='BUY', price='100', second=0, realized_pnl='0')
        self._raw(account='DU-A', execution_id='a-sell', side='SELL', price='101', second=1, realized_pnl='5')
        self._raw(account='DU-B', execution_id='b-buy', side='BUY', price='200', second=0, realized_pnl='0')
        self._raw(account='DU-B', execution_id='b-sell', side='SELL', price='198', second=1, realized_pnl='-10')

        rebuild_all_trade_groups()

        self.assertEqual(TradeGroup.objects.filter(account=self.account_a).count(), 1)
        self.assertEqual(TradeGroup.objects.filter(account=self.account_b).count(), 1)
        group_a = TradeGroup.objects.get(account=self.account_a)
        detail = self.client.get(f'/api/trades/groups/{group_a.id}/?account=DU-A')
        self.assertEqual(detail.status_code, 200)
        self.assertEqual({row['account'] for row in detail.data['raw_executions']}, {'DU-A'})

    def test_dashboard_filters_by_authoritative_trade_group_account(self):
        self._group(self.account_a, pnl='10')
        self._group(self.account_b, pnl='-20')

        response = self.client.get('/api/trades/groups/dashboard/?account=DU-A')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['trade_groups'], 1)

    def test_multiple_accounts_require_explicit_account_for_trades(self):
        groups = self.client.get('/api/trades/groups/')
        executions = self.client.get('/api/trades/raw-executions/')

        self.assertEqual(groups.status_code, 400)
        self.assertEqual(executions.status_code, 400)

    def test_unknown_account_never_falls_back_to_other_account(self):
        self._group(self.account_a)
        response = self.client.get('/api/trades/groups/?account=DOES-NOT-EXIST')

        self.assertEqual(response.status_code, 404)
