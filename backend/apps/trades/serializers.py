from datetime import timedelta

from rest_framework import serializers
from django.db import connection
from django.db.utils import ProgrammingError
from django.db.models import Q
from .models import RawIBKRExecution, TradeFill, TradeGroup, TradeLotSnapshot, TradeMatchedLot


def _trade_matched_lot_table_exists():
    with connection.cursor() as cursor:
        return TradeMatchedLot._meta.db_table in connection.introspection.table_names(cursor)


def _spread_leg_symbols(symbol):
    if not symbol:
        return []
    text = str(symbol).strip()
    if not (text.startswith('SPREAD(') and text.endswith(')')):
        return []
    return [item.strip() for item in text[len('SPREAD('):-1].split(',') if item.strip()]


def _bound_group_queryset_to_trade_window(qs, obj, *, is_spread):
    if obj.opened_at:
        qs = qs.filter(executed_at__gte=obj.opened_at)
    if obj.closed_at:
        qs = qs.filter(executed_at__lte=obj.closed_at)
    elif is_spread and obj.opened_at:
        qs = qs.filter(executed_at__lte=obj.opened_at + timedelta(seconds=2))
    return qs


class RawIBKRExecutionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawIBKRExecution
        fields = '__all__'


class TradeFillSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeFill
        fields = '__all__'


class TradeLotSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeLotSnapshot
        fields = '__all__'


class TradeMatchedLotSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradeMatchedLot
        fields = '__all__'


class TradeGroupSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.account_code', read_only=True)
    lot_snapshots = TradeLotSnapshotSerializer(many=True, read_only=True)
    matched_lots = TradeMatchedLotSerializer(many=True, read_only=True)
    raw_executions = serializers.SerializerMethodField()
    fills = serializers.SerializerMethodField()

    class Meta:
        model = TradeGroup
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not _trade_matched_lot_table_exists():
            self.fields.pop('matched_lots', None)

    def _matched_lots_for_group(self, obj):
        if not _trade_matched_lot_table_exists():
            return []
        try:
            return list(obj.matched_lots.all())
        except ProgrammingError:
            return []

    def _group_executions_queryset(self, obj):
        matched_lots = self._matched_lots_for_group(obj)
        if matched_lots:
            lot_query = Q()
            for lot in matched_lots:
                lot_side = (lot.side or '').upper()
                open_side = 'SELL' if lot_side == 'SHORT' else 'BUY'
                close_side = 'BUY' if lot_side == 'SHORT' else 'SELL'
                lot_query |= Q(symbol=obj.symbol, executed_at=lot.opened_at, side=open_side, price=lot.open_price)
                lot_query |= Q(symbol=obj.symbol, executed_at=lot.closed_at, side=close_side, price=lot.close_price)
            return RawIBKRExecution.objects.filter(
                lot_query,
                broker_account=obj.account,
            ).order_by('executed_at', 'id')

        leg_symbols = _spread_leg_symbols(obj.symbol)
        if leg_symbols:
            qs = RawIBKRExecution.objects.filter(symbol__in=leg_symbols)
        else:
            qs = RawIBKRExecution.objects.filter(symbol=obj.symbol)
        qs = _bound_group_queryset_to_trade_window(qs, obj, is_spread=bool(leg_symbols))
        qs = qs.filter(broker_account=obj.account)
        return qs.order_by('executed_at', 'id')

    def _group_fills_queryset(self, obj):
        matched_lots = self._matched_lots_for_group(obj)
        if matched_lots:
            lot_query = Q()
            for lot in matched_lots:
                lot_side = (lot.side or '').upper()
                open_side = 'SELL' if lot_side == 'SHORT' else 'BUY'
                close_side = 'BUY' if lot_side == 'SHORT' else 'SELL'
                lot_query |= Q(symbol=obj.symbol, executed_at=lot.opened_at, side=open_side, price=lot.open_price)
                lot_query |= Q(symbol=obj.symbol, executed_at=lot.closed_at, side=close_side, price=lot.close_price)
            return TradeFill.objects.filter(
                lot_query,
                raw_execution__broker_account=obj.account,
            ).order_by('executed_at', 'id')

        leg_symbols = _spread_leg_symbols(obj.symbol)
        if leg_symbols:
            qs = TradeFill.objects.filter(symbol__in=leg_symbols)
        else:
            qs = TradeFill.objects.filter(symbol=obj.symbol)
        qs = _bound_group_queryset_to_trade_window(qs, obj, is_spread=bool(leg_symbols))
        qs = qs.filter(raw_execution__broker_account=obj.account)
        return qs.order_by('executed_at', 'id')

    def get_raw_executions(self, obj):
        qs = self._group_executions_queryset(obj)
        return RawIBKRExecutionSerializer(qs, many=True).data

    def get_fills(self, obj):
        qs = self._group_fills_queryset(obj)
        return TradeFillSerializer(qs, many=True).data
