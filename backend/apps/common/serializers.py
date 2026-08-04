from rest_framework import serializers
from .models import BrokerAccount, DashboardTab, StrategyOption


class BrokerAccountSerializer(serializers.ModelSerializer):
    flex_token = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=True)
    token_configured = serializers.BooleanField(read_only=True)
    token_preview = serializers.SerializerMethodField(read_only=True)
    local_cache_exists = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = BrokerAccount
        fields = [
            "id",
            "broker",
            "account_code",
            "display_name",
            "flex_token",
            "flex_query_id",
            "token_configured",
            "token_preview",
            "local_cache_exists",
            "connection_status",
            "last_validated_at",
            "last_sync_at",
            "last_sync_error",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "broker",
            "connection_status",
            "last_validated_at",
            "last_sync_at",
            "last_sync_error",
            "created_at",
            "updated_at",
        ]

    def validate_account_code(self, value):
        normalized = str(value or "").strip().upper()
        if not normalized:
            raise serializers.ValidationError("IBKR account code is required.")
        if self.instance and normalized != self.instance.account_code:
            raise serializers.ValidationError("The account code cannot be changed after creation.")
        return normalized

    def _save_token(self, instance, token_marker, token):
        if token_marker and token:
            instance.set_flex_token(token)
        if token_marker or "flex_query_id" in self.validated_data:
            instance.connection_status = "unverified" if instance.token_configured and instance.flex_query_id else "unconfigured"
            instance.last_sync_error = ""
        instance.save()
        return instance

    def create(self, validated_data):
        token_marker = "flex_token" in validated_data
        token = validated_data.pop("flex_token", "")
        instance = BrokerAccount(**validated_data)
        return self._save_token(instance, token_marker, token)

    def update(self, instance, validated_data):
        token_marker = "flex_token" in validated_data
        token = validated_data.pop("flex_token", "")
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return self._save_token(instance, token_marker, token)

    def get_token_preview(self, obj):
        return obj.token_preview()

    def get_local_cache_exists(self, obj):
        from apps.brokers.ibkr_client import IBKRClient

        return IBKRClient(account_code=obj.account_code).has_flex_statement_cache


class DashboardTabSerializer(serializers.ModelSerializer):
    class Meta:
        model = DashboardTab
        fields = [
            "id",
            "name",
            "sort_order",
            "visible_widgets",
            "filters",
            "panel_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StrategyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StrategyOption
        fields = [
            "id",
            "name",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
