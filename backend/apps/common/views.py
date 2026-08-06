from django.db.models import Max
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone

from apps.brokers.ibkr_client import IBKRClient

from .models import BrokerAccount, DashboardTab
from .serializers import BrokerAccountSerializer, DashboardTabSerializer

DEFAULT_WIDGETS = [
    "overviewCards",
    "performanceCards",
    "dailyPnl",
    "winsLosses",
    "cumulativePnl",
    "symbolPnl",
    "miniAnalytics",
    "detailTabs",
]
DEFAULT_PANEL_ORDER = [
    "dailyPnl",
    "winsLosses",
    "cumulativePnl",
    "symbolPnl",
    "miniAnalytics",
]


class BrokerAccountViewSet(viewsets.ModelViewSet):
    serializer_class = BrokerAccountSerializer
    queryset = BrokerAccount.objects.all().order_by("broker", "account_code")

    @action(detail=True, methods=["post"], url_path="test-connection")
    def test_connection(self, request, pk=None):
        account = self.get_object()
        if not account.token_configured or not account.flex_query_id:
            return Response(
                {"error": "Configure the Flex Token and Query ID first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            client = IBKRClient(
                flex_token=account.get_flex_token(),
                flex_query_id=account.flex_query_id,
                account_code=account.account_code,
            )
            xml_text = client.fetch_flex_statement_xml()
            reported_accounts = client.extract_account_codes(xml_text)
            unexpected_accounts = sorted(set(reported_accounts) - {account.account_code})
            if account.account_code not in reported_accounts:
                raise ValueError(
                    f"Flex Query did not return configured account {account.account_code}. "
                    f"Reported accounts: {', '.join(reported_accounts) or 'none'}."
                )
            if unexpected_accounts:
                raise ValueError(
                    f"Flex Query also returned other accounts: {', '.join(unexpected_accounts)}. "
                    "Use an account-specific Flex Query."
                )
        except Exception as exc:
            account.connection_status = "error"
            account.last_sync_error = str(exc)
            account.save(update_fields=["connection_status", "last_sync_error", "updated_at"])
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        account.connection_status = "connected"
        account.last_validated_at = timezone.now()
        account.last_sync_error = ""
        account.save(update_fields=[
            "connection_status", "last_validated_at", "last_sync_error", "updated_at",
        ])
        return Response({
            "status": "connected",
            "account": account.account_code,
            "reported_accounts": reported_accounts,
        })

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


def ensure_default_tab():
    first = DashboardTab.objects.order_by("sort_order", "id").first()
    if first:
        return first
    return DashboardTab.objects.create(
        name="Overview",
        sort_order=0,
        visible_widgets=DEFAULT_WIDGETS,
        filters={"date_from": "", "date_to": "", "account": "", "symbol": "", "strategy": "", "asset_class": ""},
        panel_order=DEFAULT_PANEL_ORDER,
    )


class DashboardTabViewSet(viewsets.ModelViewSet):
    serializer_class = DashboardTabSerializer
    queryset = DashboardTab.objects.all().order_by("sort_order", "id")

    def get_queryset(self):
        ensure_default_tab()
        return super().get_queryset()

    def perform_create(self, serializer):
        max_order = DashboardTab.objects.aggregate(value=Max("sort_order")).get("value") or 0
        serializer.save(sort_order=max_order + 1)
