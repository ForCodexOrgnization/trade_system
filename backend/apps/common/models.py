from django.db import models


class BrokerAccount(models.Model):
    CONNECTION_STATUS_CHOICES = [
        ("unconfigured", "Unconfigured"),
        ("unverified", "Unverified"),
        ("connected", "Connected"),
        ("error", "Error"),
    ]

    broker = models.CharField(max_length=20, default="ibkr")
    account_code = models.CharField(max_length=64)
    display_name = models.CharField(max_length=120, blank=True, default="")
    flex_token_encrypted = models.TextField(blank=True, default="")
    flex_query_id = models.CharField(max_length=64, blank=True, default="")
    connection_status = models.CharField(
        max_length=20,
        choices=CONNECTION_STATUS_CHOICES,
        default="unconfigured",
    )
    last_validated_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_error = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["broker", "account_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["broker", "account_code"],
                name="unique_broker_account_code",
            ),
        ]

    def __str__(self):
        return self.display_name or self.account_code

    @property
    def token_configured(self):
        return bool(self.flex_token_encrypted)

    def set_flex_token(self, token):
        from .credentials import encrypt_credential

        self.flex_token_encrypted = encrypt_credential(str(token or "").strip())

    def get_flex_token(self):
        from .credentials import decrypt_credential

        return decrypt_credential(self.flex_token_encrypted)

    def token_preview(self):
        token = self.get_flex_token()
        if not token:
            return ""
        return f"****{token[-4:]}" if len(token) >= 4 else "****"


class DashboardTab(models.Model):
    name = models.CharField(max_length=80, default="Overview")
    sort_order = models.PositiveIntegerField(default=0)
    visible_widgets = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    panel_order = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.name


class StrategyOption(models.Model):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name", "id"]

    def __str__(self):
        return self.name
