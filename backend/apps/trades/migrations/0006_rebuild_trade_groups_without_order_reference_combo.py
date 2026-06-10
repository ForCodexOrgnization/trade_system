from django.db import migrations


def rebuild_trade_groups(apps, schema_editor):
    from apps.trades.services import rebuild_all_trade_groups

    rebuild_all_trade_groups()


class Migration(migrations.Migration):

    dependencies = [
        ('trades', '0005_tradegroup_soft_delete_fields'),
    ]

    operations = [
        migrations.RunPython(rebuild_trade_groups, migrations.RunPython.noop),
    ]
