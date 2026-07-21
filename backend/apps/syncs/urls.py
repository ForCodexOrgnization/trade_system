from django.urls import path
from .views import DeleteIBKRAccountDataAPIView, IBKRConfigDebugAPIView, StartIBKRSyncAPIView, StartLocalIBKRSyncAPIView, SyncJobListAPIView

urlpatterns = [
    path('ibkr/start/', StartIBKRSyncAPIView.as_view(), name='ibkr-sync-start'),
    path('ibkr/start-local/', StartLocalIBKRSyncAPIView.as_view(), name='ibkr-sync-start-local'),
    path('ibkr/account-data/', DeleteIBKRAccountDataAPIView.as_view(), name='ibkr-account-data'),
    path('jobs/', SyncJobListAPIView.as_view(), name='sync-job-list'),
    path('ibkr/config-debug/', IBKRConfigDebugAPIView.as_view(), name='ibkr-config-debug'),
]
