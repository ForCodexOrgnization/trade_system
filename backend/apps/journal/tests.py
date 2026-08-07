from datetime import datetime, timezone

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.models import BrokerAccount
from apps.trades.models import RawIBKRExecution, TradeFill

from .models import Attempt, Campaign, CorrectionRecord, DecisionContext, DecisionSnapshot, DecisionVersion, TradingDay


class JournalMVPTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.account = BrokerAccount.objects.create(account_code="DU-JOURNAL", display_name="Journal Account")
        self.day = TradingDay.objects.create(account=self.account, trade_date="2026-08-06")
        self.context = DecisionContext.objects.create(
            account=self.account, trading_day=self.day, name="Opening", context_kind="intraday", context_type="opening"
        )
        self.campaign = Campaign.objects.create(
            account=self.account,
            context=self.context,
            symbol="MESU6",
            direction="long",
            setup="Opening Breakout",
            planned_risk_amount="100",
            max_risk_r="1",
            max_attempts=2,
        )

    def snapshot_payload(self, probabilities=(60, 40)):
        return {
            "observed_evidence": ["VWAP reclaim"],
            "interpretation": "Buyers are accepting above VWAP.",
            "strongest_counter_case": "Breadth remains weak.",
            "chosen_action": "Enter on confirmation.",
            "entry_trigger": "Five-minute close above the opening range.",
            "invalidation": "Close back below VWAP.",
            "time_stop": "No follow-through in 15 minutes.",
            "scenarios": [
                {
                    "name": "Continuation",
                    "probability": probabilities[0],
                    "confirmation": "Higher high with breadth.",
                    "contradiction": "Immediate range rejection.",
                    "planned_action": "Hold to target.",
                },
                {
                    "name": "Failure",
                    "probability": probabilities[1],
                    "confirmation": "VWAP rejection.",
                    "contradiction": "Sustained acceptance above range.",
                    "planned_action": "Exit at invalidation.",
                },
            ],
        }

    def create_version(self, payload=None):
        return self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/decision-versions/?account=DU-JOURNAL",
            payload or self.snapshot_payload(),
            format="json",
        )

    def create_fill(self, execution_id, side, signed_qty, realized_pnl, second, symbol="MESU6"):
        raw = RawIBKRExecution.objects.create(
            broker_account=self.account,
            account=self.account.account_code,
            execution_id=execution_id,
            symbol=symbol,
            side=side,
            quantity="1",
            price="5000",
            commission="0.50",
            realized_pnl=realized_pnl,
            executed_at=datetime(2026, 8, 6, 14, 30, second, tzinfo=timezone.utc),
            trade_date="2026-08-06",
            dedupe_key=f"journal-{execution_id}",
        )
        return TradeFill.objects.create(
            raw_execution=raw,
            symbol=symbol,
            side=side,
            quantity="1",
            price="5000",
            executed_at=raw.executed_at,
            commission="0.50",
            signed_qty=signed_qty,
            asset_class="FUT",
            trade_day="2026-08-06",
        )

    def test_snapshot_requires_two_or_three_scenarios_totaling_about_100(self):
        response = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/decision-versions/?account=DU-JOURNAL",
            self.snapshot_payload((80, 40)),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(DecisionSnapshot.objects.filter(campaign=self.campaign).exists())

    def test_pretrade_versions_then_first_fill_locks_original_decision(self):
        first = self.create_version()
        changed_payload = self.snapshot_payload()
        changed_payload["interpretation"] = "Buyers remain in control after a retest."
        changed_payload["change_note"] = "Added retest evidence."
        second = self.create_version(changed_payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(DecisionVersion.objects.filter(campaign=self.campaign).count(), 2)
        self.assertFalse(DecisionSnapshot.objects.filter(campaign=self.campaign).exists())

        fill = self.create_fill("lock-entry", "BUY", "1", "0", 0)
        grouped = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [fill.id], "planned_risk_r": 1},
            format="json",
        )
        self.assertEqual(grouped.status_code, 200)
        snapshot = DecisionSnapshot.objects.get(campaign=self.campaign)
        original_hash = snapshot.immutable_snapshot_hash
        snapshot.interpretation = "Hindsight rewrite"

        with self.assertRaises(DjangoValidationError):
            snapshot.save()

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.immutable_snapshot_hash, original_hash)
        self.assertEqual(snapshot.interpretation, "Buyers remain in control after a retest.")
        self.assertEqual(self.create_version().status_code, 400)
        self.assertEqual(
            self.client.patch(
                f"/api/journal/campaigns/{self.campaign.id}/?account=DU-JOURNAL",
                {"setup": "Hindsight setup"}, format="json",
            ).status_code,
            400,
        )
        correction = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/corrections/?account=DU-JOURNAL",
            {"target_type": "decision", "field_name": "interpretation", "original_value": "typo", "corrected_value": "correct text", "reason": "Data-entry error"},
            format="json",
        )
        self.assertEqual(correction.status_code, 201)
        self.assertEqual(CorrectionRecord.objects.filter(campaign=self.campaign).count(), 1)

    def test_fill_grouping_close_and_review_workflow(self):
        self.assertEqual(self.create_version().status_code, 201)
        self.assertEqual(
            self.client.post(f"/api/journal/campaigns/{self.campaign.id}/activate/?account=DU-JOURNAL").status_code,
            200,
        )
        buy = self.create_fill("buy", "BUY", "1", "0", 0)
        sell = self.create_fill("sell", "SELL", "-1", "10", 1)

        grouped = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [buy.id, sell.id], "planned_risk_r": 1},
            format="json",
        )
        self.assertEqual(grouped.status_code, 200)
        self.assertEqual(grouped.data["attempts"][0]["status"], "closed")
        attempt_id = grouped.data["attempts"][0]["id"]

        undone = self.client.post(f"/api/journal/campaigns/{self.campaign.id}/undo-grouping/?account=DU-JOURNAL")
        self.assertEqual(undone.status_code, 200)
        self.assertEqual(undone.data["attempts"][0]["fills"], [])
        regrouped = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [buy.id, sell.id], "attempt_id": attempt_id},
            format="json",
        )
        self.assertEqual(regrouped.data["attempts"][0]["status"], "closed")

        closed = self.client.post(f"/api/journal/campaigns/{self.campaign.id}/close/?account=DU-JOURNAL")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.data["status"], "review_pending")
        scenario_id = closed.data["decision_snapshot"]["scenarios"][0]["id"]

        reviewed = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/review/?account=DU-JOURNAL",
            {
                "exit_reason": "target",
                "actual_scenario": scenario_id,
                "entry_followed": "yes",
                "management_followed": "partly",
                "exit_followed": "yes",
                "decision_grade": "A",
                "execution_grade": "B",
                "outcome_drivers": ["process", "variance"],
                "hindsight_known_then": "The trigger and invalidation were observable.",
                "hindsight_luck": "Follow-through magnitude was uncertain.",
                "hindsight_process": "Keep the same entry rule.",
                "would_repeat": True,
                "lesson": "When breadth confirms, keep the original risk boundary.",
            },
            format="json",
        )
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.data["status"], "reviewed")
        self.assertEqual(reviewed.data["review"]["decision_grade"], "A")

    def test_csv_import_is_idempotent(self):
        content = (
            "execution_id,symbol,side,quantity,price,commission,realized_pnl,executed_at,sec_type\n"
            "csv-1,MESU6,BUY,1,5000,0.5,0,2026-08-06T14:30:00Z,FUT\n"
        ).encode()
        first = self.client.post(
            "/api/journal/fills/import/?account=DU-JOURNAL",
            {"file": SimpleUploadedFile("fills.csv", content, content_type="text/csv")},
        )
        second = self.client.post(
            "/api/journal/fills/import/?account=DU-JOURNAL",
            {"file": SimpleUploadedFile("fills.csv", content, content_type="text/csv")},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data, {"imported": 1, "duplicates": 0})
        self.assertEqual(second.data, {"imported": 0, "duplicates": 1})
        self.assertEqual(TradeFill.objects.filter(raw_execution__broker_account=self.account).count(), 1)

    def test_context_kind_enforces_trading_day_boundary(self):
        intraday = self.client.post(
            "/api/journal/contexts/?account=DU-JOURNAL",
            {"name": "Opening", "context_kind": "intraday", "context_type": "opening"},
            format="json",
        )
        swing_with_day = self.client.post(
            "/api/journal/contexts/?account=DU-JOURNAL",
            {"name": "MCL lifecycle", "context_kind": "swing", "context_type": "idea_validation", "trading_day": self.day.id},
            format="json",
        )
        self.assertEqual(intraday.status_code, 400)
        self.assertEqual(swing_with_day.status_code, 400)

    def test_swing_campaign_supports_position_stage_decision_updates(self):
        context = self.client.post(
            "/api/journal/contexts/?account=DU-JOURNAL",
            {"name": "MCL lifecycle", "context_kind": "swing", "context_type": "idea_validation", "risk_limit_r": "2"},
            format="json",
        )
        self.assertEqual(context.status_code, 201)
        self.assertIsNone(context.data["trading_day"])

        campaign = self.client.post(
            "/api/journal/campaigns/?account=DU-JOURNAL",
            {
                "context": context.data["id"], "symbol": "MCL", "direction": "long", "setup": "Weekly trend",
                "horizon": "swing", "planned_risk_amount": "200", "max_risk_r": "1", "max_attempts": 3,
            },
            format="json",
        )
        self.assertEqual(campaign.status_code, 201)
        snapshot = self.client.post(
            f"/api/journal/campaigns/{campaign.data['id']}/decision-versions/?account=DU-JOURNAL",
            self.snapshot_payload(),
            format="json",
        )
        self.assertEqual(snapshot.status_code, 201)
        activated = self.client.post(f"/api/journal/campaigns/{campaign.data['id']}/activate/?account=DU-JOURNAL")
        self.assertEqual(activated.status_code, 200)
        entry = self.create_fill("mcl-entry", "BUY", "1", "0", 2, symbol="MCL")
        grouped = self.client.post(
            f"/api/journal/campaigns/{campaign.data['id']}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [entry.id], "planned_risk_r": 1},
            format="json",
        )
        self.assertEqual(grouped.status_code, 200)
        self.assertTrue(grouped.data["lifecycle"]["decision_locked"])

        updated = self.client.post(
            f"/api/journal/campaigns/{campaign.data['id']}/decision-updates/?account=DU-JOURNAL",
            {
                "position_stage": "holding", "event_type": "economic_data", "event_at": "2026-08-07T14:30:00Z",
                "observed_evidence": ["Inventory data did not break support"],
                "interpretation": "The weekly thesis remains intact.", "decision": "Hold the current size.",
                "risk_change": "No change", "invalidation_update": "Daily close below support",
            },
            format="json",
        )
        self.assertEqual(updated.status_code, 201)
        self.assertEqual(updated.data["context_type"], "holding")
        self.assertEqual(updated.data["decision_updates"][0]["decision"], "Hold the current size.")

    def test_safe_deletion_pause_resume_and_close_guard(self):
        dirty = Campaign.objects.create(
            account=self.account, context=self.context, symbol="MCL", direction="long", setup="Mistake",
            horizon="intraday", planned_risk_amount="100", max_risk_r="1", max_attempts=2,
        )
        deleted = self.client.delete(f"/api/journal/campaigns/{dirty.id}/?account=DU-JOURNAL")
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(Campaign.objects.filter(pk=dirty.id).exists())

        self.assertEqual(self.create_version().status_code, 201)
        self.assertEqual(self.client.post(f"/api/journal/campaigns/{self.campaign.id}/activate/?account=DU-JOURNAL").status_code, 200)
        paused = self.client.post(f"/api/journal/campaigns/{self.campaign.id}/pause/?account=DU-JOURNAL")
        self.assertEqual(paused.data["status"], "paused")
        resumed = self.client.post(f"/api/journal/campaigns/{self.campaign.id}/resume/?account=DU-JOURNAL")
        self.assertEqual(resumed.data["status"], "active")

        buy = self.create_fill("guard-buy", "BUY", "1", "0", 3)
        grouped = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [buy.id]}, format="json",
        )
        self.assertEqual(grouped.status_code, 200)
        self.assertTrue(grouped.data["lifecycle"]["has_open_position"])
        self.assertFalse(grouped.data["lifecycle"]["can_close"])
        empty_attempt = Attempt.objects.create(campaign=self.campaign, sequence_no=2)
        removed_attempt = self.client.delete(f"/api/journal/attempts/{empty_attempt.id}/?account=DU-JOURNAL")
        self.assertEqual(removed_attempt.status_code, 200)
        self.assertFalse(Attempt.objects.filter(pk=empty_attempt.id).exists())
        self.assertEqual(self.client.delete(f"/api/journal/campaigns/{self.campaign.id}/?account=DU-JOURNAL").status_code, 400)
        blocked_close = self.client.post(f"/api/journal/campaigns/{self.campaign.id}/close/?account=DU-JOURNAL")
        self.assertEqual(blocked_close.status_code, 400)

        sell = self.create_fill("guard-sell", "SELL", "-1", "5", 4)
        closed_attempt = self.client.post(
            f"/api/journal/campaigns/{self.campaign.id}/attach-fills/?account=DU-JOURNAL",
            {"fill_ids": [sell.id], "attempt_id": grouped.data["attempts"][0]["id"]}, format="json",
        )
        self.assertFalse(closed_attempt.data["lifecycle"]["has_open_position"])
        self.assertTrue(closed_attempt.data["lifecycle"]["can_close"])
