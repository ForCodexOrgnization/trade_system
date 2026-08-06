from decimal import Decimal

from rest_framework import serializers

from .models import (
    Attempt,
    AttemptFill,
    Campaign,
    CampaignReview,
    DecisionSnapshot,
    Scenario,
    Session,
    SessionReview,
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


class CampaignSerializer(serializers.ModelSerializer):
    decision_snapshot = DecisionSnapshotSerializer(read_only=True)
    attempts = AttemptSerializer(many=True, read_only=True)
    review = CampaignReviewSerializer(read_only=True)
    session_name = serializers.CharField(source="session.name", read_only=True)
    trade_date = serializers.DateField(source="session.trading_day.trade_date", read_only=True)
    readiness = serializers.SerializerMethodField()

    class Meta:
        model = Campaign
        fields = [
            "id", "session", "session_name", "trade_date", "symbol", "direction", "setup", "horizon",
            "status", "max_risk_r", "planned_risk_amount", "max_attempts", "result_r", "realized_pnl",
            "closed_at", "cancel_reason", "decision_snapshot", "attempts", "review", "readiness",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "result_r", "realized_pnl", "closed_at", "decision_snapshot", "attempts", "review", "created_at", "updated_at"]

    def get_readiness(self, obj):
        snapshot = getattr(obj, "decision_snapshot", None)
        if not snapshot:
            return {"score": 25, "ready": False, "missing": ["decision_snapshot"]}
        missing = []
        for field in ("interpretation", "strongest_counter_case", "entry_trigger", "invalidation"):
            if not getattr(snapshot, field):
                missing.append(field)
        scenarios = list(snapshot.scenarios.all())
        total = sum((item.probability for item in scenarios), Decimal("0"))
        if len(scenarios) not in (2, 3):
            missing.append("2_to_3_scenarios")
        if not Decimal("99") <= total <= Decimal("101"):
            missing.append("scenario_probability_total")
        score = max(0, 100 - len(missing) * 20)
        return {"score": score, "ready": not missing, "missing": missing}


class SessionReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionReview
        fields = "__all__"
        read_only_fields = ["id", "session", "created_at", "updated_at"]


class SessionSerializer(serializers.ModelSerializer):
    campaigns = CampaignSerializer(many=True, read_only=True)
    review = SessionReviewSerializer(read_only=True)
    campaign_count = serializers.IntegerField(source="campaigns.count", read_only=True)

    class Meta:
        model = Session
        fields = [
            "id", "trading_day", "name", "session_type", "start_at", "end_at", "status", "risk_limit_r",
            "result_r", "market_environment", "allowed_setups", "no_trade_conditions", "stop_rule",
            "energy_score", "focus_score", "stress_score", "campaign_count", "campaigns", "review",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "result_r", "campaign_count", "campaigns", "review", "created_at", "updated_at"]


class TradingDaySerializer(serializers.ModelSerializer):
    sessions = SessionSerializer(many=True, read_only=True)
    campaign_count = serializers.SerializerMethodField()
    attempt_count = serializers.SerializerMethodField()

    class Meta:
        model = TradingDay
        fields = [
            "id", "account", "trade_date", "status", "timezone", "daily_risk_limit", "max_trades",
            "realized_pnl", "total_r", "market_environment", "closing_note", "campaign_count",
            "attempt_count", "sessions", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "account", "realized_pnl", "total_r", "campaign_count", "attempt_count", "sessions", "created_at", "updated_at"]

    def get_campaign_count(self, obj):
        return Campaign.objects.filter(session__trading_day=obj).count()

    def get_attempt_count(self, obj):
        return Attempt.objects.filter(campaign__session__trading_day=obj).count()
