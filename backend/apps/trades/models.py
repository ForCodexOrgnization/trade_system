from django.db import models


class ActiveTradeGroupManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_soft_deleted=False)


class RawIBKRExecution(models.Model):
    sync_job = models.ForeignKey('syncs.SyncJob', on_delete=models.SET_NULL, null=True, blank=True)
    broker_account = models.ForeignKey(
        'common.BrokerAccount',
        on_delete=models.PROTECT,
        related_name='raw_executions',
    )
    broker = models.CharField(max_length=20, default='ibkr')
    execution_id = models.CharField(max_length=128, blank=True, null=True)
    perm_id = models.CharField(max_length=128, blank=True, null=True)
    order_id = models.CharField(max_length=128, blank=True, null=True)
    client_id = models.CharField(max_length=128, blank=True, null=True)
    account = models.CharField(max_length=64, blank=True, null=True)
    symbol = models.CharField(max_length=64)
    local_symbol = models.CharField(max_length=64, blank=True, null=True)
    conid = models.CharField(max_length=64, blank=True, null=True)
    sec_type = models.CharField(max_length=32, blank=True, null=True)
    currency = models.CharField(max_length=16, blank=True, null=True)
    exchange = models.CharField(max_length=64, blank=True, null=True)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    commission = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    executed_at = models.DateTimeField()
    trade_date = models.DateField(blank=True, null=True)
    raw_payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=255, unique=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['executed_at', 'id']
        indexes = [
            models.Index(fields=['symbol', 'executed_at']),
            models.Index(fields=['trade_date']),
            models.Index(fields=['perm_id']),
        ]

    def __str__(self):
        return f"{self.symbol} {self.side} {self.quantity} @ {self.price}"

    def save(self, *args, **kwargs):
        if not self.broker_account_id:
            from apps.common.models import BrokerAccount

            account_code = str(self.account or '').strip() or '__legacy_unknown__'
            self.broker_account, _ = BrokerAccount.objects.get_or_create(
                broker='ibkr',
                account_code=account_code,
                defaults={
                    'display_name': account_code,
                    'is_active': account_code != '__legacy_unknown__',
                },
            )
        super().save(*args, **kwargs)


class TradeFill(models.Model):
    raw_execution = models.OneToOneField(RawIBKRExecution, on_delete=models.CASCADE, related_name='fill')
    symbol = models.CharField(max_length=64)
    side = models.CharField(max_length=8)
    quantity = models.DecimalField(max_digits=20, decimal_places=6)
    price = models.DecimalField(max_digits=20, decimal_places=8)
    executed_at = models.DateTimeField()
    commission = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    signed_qty = models.DecimalField(max_digits=20, decimal_places=6)
    asset_class = models.CharField(max_length=32, blank=True, null=True)
    trade_day = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['executed_at', 'id']


class TradeGroup(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('partial', 'Partial'),
        ('closed', 'Closed'),
    ]

    account = models.ForeignKey(
        'common.BrokerAccount',
        on_delete=models.PROTECT,
        related_name='trade_groups',
    )
    symbol = models.CharField(max_length=64)
    trade_date = models.DateField()
    asset_class = models.CharField(max_length=32, blank=True, null=True)
    direction = models.CharField(max_length=8, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    total_buy_qty = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    total_sell_qty = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    net_qty = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    avg_buy_price = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    avg_sell_price = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    avg_open_cost = models.DecimalField(max_digits=20, decimal_places=8, blank=True, null=True)
    open_qty = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    commission_total = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    opened_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    is_soft_deleted = models.BooleanField(default=False, db_index=True)
    soft_deleted_at = models.DateTimeField(blank=True, null=True)
    soft_delete_reason = models.CharField(max_length=128, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ActiveTradeGroupManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ['-trade_date', '-id']


class TradeLotSnapshot(models.Model):
    trade_group = models.ForeignKey(TradeGroup, on_delete=models.CASCADE, related_name='lot_snapshots')
    symbol = models.CharField(max_length=64)
    open_qty = models.DecimalField(max_digits=20, decimal_places=6)
    remaining_qty = models.DecimalField(max_digits=20, decimal_places=6)
    open_price = models.DecimalField(max_digits=20, decimal_places=8)
    opened_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class TradeMatchedLot(models.Model):
    trade_group = models.ForeignKey(TradeGroup, on_delete=models.CASCADE, related_name='matched_lots')
    symbol = models.CharField(max_length=64)
    side = models.CharField(max_length=8, blank=True, null=True)
    matched_qty = models.DecimalField(max_digits=20, decimal_places=6)
    open_price = models.DecimalField(max_digits=20, decimal_places=8)
    close_price = models.DecimalField(max_digits=20, decimal_places=8)
    realized_pnl = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    commission_total = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    opened_at = models.DateTimeField(blank=True, null=True)
    closed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
