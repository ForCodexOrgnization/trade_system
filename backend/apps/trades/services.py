from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.db import connection
from django.db import transaction
from django.utils import timezone

from apps.common.models import BrokerAccount
from .models import RawIBKRExecution, TradeFill, TradeGroup, TradeLotSnapshot, TradeMatchedLot


ZERO = Decimal('0')
ONE = Decimal('1')
FUTURES_MULTIPLIERS = {
    'MCL': Decimal('100'),
    'CL': Decimal('1000'),
    'MES': Decimal('5'),
    'ES': Decimal('50'),
    'MNQ': Decimal('2'),
    'NQ': Decimal('20'),
}


@dataclass
class SyntheticSpreadFill:
    symbol: str
    asset_class: str
    side: str
    quantity: Decimal
    price: Decimal
    commission: Decimal
    executed_at: object
    raw_execution: object = None
    trade_day: object = None
    id: int = 0
    spread_leg_count: int = 0
    spread_symbols: tuple = ()
    spread_execution_key: str = ''


def _to_decimal(value, default: str = '0') -> Decimal:
    if value in (None, ''):
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _has_trade_matched_lot_table():
    with connection.cursor() as cursor:
        return TradeMatchedLot._meta.db_table in connection.introspection.table_names(cursor)


def _has_trade_group_account_column():
    with connection.cursor() as cursor:
        columns = {
            item.name
            for item in connection.introspection.get_table_description(
                cursor,
                TradeGroup._meta.db_table,
            )
        }
    return 'account_id' in columns


def _has_raw_execution_broker_account_column():
    table_name = RawIBKRExecution._meta.db_table
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return False
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, table_name)
        }
    return 'broker_account_id' in columns


def _group_signature(
    *,
    account_code,
    symbol,
    asset_class,
    status,
    total_buy_qty,
    total_sell_qty,
    net_qty,
    avg_open_cost,
    realized_pnl,
    opened_at,
    closed_at,
):
    """
    Deterministic identity used to retain existing TradeGroup ids across rebuilds.
    """
    return (
        account_code or '',
        symbol or '',
        asset_class or '',
        status or '',
        _to_decimal(total_buy_qty),
        _to_decimal(total_sell_qty),
        _to_decimal(net_qty),
        _to_decimal(avg_open_cost, default='0') if avg_open_cost is not None else None,
        _to_decimal(realized_pnl),
        opened_at,
        closed_at,
    )


def _group_lifecycle_key(*, account_code, symbol, asset_class, direction, opened_at, closed_at):
    """
    Lifecycle identity for strategy-style trade groups.

    This intentionally excludes PnL/qty aggregates so we can keep stable TradeGroup
    ids (and attached reviews/journal data) even when calculation logic evolves.
    """
    return (
        account_code or '',
        symbol or '',
        asset_class or '',
        (direction or '').lower(),
        opened_at,
        closed_at,
    )


def _sign(value: Decimal) -> int:
    if value > ZERO:
        return 1
    if value < ZERO:
        return -1
    return 0


def _extract_multiplier(fill) -> Decimal:
    raw_execution = getattr(fill, 'raw_execution', None)
    payload = getattr(raw_execution, 'raw_payload', None) or {}
    raw_value = (
        payload.get('multiplier')
        or payload.get('Multiplier')
        or payload.get('contractMultiplier')
        or payload.get('contract_multiplier')
        or payload.get('mult')
    )
    if raw_value not in (None, ''):
        try:
            value = _to_decimal(raw_value, default='1')
            if value != ZERO:
                return value
        except Exception:
            pass

    symbol = (getattr(fill, 'symbol', None) or '').upper()
    for prefix in ('MNQ', 'MCL', 'MES', 'NQ', 'CL', 'ES'):
        if symbol == prefix or symbol.startswith(prefix):
            return FUTURES_MULTIPLIERS[prefix]
    return ONE



def _normalize_combo_key(value):
    if value in (None, ''):
        return ''
    return str(value).strip()


def _infer_combo_key(fill):
    raw_execution = getattr(fill, 'raw_execution', None)
    if raw_execution is None:
        return ''

    payload = getattr(raw_execution, 'raw_payload', None) or {}

    # Only use combo aggregation when execution payload explicitly marks a combo/spread.
    # Falling back to order_id / perm_id would make every standalone order look like
    # an isolated combo bucket and break normal open/close matching.
    combo_key_candidates = [
        payload.get('combo_id'),
        payload.get('comboId'),
        payload.get('spreadId'),
    ]
    for candidate in combo_key_candidates:
        normalized = _normalize_combo_key(candidate)
        if normalized:
            return normalized
    return ''


def _build_position_group_key(fill):
    account = getattr(fill.raw_execution, 'account', None) if getattr(fill, 'raw_execution', None) else None
    if isinstance(fill, SyntheticSpreadFill):
        # A synthetic spread fill represents one execution of a calendar-spread
        # position.  Position grouping must use the canonical spread symbol (plus
        # account/asset class), not the per-execution fallback key, otherwise every
        # fallback-detected spread execution becomes an isolated open trade and the
        # later reverse spread can never close the earlier one.
        return (account or '', fill.symbol or '', fill.asset_class or '')
    combo_key = _infer_combo_key(fill)
    if combo_key:
        return (account or '', f'combo::{combo_key}', fill.asset_class or '')
    return (account or '', fill.symbol or '', fill.asset_class or '')


def _spread_underlying_from_symbols(symbols):
    prefixes = []
    for symbol in symbols:
        text = str(symbol or '').strip().upper()
        prefix = ''.join(char for char in text if char.isalpha())
        if not prefix:
            return ''
        prefixes.append(prefix)
    if not prefixes:
        return ''

    common = prefixes[0]
    for prefix in prefixes[1:]:
        while common and not prefix.startswith(common):
            common = common[:-1]
    return common


def _build_spread_vector_group_key(fill):
    account = getattr(fill.raw_execution, 'account', None) if getattr(fill, 'raw_execution', None) else None
    symbols = tuple(getattr(fill, 'spread_symbols', ()) or ())
    underlying = _spread_underlying_from_symbols(symbols)
    if not underlying:
        underlying = fill.symbol or ''
    return (account or '', underlying, fill.asset_class or '')


def _display_symbol_for_bucket(fills):
    symbols = sorted({(fill.symbol or '').strip() for fill in fills if (fill.symbol or '').strip()})
    if len(symbols) <= 1:
        return symbols[0] if symbols else ''
    return 'SPREAD(' + ','.join(symbols) + ')'



def _raw_order_combo_key(fill):
    raw_execution = getattr(fill, 'raw_execution', None)
    if raw_execution is None:
        return ''
    account = getattr(raw_execution, 'account', None) or ''
    order_id = getattr(raw_execution, 'order_id', None) or getattr(raw_execution, 'perm_id', None) or ''
    explicit_combo_key = _infer_combo_key(fill)
    if explicit_combo_key:
        return f"{account}|explicit|{explicit_combo_key}"
    if not order_id:
        return ''
    # IBKR Flex reports a native spread as one order with multiple leg executions.
    # A standalone order may have multiple partial fills, so it is only treated as a
    # spread later if this key contains more than one distinct contract/symbol.
    return f"{account}|order|{order_id}"


def _payload_value(fill, *names):
    raw_execution = getattr(fill, 'raw_execution', None)
    payload = getattr(raw_execution, 'raw_payload', None) or {}
    for name in names:
        if raw_execution is not None and hasattr(raw_execution, name):
            value = getattr(raw_execution, name)
            if value not in (None, ''):
                return value
        value = payload.get(name)
        if value not in (None, ''):
            return value
    return ''


def _is_futures_fill(fill):
    asset_class = (getattr(fill, 'asset_class', None) or '').upper()
    sec_type = str(_payload_value(fill, 'sec_type', 'assetCategory')).upper()
    return asset_class == 'FUT' or sec_type == 'FUT'


def _fallback_underlying_symbol(fill):
    return str(_payload_value(fill, 'underlyingSymbol')).strip().upper()


def _fallback_execution_prefix(fill):
    execution_id = str(_payload_value(fill, 'execution_id', 'ibExecID')).strip()
    if not execution_id:
        return ''
    parts = execution_id.split('.')
    if len(parts) < 3:
        return ''
    return '.'.join(parts[:-2])


def _fallback_rtn_key(fill):
    rtn = str(_payload_value(fill, 'rtn')).strip()
    parts = rtn.split('.')
    if len(parts) < 4 or not all(parts[index] for index in (0, 2, 3)):
        return ''
    return '.'.join((parts[0], parts[2], parts[3]))


def _parse_ibkr_time(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ('%Y%m%d;%H%M%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _seconds_apart(left, right):
    if left is None or right is None:
        return None
    if timezone.is_aware(left):
        left = timezone.make_naive(left, dt_timezone.utc)
    if timezone.is_aware(right):
        right = timezone.make_naive(right, dt_timezone.utc)
    return abs((left - right).total_seconds())


def _times_close(left, right, *, tolerance=timedelta(seconds=2)):
    seconds = _seconds_apart(left, right)
    return seconds is not None and seconds <= tolerance.total_seconds()


def _order_times_close(left_fill, right_fill):
    left_order_time = _parse_ibkr_time(_payload_value(left_fill, 'orderTime'))
    right_order_time = _parse_ibkr_time(_payload_value(right_fill, 'orderTime'))
    if left_order_time is None and right_order_time is None:
        return True
    return _times_close(left_order_time, right_order_time)


def _looks_like_futures_calendar_spread_pair(left_fill, right_fill):
    if not (_is_futures_fill(left_fill) and _is_futures_fill(right_fill)):
        return False

    left_underlying = _fallback_underlying_symbol(left_fill)
    right_underlying = _fallback_underlying_symbol(right_fill)
    if not left_underlying or left_underlying != right_underlying:
        return False

    left_symbol = getattr(left_fill, 'symbol', None) or ''
    right_symbol = getattr(right_fill, 'symbol', None) or ''
    if left_symbol == right_symbol:
        return False

    left_side = (getattr(left_fill, 'side', None) or '').upper()
    right_side = (getattr(right_fill, 'side', None) or '').upper()
    if {left_side, right_side} != {'BUY', 'SELL'}:
        return False

    left_qty = abs(_to_decimal(getattr(left_fill, 'quantity', ZERO)))
    right_qty = abs(_to_decimal(getattr(right_fill, 'quantity', ZERO)))
    if left_qty != right_qty:
        return False

    if not _times_close(
        getattr(left_fill, 'executed_at', None),
        getattr(right_fill, 'executed_at', None),
    ):
        return False

    if not _order_times_close(left_fill, right_fill):
        return False

    return True


def _fallback_spread_group_key(fill):
    if not _is_futures_fill(fill):
        return ''
    underlying = _fallback_underlying_symbol(fill)
    if not underlying:
        return ''
    account = getattr(getattr(fill, 'raw_execution', None), 'account', None) or ''
    execution_prefix = _fallback_execution_prefix(fill)
    if execution_prefix:
        return f'{account}|fallback_exec|{underlying}|{execution_prefix}'
    rtn_key = _fallback_rtn_key(fill)
    if rtn_key:
        return f'{account}|fallback_rtn|{underlying}|{rtn_key}'
    return ''


def _collect_fallback_spread_keys(fills):
    candidates = defaultdict(list)
    for fill in fills:
        key = _fallback_spread_group_key(fill)
        if key:
            candidates[key].append(fill)

    spread_keys = set()
    for key, key_fills in candidates.items():
        if len(key_fills) != 2:
            continue
        if _looks_like_futures_calendar_spread_pair(key_fills[0], key_fills[1]):
            spread_keys.add(key)
    return spread_keys


def _leg_totals_by_symbol(fills):
    legs = defaultdict(
        lambda: {
            'quantity': ZERO,
            'notional': ZERO,
            'sides': set(),
        }
    )
    for fill in fills:
        symbol = (fill.symbol or '').strip()
        side = (fill.side or '').upper()
        qty = _to_decimal(fill.quantity)
        legs[symbol]['quantity'] += qty
        legs[symbol]['notional'] += qty * _to_decimal(fill.price)
        legs[symbol]['sides'].add(side)
    return legs


def _calendar_spread_shape(fills):
    legs = _leg_totals_by_symbol(fills)
    if len(legs) != 2:
        return None

    symbols = tuple(sorted(symbol for symbol in legs if symbol))
    if len(symbols) != 2:
        return None

    left, right = symbols
    left_leg = legs[left]
    right_leg = legs[right]
    if len(left_leg['sides']) != 1 or len(right_leg['sides']) != 1:
        return None

    left_side = next(iter(left_leg['sides']))
    right_side = next(iter(right_leg['sides']))
    if {left_side, right_side} != {'BUY', 'SELL'}:
        return None

    left_qty = left_leg['quantity']
    right_qty = right_leg['quantity']
    if left_qty <= ZERO or left_qty != right_qty:
        return None

    left_avg = left_leg['notional'] / left_qty
    right_avg = right_leg['notional'] / right_qty
    return {
        'symbols': symbols,
        'side': left_side,
        'quantity': left_qty,
        'price': left_avg - right_avg,
    }


def _collect_spread_order_keys(fills):
    candidates = defaultdict(list)
    for fill in fills:
        key = _raw_order_combo_key(fill)
        if key:
            candidates[key].append(fill)

    spread_keys = set()
    for key, key_fills in candidates.items():
        if _calendar_spread_shape(key_fills) is not None:
            spread_keys.add(key)
    return spread_keys


def _build_synthetic_spread_fill(spread_key, key_fills):
    ordered = sorted(key_fills, key=lambda item: (item.executed_at, item.id))
    spread_shape = _calendar_spread_shape(ordered)
    if spread_shape:
        symbols = spread_shape['symbols']
        synthetic_side = spread_shape['side']
        spread_qty = spread_shape['quantity']
        price = spread_shape['price']
    else:
        symbols = tuple(sorted({(fill.symbol or '').strip() for fill in ordered if (fill.symbol or '').strip()}))
        buy_qty = sum((_to_decimal(fill.quantity) for fill in ordered if (fill.side or '').upper() == 'BUY'), ZERO)
        sell_qty = sum((_to_decimal(fill.quantity) for fill in ordered if (fill.side or '').upper() == 'SELL'), ZERO)
        spread_qty = max(buy_qty, sell_qty)
        if spread_qty <= ZERO:
            spread_qty = max((_to_decimal(fill.quantity) for fill in ordered), default=ZERO)

        buy_notional = sum(
            (_to_decimal(fill.quantity) * _to_decimal(fill.price) for fill in ordered if (fill.side or '').upper() == 'BUY'),
            ZERO,
        )
        sell_notional = sum(
            (_to_decimal(fill.quantity) * _to_decimal(fill.price) for fill in ordered if (fill.side or '').upper() == 'SELL'),
            ZERO,
        )
        net_debit = buy_notional - sell_notional
        synthetic_side = 'BUY' if net_debit >= ZERO else 'SELL'
        price = (abs(net_debit) / spread_qty) if spread_qty > ZERO else ZERO

    display_symbol = 'SPREAD(' + ','.join(symbols) + ')'
    first_fill = ordered[0]

    return SyntheticSpreadFill(
        symbol=display_symbol,
        asset_class=first_fill.asset_class,
        side=synthetic_side,
        quantity=spread_qty,
        price=price,
        commission=sum((_to_decimal(fill.commission) for fill in ordered), ZERO),
        executed_at=first_fill.executed_at,
        raw_execution=first_fill.raw_execution,
        trade_day=getattr(first_fill, 'trade_day', None),
        id=first_fill.id,
        spread_leg_count=len(ordered),
        spread_symbols=symbols,
        spread_execution_key=spread_key if '|fallback_' in str(spread_key) else '',
    )


def _prepare_rebuild_fills(fills):
    spread_order_keys = _collect_spread_order_keys(fills)
    fallback_spread_keys = _collect_fallback_spread_keys(fills)
    if not spread_order_keys and not fallback_spread_keys:
        return fills

    normal_fills = []
    spread_fills_by_order = defaultdict(list)
    for fill in fills:
        spread_key = _raw_order_combo_key(fill)
        if spread_key not in spread_order_keys:
            spread_key = _fallback_spread_group_key(fill)
        if spread_key in spread_order_keys or spread_key in fallback_spread_keys:
            spread_fills_by_order[spread_key].append(fill)
        else:
            normal_fills.append(fill)

    synthetic_spreads = [
        _build_synthetic_spread_fill(spread_key, key_fills)
        for spread_key, key_fills in spread_fills_by_order.items()
    ]
    return sorted(
        normal_fills + synthetic_spreads,
        key=lambda item: (item.symbol, item.asset_class or '', item.executed_at, item.id),
    )


def _new_trade_bucket(fill, direction: str):
    return {
        'account_code': getattr(getattr(fill, 'raw_execution', None), 'account', None) or '',
        'symbol': fill.symbol,
        'asset_class': fill.asset_class,
        'opened_at': fill.executed_at,
        'closed_at': None,
        'last_fill_at': fill.executed_at,
        'direction': direction,
        'position_qty': ZERO,
        'entry_qty': ZERO,
        'entry_notional': ZERO,
        'exit_qty': ZERO,
        'exit_notional': ZERO,
        'buy_qty': ZERO,
        'buy_notional': ZERO,
        'sell_qty': ZERO,
        'sell_notional': ZERO,
        'commission_total': ZERO,
        'multiplier': _extract_multiplier(fill),
    }


def _apply_segment(bucket, *, side: str, qty: Decimal, price: Decimal, commission: Decimal, is_entry: bool, executed_at):
    if qty <= ZERO:
        return

    segment_notional = qty * price
    bucket['last_fill_at'] = executed_at
    bucket['commission_total'] += commission

    if side == 'BUY':
        bucket['buy_qty'] += qty
        bucket['buy_notional'] += segment_notional
        bucket['position_qty'] += qty
    else:
        bucket['sell_qty'] += qty
        bucket['sell_notional'] += segment_notional
        bucket['position_qty'] -= qty

    if is_entry:
        bucket['entry_qty'] += qty
        bucket['entry_notional'] += segment_notional
    else:
        bucket['exit_qty'] += qty
        bucket['exit_notional'] += segment_notional


def _finalize_bucket(bucket, *, force_open=False):
    entry_qty = bucket['entry_qty']
    exit_qty = bucket['exit_qty']
    entry_avg = (bucket['entry_notional'] / entry_qty) if entry_qty > ZERO else None
    exit_avg = (bucket['exit_notional'] / exit_qty) if exit_qty > ZERO else None
    position_qty = bucket['position_qty']

    is_closed = position_qty == ZERO and not force_open
    status = 'closed' if is_closed else 'open'

    if bucket['direction'] == 'long':
        avg_open_cost = entry_avg if not is_closed else None
        open_qty = position_qty
    else:
        avg_open_cost = entry_avg if not is_closed else None
        open_qty = position_qty

    qty_for_pnl = entry_qty if is_closed else min(entry_qty, exit_qty)
    if entry_avg is None or exit_avg is None or qty_for_pnl <= ZERO:
        realized_pnl = ZERO
    else:
        if bucket['direction'] == 'long':
            realized_pnl = (exit_avg - entry_avg) * qty_for_pnl * bucket['multiplier']
        else:
            realized_pnl = (entry_avg - exit_avg) * qty_for_pnl * bucket['multiplier']

    return {
        'account_code': bucket['account_code'],
        'symbol': bucket['symbol'],
        'asset_class': bucket['asset_class'],
        'total_buy_qty': bucket['buy_qty'],
        'total_sell_qty': bucket['sell_qty'],
        'buy_notional': bucket['buy_notional'],
        'sell_notional': bucket['sell_notional'],
        'net_qty': position_qty,
        'avg_open_cost': avg_open_cost,
        'open_qty': open_qty,
        'realized_pnl': realized_pnl,
        'commission_total': bucket['commission_total'],
        'opened_at': bucket['opened_at'],
        'closed_at': bucket['last_fill_at'] if is_closed else None,
        'last_fill_at': bucket['last_fill_at'],
        'direction': bucket['direction'],
        'status': status,
        'lot_snapshots': [
            {
                'open_qty': open_qty,
                'remaining_qty': abs(position_qty),
                'open_price': entry_avg,
                'opened_at': bucket['opened_at'],
            }
        ]
        if not is_closed and entry_avg is not None and position_qty != ZERO
        else [],
        'matched_lots': [],
    }


def _is_spread_vector_flat(leg_positions):
    return all(qty == ZERO for qty in leg_positions.values())


def _spread_leg_delta(fill):
    symbols = tuple(getattr(fill, 'spread_symbols', ()) or ())
    if len(symbols) != 2:
        return {}
    qty = _to_decimal(getattr(fill, 'quantity', ZERO))
    if qty <= ZERO:
        return {}
    side = (getattr(fill, 'side', None) or '').upper()
    if side == 'BUY':
        return {symbols[0]: qty, symbols[1]: -qty}
    if side == 'SELL':
        return {symbols[0]: -qty, symbols[1]: qty}
    return {}


def _new_spread_vector_bucket(fill):
    return {
        'account_code': getattr(getattr(fill, 'raw_execution', None), 'account', None) or '',
        'symbol': fill.symbol,
        'asset_class': fill.asset_class,
        'opened_at': fill.executed_at,
        'closed_at': None,
        'last_fill_at': fill.executed_at,
        'direction': 'long' if (fill.side or '').upper() == 'BUY' else 'short',
        'leg_positions': defaultdict(Decimal),
        'symbols': set(getattr(fill, 'spread_symbols', ()) or ()),
        'buy_qty': ZERO,
        'buy_notional': ZERO,
        'sell_qty': ZERO,
        'sell_notional': ZERO,
        'commission_total': ZERO,
        'cashflow': ZERO,
        'multiplier': _extract_multiplier(fill),
    }


def _apply_spread_vector_fill(bucket, fill):
    qty = _to_decimal(fill.quantity)
    if qty <= ZERO:
        return

    side = (fill.side or '').upper()
    price = _to_decimal(fill.price)
    notional = qty * price
    bucket['last_fill_at'] = fill.executed_at
    bucket['commission_total'] += _to_decimal(fill.commission)
    bucket['symbols'].update(getattr(fill, 'spread_symbols', ()) or ())

    if side == 'BUY':
        bucket['buy_qty'] += qty
        bucket['buy_notional'] += notional
        bucket['cashflow'] -= notional
    elif side == 'SELL':
        bucket['sell_qty'] += qty
        bucket['sell_notional'] += notional
        bucket['cashflow'] += notional
    else:
        return

    for symbol, delta in _spread_leg_delta(fill).items():
        bucket['leg_positions'][symbol] += delta


def _finalize_spread_vector_bucket(bucket, *, force_open=False):
    flat = _is_spread_vector_flat(bucket['leg_positions'])
    is_closed = flat and not force_open
    status = 'closed' if is_closed else 'open'
    symbols = tuple(sorted(symbol for symbol in bucket['symbols'] if symbol))
    display_symbol = 'SPREAD(' + ','.join(symbols) + ')' if symbols else bucket['symbol']
    net_qty = sum(bucket['leg_positions'].values(), ZERO)
    gross_open_qty = sum((abs(qty) for qty in bucket['leg_positions'].values()), ZERO) / Decimal('2')

    avg_buy_price = (bucket['buy_notional'] / bucket['buy_qty']) if bucket['buy_qty'] > ZERO else None
    avg_sell_price = (bucket['sell_notional'] / bucket['sell_qty']) if bucket['sell_qty'] > ZERO else None
    if status == 'closed':
        avg_open_cost = None
        open_qty = ZERO
    else:
        avg_open_cost = avg_buy_price or avg_sell_price
        open_qty = net_qty if net_qty != ZERO else gross_open_qty

    realized_pnl = bucket['cashflow'] * bucket['multiplier'] if is_closed else ZERO

    return {
        'account_code': bucket['account_code'],
        'symbol': display_symbol,
        'asset_class': bucket['asset_class'],
        'total_buy_qty': bucket['buy_qty'],
        'total_sell_qty': bucket['sell_qty'],
        'buy_notional': bucket['buy_notional'],
        'sell_notional': bucket['sell_notional'],
        'net_qty': net_qty,
        'avg_open_cost': avg_open_cost,
        'open_qty': open_qty,
        'realized_pnl': realized_pnl,
        'commission_total': bucket['commission_total'],
        'opened_at': bucket['opened_at'],
        'closed_at': bucket['last_fill_at'] if is_closed else None,
        'last_fill_at': bucket['last_fill_at'],
        'direction': bucket['direction'],
        'status': status,
        'lot_snapshots': [
            {
                'open_qty': open_qty,
                'remaining_qty': abs(open_qty),
                'open_price': avg_open_cost,
                'opened_at': bucket['opened_at'],
            }
        ]
        if status != 'closed' and avg_open_cost is not None and open_qty != ZERO
        else [],
        'matched_lots': [],
    }


def _build_spread_vector_buckets(fills):
    trade_buckets = []
    fills_by_position_key = defaultdict(list)
    for fill in fills:
        fills_by_position_key[_build_spread_vector_group_key(fill)].append(fill)

    for key_fills in fills_by_position_key.values():
        current_bucket = None
        ordered_fills = sorted(key_fills, key=lambda item: (item.executed_at, item.id))
        for fill in ordered_fills:
            if not _spread_leg_delta(fill):
                continue
            if current_bucket is None:
                current_bucket = _new_spread_vector_bucket(fill)
            _apply_spread_vector_fill(current_bucket, fill)
            if _is_spread_vector_flat(current_bucket['leg_positions']):
                trade_buckets.append(_finalize_spread_vector_bucket(current_bucket))
                current_bucket = None
        if current_bucket is not None:
            trade_buckets.append(_finalize_spread_vector_bucket(current_bucket, force_open=True))
    return trade_buckets


def _build_trade_buckets(fills):
    trade_buckets = []
    spread_vector_fills = []
    scalar_fills = []
    for fill in fills:
        if isinstance(fill, SyntheticSpreadFill) and len(getattr(fill, 'spread_symbols', ()) or ()) == 2:
            spread_vector_fills.append(fill)
        else:
            scalar_fills.append(fill)

    if spread_vector_fills:
        trade_buckets.extend(_build_spread_vector_buckets(spread_vector_fills))

    fills_by_position_key = defaultdict(list)
    for fill in scalar_fills:
        key = _build_position_group_key(fill)
        fills_by_position_key[key].append(fill)

    for (_, _symbol, _asset_class), key_fills in fills_by_position_key.items():
        current_bucket = None
        bucket_display_symbol = _display_symbol_for_bucket(key_fills)

        for fill in key_fills:
            side = (fill.side or '').upper()
            if side not in ('BUY', 'SELL'):
                continue

            fill_qty_total = _to_decimal(fill.quantity)
            if fill_qty_total <= ZERO:
                continue

            fill_price = _to_decimal(fill.price)
            fill_commission = _to_decimal(fill.commission)
            qty_remaining = fill_qty_total

            while qty_remaining > ZERO:
                if current_bucket is None:
                    direction = 'long' if side == 'BUY' else 'short'
                    current_bucket = _new_trade_bucket(fill, direction)
                    current_bucket['symbol'] = bucket_display_symbol or fill.symbol

                position_sign = _sign(current_bucket['position_qty'])
                side_sign = 1 if side == 'BUY' else -1

                if position_sign == 0 or position_sign == side_sign:
                    segment_qty = qty_remaining
                    segment_commission = fill_commission * (segment_qty / fill_qty_total)
                    _apply_segment(
                        current_bucket,
                        side=side,
                        qty=segment_qty,
                        price=fill_price,
                        commission=segment_commission,
                        is_entry=True,
                        executed_at=fill.executed_at,
                    )
                    qty_remaining -= segment_qty
                    continue

                closing_capacity = abs(current_bucket['position_qty'])
                segment_qty = min(qty_remaining, closing_capacity)
                segment_commission = fill_commission * (segment_qty / fill_qty_total)
                _apply_segment(
                    current_bucket,
                    side=side,
                    qty=segment_qty,
                    price=fill_price,
                    commission=segment_commission,
                    is_entry=False,
                    executed_at=fill.executed_at,
                )
                qty_remaining -= segment_qty

                if current_bucket['position_qty'] == ZERO:
                    trade_buckets.append(_finalize_bucket(current_bucket))
                    current_bucket = None

        if current_bucket is not None:
            trade_buckets.append(_finalize_bucket(current_bucket, force_open=True))

    return trade_buckets


@transaction.atomic
def create_fill_from_raw(raw_execution: RawIBKRExecution):
    side = (raw_execution.side or '').upper()
    qty = _to_decimal(raw_execution.quantity)
    signed_qty = qty if side == 'BUY' else -qty
    fill, _ = TradeFill.objects.update_or_create(
        raw_execution=raw_execution,
        defaults={
            'symbol': raw_execution.symbol,
            'side': raw_execution.side,
            'quantity': raw_execution.quantity,
            'price': raw_execution.price,
            'executed_at': raw_execution.executed_at,
            'commission': raw_execution.commission or ZERO,
            'signed_qty': signed_qty,
            'asset_class': raw_execution.sec_type,
            'trade_day': raw_execution.trade_date or raw_execution.executed_at.date(),
        },
    )
    return fill


@transaction.atomic
def rebuild_trade_groups_for_dates(trade_dates):
    """
    Rebuild all trade groups.

    The previous date-scoped rebuild reset matching at midnight, which breaks overnight
    positions and causes the dashboard PnL/open-position totals to drift away from IBKR.
    Rebuilding from the full ordered fill history keeps FIFO state continuous across days.
    """
    rebuild_all_trade_groups()


@transaction.atomic
def rebuild_trade_groups_for_date(trade_date):
    rebuild_all_trade_groups()


@transaction.atomic
def rebuild_all_trade_groups():
    fills_qs = TradeFill.objects.select_related('raw_execution').all()
    if not _has_raw_execution_broker_account_column():
        fills_qs = fills_qs.defer('raw_execution__broker_account')
    fills = list(fills_qs.order_by('symbol', 'asset_class', 'executed_at', 'id'))
    fills = _prepare_rebuild_fills(fills)

    has_matched_lot_table = _has_trade_matched_lot_table()
    if not fills:
        TradeLotSnapshot.objects.all().delete()
        if has_matched_lot_table:
            TradeMatchedLot.objects.all().delete()
        if _has_trade_group_account_column():
            TradeGroup.all_objects.all().delete()
        else:
            with connection.cursor() as cursor:
                cursor.execute(f'DELETE FROM {TradeGroup._meta.db_table}')
        return

    account_codes = sorted({
        str(getattr(fill.raw_execution, 'account', '') or '').strip()
        for fill in fills
        if str(getattr(fill.raw_execution, 'account', '') or '').strip()
    })
    accounts_by_code = {}
    for account_code in account_codes:
        accounts_by_code[account_code], _ = BrokerAccount.objects.get_or_create(
            broker='ibkr',
            account_code=account_code,
            defaults={'display_name': account_code, 'is_active': True},
        )
    if any(not str(getattr(fill.raw_execution, 'account', '') or '').strip() for fill in fills):
        accounts_by_code[''], _ = BrokerAccount.objects.get_or_create(
            broker='ibkr',
            account_code='__legacy_unknown__',
            defaults={'display_name': 'Legacy unknown account', 'is_active': False},
        )

    existing_groups = list(TradeGroup.all_objects.all().order_by('id'))
    existing_by_signature = defaultdict(list)
    existing_by_lifecycle = defaultdict(list)
    for group in existing_groups:
        lifecycle_key = _group_lifecycle_key(
            account_code=group.account.account_code,
            symbol=group.symbol,
            asset_class=group.asset_class,
            direction=group.direction,
            opened_at=group.opened_at,
            closed_at=group.closed_at,
        )
        existing_by_lifecycle[lifecycle_key].append(group)

        signature = _group_signature(
            account_code=group.account.account_code,
            symbol=group.symbol,
            asset_class=group.asset_class,
            status=group.status,
            total_buy_qty=group.total_buy_qty,
            total_sell_qty=group.total_sell_qty,
            net_qty=group.net_qty,
            avg_open_cost=group.avg_open_cost,
            realized_pnl=group.realized_pnl,
            opened_at=group.opened_at,
            closed_at=group.closed_at,
        )
        existing_by_signature[signature].append(group)

    trade_buckets = _build_trade_buckets(fills)

    retained_group_ids = set()
    for bucket in sorted(
        trade_buckets,
        key=lambda item: (
            item['account_code'],
            item['closed_at'] or item['last_fill_at'] or item['opened_at'],
            item['symbol'],
            item['opened_at'],
        ),
    ):
        group_trade_date = (
            bucket['closed_at'].date()
            if bucket['closed_at']
            else bucket['opened_at'].date()
        )
        avg_buy_price = None
        if bucket['total_buy_qty'] > ZERO:
            avg_buy_price = bucket['buy_notional'] / bucket['total_buy_qty']

        avg_sell_price = None
        if bucket['total_sell_qty'] > ZERO:
            avg_sell_price = bucket['sell_notional'] / bucket['total_sell_qty']

        signature = _group_signature(
            account_code=bucket['account_code'],
            symbol=bucket['symbol'],
            asset_class=bucket['asset_class'],
            status=bucket['status'],
            total_buy_qty=bucket['total_buy_qty'],
            total_sell_qty=bucket['total_sell_qty'],
            net_qty=bucket['net_qty'],
            avg_open_cost=bucket['avg_open_cost'],
            realized_pnl=bucket['realized_pnl'],
            opened_at=bucket['opened_at'],
            closed_at=bucket['closed_at'],
        )
        lifecycle_key = _group_lifecycle_key(
            account_code=bucket['account_code'],
            symbol=bucket['symbol'],
            asset_class=bucket['asset_class'],
            direction=bucket['direction'],
            opened_at=bucket['opened_at'],
            closed_at=bucket['closed_at'],
        )
        candidates = existing_by_lifecycle.get(lifecycle_key) or []
        if not candidates:
            candidates = existing_by_signature.get(signature) or []
        group = candidates.pop(0) if candidates else None
        payload = {
            'account': accounts_by_code[bucket['account_code']],
            'symbol': bucket['symbol'],
            'trade_date': group_trade_date,
            'asset_class': bucket['asset_class'],
            'direction': bucket['direction'],
            'status': bucket['status'],
            'total_buy_qty': bucket['total_buy_qty'],
            'total_sell_qty': bucket['total_sell_qty'],
            'net_qty': bucket['net_qty'],
            'avg_buy_price': avg_buy_price,
            'avg_sell_price': avg_sell_price,
            'avg_open_cost': bucket['avg_open_cost'],
            'open_qty': bucket['open_qty'],
            'realized_pnl': bucket['realized_pnl'],
            'commission_total': bucket['commission_total'],
            'opened_at': bucket['opened_at'],
            'closed_at': bucket['closed_at'],
        }
        if group is None:
            group = TradeGroup.objects.create(**payload)
        else:
            for field, value in payload.items():
                setattr(group, field, value)
            group.is_soft_deleted = False
            group.soft_deleted_at = None
            group.soft_delete_reason = ''
            group.save()
            group.lot_snapshots.all().delete()
            if has_matched_lot_table:
                group.matched_lots.all().delete()

        retained_group_ids.add(group.id)

        snapshots = bucket['lot_snapshots']
        if snapshots:
            TradeLotSnapshot.objects.bulk_create(
                [
                    TradeLotSnapshot(
                        trade_group=group,
                        symbol=group.symbol,
                        open_qty=snapshot['open_qty'],
                        remaining_qty=snapshot['remaining_qty'],
                        open_price=snapshot['open_price'],
                        opened_at=snapshot['opened_at'] or group.opened_at,
                    )
                    for snapshot in snapshots
                ]
            )

    stale_group_ids = [group.id for group in existing_groups if group.id not in retained_group_ids]
    if stale_group_ids:
        stale_groups = list(
            TradeGroup.all_objects.filter(id__in=stale_group_ids).prefetch_related(
                'daily_reviews',
                'daily_review_links',
                'position_checkpoints',
            )
        )
        deletable_ids = []
        soft_delete_ids = []
        for group in stale_groups:
            has_user_links = any(
                [
                    hasattr(group, 'journal'),
                    hasattr(group, 'trade_review'),
                    hasattr(group, 'pretrade_snapshot'),
                    group.daily_reviews.exists(),
                    group.daily_review_links.exists(),
                    group.position_checkpoints.exists(),
                ]
            )
            if not has_user_links:
                deletable_ids.append(group.id)
            else:
                soft_delete_ids.append(group.id)

        if deletable_ids:
            TradeGroup.all_objects.filter(id__in=deletable_ids).delete()
        if soft_delete_ids:
            TradeGroup.all_objects.filter(id__in=soft_delete_ids).update(
                is_soft_deleted=True,
                soft_deleted_at=timezone.now(),
                soft_delete_reason='protected_during_rebuild',
            )
