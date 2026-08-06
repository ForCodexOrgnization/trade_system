from pathlib import Path
import uuid
from decimal import Decimal
from datetime import datetime

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.accounts import resolve_request_account
from apps.trades.models import RawIBKRExecution
from apps.trades.models import TradeGroup
from .models import DailyReview, MistakeTag, PositionCheckpoint, PreTradePlan, SetupSnapshot, SetupTag, TradeJournal, TradeReview
from .serializers import (
    DailyReviewSerializer,
    MistakeTagSerializer,
    PositionCheckpointSerializer,
    PreTradePlanSerializer,
    SetupSnapshotSerializer,
    SetupTagSerializer,
    TradeJournalSerializer,
    TradeReviewSerializer,
)

DEFAULT_SETUP_TAGS = [
    'Breakout',
    'Pullback',
    'Reversal',
    'Range Fade',
    'Opening Drive',
]

DEFAULT_MISTAKE_TAGS = [
    'FOMO Entry',
    'Late Exit',
    'Oversized Position',
    'Ignored Stop',
    'Overtrading',
]


class AccountScopedMixin:
    def get_request_account(self):
        if not hasattr(self, '_resolved_request_account'):
            self._resolved_request_account = resolve_request_account(self.request)
        return self._resolved_request_account


def _trade_review_column_exists(column_name):
    table_name = TradeReview._meta.db_table
    with connection.cursor() as cursor:
        if table_name not in connection.introspection.table_names(cursor):
            return False
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, table_name)
        }
    return column_name in columns


def _trade_review_schema_ready():
    return _trade_review_column_exists('would_take_again')


def _daily_review_column_exists(column_name):
    table_name = DailyReview._meta.db_table
    with connection.cursor() as cursor:
        columns = {
            item.name
            for item in connection.introspection.get_table_description(cursor, table_name)
        }
    return column_name in columns


class DailyReviewViewSet(
    AccountScopedMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = DailyReview.objects.all().order_by('-review_date', '-updated_at')
    serializer_class = DailyReviewSerializer

    def get_queryset(self):
        return super().get_queryset().filter(account=self.get_request_account())

    def create(self, request, *args, **kwargs):
        account = self.get_request_account()
        payload = request.data.copy()
        payload['account'] = account.id
        if not payload.get('review_date'):
            payload['review_date'] = timezone.localdate().isoformat()

        existing = DailyReview.objects.filter(account=account, review_date=payload['review_date']).first()
        if existing:
            serializer = self.get_serializer(existing, data=payload, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def perform_update(self, serializer):
        serializer.save(account=self.get_request_account())

    @action(detail=False, methods=['get'], url_path='review-queue')
    def review_queue(self, request):
        account = self.get_request_account()
        selected_date = request.query_params.get('date') or timezone.localdate().isoformat()
        closed_trades = TradeGroup.objects.filter(
            Q(closed_at__date=selected_date) | Q(trade_date=selected_date, status='closed'),
            account=account,
            status='closed',
        ).order_by('closed_at', 'id')
        open_positions = TradeGroup.objects.filter(
            account=account,
            status='open',
        ).filter(
            Q(opened_at__date__lte=selected_date) | Q(trade_date__lte=selected_date),
        ).exclude(open_qty=Decimal('0')).order_by('opened_at', 'id')

        daily_review = DailyReview.objects.filter(account=account, review_date=selected_date).first()

        def _hold_minutes(group):
            if not group.opened_at or not group.closed_at:
                return None
            return round((group.closed_at - group.opened_at).total_seconds() / 60, 2)

        def _review_completeness(review):
            if not review:
                return 0
            checks = [
                bool(review.strategy),
                bool(review.setup_id),
                bool(review.thesis),
                review.entry_quality is not None,
                review.exit_quality is not None,
                review.risk_management is not None,
                review.followed_plan is not None,
                bool(review.what_to_improve),
                bool(review.final_grade),
                review.mistake_tags.count() > 0,
                bool(review.screenshots),
            ]
            return int(round((sum(checks) / len(checks)) * 100))

        def _missing_review_items(review):
            if not review:
                return ['strategy', 'setup', 'grade', 'mistake_tags', 'screenshot']
            missing = []
            if not review.strategy:
                missing.append('strategy')
            if not review.setup_id:
                missing.append('setup')
            if not review.final_grade:
                missing.append('grade')
            if review.mistake_tags.count() == 0:
                missing.append('mistake_tags')
            if not review.screenshots:
                missing.append('screenshot')
            return missing

        closed_trade_cards = []
        trade_review_enabled = _trade_review_column_exists('would_take_again')
        for group in closed_trades:
            trade_review = getattr(group, 'trade_review', None) if trade_review_enabled else None
            pretrade = PreTradePlan.objects.filter(account=account, plan_date=selected_date).first()
            snapshot = None
            snapshot_options = []
            if pretrade:
                snapshot_qs = pretrade.setup_snapshots.order_by('-updated_at')
                snapshot_options = [{
                    'id': row.id,
                    'symbol': row.symbol,
                    'strategy': row.strategy,
                    'setup_type': row.setup_type,
                    'timeframe': row.timeframe,
                    'planned_entry': row.planned_entry,
                    'planned_risk_r': row.planned_risk_r,
                    'checklist_passed': row.checklist_passed,
                    'is_bound': bool(row.trade_group_id),
                    'trade_group_id': row.trade_group_id,
                } for row in snapshot_qs]
                snapshot = snapshot_qs.filter(trade_group_id=group.id).first()
                if not snapshot:
                    snapshot = snapshot_qs.filter(Q(symbol__iexact=group.symbol), Q(trade_group__isnull=True) | Q(trade_group_id=group.id)).first()
            selected_snapshot = getattr(group, 'pretrade_snapshot', None) or snapshot
            actual_entry = group.avg_buy_price if group.direction == 'long' else group.avg_sell_price
            actual_exit = group.avg_sell_price if group.direction == 'long' else group.avg_buy_price
            late_entry = False
            broke_stop_rule = False
            setup_match = None
            if selected_snapshot and selected_snapshot.planned_entry is not None and actual_entry is not None:
                late_entry = (group.direction == 'long' and actual_entry > selected_snapshot.planned_entry) or (group.direction == 'short' and actual_entry < selected_snapshot.planned_entry)
            if selected_snapshot and selected_snapshot.planned_stop is not None and actual_exit is not None:
                broke_stop_rule = (group.direction == 'long' and actual_exit < selected_snapshot.planned_stop) or (group.direction == 'short' and actual_exit > selected_snapshot.planned_stop)
            if selected_snapshot and trade_review and trade_review.setup:
                setup_match = trade_review.setup.name.lower().startswith(selected_snapshot.setup_type.lower())
            executions_qs = RawIBKRExecution.objects.filter(
                broker_account=account,
                symbol=group.symbol,
            )
            if group.opened_at:
                executions_qs = executions_qs.filter(executed_at__gte=group.opened_at)
            else:
                executions_qs = executions_qs.filter(executed_at__gte=timezone.make_aware(datetime.min))
            if group.closed_at:
                executions_qs = executions_qs.filter(executed_at__lte=group.closed_at)
            else:
                executions_qs = executions_qs.filter(executed_at__lte=timezone.now())
            executions_count = executions_qs.count()
            closed_trade_cards.append({
                'trade_group_id': group.id,
                'symbol': group.symbol,
                'status': group.status,
                'realized_pnl': group.realized_pnl,
                'hold_minutes': _hold_minutes(group),
                'executions_count': executions_count,
                'screenshots_count': len(trade_review.screenshots or []) if trade_review else 0,
                'planned_entry': selected_snapshot.planned_entry if selected_snapshot else None,
                'planned_stop': selected_snapshot.planned_stop if selected_snapshot else None,
                'planned_target': selected_snapshot.planned_target if selected_snapshot else None,
                'planned_direction': selected_snapshot.direction if selected_snapshot else '',
                'planned_setup_type': selected_snapshot.setup_type if selected_snapshot else '',
                'planned_timeframe': selected_snapshot.timeframe if selected_snapshot else '',
                'selected_snapshot_id': selected_snapshot.id if selected_snapshot else None,
                'snapshot_options': snapshot_options,
                'actual_entry': actual_entry,
                'actual_exit': actual_exit,
                'late_entry': late_entry,
                'broke_stop_rule': broke_stop_rule,
                'setup_match': setup_match,
                'review_completeness': _review_completeness(trade_review),
                'has_review': bool(trade_review),
                'setup_name': trade_review.setup.name if trade_review and trade_review.setup else '',
                'grade': trade_review.final_grade if trade_review else '',
                'mistake_tags': [tag.name for tag in trade_review.mistake_tags.all()] if trade_review else [],
                'missing_items': _missing_review_items(trade_review),
                'trade_review': TradeReviewSerializer(trade_review).data if trade_review else None,
            })

        open_position_cards = []
        for group in open_positions:
            latest_checkpoint = group.position_checkpoints.first()
            open_position_cards.append({
                'trade_group_id': group.id,
                'symbol': group.symbol,
                'status': group.status,
                'open_qty': group.open_qty,
                'avg_open_cost': group.avg_open_cost,
                'opened_at': group.opened_at,
                'latest_checkpoint_id': latest_checkpoint.id if latest_checkpoint else None,
                'latest_checkpoint_date': latest_checkpoint.review_date if latest_checkpoint else None,
            })

        summary = {
            'closed_trade_count': len(closed_trade_cards),
            'open_position_count': len(open_position_cards),
            'daily_review_completed': bool(
                daily_review and (
                    daily_review.review_status == 'completed'
                    if _daily_review_column_exists('review_status')
                    else True
                )
            ),
        }

        return Response({
            'date': selected_date,
            'summary': summary,
            'daily_review': DailyReviewSerializer(daily_review).data if daily_review else None,
            'closed_trades': closed_trade_cards,
            'open_positions': open_position_cards,
        })

    @action(detail=False, methods=['get'], url_path='trade-options')
    def trade_options(self, request):
        account = self.get_request_account()
        review_date = request.query_params.get('date')
        if not review_date:
            return Response([])
        trade_groups = (
            TradeGroup.objects.filter(
                Q(trade_date=review_date)
                | Q(opened_at__date=review_date)
                | Q(closed_at__date=review_date),
                account=account,
            )
            .order_by('opened_at', 'id')
        )
        data = [
            {
                'id': item.id,
                'label': f"{item.symbol} | {item.opened_at} -> {item.closed_at} | PnL {item.realized_pnl}",
                'symbol': item.symbol,
                'trade_date': item.trade_date,
                'opened_at': item.opened_at,
                'closed_at': item.closed_at,
                'status': item.status,
                'realized_pnl': item.realized_pnl,
            }
            for item in trade_groups
        ]
        return Response(data)


class TradeJournalViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    queryset = TradeJournal.objects.select_related('trade_group').all().order_by('-updated_at', '-id')
    serializer_class = TradeJournalSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(trade_group__account=self.get_request_account())
        trade_group_id = self.request.query_params.get('trade_group')
        if trade_group_id:
            qs = qs.filter(trade_group_id=trade_group_id)
        return qs

    def create(self, request, *args, **kwargs):
        account = self.get_request_account()
        trade_group_id = request.data.get('trade_group')
        if trade_group_id:
            get_object_or_404(TradeGroup, id=trade_group_id, account=account)
            instance = TradeJournal.objects.filter(trade_group_id=trade_group_id, trade_group__account=account).first()
            if instance:
                serializer = self.get_serializer(instance, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(serializer.data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)


class TradeReviewViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    queryset = TradeReview.objects.select_related('trade_group', 'daily_review', 'setup').prefetch_related('mistake_tags').all()
    serializer_class = TradeReviewSerializer

    def get_queryset(self):
        if not _trade_review_schema_ready():
            return TradeReview.objects.none()
        qs = super().get_queryset().filter(
            trade_group__account=self.get_request_account(),
        ).order_by('-updated_at', '-id')
        trade_group_id = self.request.query_params.get('trade_group')
        daily_review_id = self.request.query_params.get('daily_review')
        if trade_group_id:
            qs = qs.filter(trade_group_id=trade_group_id)
        if daily_review_id:
            qs = qs.filter(daily_review_id=daily_review_id)
        return qs

    def list(self, request, *args, **kwargs):
        if not _trade_review_schema_ready():
            return Response([])
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        if not _trade_review_schema_ready():
            return Response({'detail': 'TradeReview schema is not ready. Please run migrations.'}, status=status.HTTP_409_CONFLICT)
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if not _trade_review_schema_ready():
            return Response({'detail': 'TradeReview schema is not ready. Please run migrations.'}, status=status.HTTP_409_CONFLICT)
        trade_group_id = request.data.get('trade_group')
        if trade_group_id:
            account = self.get_request_account()
            get_object_or_404(TradeGroup, id=trade_group_id, account=account)
            instance = TradeReview.objects.filter(
                trade_group_id=trade_group_id,
                trade_group__account=account,
            ).first()
            if instance:
                serializer = self.get_serializer(instance, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                return Response(serializer.data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not _trade_review_schema_ready():
            return Response({'detail': 'TradeReview schema is not ready. Please run migrations.'}, status=status.HTTP_409_CONFLICT)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not _trade_review_schema_ready():
            return Response({'detail': 'TradeReview schema is not ready. Please run migrations.'}, status=status.HTTP_409_CONFLICT)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=False, methods=['get'], url_path='analytics-summary')
    def analytics_summary(self, request):
        qs = self.get_queryset().select_related('trade_group', 'trade_group__pretrade_snapshot', 'setup').prefetch_related('mistake_tags')
        by_strategy = {}
        by_session = {}
        by_symbol = {}
        mistake_impact = {}
        followed_plan_bucket = {'followed': {}, 'not_followed': {}, 'unknown': {}}
        equity_points = []
        holding_vs_pnl = []
        r_values = []
        total_profit = 0.0
        total_loss_abs = 0.0
        late_entry_count = 0
        broke_stop_count = 0
        plan_compare_count = 0

        ordered = sorted(
            list(qs),
            key=lambda x: (
                x.trade_group.closed_at if x.trade_group and x.trade_group.closed_at else timezone.now(),
                x.id,
            ),
        )

        for item in ordered:
            trade_group = item.trade_group
            snapshot = getattr(trade_group, 'pretrade_snapshot', None) if trade_group else None
            realized_r = float(item.realized_r) if item.realized_r is not None else None
            realized_pnl = float(trade_group.realized_pnl) if trade_group and trade_group.realized_pnl is not None else 0.0
            hold_minutes = None
            if trade_group and trade_group.opened_at and trade_group.closed_at:
                hold_minutes = (trade_group.closed_at - trade_group.opened_at).total_seconds() / 60
            win = bool(realized_r is not None and realized_r > 0)
            if realized_pnl >= 0:
                total_profit += realized_pnl
            else:
                total_loss_abs += abs(realized_pnl)
            if realized_r is not None:
                r_values.append(realized_r)
            if hold_minutes is not None:
                holding_vs_pnl.append({
                    'symbol': trade_group.symbol if trade_group else 'unknown',
                    'holding_minutes': round(hold_minutes, 2),
                    'pnl': round(realized_pnl, 2),
                })
            actual_entry = None
            actual_exit = None
            if trade_group:
                actual_entry = trade_group.avg_buy_price if trade_group.direction == 'long' else trade_group.avg_sell_price
                actual_exit = trade_group.avg_sell_price if trade_group.direction == 'long' else trade_group.avg_buy_price
            if snapshot and snapshot.planned_entry is not None and actual_entry is not None:
                plan_compare_count += 1
                late_entry = (trade_group.direction == 'long' and actual_entry > snapshot.planned_entry) or (trade_group.direction == 'short' and actual_entry < snapshot.planned_entry)
                late_entry_count += 1 if late_entry else 0
            if snapshot and snapshot.planned_stop is not None and actual_exit is not None:
                broke_stop = (trade_group.direction == 'long' and actual_exit < snapshot.planned_stop) or (trade_group.direction == 'short' and actual_exit > snapshot.planned_stop)
                broke_stop_count += 1 if broke_stop else 0

            def _accumulate(bucket, key):
                if not key:
                    return
                row = bucket.setdefault(key, {'count': 0, 'wins': 0, 'losses': 0, 'r_total': 0.0, 'r_count': 0, 'hold_total': 0.0, 'hold_count': 0, 'pnl_total': 0.0, 'profit_sum': 0.0, 'loss_sum_abs': 0.0})
                row['count'] += 1
                row['wins'] += 1 if win else 0
                row['losses'] += 0 if win else 1
                if realized_r is not None:
                    row['r_total'] += realized_r
                    row['r_count'] += 1
                if hold_minutes is not None:
                    row['hold_total'] += hold_minutes
                    row['hold_count'] += 1
                row['pnl_total'] += realized_pnl
                if realized_pnl >= 0:
                    row['profit_sum'] += realized_pnl
                else:
                    row['loss_sum_abs'] += abs(realized_pnl)

            strategy_key = item.strategy or (snapshot.strategy if snapshot and snapshot.strategy else None) or (item.setup.name if item.setup else None) or (snapshot.setup_type if snapshot else None) or 'Unknown'
            _accumulate(by_strategy, strategy_key)
            _accumulate(by_session, item.session or 'unknown')
            _accumulate(by_symbol, trade_group.symbol if trade_group else 'unknown')
            _accumulate(
                followed_plan_bucket[
                    'followed' if item.followed_plan is True else 'not_followed' if item.followed_plan is False else 'unknown'
                ],
                'all',
            )
            for tag in item.mistake_tags.all():
                _accumulate(mistake_impact, tag.name)
            if trade_group and trade_group.closed_at:
                equity_points.append({
                    'date': trade_group.closed_at.date().isoformat(),
                    'pnl': realized_pnl,
                })

        def _finalize(bucket):
            rows = []
            for key, val in bucket.items():
                count = val['count'] or 1
                avg_r = (val['r_total'] / val['r_count']) if val['r_count'] else None
                win_rate = (val['wins'] / count) * 100
                expectancy = avg_r
                avg_holding_minutes = (val['hold_total'] / val['hold_count']) if val['hold_count'] else None
                profit_factor = (val['profit_sum'] / val['loss_sum_abs']) if val['loss_sum_abs'] else None
                rows.append({
                    'key': key,
                    'trades': val['count'],
                    'losses': val['losses'],
                    'win_rate': round(win_rate, 2),
                    'total_pnl': round(val['pnl_total'], 2),
                    'avg_r': round(avg_r, 4) if avg_r is not None else None,
                    'expectancy': round(expectancy, 4) if expectancy is not None else None,
                    'profit_factor': round(profit_factor, 4) if profit_factor is not None else None,
                    'avg_holding_minutes': round(avg_holding_minutes, 2) if avg_holding_minutes is not None else None,
                    'edge_score': round(((expectancy or 0.0) * (win_rate / 100)), 4),
                })
            rows.sort(key=lambda x: x['trades'], reverse=True)
            return rows

        cumulative = 0.0
        max_peak = 0.0
        max_drawdown = 0.0
        equity_curve = []
        for point in equity_points:
            cumulative += point['pnl']
            max_peak = max(max_peak, cumulative)
            drawdown = cumulative - max_peak
            max_drawdown = min(max_drawdown, drawdown)
            equity_curve.append({'date': point['date'], 'equity': round(cumulative, 2)})

        wins = len([x for x in r_values if x > 0])
        losses = len([x for x in r_values if x <= 0])
        strategy_rows = _finalize(by_strategy)
        strategy_edge_ranking = sorted(strategy_rows, key=lambda x: ((x['expectancy'] or -999), x['trades']), reverse=True)
        for row in strategy_edge_ranking:
            if row['expectancy'] is None:
                row['action'] = 'Need more R data'
            elif row['expectancy'] >= 0.2 and row['trades'] >= 5:
                row['action'] = 'Scale up'
            elif row['expectancy'] < 0:
                row['action'] = 'Reduce / fix execution'
            else:
                row['action'] = 'Keep observing'
        followed_rows = {
            key: (_finalize(bucket)[0] if bucket else None)
            for key, bucket in followed_plan_bucket.items()
        }
        insights = []
        if strategy_edge_ranking:
            top = strategy_edge_ranking[0]
            insights.append(f"Top edge strategy now: {top['key']} (Exp {top['expectancy']}, Win {top['win_rate']}%).")
            worst = strategy_edge_ranking[-1]
            if worst['expectancy'] is not None and top['key'] != worst['key']:
                insights.append(f"Weakest strategy: {worst['key']} (Exp {worst['expectancy']}).")
        if followed_rows['followed'] and followed_rows['not_followed']:
            insights.append(
                f"Followed plan Exp {followed_rows['followed']['expectancy']} vs Not-followed Exp {followed_rows['not_followed']['expectancy']}."
            )
        mistake_rows = sorted(_finalize(mistake_impact), key=lambda x: ((x['avg_r'] or 999), x['trades']))
        if mistake_rows:
            heavy = mistake_rows[0]
            insights.append(f"Highest drag mistake: {heavy['key']} (Avg R {heavy['avg_r']}, PnL {heavy['total_pnl']}).")

        return Response({
            'by_strategy': strategy_rows,
            'by_session': _finalize(by_session),
            'by_symbol': _finalize(by_symbol),
            'strategy_edge_ranking': strategy_edge_ranking,
            'mistake_impact': mistake_rows,
            'plan_adherence': {
                'followed': followed_rows['followed'],
                'not_followed': followed_rows['not_followed'],
                'unknown': followed_rows['unknown'],
                'late_entry_rate': round((late_entry_count / plan_compare_count) * 100, 2) if plan_compare_count else None,
                'broke_stop_rate': round((broke_stop_count / plan_compare_count) * 100, 2) if plan_compare_count else None,
                'compare_sample_size': plan_compare_count,
            },
            'insights': insights,
            'summary': {
                'trades': len(ordered),
                'wins': wins,
                'losses': losses,
                'total_pnl': round(sum([p['pnl'] for p in equity_points]), 2) if equity_points else 0.0,
                'expectancy': round((sum(r_values) / len(r_values)), 4) if r_values else None,
                'profit_factor': round((total_profit / total_loss_abs), 4) if total_loss_abs else None,
                'max_drawdown': round(max_drawdown, 2),
            },
            'equity_curve': equity_curve,
            'r_distribution': [round(v, 4) for v in r_values],
            'holding_vs_pnl': holding_vs_pnl,
        })


class PositionCheckpointViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    queryset = PositionCheckpoint.objects.select_related('trade_group').all().order_by('-review_date', '-updated_at')
    serializer_class = PositionCheckpointSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(trade_group__account=self.get_request_account())
        review_date = self.request.query_params.get('date')
        trade_group_id = self.request.query_params.get('trade_group')
        status_value = self.request.query_params.get('status')
        if review_date:
            qs = qs.filter(review_date=review_date)
        if trade_group_id:
            qs = qs.filter(trade_group_id=trade_group_id)
        if status_value:
            qs = qs.filter(status=status_value)
        return qs

    def perform_create(self, serializer):
        self.get_request_account()
        serializer.save()

    def perform_update(self, serializer):
        self.get_request_account()
        serializer.save()


class SetupTagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SetupTagSerializer

    def get_queryset(self):
        if not SetupTag.objects.exists():
            for name in DEFAULT_SETUP_TAGS:
                SetupTag.objects.get_or_create(name=name)
        return SetupTag.objects.all().order_by('name')


class MistakeTagViewSet(viewsets.ModelViewSet):
    serializer_class = MistakeTagSerializer
    queryset = MistakeTag.objects.all().order_by('name')

    def get_queryset(self):
        if not MistakeTag.objects.exists():
            for name in DEFAULT_MISTAKE_TAGS:
                MistakeTag.objects.get_or_create(name=name)
        return MistakeTag.objects.all().order_by('name')


class PreTradePlanViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    queryset = PreTradePlan.objects.all().order_by('-plan_date', '-updated_at')
    serializer_class = PreTradePlanSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(account=self.get_request_account())
        plan_date = self.request.query_params.get('date')
        session = self.request.query_params.get('session')
        if plan_date:
            qs = qs.filter(plan_date=plan_date)
        if session:
            qs = qs.filter(session=session)
        return qs

    def perform_create(self, serializer):
        serializer.save(account=self.get_request_account())

    def perform_update(self, serializer):
        serializer.save(account=self.get_request_account())


class SetupSnapshotViewSet(AccountScopedMixin, viewsets.ModelViewSet):
    queryset = SetupSnapshot.objects.select_related('pretrade_plan', 'setup', 'trade_group').all().order_by('-updated_at', '-id')
    serializer_class = SetupSnapshotSerializer

    def get_queryset(self):
        qs = super().get_queryset().filter(pretrade_plan__account=self.get_request_account())
        plan_id = self.request.query_params.get('pretrade_plan')
        symbol = self.request.query_params.get('symbol')
        if plan_id:
            qs = qs.filter(pretrade_plan_id=plan_id)
        if symbol:
            qs = qs.filter(symbol__iexact=symbol)
        return qs

    def perform_create(self, serializer):
        self.get_request_account()
        serializer.save()

    def perform_update(self, serializer):
        self.get_request_account()
        serializer.save()


class DailyReviewImageUploadAPIView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        uploaded_files = request.FILES.getlist('images')
        single_file = request.FILES.get('image')
        if single_file and not uploaded_files:
            uploaded_files = [single_file]

        if not uploaded_files:
            return Response({'error': 'No image uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        image_urls = []
        for image_file in uploaded_files:
            ext = Path(image_file.name).suffix or '.png'
            file_name = f"daily_reviews/{uuid.uuid4().hex}{ext}"
            file_path = Path(settings.MEDIA_ROOT) / file_name
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'wb+') as destination:
                for chunk in image_file.chunks():
                    destination.write(chunk)

            image_urls.append(request.build_absolute_uri(settings.MEDIA_URL + file_name))

        if len(image_urls) == 1:
            return Response({'image_url': image_urls[0], 'image_urls': image_urls})
        return Response({'image_urls': image_urls})
