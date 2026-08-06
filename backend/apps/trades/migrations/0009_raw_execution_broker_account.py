import hashlib

import django.db.models.deletion
from django.db import migrations, models


def bind_raw_executions_to_accounts(apps, schema_editor):
    BrokerAccount = apps.get_model('common', 'BrokerAccount')
    RawExecution = apps.get_model('trades', 'RawIBKRExecution')

    account_ids = {}
    for execution in RawExecution.objects.all().iterator():
        account_code = str(execution.account or '').strip() or '__legacy_unknown__'
        if account_code not in account_ids:
            account, _ = BrokerAccount.objects.get_or_create(
                broker='ibkr',
                account_code=account_code,
                defaults={
                    'display_name': account_code,
                    'is_active': account_code != '__legacy_unknown__',
                },
            )
            account_ids[account_code] = account.id

        update_fields = {'broker_account_id': account_ids[account_code]}
        if execution.execution_id:
            scoped_key = f'ibkr|{account_code}|exec|{execution.execution_id}'
            update_fields['dedupe_key'] = hashlib.sha256(scoped_key.encode()).hexdigest()
        RawExecution.objects.filter(pk=execution.pk).update(**update_fields)


class Migration(migrations.Migration):
    dependencies = [
        ('common', '0004_brokeraccount_connection_status_and_more'),
        ('trades', '0008_repair_tradegroup_account_backfill'),
    ]

    operations = [
        migrations.AddField(
            model_name='rawibkrexecution',
            name='broker_account',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='raw_executions',
                to='common.brokeraccount',
            ),
        ),
        migrations.RunPython(bind_raw_executions_to_accounts, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='rawibkrexecution',
            name='broker_account',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='raw_executions',
                to='common.brokeraccount',
            ),
        ),
    ]
