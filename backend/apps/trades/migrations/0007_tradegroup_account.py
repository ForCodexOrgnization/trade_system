from django.db import migrations, models
import django.db.models.deletion


LEGACY_UNKNOWN = "__legacy_unknown__"
LEGACY_AMBIGUOUS = "__legacy_ambiguous__"


def backfill_trade_group_accounts(apps, schema_editor):
    BrokerAccount = apps.get_model("common", "BrokerAccount")
    RawExecution = apps.get_model("trades", "RawIBKRExecution")
    TradeGroup = apps.get_model("trades", "TradeGroup")

    account_map = {}
    for code in RawExecution.objects.exclude(account__isnull=True).exclude(account="").values_list("account", flat=True).distinct():
        account, _ = BrokerAccount.objects.get_or_create(
            broker="ibkr",
            account_code=code,
            defaults={"display_name": code, "is_active": True},
        )
        account_map[code] = account

    only_account = next(iter(account_map.values())) if len(account_map) == 1 else None
    unknown = None
    ambiguous = None

    for group in TradeGroup.objects.all().iterator():
        qs = RawExecution.objects.all()
        if group.symbol.startswith("SPREAD(") and group.symbol.endswith(")"):
            symbols = [value.strip() for value in group.symbol[7:-1].split(",") if value.strip()]
            qs = qs.filter(symbol__in=symbols)
        else:
            qs = qs.filter(symbol=group.symbol)
        if group.opened_at:
            qs = qs.filter(executed_at__gte=group.opened_at)
        if group.closed_at:
            qs = qs.filter(executed_at__lte=group.closed_at)

        codes = list(
            qs.exclude(account__isnull=True)
            .exclude(account="")
            .order_by()
            .values_list("account", flat=True)
            .distinct()[:2]
        )
        if len(codes) == 1:
            account = account_map.get(codes[0])
        elif not codes and only_account:
            account = only_account
        elif len(codes) > 1:
            if ambiguous is None:
                ambiguous, _ = BrokerAccount.objects.get_or_create(
                    broker="ibkr",
                    account_code=LEGACY_AMBIGUOUS,
                    defaults={"display_name": "Legacy ambiguous account", "is_active": False},
                )
            account = ambiguous
        else:
            if unknown is None:
                unknown, _ = BrokerAccount.objects.get_or_create(
                    broker="ibkr",
                    account_code=LEGACY_UNKNOWN,
                    defaults={"display_name": "Legacy unknown account", "is_active": False},
                )
            account = unknown

        group.account_id = account.id
        group.save(update_fields=["account"])


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0003_brokeraccount"),
        ("trades", "0006_rebuild_trade_groups_without_order_reference_combo"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradegroup",
            name="account",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trade_groups",
                to="common.brokeraccount",
            ),
        ),
        migrations.RunPython(backfill_trade_group_accounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="tradegroup",
            name="account",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="trade_groups",
                to="common.brokeraccount",
            ),
        ),
    ]
