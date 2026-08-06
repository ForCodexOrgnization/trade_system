from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("journal", "0015_account_isolation"),
        ("trades", "0009_raw_execution_broker_account"),
    ]

    operations = [
        migrations.DeleteModel(name="SetupSnapshot"),
        migrations.DeleteModel(name="PositionCheckpoint"),
        migrations.DeleteModel(name="TradeReview"),
        migrations.DeleteModel(name="TradeJournal"),
        migrations.DeleteModel(name="DailyReviewImage"),
        migrations.DeleteModel(name="DailyReview"),
        migrations.DeleteModel(name="PreTradePlan"),
        migrations.DeleteModel(name="MistakeTag"),
        migrations.DeleteModel(name="SetupTag"),
    ]
