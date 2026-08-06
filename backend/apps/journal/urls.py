from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AttemptViewSet, CampaignViewSet, DecisionContextViewSet, JournalAnalyticsAPIView, JournalFillImportAPIView, TradingDayViewSet


router = DefaultRouter()
router.register("trading-days", TradingDayViewSet, basename="journal-trading-day")
router.register("contexts", DecisionContextViewSet, basename="journal-context")
router.register("campaigns", CampaignViewSet, basename="journal-campaign")
router.register("attempts", AttemptViewSet, basename="journal-attempt")

urlpatterns = router.urls + [
    path("fills/import/", JournalFillImportAPIView.as_view(), name="journal-fill-import"),
    path("analytics/", JournalAnalyticsAPIView.as_view(), name="journal-analytics"),
]
