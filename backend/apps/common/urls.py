from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrokerAccountViewSet, DashboardPreferenceAPIView, DashboardTabViewSet, StrategyOptionViewSet

router = DefaultRouter()
router.register("dashboard-tabs", DashboardTabViewSet, basename="dashboard-tab")
router.register("strategy-options", StrategyOptionViewSet, basename="strategy-option")
router.register("broker-accounts", BrokerAccountViewSet, basename="broker-account")

urlpatterns = router.urls + [
    path("dashboard-preferences/", DashboardPreferenceAPIView.as_view(), name="dashboard-preferences"),
]
