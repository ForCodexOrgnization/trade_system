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
    def _fill(
        self, *, fill_id, order_id, symbol, side, quantity, price, executed_at=None, raw_payload=None
    ):
        raw_execution = SimpleNamespace(
            account='DU123',
            order_id=order_id,
            perm_id=order_id,
            conid=f'{symbol}-conid',
            execution_id=(raw_payload or {}).get('ibExecID'),
            raw_payload=raw_payload or {},
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
            executed_at=(
                executed_at or datetime(2026, 3, 6, 14, 0, fill_id, tzinfo=timezone.utc)
            ),
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
        self.assertEqual(spread.side, 'SELL')
        self.assertEqual(spread.quantity, Decimal('6'))
        self.assertEqual(spread.price, Decimal('-1'))
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

    def test_futures_calendar_spread_fallback_uses_ib_exec_prefix(self):
        executed_at = datetime(2026, 5, 14, 14, 48, 4, tzinfo=timezone.utc)
        rows = [
            self._fill(
                fill_id=1,
                order_id='leg-a',
                symbol='MCLN6',
                side='BUY',
                quantity='1',
                price='63.10',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'dateTime': '20260514;144804',
                    'orderTime': '20260514;144804',
                    'buySell': 'BUY',
                    'ibExecID': '000100f5.6a0509a5.02.01',
                },
            ),
            self._fill(
                fill_id=2,
                order_id='leg-b',
                symbol='MCLQ6',
                side='SELL',
                quantity='1',
                price='63.00',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'dateTime': '20260514;144804',
                    'orderTime': '20260514;144804',
                    'buySell': 'SELL',
                    'ibExecID': '000100f5.6a0509a5.03.01',
                },
            ),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(len(prepared), 1)
        spread = prepared[0]
        self.assertIsInstance(spread, SyntheticSpreadFill)
        self.assertEqual(spread.symbol, 'SPREAD(MCLN6,MCLQ6)')
        self.assertEqual(spread.side, 'BUY')
        self.assertEqual(spread.price, Decimal('0.10'))
        self.assertEqual(spread.spread_leg_count, 2)

    def test_futures_calendar_spread_fallback_can_use_rtn_when_exec_prefix_missing(self):
        executed_at = datetime(2026, 5, 14, 14, 48, 4, tzinfo=timezone.utc)
        rows = [
            self._fill(
                fill_id=1,
                order_id='leg-a',
                symbol='MCLN6',
                side='BUY',
                quantity='1',
                price='63.10',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'rtn': '20587.42026750.8063752052369.20260514484',
                },
            ),
            self._fill(
                fill_id=2,
                order_id='leg-b',
                symbol='MCLQ6',
                side='SELL',
                quantity='1',
                price='63.00',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'rtn': '20587.42026511.8063752052369.20260514484',
                },
            ),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(len(prepared), 1)
        self.assertIsInstance(prepared[0], SyntheticSpreadFill)


    def test_fallback_spread_side_uses_canonical_leg_not_net_debit(self):
        executed_at = datetime(2026, 5, 14, 14, 48, 4, tzinfo=timezone.utc)
        rows = [
            self._fill(
                fill_id=1,
                order_id='leg-a',
                symbol='MCLN6',
                side='BUY',
                quantity='4',
                price='62.90',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.02.01',
                },
            ),
            self._fill(
                fill_id=2,
                order_id='leg-b',
                symbol='MCLQ6',
                side='SELL',
                quantity='4',
                price='63.00',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.03.01',
                },
            ),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(len(prepared), 1)
        self.assertEqual(prepared[0].side, 'BUY')
        self.assertEqual(prepared[0].quantity, Decimal('4'))
        self.assertEqual(prepared[0].price, Decimal('-0.10'))

    def test_order_spread_requires_balanced_two_leg_calendar_shape(self):
        rows = [
            self._fill(fill_id=1, order_id='500', symbol='MCLN6', side='BUY', quantity='4', price='62.90'),
            self._fill(fill_id=2, order_id='500', symbol='MCLQ6', side='SELL', quantity='6', price='63.00'),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(prepared, rows)


    def test_fallback_spreads_keep_execution_key_in_position_group(self):
        first_time = datetime(2026, 5, 14, 14, 48, 4, tzinfo=timezone.utc)
        second_time = datetime(2026, 5, 14, 14, 49, 4, tzinfo=timezone.utc)
        rows = [
            self._fill(
                fill_id=1,
                order_id='leg-a',
                symbol='MCLN6',
                side='BUY',
                quantity='1',
                price='63.10',
                executed_at=first_time,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.02.01',
                },
            ),
            self._fill(
                fill_id=2,
                order_id='leg-b',
                symbol='MCLQ6',
                side='SELL',
                quantity='1',
                price='63.00',
                executed_at=first_time,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.03.01',
                },
            ),
            self._fill(
                fill_id=3,
                order_id='leg-c',
                symbol='MCLN6',
                side='SELL',
                quantity='1',
                price='63.20',
                executed_at=second_time,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144904',
                    'ibExecID': '000100f5.6a0509b6.02.01',
                },
            ),
            self._fill(
                fill_id=4,
                order_id='leg-d',
                symbol='MCLQ6',
                side='BUY',
                quantity='1',
                price='63.05',
                executed_at=second_time,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144904',
                    'ibExecID': '000100f5.6a0509b6.03.01',
                },
            ),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(len(prepared), 2)
        self.assertEqual({fill.symbol for fill in prepared}, {'SPREAD(MCLN6,MCLQ6)'})
        position_keys = {_build_position_group_key(fill) for fill in prepared}
        self.assertEqual(len(position_keys), 2)
        self.assertTrue(all('fallback_exec' in key[1] for key in position_keys))

    def test_fallback_does_not_collapse_normal_futures_orders(self):
        executed_at = datetime(2026, 5, 14, 14, 48, 4, tzinfo=timezone.utc)
        rows = [
            self._fill(
                fill_id=1,
                order_id='leg-a',
                symbol='MCLN6',
                side='BUY',
                quantity='1',
                price='63.10',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.02.01',
                },
            ),
            self._fill(
                fill_id=2,
                order_id='leg-b',
                symbol='MCLQ6',
                side='BUY',
                quantity='1',
                price='63.00',
                executed_at=executed_at,
                raw_payload={
                    'assetCategory': 'FUT',
                    'underlyingSymbol': 'MCL',
                    'orderTime': '20260514;144804',
                    'ibExecID': '000100f5.6a0509a5.03.01',
                },
            ),
        ]

        prepared = _prepare_rebuild_fills(rows)

        self.assertEqual(prepared, rows)
