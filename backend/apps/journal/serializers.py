from decimal import Decimal

from rest_framework import serializers

from .models import (
    Attempt,
    AttemptFill,
    Campaign,
    CampaignReview,
    CorrectionRecord,
    DecisionContext,
    DecisionContextReview,
    DecisionSnapshot,
    DecisionUpdate,
    DecisionVersion,
    Scenario,
    TradingDay,
)


class ScenarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Scenario
        fields = ["id", "name", "probability", "confirmation", "contradiction", "planned_action", "sort_order"]
        read_only_fields = ["id"]


class DecisionSnapshotSerializer(serializers.ModelSerializer):
    scenarios = ScenarioSerializer(many=True, read_only=True)

    class Meta:
        model = DecisionSnapshot
        fields = [
            "id", "observed_evidence", "interpretation", "strongest_counter_case", "chosen_action",
            "entry_trigger", "invalidation", "time_stop", "immutable_snapshot_hash", "revision_no",
            "created_at", "scenarios",
        ]
        read_only_fields = ["id", "immutable_snapshot_hash", "revision_no", "created_at", "scenarios"]


class DecisionVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionVersion
        fields = [
            "id", "campaign", "version_no", "observed_evidence", "interpretation", "strongest_counter_case",
            "chosen_action", "entry_trigger", "invalidation", "time_stop", "scenarios", "change_note", "created_at",
        ]
        read_only_fields = ["id", "campaign", "version_no", "created_at"]


class FillSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    symbol = serializers.CharField()
    side = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=20, decimal_places=6)
    price = serializers.DecimalField(max_digits=20, decimal_places=8)
    commission = serializers.DecimalField(max_digits=20, decimal_places=8)
    executed_at = serializers.DateTimeField()
    trade_day = serializers.DateField()


class AttemptSerializer(serializers.ModelSerializer):
    fills = serializers.SerializerMethodField()

    class Meta:
        model = Attempt
        fields = [
            "id", "campaign", "sequence_no", "status", "entry_at", "exit_at", "planned_risk_r",
            "actual_risk_r", "result_r", "realized_pnl", "reentry_reason", "what_changed",
            "was_planned", "fills", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "sequence_no", "status", "entry_at", "exit_at", "result_r", "realized_pnl", "fills", "created_at", "updated_at"]

    def get_fills(self, obj):
        rows = [link.fill for link in obj.fill_links.select_related("fill").all()]
        return FillSummarySerializer(rows, many=True).data


class CampaignReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignReview
        fields = "__all__"
        read_only_fields = ["id", "campaign", "created_at", "updated_at"]


class DecisionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionUpdate
        fields = [
            "id", "campaign", "position_stage", "event_type", "event_at", "observed_evidence",
            "interpretation", "decision", "risk_change", "invalidation_update", "next_review_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "campaign", "created_at", "updated_at"]


class CorrectionRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorrectionRecord
        fields = [
            "id", "campaign", "target_type", "field_name", "original_value", "corrected_value", "reason", "created_at",
        ]
        read_only_fields = ["id", "campaign", "created_at"]


class CampaignSerializer(serializers.ModelSerializer):
    decision_snapshot = DecisionSnapshotSerializer(read_only=True)
    decision_versions = DecisionVersionSerializer(many=True, read_only=True)
    current_decision = serializers.SerializerMethodField()
    attempts = AttemptSerializer(many=True, read_only=True)
    review = CampaignReviewSerializer(read_only=True)
    decision_updates = DecisionUpdateSerializer(many=True, read_only=True)
    corrections = CorrectionRecordSerializer(many=True, read_only=True)
    context_name = serializers.CharField(source="context.name", read_only=True)
    context_kind = serializers.CharField(source="context.context_kind", read_only=True)
    context_type = serializers.CharField(source="context.context_type", read_only=True)
    trade_date = serializers.DateField(source="context.trading_day.trade_date", read_only=True, allow_null=True)
    readiness = serializers.SerializerMethodField()
    lifecycle = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "context", "context_name", "context_kind", "context_type", "trade_date", "symbol", "direction", "setup", "horizon",
            "status", "max_risk_r", "planned_risk_amount", "max_attempts", "result_r", "realized_pnl",
            "closed_at", "cancel_reason", "decision_snapshot", "decision_versions", "current_decision", "decision_updates",
            "corrections", "attempts", "review", "readiness", "lifecycle",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "result_r", "realized_pnl", "closed_at", "decision_snapshot", "decision_versions", "current_decision", "decision_updates", "corrections", "attempts", "review", "lifecycle", "created_at", "updated_at"]

    def get_current_decision(self, obj):
        if hasattr(obj, "decision_snapshot"):
            return DecisionSnapshotSerializer(obj.decision_snapshot).data
        version = obj.decision_versions.order_by("-version_no").first()
        return DecisionVersionSerializer(version).data if version else None

    def get_lifecycle(self, obj):
        locked = hasattr(obj, "decision_snapshot")
        ended = obj.status in ("closed", "review_pending", "reviewed", "cancelled")
        attempts = list(obj.attempts.all())
        has_fills = any(item.fill_links.all() for item in attempts)
        has_open_position = any(item.status in ("open", "scaling") for item in attempts)
        if ended:
            phase = "review"
        elif locked and has_open_position:
            phase = "holding"
        elif locked:
            phase = "ready_to_close"
        else:
            phase = "pre_trade"
        return {
            "phase": phase,
            "decision_locked": locked,
            "can_edit_decision": not locked and not ended,
            "can_add_update": locked and has_open_position and not ended,
            "can_close": locked and has_fills and not has_open_position and obj.status in ("active", "paused"),
            "can_delete": not has_fills,
            "can_pause": obj.status == "active",
            "can_resume": obj.status == "paused",
            "has_open_position": has_open_position,
            "can_review": ended,
            "version_count": obj.decision_versions.count(),
        }

    def get_readiness(self, obj):
        snapshot = getattr(obj, "decision_snapshot", None)
        version = obj.decision_versions.order_by("-version_no").first() if not snapshot else None
        decision = snapshot or version
        if not decision:
            return {"score": 25, "ready": False, "missing": ["decision_snapshot"]}
        missing = []
        for field in ("interpretation", "strongest_counter_case", "entry_trigger", "invalidation"):
            if not getattr(decision, field):
                missing.append(field)
        scenarios = list(snapshot.scenarios.all()) if snapshot else version.scenarios
        total = sum((item.probability for item in scenarios), Decimal("0")) if snapshot else sum((Decimal(str(item.get("probability") or 0)) for item in scenarios), Decimal("0"))
        if len(scenarios) not in (2, 3):
            missing.append("2_to_3_scenarios")
        if not Decimal("99") <= total <= Decimal("101"):
            missing.append("scenario_probability_total")
        score = max(0, 100 - len(missing) * 20)
        return {"score": score, "ready": not missing, "missing": missing}


class DecisionContextReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = DecisionContextReview
        fields = "__all__"
        read_only_fields = ["id", "context", "created_at", "updated_at"]


class DecisionContextSerializer(serializers.ModelSerializer):
    campaigns = CampaignSerializer(many=True, read_only=True)
    review = DecisionContextReviewSerializer(read_only=True)
    campaign_count = serializers.IntegerField(source="campaigns.count", read_only=True)

    class Meta:
        model = DecisionContext
        fields = [
            "id", "trading_day", "name", "context_kind", "context_type", "start_at", "end_at", "status", "risk_limit_r",
            "result_r", "market_environment", "allowed_setups", "no_trade_conditions", "stop_rule",
            "energy_score", "focus_score", "stress_score", "campaign_count", "campaigns", "review",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "result_r", "campaign_count", "campaigns", "review", "created_at", "updated_at"]

    def validate(self, attrs):
        kind = attrs.get("context_kind", getattr(self.instance, "context_kind", "intraday"))
        day = attrs.get("trading_day", getattr(self.instance, "trading_day", None))
        context_type = attrs.get("context_type", getattr(self.instance, "context_type", "custom"))
        if kind == "intraday" and not day:
            raise serializers.ValidationError({"trading_day": "Intraday contexts require a trading day."})
        if kind == "swing" and day:
            raise serializers.ValidationError({"trading_day": "Swing contexts cannot belong to a trading day."})
        intraday_types = {"premarket", "opening", "morning", "midday", "power_hour", "custom"}
        swing_types = {value for value, _ in DecisionContext.POSITION_STAGE_CHOICES}
        if kind == "intraday" and context_type not in intraday_types:
            raise serializers.ValidationError({"context_type": "Choose an intraday time segment."})
        if kind == "swing" and context_type not in swing_types:
            raise serializers.ValidationError({"context_type": "Choose a swing position stage."})
        return attrs


class TradingDaySerializer(serializers.ModelSerializer):
    contexts = DecisionContextSerializer(many=True, read_only=True)
    campaign_count = serializers.SerializerMethodField()
    attempt_count = serializers.SerializerMethodField()

    class Meta:
        model = TradingDay
        fields = [
            "id", "account", "trade_date", "status", "timezone", "daily_risk_limit", "max_trades",
            "realized_pnl", "total_r", "market_environment", "closing_note", "campaign_count",
            "attempt_count", "contexts", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "account", "realized_pnl", "total_r", "campaign_count", "attempt_count", "contexts", "created_at", "updated_at"]

    def get_campaign_count(self, obj):
        return Campaign.objects.filter(context__trading_day=obj).count()

    def get_attempt_count(self, obj):
        return Attempt.objects.filter(campaign__context__trading_day=obj).count()
