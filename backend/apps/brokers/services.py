from django.db import IntegrityError, transaction

from apps.common.models import BrokerAccount
from apps.syncs.models import SyncJob
from apps.trades.models import RawIBKRExecution, TradeGroup
from apps.trades.services import create_fill_from_raw, rebuild_trade_groups_for_dates
from decimal import Decimal

from .normalizers import build_execution_dedupe_key, parse_dt


class IBKRSyncService:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def _safe_decimal(value, default: str = '0') -> Decimal:
        if value in (None, ''):
            return Decimal(default)
        return Decimal(str(value))

    def normalize_row(self, row: dict) -> dict:
        executed_at = parse_dt(row.get('executed_at'))
        side = (row.get('side') or '').upper()
        return {
            'execution_id': row.get('execution_id'),
            'perm_id': row.get('perm_id'),
            'order_id': row.get('order_id'),
            'client_id': row.get('client_id'),
            'account': row.get('account'),
            'symbol': row.get('symbol'),
            'local_symbol': row.get('local_symbol'),
            'conid': row.get('conid'),
            'sec_type': row.get('sec_type'),
            'currency': row.get('currency'),
            'exchange': row.get('exchange'),
            'side': side,
            'quantity': self._safe_decimal(row.get('quantity')),
            'price': self._safe_decimal(row.get('price')),
            'commission': self._safe_decimal(row.get('commission')),
            'realized_pnl': self._safe_decimal(row.get('realized_pnl')) if row.get('realized_pnl') not in (None, '') else None,
            'executed_at': executed_at,
            'trade_date': executed_at.date() if executed_at else None,
            "raw_payload": row.get("raw_payload", {})
        }

    def _build_pre_sync_snapshot(self) -> dict:
        groups = TradeGroup.all_objects.all().order_by('id')
        protected_groups = []
        for group in groups:
            has_user_content = any(
                [
                    hasattr(group, 'journal'),
                    hasattr(group, 'trade_review'),
                    hasattr(group, 'pretrade_snapshot'),
                    group.daily_reviews.exists(),
                    group.daily_review_links.exists(),
                    group.position_checkpoints.exists(),
                ]
            )
            if not has_user_content:
                continue
            protected_groups.append(
                {
                    'id': group.id,
                    'symbol': group.symbol,
                    'asset_class': group.asset_class,
                    'direction': group.direction,
                    'opened_at': group.opened_at.isoformat() if group.opened_at else None,
                    'closed_at': group.closed_at.isoformat() if group.closed_at else None,
                    'status': group.status,
                }
            )

        return {
            'total_trade_groups': groups.count(),
            'protected_trade_groups': len(protected_groups),
            'protected_examples': protected_groups[:50],
        }

    def run_full_sync(self, sync_job: SyncJob):
        pre_sync_snapshot = self._build_pre_sync_snapshot()
        sync_job.metadata = {
            **(sync_job.metadata or {}),
            'pre_sync_tradegroup_snapshot': pre_sync_snapshot,
        }
        sync_job.save(update_fields=['metadata', 'updated_at'])

        rows = self.client.fetch_all_executions()
        accounts = sorted({str(row.get('account')).strip() for row in rows if row.get('account')})
        for account_code in accounts:
            BrokerAccount.objects.update_or_create(
                broker='ibkr',
                account_code=account_code,
                defaults={'display_name': account_code, 'is_active': True},
            )
        sync_job.metadata = {
            **(sync_job.metadata or {}),
            'accounts': accounts,
            'ibkr_fetch': getattr(self.client, 'last_fetch_metadata', {}),
        }
        sync_job.raw_count = len(rows)
        sync_job.save(update_fields=['metadata', 'raw_count', 'updated_at'])

        inserted = 0
        duplicate_count = 0
        touched_trade_dates = set()

        for row in rows:
            normalized = self.normalize_row(row)
            if normalized.get('trade_date'):
                touched_trade_dates.add(normalized['trade_date'])
            dedupe_key = build_execution_dedupe_key(normalized)
            normalized['dedupe_key'] = dedupe_key
            try:
                with transaction.atomic():
                    raw_obj = RawIBKRExecution.objects.create(sync_job=sync_job, **normalized)
                    create_fill_from_raw(raw_obj)
                    inserted += 1
                    if raw_obj.trade_date:
                        touched_trade_dates.add(raw_obj.trade_date)
            except IntegrityError:
                duplicate_count += 1
            except Exception as exc:
                sync_job.error_count += 1
                sync_job.error_message = str(exc)
                sync_job.save(update_fields=['error_count', 'error_message', 'updated_at'])

        rebuild_trade_groups_for_dates(touched_trade_dates)

        sync_job.inserted_count = inserted
        sync_job.duplicate_count = duplicate_count
        sync_job.status = 'success' if sync_job.error_count == 0 else 'partial'
        sync_job.save(update_fields=['inserted_count', 'duplicate_count', 'status', 'updated_at'])

        return {
            'raw_count': len(rows),
            'inserted_count': inserted,
            'duplicate_count': duplicate_count,
            'error_count': sync_job.error_count,
            'accounts': accounts,
            'ibkr_fetch': getattr(self.client, 'last_fetch_metadata', {}),
            'touched_trade_dates': [str(x) for x in sorted(touched_trade_dates)],
        }
