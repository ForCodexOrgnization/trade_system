import csv
import hashlib
import io
import json
import re
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ParseError, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.accounts import resolve_request_account
from apps.trades.models import RawIBKRExecution, TradeFill
from apps.trades.services import create_fill_from_raw

from .models import (
    Attempt,
    AttemptFill,
    AuditEvent,
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
from .serializers import (
    AttemptSerializer,
    CampaignReviewSerializer,
    CampaignSerializer,
    CorrectionRecordSerializer,
    DecisionContextReviewSerializer,
    DecisionContextSerializer,
    DecisionSnapshotSerializer,
    DecisionUpdateSerializer,
    DecisionVersionSerializer,
    FillSummarySerializer,
    TradingDaySerializer,
)


ZERO = Decimal("0")
FUTURES_CONTRACT_PATTERN = re.compile(r"^(.+?)[FGHJKMNQUVXZ]\d{1,4}$")


def _decimal(value):
    return Decimal(str(value or 0))


def _campaign_account(campaign):
    return campaign.account


def _symbols_compatible(campaign_symbol, fill_symbol):
    campaign_value = str(campaign_symbol or "").strip().upper()
    fill_value = str(fill_symbol or "").strip().upper()
    if campaign_value == fill_value:
        return True
    campaign_contract = FUTURES_CONTRACT_PATTERN.fullmatch(campaign_value)
    fill_contract = FUTURES_CONTRACT_PATTERN.fullmatch(fill_value)
    return bool(
        (fill_contract and not campaign_contract and fill_contract.group(1) == campaign_value)
        or (campaign_contract and not fill_contract and campaign_contract.group(1) == fill_value)
    )


def _audit(account, aggregate, event_type, payload=None):
    AuditEvent.objects.create(
        account=account,
        aggregate_type=aggregate.__class__.__name__.lower(),
        aggregate_id=aggregate.id,
        event_type=event_type,
        payload=payload or {},
    )


def _validated_scenarios(data):
    scenarios = data.get("scenarios") or []
    if not 2 <= len(scenarios) <= 6:
        raise ValidationError({"scenarios": "Between 2 and 6 scenarios are required."})
    probabilities = [_decimal(item.get("probability")) for item in scenarios]
    total = sum(probabilities, ZERO)
    if not Decimal("99") <= total <= Decimal("101"):
        raise ValidationError({"scenarios": "Scenario probabilities must total between 99 and 101."})
    normalized = []
    for index, item in enumerate(scenarios):
        probability = probabilities[index]
        if not Decimal("1") <= probability <= Decimal("99"):
            raise ValidationError({"scenarios": "Each probability must be between 1 and 99."})
        for field in ("name", "planned_action"):
            if not str(item.get(field) or "").strip():
                raise ValidationError({"scenarios": f"Scenario {index + 1} requires {field}."})
        normalized.append({
            "name": str(item["name"]).strip(), "probability": str(probability),
            "confirmation": str(item.get("confirmation") or "").strip(), "contradiction": str(item.get("contradiction") or "").strip(),
            "planned_action": str(item["planned_action"]).strip(), "sort_order": index,
        })
    return normalized


def _lock_original_decision(campaign):
    if hasattr(campaign, "decision_snapshot"):
        return campaign.decision_snapshot
    version = campaign.decision_versions.order_by("-version_no").first()
    if not version:
        raise ParseError("Save a pre-trade decision version before attaching the first fill.")
    snapshot = DecisionSnapshot.objects.create(
        campaign=campaign,
        observed_evidence=version.observed_evidence,
        interpretation=version.interpretation,
        strongest_counter_case=version.strongest_counter_case,
        chosen_action=version.chosen_action,
        entry_trigger=version.entry_trigger,
        invalidation=version.invalidation,
        time_stop=version.time_stop,
    )
    for item in version.scenarios:
        Scenario.objects.create(
            snapshot=snapshot, name=item["name"], probability=_decimal(item["probability"]),
            confirmation=item["confirmation"], contradiction=item["contradiction"],
            planned_action=item["planned_action"], sort_order=item.get("sort_order", 0),
        )
    snapshot = DecisionSnapshot.objects.prefetch_related("scenarios").get(pk=snapshot.pk)
    raw = json.dumps(snapshot.canonical_payload(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    final_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    DecisionSnapshot.objects.filter(pk=snapshot.pk).update(immutable_snapshot_hash=final_hash)
    _audit(_campaign_account(campaign), campaign, "OriginalDecisionLocked", {
        "decision_version_id": str(version.id), "version_no": version.version_no, "hash": final_hash,
    })
    return snapshot


def _recalculate_attempt(attempt):
    fills = list(
        TradeFill.objects.filter(journal_attempt_link__attempt=attempt)
        .select_related("raw_execution")
        .order_by("executed_at", "id")
    )
    if not fills:
        Attempt.objects.filter(pk=attempt.pk).update(
            status="pending", entry_at=None, exit_at=None, realized_pnl=ZERO, result_r=ZERO,
        )
        return
    net_qty = sum((_decimal(item.signed_qty) for item in fills), ZERO)
    realized_pnl = sum(
        (_decimal(item.raw_execution.realized_pnl) - _decimal(item.commission) for item in fills),
        ZERO,
    )
    status_value = "closed" if net_qty == ZERO else "open" if len(fills) == 1 else "scaling"
    risk_amount = _decimal(attempt.campaign.planned_risk_amount)
    result_r = realized_pnl / risk_amount if risk_amount > ZERO else ZERO
    Attempt.objects.filter(pk=attempt.pk).update(
        status=status_value,
        entry_at=fills[0].executed_at,
        exit_at=fills[-1].executed_at if status_value == "closed" else None,
        realized_pnl=realized_pnl,
        result_r=result_r,
    )


def _recalculate_campaign(campaign):
    attempts = Campaign.objects.get(pk=campaign.pk).attempts.exclude(status="voided")
    totals = attempts.aggregate(realized_pnl=Sum("realized_pnl"), result_r=Sum("result_r"))
    realized_pnl = totals["realized_pnl"] or ZERO
    result_r = totals["result_r"] or ZERO
    Campaign.objects.filter(pk=campaign.pk).update(realized_pnl=realized_pnl, result_r=result_r)
    context = campaign.context
    context_total = Campaign.objects.filter(context=context).exclude(status="cancelled").aggregate(value=Sum("result_r"))["value"] or ZERO
    DecisionContext.objects.filter(pk=context.pk).update(result_r=context_total)
    if context.trading_day_id:
        day = context.trading_day
        day_totals = Campaign.objects.filter(context__trading_day=day).exclude(status="cancelled").aggregate(
            pnl=Sum("realized_pnl"), result_r=Sum("result_r")
        )
        TradingDay.objects.filter(pk=day.pk).update(
            realized_pnl=day_totals["pnl"] or ZERO,
            total_r=day_totals["result_r"] or ZERO,
        )


def _normalize_attempt_sequences(campaign):
    attempts = list(campaign.attempts.order_by("entry_at", "created_at", "sequence_no"))
    for index, attempt in enumerate(attempts, start=1):
        Attempt.objects.filter(pk=attempt.pk).update(sequence_no=1000 + index)
    for index, attempt in enumerate(attempts, start=1):
        Attempt.objects.filter(pk=attempt.pk).update(sequence_no=index)


def _delete_empty_attempts(campaign):
    empty_ids = list(campaign.attempts.filter(fill_links__isnull=True).values_list("id", flat=True))
    if empty_ids:
        Attempt.objects.filter(id__in=empty_ids).delete()
        _normalize_attempt_sequences(campaign)
    return len(empty_ids)


class AccountScopedViewSet(viewsets.ModelViewSet):
    def request_account(self):
        if not hasattr(self, "_journal_account"):
            self._journal_account = resolve_request_account(self.request)
        return self._journal_account


class TradingDayViewSet(AccountScopedViewSet):
    serializer_class = TradingDaySerializer
    queryset = TradingDay.objects.select_related("account").prefetch_related(
        "contexts__campaigns__decision_snapshot__scenarios",
        "contexts__campaigns__decision_versions",
        "contexts__campaigns__decision_updates",
        "contexts__campaigns__corrections",
        "contexts__campaigns__attempts__fill_links__fill",
        "contexts__campaigns__review",
        "contexts__review",
    )

    def get_queryset(self):
        qs = super().get_queryset().filter(account=self.request_account())
        trade_date = self.request.query_params.get("date")
        return qs.filter(trade_date=trade_date) if trade_date else qs

    def perform_create(self, serializer):
        day = serializer.save(account=self.request_account())
        _audit(day.account, day, "TradingDayCreated")

    @action(detail=False, methods=["get", "post"], url_path="today")
    def today(self, request):
        account = self.request_account()
        trade_date = request.query_params.get("date") or request.data.get("trade_date") or timezone.localdate()
        day = self.get_queryset().filter(trade_date=trade_date).first()
        if request.method == "POST" and not day:
            day = TradingDay.objects.create(
                account=account,
                trade_date=trade_date,
                status=request.data.get("status", "draft"),
                daily_risk_limit=request.data.get("daily_risk_limit") or None,
                max_trades=request.data.get("max_trades") or None,
                market_environment=request.data.get("market_environment", ""),
            )
            _audit(account, day, "TradingDayCreated")
        fills = TradeFill.objects.filter(
            raw_execution__broker_account=account,
            trade_day=trade_date,
            journal_attempt_link__isnull=True,
        ).order_by("executed_at", "id")
        return Response({
            "trading_day": TradingDaySerializer(day).data if day else None,
            "ungrouped_fills": FillSummarySerializer(fills, many=True).data,
        })


class DecisionContextViewSet(AccountScopedViewSet):
    serializer_class = DecisionContextSerializer
    queryset = DecisionContext.objects.select_related("account", "trading_day").prefetch_related(
        "campaigns__decision_snapshot__scenarios", "campaigns__decision_versions", "campaigns__decision_updates",
        "campaigns__corrections", "campaigns__attempts__fill_links__fill", "campaigns__review"
    )

    def get_queryset(self):
        qs = super().get_queryset().filter(account=self.request_account())
        day_id = self.request.query_params.get("trading_day")
        kind = self.request.query_params.get("context_kind")
        if day_id:
            qs = qs.filter(trading_day_id=day_id)
        if kind:
            qs = qs.filter(context_kind=kind)
        return qs

    def perform_create(self, serializer):
        day = serializer.validated_data.get("trading_day")
        if day and day.account_id != self.request_account().id:
            raise ValidationError("Trading day belongs to another account.")
        context = serializer.save(account=self.request_account())
        _audit(self.request_account(), context, "DecisionContextCreated")

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        context = self.get_object()
        if context.status not in ("planned", "active"):
            raise ParseError("Only a planned context can be started.")
        context.status = "active"
        context.start_at = context.start_at or timezone.now()
        context.save(update_fields=["status", "start_at", "updated_at"])
        if context.trading_day_id:
            TradingDay.objects.filter(pk=context.trading_day_id, status="draft").update(status="active")
        _audit(context.account, context, "DecisionContextStarted")
        return Response(self.get_serializer(context).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        context = self.get_object()
        if context.campaigns.filter(status__in=["active", "paused"]).exists():
            raise ParseError("Close or cancel active campaigns first.")
        context.status = "closed"
        context.end_at = context.end_at or timezone.now()
        context.save(update_fields=["status", "end_at", "updated_at"])
        _audit(context.account, context, "DecisionContextClosed")
        return Response(self.get_serializer(context).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        context = self.get_object()
        serializer = DecisionContextReviewSerializer(data=request.data, instance=getattr(context, "review", None))
        serializer.is_valid(raise_exception=True)
        serializer.save(context=context)
        context.status = "reviewed"
        context.save(update_fields=["status", "updated_at"])
        _audit(context.account, context, "DecisionContextReviewed")
        return Response(self.get_serializer(context).data)


class CampaignViewSet(AccountScopedViewSet):
    serializer_class = CampaignSerializer
    queryset = Campaign.objects.select_related("account", "context__trading_day", "decision_snapshot").prefetch_related(
        "decision_snapshot__scenarios", "decision_versions", "decision_updates", "corrections",
        "attempts__fill_links__fill", "review"
    )

    def get_queryset(self):
        qs = super().get_queryset().filter(account=self.request_account())
        for param, field in (("context", "context_id"), ("status", "status"), ("date", "context__trading_day__trade_date"), ("horizon", "horizon")):
            value = self.request.query_params.get(param)
            if value:
                qs = qs.filter(**{field: value})
        return qs

    def perform_create(self, serializer):
        context = serializer.validated_data["context"]
        if context.account_id != self.request_account().id:
            raise ValidationError("Decision context belongs to another account.")
        horizon = serializer.validated_data.get("horizon", "intraday")
        if horizon in ("scalp", "intraday") and context.context_kind != "intraday":
            raise ValidationError("Intraday campaigns require an intraday decision context.")
        if horizon in ("swing", "position") and context.context_kind != "swing":
            raise ValidationError("Swing campaigns require a swing decision context.")
        if context.context_kind == "swing" and context.campaigns.exists():
            raise ValidationError("A swing decision context belongs to one campaign lifecycle.")
        campaign = serializer.save(account=self.request_account(), symbol=serializer.validated_data["symbol"].strip().upper())
        _audit(self.request_account(), campaign, "CampaignCreated")

    def update(self, request, *args, **kwargs):
        campaign = self.get_object()
        if hasattr(campaign, "decision_snapshot") or campaign.status in ("closed", "review_pending", "reviewed", "cancelled"):
            raise ParseError("Campaign fields are locked after the first fill. Use a correction record for data-entry errors.")
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        campaign = self.get_object()
        if AttemptFill.objects.filter(attempt__campaign=campaign).exists():
            raise ParseError("Campaigns with executions cannot be deleted. Use correction records and complete the review instead.")
        account = campaign.account
        context = campaign.context
        campaign_id = campaign.id
        _audit(account, campaign, "CampaignDeleted", {"symbol": campaign.symbol, "setup": campaign.setup})
        campaign.delete()
        context_total = Campaign.objects.filter(context=context).exclude(status="cancelled").aggregate(value=Sum("result_r"))["value"] or ZERO
        DecisionContext.objects.filter(pk=context.pk).update(result_r=context_total)
        if context.trading_day_id:
            day_totals = Campaign.objects.filter(context__trading_day=context.trading_day).exclude(status="cancelled").aggregate(
                pnl=Sum("realized_pnl"), result_r=Sum("result_r")
            )
            TradingDay.objects.filter(pk=context.trading_day_id).update(
                realized_pnl=day_totals["pnl"] or ZERO, total_r=day_totals["result_r"] or ZERO,
            )
        return Response({"deleted": str(campaign_id)}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="decision-versions")
    def decision_versions(self, request, pk=None):
        campaign = self.get_object()
        if hasattr(campaign, "decision_snapshot") or campaign.status in ("closed", "review_pending", "reviewed", "cancelled"):
            raise ParseError("The original decision is locked. Append a decision update or correction instead.")
        scenarios = _validated_scenarios(request.data)
        serializer = DecisionVersionSerializer(data={**request.data, "scenarios": scenarios})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            version_no = (campaign.decision_versions.order_by("-version_no").values_list("version_no", flat=True).first() or 0) + 1
            version = serializer.save(campaign=campaign, version_no=version_no)
            _audit(_campaign_account(campaign), campaign, "DecisionVersionSaved", {
                "decision_version_id": str(version.id), "version_no": version.version_no,
            })
        return Response(CampaignSerializer(self.get_object()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in ("planned", "paused"):
            raise ParseError("Only planned or paused campaigns can be activated.")
        readiness = CampaignSerializer(campaign).data["readiness"]
        if not readiness["ready"]:
            raise ValidationError({"readiness": readiness})
        campaign.status = "active"
        campaign.save(update_fields=["status", "updated_at"])
        _audit(_campaign_account(campaign), campaign, "CampaignActivated")
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status != "active":
            raise ParseError("Only active campaigns can be paused.")
        campaign.status = "paused"
        campaign.save(update_fields=["status", "updated_at"])
        _audit(_campaign_account(campaign), campaign, "CampaignPaused")
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status != "paused":
            raise ParseError("Only paused campaigns can be resumed.")
        campaign.status = "active"
        campaign.save(update_fields=["status", "updated_at"])
        _audit(_campaign_account(campaign), campaign, "CampaignResumed")
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=["post"], url_path="decision-updates")
    def decision_updates(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in ("active", "paused"):
            raise ParseError("Activate the campaign before recording a decision update.")
        if not hasattr(campaign, "decision_snapshot"):
            raise ParseError("The original decision locks on the first fill; updates are available after that point.")
        serializer = DecisionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            update = serializer.save(campaign=campaign)
            context = campaign.context
            if context.context_kind == "swing" and not update.position_stage:
                raise ValidationError({"position_stage": "Swing decision updates require a position stage."})
            if context.context_kind == "swing" and context.context_type != update.position_stage:
                context.context_type = update.position_stage
                context.save(update_fields=["context_type", "updated_at"])
            _audit(_campaign_account(campaign), campaign, "DecisionUpdated", {
                "decision_update_id": str(update.id),
                "position_stage": update.position_stage,
                "event_type": update.event_type,
            })
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def corrections(self, request, pk=None):
        campaign = self.get_object()
        if not hasattr(campaign, "decision_snapshot"):
            raise ParseError("Before the first fill, correct the decision by saving a new version.")
        serializer = CorrectionRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        correction = serializer.save(campaign=campaign)
        _audit(_campaign_account(campaign), campaign, "CorrectionRecorded", {
            "correction_id": str(correction.id), "target_type": correction.target_type, "field_name": correction.field_name,
        })
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="attach-fills")
    def attach_fills(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status == "planned":
            raise ParseError("Confirm the plan and start execution before grouping fills.")
        if campaign.status not in ("active", "paused"):
            raise ParseError("Only active or paused decisions can receive fills.")
        fill_ids = request.data.get("fill_ids") or []
        if not fill_ids:
            raise ValidationError({"fill_ids": "Select at least one fill."})
        fills = list(TradeFill.objects.filter(
            id__in=fill_ids,
            raw_execution__broker_account=self.request_account(),
        ).select_related("raw_execution"))
        if len(fills) != len(set(map(int, fill_ids))):
            raise ValidationError({"fill_ids": "One or more fills are unavailable for this account."})
        if any(not _symbols_compatible(campaign.symbol, item.symbol) for item in fills):
            raise ValidationError({"fill_ids": "All fills must match the campaign symbol or its futures root."})
        attempt_id = request.data.get("attempt_id")
        with transaction.atomic():
            _lock_original_decision(campaign)
            if attempt_id:
                attempt = campaign.attempts.filter(pk=attempt_id).first()
                if not attempt:
                    raise ValidationError({"attempt_id": "Attempt does not belong to this campaign."})
            else:
                open_attempts = list(campaign.attempts.filter(status__in=["open", "scaling"]))
                if len(open_attempts) == 1:
                    attempt = open_attempts[0]
                elif len(open_attempts) > 1:
                    raise ParseError("Multiple open attempts require an explicit target attempt.")
                else:
                    prior_attempts_exist = campaign.attempts.filter(status="closed").exists()
                    reentry_reason = str(request.data.get("reentry_reason") or "").strip()
                    what_changed = str(request.data.get("what_changed") or "").strip()
                    if prior_attempts_exist and (not reentry_reason or not what_changed):
                        raise ValidationError({"reentry": "A new round after a closed position requires a re-entry reason and what changed."})
                if not open_attempts:
                    if campaign.status == "paused":
                        raise ParseError("Resume the campaign before creating a new attempt. Closing fills may still be attached to an existing attempt.")
                    _delete_empty_attempts(campaign)
                    sequence = (campaign.attempts.order_by("-sequence_no").values_list("sequence_no", flat=True).first() or 0) + 1
                    if sequence > campaign.max_attempts:
                        raise ValidationError({"attempt": "Campaign maximum attempts has been reached."})
                    attempt = Attempt.objects.create(
                        campaign=campaign,
                        sequence_no=sequence,
                        planned_risk_r=request.data.get("planned_risk_r") or campaign.max_risk_r,
                        reentry_reason=request.data.get("reentry_reason", ""),
                        what_changed=request.data.get("what_changed", ""),
                        was_planned=request.data.get("was_planned", True),
                    )
            old_attempts = set()
            previous_assignments = {}
            for fill in fills:
                link = AttemptFill.objects.filter(fill=fill).first()
                previous_assignments[str(fill.id)] = str(link.attempt_id) if link else None
                if link:
                    old_attempts.add(link.attempt)
                    link.attempt = attempt
                    link.save(update_fields=["attempt", "updated_at"])
                else:
                    AttemptFill.objects.create(attempt=attempt, fill=fill)
            for old in old_attempts:
                if old.pk != attempt.pk:
                    _recalculate_attempt(old)
                    old_campaign = old.campaign
                    _recalculate_campaign(old_campaign)
            _recalculate_attempt(attempt)
            _recalculate_campaign(campaign)
            _audit(_campaign_account(campaign), campaign, "FillsAttached", {
                "attempt_id": str(attempt.id),
                "fill_ids": list(map(int, fill_ids)),
                "previous_assignments": previous_assignments,
            })
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="undo-grouping")
    def undo_grouping(self, request, pk=None):
        campaign = self.get_object()
        last_event = AuditEvent.objects.filter(aggregate_id=campaign.id).order_by("-occurred_at").first()
        if not last_event or last_event.event_type != "FillsAttached":
            raise ParseError("There is no immediately reversible grouping action.")
        previous = last_event.payload.get("previous_assignments") or {}
        if not previous:
            raise ParseError("The last grouping action has no reversal data.")
        affected_attempts = set()
        affected_campaigns = {campaign}
        with transaction.atomic():
            for fill_id, previous_attempt_id in previous.items():
                link = AttemptFill.objects.filter(fill_id=fill_id).select_related("attempt__campaign").first()
                if link:
                    affected_attempts.add(link.attempt)
                    affected_campaigns.add(link.attempt.campaign)
                if previous_attempt_id:
                    prior_attempt = Attempt.objects.filter(
                        pk=previous_attempt_id,
                        campaign__account=self.request_account(),
                    ).select_related("campaign").first()
                    if not prior_attempt:
                        raise ParseError("The previous attempt is no longer available.")
                    affected_attempts.add(prior_attempt)
                    affected_campaigns.add(prior_attempt.campaign)
                    if link:
                        link.attempt = prior_attempt
                        link.save(update_fields=["attempt", "updated_at"])
                    else:
                        AttemptFill.objects.create(attempt=prior_attempt, fill_id=fill_id)
                elif link:
                    link.delete()
            for attempt in affected_attempts:
                _recalculate_attempt(attempt)
            for affected_campaign in affected_campaigns:
                _recalculate_campaign(affected_campaign)
            _audit(_campaign_account(campaign), campaign, "GroupingUndone", {"reversed_event_id": str(last_event.id)})
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        campaign = self.get_object()
        _delete_empty_attempts(campaign)
        for attempt in campaign.attempts.all():
            _recalculate_attempt(attempt)
        _recalculate_campaign(campaign)
        campaign.refresh_from_db()
        if campaign.attempts.filter(status__in=["open", "scaling"]).exists():
            raise ParseError("The campaign still has an open position. Attach the closing fill to the open attempt before ending the decision.")
        if not campaign.attempts.filter(status="closed").exists():
            raise ParseError("A campaign needs at least one completed attempt before it can end.")
        campaign.status = "review_pending"
        campaign.closed_at = timezone.now()
        campaign.save(update_fields=["status", "closed_at", "updated_at"])
        _audit(_campaign_account(campaign), campaign, "CampaignClosed")
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        campaign = self.get_object()
        if campaign.status not in ("closed", "review_pending", "reviewed"):
            raise ParseError("Close the campaign before reviewing it.")
        existing = getattr(campaign, "review", None)
        serializer = CampaignReviewSerializer(instance=existing, data=request.data)
        serializer.is_valid(raise_exception=True)
        review = serializer.save(campaign=campaign)
        campaign.status = "reviewed"
        campaign.save(update_fields=["status", "updated_at"])
        _audit(_campaign_account(campaign), campaign, "CampaignReviewed", {"decision_grade": review.decision_grade})
        return Response(self.get_serializer(campaign).data)

    @action(detail=True, methods=["get"])
    def audit(self, request, pk=None):
        campaign = self.get_object()
        rows = AuditEvent.objects.filter(aggregate_id=campaign.id).values(
            "id", "event_type", "payload", "occurred_at"
        )
        return Response(list(rows))


class AttemptViewSet(AccountScopedViewSet):
    serializer_class = AttemptSerializer
    queryset = Attempt.objects.select_related("campaign__account").prefetch_related("fill_links__fill")

    def get_queryset(self):
        return super().get_queryset().filter(campaign__account=self.request_account())

    def perform_create(self, serializer):
        campaign = serializer.validated_data["campaign"]
        if _campaign_account(campaign).id != self.request_account().id:
            raise ValidationError("Campaign belongs to another account.")
        sequence = (campaign.attempts.order_by("-sequence_no").values_list("sequence_no", flat=True).first() or 0) + 1
        serializer.save(sequence_no=sequence)

    def destroy(self, request, *args, **kwargs):
        attempt = self.get_object()
        if attempt.fill_links.exists():
            raise ParseError("Attempts with fills cannot be deleted. Correct the fill grouping instead.")
        campaign = attempt.campaign
        attempt_id = attempt.id
        _audit(_campaign_account(campaign), campaign, "EmptyAttemptDeleted", {
            "attempt_id": str(attempt.id), "sequence_no": attempt.sequence_no,
        })
        attempt.delete()
        _normalize_attempt_sequences(campaign)
        _recalculate_campaign(campaign)
        return Response({"deleted": str(attempt_id)}, status=status.HTTP_200_OK)


class JournalAnalyticsAPIView(APIView):
    def get(self, request):
        account = resolve_request_account(request)
        campaigns = Campaign.objects.filter(account=account).exclude(status="cancelled")
        setup_rows = list(campaigns.values("setup").annotate(
            campaigns=Count("id"), average_r=Avg("result_r"), total_r=Sum("result_r")
        ).order_by("-total_r"))
        context_rows = list(campaigns.values("context__context_kind", "context__context_type").annotate(
            campaigns=Count("id"), average_r=Avg("result_r"), total_r=Sum("result_r")
        ).order_by("context__context_kind", "context__context_type"))
        planned = campaigns.filter(decision_snapshot__isnull=False).aggregate(count=Count("id"), average_r=Avg("result_r"), total_r=Sum("result_r"))
        unplanned = campaigns.filter(decision_snapshot__isnull=True).aggregate(count=Count("id"), average_r=Avg("result_r"), total_r=Sum("result_r"))
        sequence_rows = list(Attempt.objects.filter(campaign__in=campaigns).values("sequence_no").annotate(
            attempts=Count("id"), average_r=Avg("result_r"), total_r=Sum("result_r")
        ).order_by("sequence_no"))
        return Response({
            "setup": setup_rows,
            "context": context_rows,
            "plan_comparison": {"planned": planned, "unplanned": unplanned},
            "attempt_sequence": sequence_rows,
            "sample_size": campaigns.count(),
        })


class JournalFillImportAPIView(APIView):
    """Import a small, explicit CSV into the immutable broker fact layer."""

    REQUIRED_COLUMNS = {"symbol", "side", "quantity", "price", "executed_at"}

    def post(self, request):
        account = resolve_request_account(request)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "Choose a CSV file."})
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "CSV must be UTF-8 encoded."}) from exc
        reader = csv.DictReader(io.StringIO(text))
        headers = {str(item or "").strip().lower() for item in (reader.fieldnames or [])}
        missing = sorted(self.REQUIRED_COLUMNS - headers)
        if missing:
            raise ValidationError({"file": f"Missing columns: {', '.join(missing)}"})
        imported = 0
        duplicates = 0
        errors = []
        with transaction.atomic():
            for row_no, original in enumerate(reader, start=2):
                row = {str(key or "").strip().lower(): str(value or "").strip() for key, value in original.items()}
                try:
                    side = row["side"].upper()
                    if side not in ("BUY", "SELL"):
                        raise ValueError("side must be BUY or SELL")
                    executed_at = datetime.fromisoformat(row["executed_at"].replace("Z", "+00:00"))
                    if timezone.is_naive(executed_at):
                        executed_at = timezone.make_aware(executed_at, timezone.get_current_timezone())
                    execution_id = row.get("execution_id") or row.get("broker_fill_id") or ""
                    identity = execution_id or "|".join([
                        row["symbol"].upper(), side, row["quantity"], row["price"], executed_at.isoformat(),
                    ])
                    dedupe_key = hashlib.sha256(f"csv|{account.account_code}|{identity}".encode()).hexdigest()
                    raw, created = RawIBKRExecution.objects.get_or_create(
                        dedupe_key=dedupe_key,
                        defaults={
                            "broker_account": account,
                            "broker": row.get("broker") or "csv",
                            "execution_id": execution_id or None,
                            "order_id": row.get("order_id") or None,
                            "account": account.account_code,
                            "symbol": row["symbol"].upper(),
                            "local_symbol": row.get("local_symbol") or None,
                            "sec_type": row.get("sec_type") or row.get("asset_class") or "",
                            "currency": row.get("currency") or "USD",
                            "side": side,
                            "quantity": row["quantity"],
                            "price": row["price"],
                            "commission": row.get("commission") or 0,
                            "realized_pnl": row.get("realized_pnl") or None,
                            "executed_at": executed_at,
                            "trade_date": row.get("trade_date") or executed_at.date(),
                            "raw_payload": {"source": "journal_csv", "row": row_no},
                        },
                    )
                    if created:
                        create_fill_from_raw(raw)
                        imported += 1
                    else:
                        duplicates += 1
                except (ValueError, TypeError) as exc:
                    errors.append({"row": row_no, "error": str(exc)})
            if errors:
                raise ValidationError({"rows": errors[:20]})
        return Response({"imported": imported, "duplicates": duplicates})
