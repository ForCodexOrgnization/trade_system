from datetime import timedelta

from rest_framework import serializers
from django.db import connection
from django.db.utils import ProgrammingError
from django.db.models import Q
from .models import RawIBKRExecution, TradeFill, TradeGroup, TradeLotSnapshot, TradeMatchedLot
from apps.journal.models import DailyReview


def _daily_review_has_strategy_column():
    table_name = DailyReview._meta.db_table
    with connection.cursor() as cursor:
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, table_name)
        }
    return 'strategy' in columns


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


def _trade_review_column_exists(column_name):
    from apps.journal.models import TradeReview
    table_name = TradeReview._meta.db_table
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return False
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, table_name)
        }
    return column_name in columns


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
    lot_snapshots = TradeLotSnapshotSerializer(many=True, read_only=True)
    matched_lots = TradeMatchedLotSerializer(many=True, read_only=True)
    raw_executions = serializers.SerializerMethodField()
    fills = serializers.SerializerMethodField()
    linked_daily_reviews = serializers.SerializerMethodField()
    trade_review = serializers.SerializerMethodField()

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
            return RawIBKRExecution.objects.filter(lot_query).order_by('executed_at', 'id')

        leg_symbols = _spread_leg_symbols(obj.symbol)
        if leg_symbols:
            qs = RawIBKRExecution.objects.filter(symbol__in=leg_symbols)
        else:
            qs = RawIBKRExecution.objects.filter(symbol=obj.symbol)
        qs = _bound_group_queryset_to_trade_window(qs, obj, is_spread=bool(leg_symbols))
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
            return TradeFill.objects.filter(lot_query).order_by('executed_at', 'id')

        leg_symbols = _spread_leg_symbols(obj.symbol)
        if leg_symbols:
            qs = TradeFill.objects.filter(symbol__in=leg_symbols)
        else:
            qs = TradeFill.objects.filter(symbol=obj.symbol)
        qs = _bound_group_queryset_to_trade_window(qs, obj, is_spread=bool(leg_symbols))
        return qs.order_by('executed_at', 'id')

    def get_raw_executions(self, obj):
        qs = self._group_executions_queryset(obj)
        return RawIBKRExecutionSerializer(qs, many=True).data

    def get_fills(self, obj):
        qs = self._group_fills_queryset(obj)
        return TradeFillSerializer(qs, many=True).data

    def get_linked_daily_reviews(self, obj):
        direct_ids = obj.daily_reviews.values_list('id', flat=True)
        linked_ids = obj.daily_review_links.values_list('id', flat=True)
        review_qs = DailyReview.objects.filter(id__in=set(direct_ids) | set(linked_ids)).order_by('-review_date', '-id')
        if not _daily_review_has_strategy_column():
            review_qs = review_qs.defer('strategy', 'thesis', 'entry_logic', 'exit_logic')
        return [
            {
                'id': review.id,
                'review_date': review.review_date,
                'market_summary': review.market_summary,
            }
            for review in review_qs
        ]

    def get_trade_review(self, obj):
        if not _trade_review_column_exists('would_take_again'):
            return None
        review = getattr(obj, 'trade_review', None)
        if not review:
            return None
        try:
            return {
                'id': review.id,
                'strategy': review.strategy,
                'session': review.session,
                'thesis': review.thesis,
                'entry_trigger': review.entry_trigger,
                'invalidation': review.invalidation,
                'planned_target': review.planned_target,
                'sizing_rationale': review.sizing_rationale,
                'entry_quality': review.entry_quality,
                'exit_quality': review.exit_quality,
                'risk_management': review.risk_management,
                'followed_plan': review.followed_plan,
                'would_take_again': review.would_take_again,
                'emotion_before': review.emotion_before,
                'emotion_during': review.emotion_during,
                'emotion_after': review.emotion_after,
                'what_i_did_well': review.what_i_did_well,
                'what_to_improve': review.what_to_improve,
                'realized_r': review.realized_r,
                'final_grade': review.final_grade,
                'setup': review.setup_id,
                'mistake_tags': list(review.mistake_tags.values_list('id', flat=True)),
                'daily_review': review.daily_review_id,
                'screenshots': review.screenshots,
            }
        except ProgrammingError:
            return None
