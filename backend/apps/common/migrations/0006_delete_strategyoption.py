from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0005_delete_dashboardpreference"),
    ]

    operations = [
        migrations.DeleteModel(name="StrategyOption"),
    ]
