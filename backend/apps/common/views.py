from django.core.management import call_command
from django.db.models import Max
from django.db.utils import OperationalError, ProgrammingError
from rest_framework.exceptions import APIException
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BrokerAccount, DashboardPreference, DashboardTab, StrategyOption
from .serializers import BrokerAccountSerializer, DashboardPreferenceSerializer, DashboardTabSerializer, StrategyOptionSerializer

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


class ServiceUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service unavailable."
    default_code = "service_unavailable"


class BrokerAccountViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = BrokerAccountSerializer
    queryset = BrokerAccount.objects.filter(is_active=True).order_by("broker", "account_code")


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


class DashboardPreferenceAPIView(APIView):
    def get(self, request):
        default_tab = ensure_default_tab()
        pref = DashboardPreference.get_solo()
        if pref.default_dashboard_tab is None:
            pref.default_dashboard_tab = default_tab
            pref.save(update_fields=["default_dashboard_tab", "updated_at"])
        serializer = DashboardPreferenceSerializer(pref)
        return Response(serializer.data)

    def put(self, request):
        pref = DashboardPreference.get_solo()
        serializer = DashboardPreferenceSerializer(pref, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    patch = put


class StrategyOptionViewSet(viewsets.ModelViewSet):
    serializer_class = StrategyOptionSerializer
    queryset = StrategyOption.objects.all().order_by("sort_order", "name", "id")

    def _ensure_strategy_option_table(self):
        try:
            StrategyOption.objects.exists()
            return True
        except (ProgrammingError, OperationalError) as exc:
            if "common_strategyoption" not in str(exc):
                return False
            try:
                call_command("migrate", "common", interactive=False, verbosity=0)
                StrategyOption.objects.exists()
                return True
            except Exception:
                return False

    def initial(self, request, *args, **kwargs):
        if not self._ensure_strategy_option_table():
            raise ServiceUnavailable(
                "StrategyOption table is unavailable and auto-migration failed. "
                "Please run `python manage.py migrate`."
            )
        return super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, (ProgrammingError, OperationalError)):
            return Response(
                {
                    "detail": (
                        "StrategyOption table is unavailable. "
                        "Please run database migrations (python manage.py migrate)."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return super().handle_exception(exc)
