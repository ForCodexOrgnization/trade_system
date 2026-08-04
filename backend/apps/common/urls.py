from rest_framework.routers import DefaultRouter

from .views import BrokerAccountViewSet, DashboardTabViewSet, StrategyOptionViewSet

router = DefaultRouter()
router.register("dashboard-tabs", DashboardTabViewSet, basename="dashboard-tab")
router.register("strategy-options", StrategyOptionViewSet, basename="strategy-option")
router.register("broker-accounts", BrokerAccountViewSet, basename="broker-account")

urlpatterns = router.urls
