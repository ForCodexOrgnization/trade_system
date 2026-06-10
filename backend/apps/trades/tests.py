from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .services import (
    SyntheticSpreadFill,
    _build_position_group_key,
    _infer_combo_key,
    _prepare_rebuild_fills,
)


class SpreadAggregationTests(SimpleTestCase):
    def _fill(self, *, fill_id, order_id, symbol, side, quantity, price):
        raw_execution = SimpleNamespace(
            account='DU123',
            order_id=order_id,
            perm_id=order_id,
            conid=f'{symbol}-conid',
            raw_payload={},
        )
        return SimpleNamespace(
            id=fill_id,
            raw_execution=raw_execution,
            symbol=symbol,
            asset_class='FUT',
            side=side,
            quantity=Decimal(quantity),
            price=Decimal(price),
            commission=Decimal('1.25'),
            executed_at=datetime(2026, 3, 6, 14, 0, fill_id, tzinfo=timezone.utc),
        )

    def test_native_ibkr_spread_legs_become_single_synthetic_fill(self):
        rows = [
            self._fill(fill_id=1, order_id='100', symbol='MCLN6', side='BUY', quantity='6', price='90'),
            self._fill(fill_id=2, order_id='100', symbol='MCLM6', side='SELL', quantity='6', price='89'),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(len(prepared), 1)
        spread = prepared[0]
        self.assertIsInstance(spread, SyntheticSpreadFill)
        self.assertEqual(spread.symbol, 'SPREAD(MCLM6,MCLN6)')
        self.assertEqual(spread.side, 'BUY')
        self.assertEqual(spread.quantity, Decimal('6'))
        self.assertEqual(spread.price, Decimal('1'))
        self.assertEqual(spread.spread_leg_count, 2)

    def test_standalone_partial_fills_are_not_collapsed(self):
        rows = [
            self._fill(fill_id=1, order_id='200', symbol='USO', side='BUY', quantity='10', price='80'),
            self._fill(fill_id=2, order_id='200', symbol='USO', side='BUY', quantity='5', price='80.10'),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(prepared, rows)

    def test_order_reference_does_not_make_standalone_combo_bucket(self):
        buy = self._fill(
            fill_id=1, order_id='300', symbol='SGOV', side='BUY', quantity='10', price='100'
        )
        sell = self._fill(
            fill_id=2, order_id='301', symbol='SGOV', side='SELL', quantity='10', price='101'
        )
        buy.raw_execution.raw_payload = {
            'orderReference': 'strategy-buy',
            'strategyId': 'not-a-spread-key',
        }
        sell.raw_execution.raw_payload = {
            'orderReference': 'strategy-sell',
            'strategyId': 'not-a-spread-key',
        }

        self.assertEqual(_infer_combo_key(buy), '')
        self.assertEqual(_infer_combo_key(sell), '')
        self.assertEqual(_build_position_group_key(buy), _build_position_group_key(sell))

    def test_explicit_combo_key_still_creates_combo_bucket(self):
        fill = self._fill(
            fill_id=1, order_id='400', symbol='MCLN6', side='BUY', quantity='1', price='90'
        )
        fill.raw_execution.raw_payload = {
            'combo_id': 'native-spread-1',
            'orderReference': 'strategy-name',
        }

        self.assertEqual(_infer_combo_key(fill), 'native-spread-1')
        self.assertEqual(_build_position_group_key(fill), ('DU123', 'combo::native-spread-1', 'FUT'))
