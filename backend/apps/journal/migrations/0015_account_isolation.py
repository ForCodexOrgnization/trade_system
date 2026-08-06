from django.db import migrations, models
import django.db.models.deletion


LEGACY_UNKNOWN = "__legacy_unknown__"


def backfill_journal_accounts(apps, schema_editor):
    BrokerAccount = apps.get_model("common", "BrokerAccount")
    DailyReview = apps.get_model("journal", "DailyReview")
    PreTradePlan = apps.get_model("journal", "PreTradePlan")

    active_accounts = list(BrokerAccount.objects.filter(is_active=True)[:2])
    only_account = active_accounts[0] if len(active_accounts) == 1 else None
    unknown = None

    def fallback_account():
        nonlocal unknown
        if only_account:
            return only_account
        if unknown is None:
            unknown, _ = BrokerAccount.objects.get_or_create(
                broker="ibkr",
                account_code=LEGACY_UNKNOWN,
                defaults={"display_name": "Legacy unknown account", "is_active": False},
            )
        return unknown

    for review in DailyReview.objects.all().iterator():
        account_ids = set(review.related_trade_groups.values_list("account_id", flat=True))
        if review.related_trade_group_id:
            account_ids.add(review.related_trade_group.account_id)
        account_ids.discard(None)
        review.account_id = next(iter(account_ids)) if len(account_ids) == 1 else fallback_account().id
        review.save(update_fields=["account"])

    for plan in PreTradePlan.objects.all().iterator():
        account_ids = set(
            plan.setup_snapshots.exclude(trade_group_id__isnull=True)
            .values_list("trade_group__account_id", flat=True)
        )
        account_ids.discard(None)
        plan.account_id = next(iter(account_ids)) if len(account_ids) == 1 else fallback_account().id
        plan.save(update_fields=["account"])


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0003_brokeraccount"),
        ("trades", "0007_tradegroup_account"),
        ("journal", "0014_setupsnapshot_planned_risk_r"),
    ]

    operations = [
        migrations.AddField(
            model_name="dailyreview",
            name="account",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="daily_reviews",
                to="common.brokeraccount",
            ),
        ),
        migrations.AddField(
            model_name="pretradeplan",
            name="account",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pretrade_plans",
                to="common.brokeraccount",
            ),
        ),
        migrations.RunPython(backfill_journal_accounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="dailyreview",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="daily_reviews",
                to="common.brokeraccount",
            ),
        ),
        migrations.AlterField(
            model_name="pretradeplan",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pretrade_plans",
                to="common.brokeraccount",
            ),
        ),
        migrations.AddConstraint(
            model_name="pretradeplan",
            constraint=models.UniqueConstraint(
                fields=("account", "plan_date"),
                name="unique_pretrade_plan_per_account_date",
            ),
        ),
    ]
