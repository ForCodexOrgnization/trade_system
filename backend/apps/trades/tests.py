from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from .services import SyntheticSpreadFill, _prepare_rebuild_fills


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
