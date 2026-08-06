from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("common", "0002_strategyoption"),
    ]

    operations = [
        migrations.CreateModel(
            name="BrokerAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("broker", models.CharField(default="ibkr", max_length=20)),
                ("account_code", models.CharField(max_length=64)),
                ("display_name", models.CharField(blank=True, default="", max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["broker", "account_code"]},
        ),
        migrations.AddConstraint(
            model_name="brokeraccount",
            constraint=models.UniqueConstraint(
                fields=("broker", "account_code"),
                name="unique_broker_account_code",
            ),
        ),
    ]
