from rest_framework import serializers
from .models import BrokerAccount, DashboardPreference, DashboardTab, StrategyOption


class BrokerAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrokerAccount
        fields = [
            "id",
            "broker",
            "account_code",
            "display_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "broker", "account_code", "created_at", "updated_at"]


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


class DashboardPreferenceSerializer(serializers.ModelSerializer):
    default_dashboard_tab_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = DashboardPreference
        fields = [
            "id",
            "default_dashboard_tab",
            "default_dashboard_tab_name",
            "default_date_range",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "default_dashboard_tab_name"]

    def get_default_dashboard_tab_name(self, obj):
        return obj.default_dashboard_tab.name if obj.default_dashboard_tab else None


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
