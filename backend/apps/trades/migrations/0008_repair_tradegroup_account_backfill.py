from django.db import migrations


def repair_trade_group_accounts(apps, schema_editor):
    BrokerAccount = apps.get_model("common", "BrokerAccount")
    RawExecution = apps.get_model("trades", "RawIBKRExecution")
    TradeGroup = apps.get_model("trades", "TradeGroup")

    account_map = {}
    for code in (
        RawExecution.objects.exclude(account__isnull=True)
        .exclude(account="")
        .order_by()
        .values_list("account", flat=True)
        .distinct()
    ):
        account, _ = BrokerAccount.objects.get_or_create(
            broker="ibkr",
            account_code=code,
            defaults={"display_name": code, "is_active": True},
        )
        account_map[code] = account

    only_account = next(iter(account_map.values())) if len(account_map) == 1 else None
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
        account = account_map.get(codes[0]) if len(codes) == 1 else only_account if not codes else None
        if account and group.account_id != account.id:
            group.account_id = account.id
            group.save(update_fields=["account"])

    BrokerAccount.objects.filter(
        is_active=False,
        account_code__in=["__legacy_unknown__", "__legacy_ambiguous__"],
        trade_groups__isnull=True,
        daily_reviews__isnull=True,
        pretrade_plans__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("journal", "0015_account_isolation"),
        ("trades", "0007_tradegroup_account"),
    ]

    operations = [
        migrations.RunPython(repair_trade_group_accounts, migrations.RunPython.noop),
    ]
