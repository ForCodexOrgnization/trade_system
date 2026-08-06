import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TradingDay(TimestampedModel):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("review_pending", "Review Pending"),
        ("reviewed", "Reviewed"),
        ("locked", "Locked"),
    ]

    account = models.ForeignKey("common.BrokerAccount", on_delete=models.PROTECT, related_name="journal_trading_days")
    trade_date = models.DateField()
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="draft")
    timezone = models.CharField(max_length=64, default="America/New_York")
    daily_risk_limit = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_trades = models.PositiveSmallIntegerField(null=True, blank=True)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    total_r = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    market_environment = models.CharField(max_length=120, blank=True, default="")
    closing_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-trade_date", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["account", "trade_date"], name="journal_unique_trading_day")]


class DecisionContext(TimestampedModel):
    KIND_CHOICES = [("intraday", "Intraday"), ("swing", "Swing")]
    POSITION_STAGE_CHOICES = [
        ("idea_validation", "Idea Validation"), ("initial_entry", "Initial Entry"),
        ("position_building", "Position Building"), ("holding", "Holding"),
        ("risk_reduction", "Risk Reduction"), ("exit", "Exit"),
    ]
    TYPE_CHOICES = [
        ("premarket", "Premarket"),
        ("opening", "Opening"),
        ("morning", "Morning"),
        ("midday", "Midday"),
        ("power_hour", "Power Hour"),
        ("idea_validation", "Idea Validation"),
        ("initial_entry", "Initial Entry"),
        ("position_building", "Position Building"),
        ("holding", "Holding"),
        ("risk_reduction", "Risk Reduction"),
        ("exit", "Exit"),
        ("custom", "Custom"),
    ]
    STATUS_CHOICES = [("planned", "Planned"), ("active", "Active"), ("closed", "Closed"), ("reviewed", "Reviewed")]

    account = models.ForeignKey("common.BrokerAccount", on_delete=models.PROTECT, related_name="journal_decision_contexts")
    trading_day = models.ForeignKey(TradingDay, on_delete=models.CASCADE, related_name="contexts", null=True, blank=True)
    name = models.CharField(max_length=100)
    context_kind = models.CharField(max_length=16, choices=KIND_CHOICES, default="intraday")
    context_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default="custom")
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")
    risk_limit_r = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    result_r = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    market_environment = models.CharField(max_length=120, blank=True, default="")
    allowed_setups = models.JSONField(default=list, blank=True)
    no_trade_conditions = models.TextField(blank=True, default="")
    stop_rule = models.TextField(blank=True, default="")
    energy_score = models.PositiveSmallIntegerField(null=True, blank=True)
    focus_score = models.PositiveSmallIntegerField(null=True, blank=True)
    stress_score = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["start_at", "created_at"]

    def clean(self):
        if self.context_kind == "intraday" and not self.trading_day_id:
            raise ValidationError("Intraday decision contexts require a trading day.")
        if self.context_kind == "swing" and self.trading_day_id:
            raise ValidationError("Swing decision contexts must not be tied to a trading day.")


class Campaign(TimestampedModel):
    DIRECTION_CHOICES = [("long", "Long"), ("short", "Short"), ("neutral", "Neutral")]
    HORIZON_CHOICES = [("scalp", "Scalp"), ("intraday", "Intraday"), ("swing", "Swing"), ("position", "Position")]
    STATUS_CHOICES = [
        ("planned", "Planned"),
        ("active", "Active"),
        ("paused", "Paused"),
        ("closed", "Closed"),
        ("review_pending", "Review Pending"),
        ("reviewed", "Reviewed"),
        ("cancelled", "Cancelled"),
    ]

    account = models.ForeignKey("common.BrokerAccount", on_delete=models.PROTECT, related_name="journal_campaigns")
    context = models.ForeignKey(DecisionContext, on_delete=models.PROTECT, related_name="campaigns")
    symbol = models.CharField(max_length=64)
    direction = models.CharField(max_length=12, choices=DIRECTION_CHOICES)
    setup = models.CharField(max_length=100)
    horizon = models.CharField(max_length=16, choices=HORIZON_CHOICES, default="intraday")
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default="planned")
    max_risk_r = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    planned_risk_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=1)
    result_r = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    closed_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["symbol", "status"])]

    @property
    def has_snapshot(self):
        return hasattr(self, "decision_snapshot")


class DecisionSnapshot(TimestampedModel):
    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name="decision_snapshot")
    observed_evidence = models.JSONField(default=list)
    interpretation = models.TextField()
    strongest_counter_case = models.TextField()
    chosen_action = models.TextField(blank=True, default="")
    entry_trigger = models.TextField()
    invalidation = models.TextField()
    time_stop = models.CharField(max_length=160, blank=True, default="")
    immutable_snapshot_hash = models.CharField(max_length=64, unique=True, editable=False)
    revision_no = models.PositiveSmallIntegerField(default=1, editable=False)

    def canonical_payload(self):
        scenarios = [
            {
                "name": item.name,
                "probability": str(item.probability),
                "confirmation": item.confirmation,
                "contradiction": item.contradiction,
                "planned_action": item.planned_action,
                "sort_order": item.sort_order,
            }
            for item in self.scenarios.order_by("sort_order", "created_at")
        ] if self.pk else []
        return {
            "campaign_id": str(self.campaign_id),
            "observed_evidence": self.observed_evidence,
            "interpretation": self.interpretation,
            "strongest_counter_case": self.strongest_counter_case,
            "chosen_action": self.chosen_action,
            "entry_trigger": self.entry_trigger,
            "invalidation": self.invalidation,
            "time_stop": self.time_stop,
            "scenarios": scenarios,
        }

    def save(self, *args, **kwargs):
        if self.pk and DecisionSnapshot.objects.filter(pk=self.pk).exists():
            raise ValidationError("Original decision snapshots are immutable.")
        if not self.immutable_snapshot_hash:
            raw = json.dumps(self.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            self.immutable_snapshot_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        super().save(*args, **kwargs)


class Scenario(TimestampedModel):
    snapshot = models.ForeignKey(DecisionSnapshot, on_delete=models.CASCADE, related_name="scenarios")
    name = models.CharField(max_length=100)
    probability = models.DecimalField(max_digits=5, decimal_places=2)
    confirmation = models.TextField()
    contradiction = models.TextField()
    planned_action = models.TextField()
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]


class Attempt(TimestampedModel):
    STATUS_CHOICES = [("pending", "Pending"), ("open", "Open"), ("scaling", "Scaling"), ("closed", "Closed"), ("voided", "Voided")]
    REENTRY_CHOICES = [
        ("planned_retry", "Planned retry"),
        ("new_signal", "New signal"),
        ("better_price", "Better price"),
        ("noise_stop", "Noise stop"),
        ("changed_setup", "Changed setup"),
        ("emotional", "Emotional"),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="attempts")
    sequence_no = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    entry_at = models.DateTimeField(null=True, blank=True)
    exit_at = models.DateTimeField(null=True, blank=True)
    planned_risk_r = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    actual_risk_r = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    result_r = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    realized_pnl = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    reentry_reason = models.CharField(max_length=24, choices=REENTRY_CHOICES, blank=True, default="")
    what_changed = models.TextField(blank=True, default="")
    was_planned = models.BooleanField(default=True)

    class Meta:
        ordering = ["sequence_no"]
        constraints = [models.UniqueConstraint(fields=["campaign", "sequence_no"], name="journal_unique_attempt_sequence")]


class AttemptFill(TimestampedModel):
    attempt = models.ForeignKey(Attempt, on_delete=models.CASCADE, related_name="fill_links")
    fill = models.OneToOneField("trades.TradeFill", on_delete=models.PROTECT, related_name="journal_attempt_link")

    class Meta:
        ordering = ["fill__executed_at", "created_at"]


class CampaignReview(TimestampedModel):
    GRADE_CHOICES = [(value, value) for value in ("A", "B", "C", "D")]
    PLAN_CHOICES = [("yes", "Yes"), ("partly", "Partly"), ("no", "No")]
    EXIT_CHOICES = [
        ("target", "Target"), ("trailing_stop", "Trailing stop"), ("initial_stop", "Initial stop"),
        ("thesis_invalidated", "Thesis invalidated"), ("time_stop", "Time stop"),
        ("market_change", "Market change"), ("manual_risk", "Manual risk"),
        ("emotional", "Emotional"), ("error", "Error"),
    ]

    campaign = models.OneToOneField(Campaign, on_delete=models.CASCADE, related_name="review")
    exit_reason = models.CharField(max_length=32, choices=EXIT_CHOICES)
    actual_scenario = models.ForeignKey(Scenario, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviews")
    entry_followed = models.CharField(max_length=8, choices=PLAN_CHOICES)
    management_followed = models.CharField(max_length=8, choices=PLAN_CHOICES)
    exit_followed = models.CharField(max_length=8, choices=PLAN_CHOICES)
    decision_grade = models.CharField(max_length=1, choices=GRADE_CHOICES)
    execution_grade = models.CharField(max_length=1, choices=GRADE_CHOICES)
    outcome_drivers = models.JSONField(default=list)
    hindsight_known_then = models.TextField()
    hindsight_luck = models.TextField()
    hindsight_process = models.TextField()
    would_repeat = models.BooleanField()
    lesson = models.TextField()


class DecisionContextReview(TimestampedModel):
    context = models.OneToOneField(DecisionContext, on_delete=models.CASCADE, related_name="review")
    preventable_loss_r = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    normal_variance_r = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    overtrading_flag = models.BooleanField(default=False)
    best_decision = models.TextField(blank=True, default="")
    main_mistake = models.TextField(blank=True, default="")
    next_rule = models.TextField(blank=True, default="")


class DecisionUpdate(TimestampedModel):
    EVENT_CHOICES = [
        ("price_action", "Price Action"),
        ("economic_data", "Economic Data"),
        ("news", "News"),
        ("earnings", "Earnings"),
        ("risk_event", "Risk Event"),
        ("time_review", "Scheduled Review"),
        ("custom", "Custom"),
    ]

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="decision_updates")
    position_stage = models.CharField(max_length=32, choices=DecisionContext.POSITION_STAGE_CHOICES)
    event_type = models.CharField(max_length=24, choices=EVENT_CHOICES, default="price_action")
    event_at = models.DateTimeField()
    observed_evidence = models.JSONField(default=list)
    interpretation = models.TextField()
    decision = models.TextField()
    risk_change = models.TextField(blank=True, default="")
    invalidation_update = models.TextField(blank=True, default="")
    next_review_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["event_at", "created_at"]


class AuditEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey("common.BrokerAccount", on_delete=models.PROTECT, related_name="journal_audit_events")
    aggregate_type = models.CharField(max_length=40)
    aggregate_id = models.UUIDField()
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["aggregate_type", "aggregate_id"])]
