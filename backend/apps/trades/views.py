from collections import defaultdict
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.common.accounts import resolve_request_account
from apps.common.models import BrokerAccount
from .models import RawIBKRExecution, TradeGroup
from .serializers import TradeGroupSerializer, RawIBKRExecutionSerializer
from apps.common.pagination import StandardPageNumberPagination


ZERO = Decimal('0')


FILTER_PLACEHOLDERS = {
    'account': {'all accounts', 'all account', 'accounts', 'all'},
    'symbol': {'all symbols', 'all symbol', 'symbols', 'all'},
    'strategy': {'all strategies', 'all strategy', 'strategies', 'all'},
    'asset_class': {'all asset classes', 'all asset class', 'asset classes', 'all'},
    'date': {'all dates', 'all date', 'dates', 'all', 'custom'},
    'date_from': {'all dates', 'all date', 'dates', 'all', 'custom'},
    'date_to': {'all dates', 'all date', 'dates', 'all', 'custom'},
}


def _clean_filter_param(key, value):
    if value is None:
        return ''
    cleaned = str(value).strip()
    if not cleaned:
        return ''
    normalized = cleaned.lower()
    if normalized in {'null', 'undefined', 'none', 'nan'}:
        return ''
    if normalized in FILTER_PLACEHOLDERS.get(key, set()):
        return ''
    return cleaned


def _safe_decimal(value):
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _extract_strategy_from_payload(payload):
    if not isinstance(payload, dict):
        return ''
    return (
        payload.get('orderReference')
        or payload.get('strategy')
        or payload.get('order_reference')
        or ''
    ).strip()


def _latest_groups_by_symbol(groups):
    latest = {}
    for group in groups:
        prev = latest.get(group.symbol)
        if prev is None or (group.trade_date, group.id) > (prev.trade_date, prev.id):
            latest[group.symbol] = group
    return list(latest.values())


class TradeGroupViewSet(ReadOnlyModelViewSet):
    serializer_class = TradeGroupSerializer
    queryset = TradeGroup.objects.select_related('account').all().order_by('-trade_date', '-id')
    pagination_class = StandardPageNumberPagination

    def _request_account(self):
        if not hasattr(self, '_resolved_request_account'):
            self._resolved_request_account = resolve_request_account(self.request)
        return self._resolved_request_account

    def _normalized_date_params(self):
        qp = self.request.query_params
        return {
            'date': _clean_filter_param('date', qp.get('date')),
            'date_from': _clean_filter_param('date_from', qp.get('date_from') or qp.get('start')),
            'date_to': _clean_filter_param('date_to', qp.get('date_to') or qp.get('end')),
        }

    def _filtered_raw_executions(self):
        qp = self.request.query_params
        dates = self._normalized_date_params()
        raw_qs = RawIBKRExecution.objects.all().order_by('executed_at', 'id')

        symbol = _clean_filter_param('symbol', qp.get('symbol') or qp.get('q'))
        account = self._request_account()
        asset_class = _clean_filter_param('asset_class', qp.get('asset_class') or qp.get('sec_type'))
        strategy = _clean_filter_param('strategy', qp.get('strategy'))
        side = _clean_filter_param('side', qp.get('side'))
        query = _clean_filter_param('query', qp.get('query'))

        if dates['date']:
            raw_qs = raw_qs.filter(trade_date=dates['date'])
        if dates['date_from']:
            raw_qs = raw_qs.filter(trade_date__gte=dates['date_from'])
        if dates['date_to']:
            raw_qs = raw_qs.filter(trade_date__lte=dates['date_to'])
        raw_qs = raw_qs.filter(broker_account=account)
        if symbol:
            raw_qs = raw_qs.filter(symbol__icontains=symbol)
        if asset_class:
            raw_qs = raw_qs.filter(sec_type=asset_class)
        if side:
            raw_qs = raw_qs.filter(side=side)
        if query:
            raw_qs = raw_qs.filter(
                Q(execution_id__icontains=query)
                | Q(order_id__icontains=query)
                | Q(symbol__icontains=query)
                | Q(local_symbol__icontains=query)
            )

        raw_items = list(raw_qs)
        if strategy:
            raw_items = [item for item in raw_items if _extract_strategy_from_payload(item.raw_payload) == strategy]
        return raw_items

    def get_queryset(self):
        qp = self.request.query_params
        dates = self._normalized_date_params()
        qs = super().get_queryset()

        trade_date = dates['date']
        symbol = _clean_filter_param('symbol', qp.get('symbol') or qp.get('q'))
        status_ = _clean_filter_param('status', qp.get('status'))
        asset_class = _clean_filter_param('asset_class', qp.get('asset_class'))
        account = self._request_account().account_code
        strategy = _clean_filter_param('strategy', qp.get('strategy'))

        if trade_date:
            qs = qs.filter(trade_date=trade_date)
        if dates['date_from']:
            qs = qs.filter(trade_date__gte=dates['date_from'])
        if dates['date_to']:
            qs = qs.filter(trade_date__lte=dates['date_to'])
        if symbol:
            qs = qs.filter(symbol__icontains=symbol)
        if status_:
            qs = qs.filter(status=status_)
        if asset_class:
            qs = qs.filter(asset_class=asset_class)
        qs = qs.filter(account__broker='ibkr', account__account_code=account, account__is_active=True)

        if strategy:
            raw_items = self._filtered_raw_executions()
            if not raw_items:
                return qs.none()
            candidate_ids = []
            groups = list(qs)
            for group in groups:
                matched = [
                    item for item in raw_items
                    if item.symbol == group.symbol
                    and item.account == group.account.account_code
                    and (not group.opened_at or item.executed_at >= group.opened_at)
                    and (not group.closed_at or item.executed_at <= group.closed_at)
                ]
                if matched:
                    candidate_ids.append(group.id)
            if not candidate_ids:
                return qs.none()
            qs = qs.filter(id__in=candidate_ids)

        return qs

    @action(detail=False, methods=['get'], url_path='filter-options')
    def filter_options(self, request):
        all_raw_items = list(RawIBKRExecution.objects.select_related('broker_account').all())
        accounts = list(
            BrokerAccount.objects.filter(broker='ibkr', is_active=True)
            .order_by('account_code')
            .values_list('account_code', flat=True)
        )
        selected_account = _clean_filter_param('account', request.query_params.get('account'))
        raw_items = [
            item for item in all_raw_items
            if not selected_account or item.broker_account.account_code == selected_account
        ]
        symbols = sorted({item.symbol for item in raw_items if item.symbol})
        strategies = sorted({_extract_strategy_from_payload(item.raw_payload) for item in raw_items if _extract_strategy_from_payload(item.raw_payload)})
        asset_classes = sorted({item.sec_type for item in raw_items if item.sec_type})
        return Response({
            'accounts': accounts,
            'symbols': symbols,
            'strategies': strategies,
            'asset_classes': asset_classes,
        })

    def _calc_summary(self, groups, raw_items):
        groups = list(groups)
        raw_items = list(raw_items)
        closed_groups = [obj for obj in groups if obj.status == 'closed']
        latest_groups = _latest_groups_by_symbol(groups)
        current_open_groups = [obj for obj in latest_groups if _safe_decimal(obj.open_qty) != ZERO]

        total_realized = sum((_safe_decimal(item.realized_pnl) for item in raw_items), ZERO)
        total_commission = sum((_safe_decimal(item.commission) for item in raw_items), ZERO)

        gross_profit = sum((_safe_decimal(obj.realized_pnl) for obj in closed_groups if _safe_decimal(obj.realized_pnl) > ZERO), ZERO)
        gross_loss = sum((-_safe_decimal(obj.realized_pnl) for obj in closed_groups if _safe_decimal(obj.realized_pnl) < ZERO), ZERO)
        wins = [obj for obj in closed_groups if _safe_decimal(obj.realized_pnl) > ZERO]
        losses = [obj for obj in closed_groups if _safe_decimal(obj.realized_pnl) < ZERO]

        total_closed = len(closed_groups)
        win_rate = (Decimal(len(wins)) / Decimal(total_closed) * Decimal('100')) if total_closed else ZERO
        profit_factor = (gross_profit / gross_loss) if gross_loss > ZERO else None
        expectancy = (total_realized / Decimal(total_closed)) if total_closed else ZERO
        avg_win = (gross_profit / Decimal(len(wins))) if wins else ZERO
        avg_loss = (sum((_safe_decimal(obj.realized_pnl) for obj in losses), ZERO) / Decimal(len(losses))) if losses else ZERO
        largest_win = max((_safe_decimal(obj.realized_pnl) for obj in wins), default=ZERO)
        largest_loss = min((_safe_decimal(obj.realized_pnl) for obj in losses), default=ZERO)
        hold_minutes = []
        for obj in closed_groups:
            if not obj.opened_at or not obj.closed_at:
                continue
            opened_at = obj.opened_at
            closed_at = obj.closed_at
            if timezone.is_naive(opened_at):
                opened_at = timezone.make_aware(opened_at, timezone.get_current_timezone())
            if timezone.is_naive(closed_at):
                closed_at = timezone.make_aware(closed_at, timezone.get_current_timezone())
            delta_minutes = Decimal(str((closed_at - opened_at).total_seconds())) / Decimal('60')
            if delta_minutes >= ZERO:
                hold_minutes.append(delta_minutes)
        avg_hold_minutes = (
            sum(hold_minutes, ZERO) / Decimal(len(hold_minutes))
            if hold_minutes else ZERO
        )

        summary = {
            'trade_groups': len(groups),
            'trade_count': len(groups),
            'open_positions': len(current_open_groups),
            'closed_trade_count': total_closed,
            'winning_trade_count': len(wins),
            'losing_trade_count': len(losses),
            'total_realized_pnl': float(total_realized),
            'total_commission': float(total_commission),
            'commission_total': float(total_commission),
            'per_trade_avg_pnl': float(expectancy),
            'avg_pnl_per_trade': float(expectancy),
            'win_rate': float(round(win_rate, 2)),
            'profit_factor': None if profit_factor is None else float(round(profit_factor, 2)),
            'expectancy': float(round(expectancy, 2)),
            'wins': len(wins),
            'losses': len(losses),
            'avg_win': float(round(avg_win, 2)),
            'avg_loss': float(round(avg_loss, 2)),
            'largest_win': float(round(largest_win, 2)),
            'largest_loss': float(round(largest_loss, 2)),
            'avg_hold_minutes': float(round(avg_hold_minutes, 2)),
            'gross_profit': float(gross_profit),
            'gross_loss': float(gross_loss),
            'current_open_symbols': [obj.symbol for obj in current_open_groups],
        }
        return summary

    def _build_charts(self, groups, raw_items):
        by_date = defaultdict(Decimal)
        symbol_totals = defaultdict(Decimal)
        daily_wins = defaultdict(int)
        daily_losses = defaultdict(int)

        for item in raw_items:
            trade_date = item.trade_date or (item.executed_at.date() if item.executed_at else None)
            if not trade_date:
                continue
            key = str(trade_date)
            pnl = _safe_decimal(item.realized_pnl)
            by_date[key] += pnl
            symbol_totals[item.symbol] += pnl
            if pnl > ZERO:
                daily_wins[key] += 1
            elif pnl < ZERO:
                daily_losses[key] += 1

        dates = sorted(by_date.keys())
        cumulative_values = []
        running = ZERO
        for d in dates:
            running += by_date[d]
            cumulative_values.append(float(running))

        latest_groups = _latest_groups_by_symbol(groups)
        current_open_groups = [obj for obj in latest_groups if _safe_decimal(obj.open_qty) != ZERO]
        status_breakdown = {
            'open': len([obj for obj in current_open_groups if obj.status == 'open']),
            'partial': len([obj for obj in current_open_groups if obj.status == 'partial']),
            'closed': len([obj for obj in groups if obj.status == 'closed']),
        }

        all_win_loss_dates = sorted(set(daily_wins.keys()) | set(daily_losses.keys()))
        charts = {
            'daily_realized_pnl': {'labels': dates, 'values': [float(by_date[d]) for d in dates]},
            'pnl_trend': [{'date': d, 'realized_pnl': str(by_date[d])} for d in dates],
            'daily_wins_losses': {
                'labels': all_win_loss_dates,
                'wins': [daily_wins.get(d, 0) for d in all_win_loss_dates],
                'losses': [daily_losses.get(d, 0) for d in all_win_loss_dates],
            },
            'cumulative_pnl': {'labels': dates, 'values': cumulative_values},
            'cumulative_pnl_legacy': [{'date': d, 'realized_pnl': str(v)} for d, v in zip(dates, cumulative_values)],
            'status_breakdown': status_breakdown,
            'pnl_by_symbol': {
                'labels': sorted(symbol_totals.keys()),
                'values': [float(symbol_totals[s]) for s in sorted(symbol_totals.keys())],
            },
            'symbol_pnl': [
                {'symbol': symbol, 'realized_pnl': str(value)}
                for symbol, value in sorted(symbol_totals.items(), key=lambda item: item[1], reverse=True)
            ],
            'calendar': [
                {
                    'date': d,
                    'realized_pnl': str(by_date[d]),
                    'wins': daily_wins.get(d, 0),
                    'losses': daily_losses.get(d, 0),
                }
                for d in dates
            ],
        }
        return charts

    def _build_widgets(self, summary, charts):
        return [
            {'key': 'trade_groups', 'label': 'Trade Groups', 'value': summary['trade_groups']},
            {'key': 'open_positions', 'label': 'Open Positions', 'value': summary['open_positions']},
            {'key': 'total_realized_pnl', 'label': 'Total PnL', 'value': summary['total_realized_pnl']},
            {'key': 'per_trade_avg_pnl', 'label': 'Per Trade Avg PnL', 'value': summary['per_trade_avg_pnl']},
            {'key': 'win_rate', 'label': 'Win Rate', 'value': summary['win_rate']},
            {'key': 'profit_factor', 'label': 'Profit Factor', 'value': summary['profit_factor']},
            {'key': 'expectancy', 'label': 'Expectancy', 'value': summary['expectancy']},
            {'key': 'commission_total', 'label': 'Commission', 'value': summary['commission_total']},
            {'key': 'daily_realized_pnl', 'label': 'Daily Realized PnL', 'chart': charts['daily_realized_pnl']},
            {'key': 'daily_wins_losses', 'label': 'Daily Wins / Losses', 'chart': charts['daily_wins_losses']},
            {'key': 'cumulative_pnl', 'label': 'Cumulative PnL', 'chart': charts['cumulative_pnl']},
            {'key': 'pnl_by_symbol', 'label': 'PnL by Symbol', 'chart': charts['pnl_by_symbol']},
            {'key': 'status_breakdown', 'label': 'Status Breakdown', 'chart': charts['status_breakdown']},
        ]

    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        groups = list(self.get_queryset())
        raw_items = self._filtered_raw_executions()
        summary = self._calc_summary(groups, raw_items)
        charts = self._build_charts(groups, raw_items)
        widgets = self._build_widgets(summary, charts)
        return Response({
            **summary,
            'summary': summary,
            'charts': charts,
            'widgets': widgets,
        })

    @action(detail=False, methods=['get'], url_path='closed-analytics')
    def closed_analytics(self, request):
        qs = self.get_queryset().filter(status='closed').order_by('-trade_date', '-id')
        page = self.paginate_queryset(qs)
        summary = self._calc_summary(list(qs), self._filtered_raw_executions())
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated = self.get_paginated_response(serializer.data)
            paginated.data['summary'] = summary
            return paginated
        serializer = self.get_serializer(qs, many=True)
        return Response({'results': serializer.data, 'summary': summary})

    @action(detail=False, methods=['get'], url_path='monthly-report')
    def monthly_report(self, request):
        qs = list(self.get_queryset())
        month_groups = defaultdict(list)
        for obj in qs:
            month_groups[obj.trade_date.strftime('%Y-%m')].append(obj)

        month_summaries = []
        for month_key, items in sorted(month_groups.items()):
            raw_items = [
                item for item in self._filtered_raw_executions()
                if (item.trade_date or (item.executed_at.date() if item.executed_at else None))
                and (item.trade_date or item.executed_at.date()).strftime('%Y-%m') == month_key
            ]
            summary = self._calc_summary(items, raw_items)
            month_summaries.append({
                'month': month_key,
                'trade_count': summary['trade_count'],
                'closed_trade_count': summary['closed_trade_count'],
                'winning_trade_count': summary['winning_trade_count'],
                'losing_trade_count': summary['losing_trade_count'],
                'win_rate': summary['win_rate'],
                'total_realized_pnl': summary['total_realized_pnl'],
                'total_commission': summary['total_commission'],
                'avg_win': summary['avg_win'],
                'avg_loss': summary['avg_loss'],
                'profit_factor': summary['profit_factor'],
            })

        selected_month = request.query_params.get('month') or (month_summaries[-1]['month'] if month_summaries else None)
        selected_groups = month_groups.get(selected_month, []) if selected_month else []
        selected_raw = [
            item for item in self._filtered_raw_executions()
            if selected_month and (item.trade_date or (item.executed_at.date() if item.executed_at else None))
            and (item.trade_date or item.executed_at.date()).strftime('%Y-%m') == selected_month
        ]
        selected_summary = self._calc_summary(selected_groups, selected_raw) if selected_month else self._calc_summary([], [])

        symbol_totals = defaultdict(Decimal)
        for item in selected_raw:
            symbol_totals[item.symbol] += _safe_decimal(item.realized_pnl)
        symbol_breakdown = [
            {'symbol': symbol, 'realized_pnl': str(value)}
            for symbol, value in sorted(symbol_totals.items(), key=lambda item: item[1], reverse=True)
        ]

        return Response({
            'available_months': [item['month'] for item in reversed(month_summaries)],
            'selected_month': selected_month,
            'selected_summary': selected_summary,
            'month_summaries': list(reversed(month_summaries)),
            'selected_groups': TradeGroupSerializer(selected_groups[:50], many=True).data,
            'charts': {
                'monthly_realized_pnl': [
                    {'month': item['month'], 'realized_pnl': item['total_realized_pnl']}
                    for item in month_summaries[-12:]
                ],
                'selected_symbol_breakdown': symbol_breakdown[:12],
            },
        })


class RawExecutionListAPIView(ListAPIView):
    queryset = RawIBKRExecution.objects.all().order_by('-executed_at', '-id')
    serializer_class = RawIBKRExecutionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        symbol = self.request.query_params.get('symbol')
        side = self.request.query_params.get('side')
        account = resolve_request_account(self.request)
        sec_type = self.request.query_params.get('sec_type') or self.request.query_params.get('asset_class')
        date_from = self.request.query_params.get('date_from') or self.request.query_params.get('start')
        date_to = self.request.query_params.get('date_to') or self.request.query_params.get('end')
        query = self.request.query_params.get('query') or self.request.query_params.get('q')
        strategy = self.request.query_params.get('strategy')

        if symbol:
            qs = qs.filter(symbol__icontains=symbol)
        if side:
            qs = qs.filter(side=side)
        qs = qs.filter(broker_account=account)
        if sec_type:
            qs = qs.filter(sec_type=sec_type)
        if date_from:
            qs = qs.filter(trade_date__gte=date_from)
        if date_to:
            qs = qs.filter(trade_date__lte=date_to)
        if query:
            qs = qs.filter(
                Q(execution_id__icontains=query)
                | Q(order_id__icontains=query)
                | Q(symbol__icontains=query)
                | Q(local_symbol__icontains=query)
            )

        items = list(qs)
        if strategy:
            items = [item.id for item in items if _extract_strategy_from_payload(item.raw_payload) == strategy]
            qs = qs.filter(id__in=items)
        return qs
