from django.urls import path
from .views import IBKRConfigDebugAPIView, StartIBKRAccountSyncAPIView, StartIBKRSyncAPIView, StartLocalIBKRSyncAPIView, SyncJobListAPIView

urlpatterns = [
    path('ibkr/start/', StartIBKRSyncAPIView.as_view(), name='ibkr-sync-start'),
    path('ibkr/start-local/', StartLocalIBKRSyncAPIView.as_view(), name='ibkr-sync-start-local'),
    path('ibkr/accounts/<int:account_id>/start/', StartIBKRAccountSyncAPIView.as_view(), name='ibkr-account-sync-start'),
    path('jobs/', SyncJobListAPIView.as_view(), name='sync-job-list'),
    path('ibkr/config-debug/', IBKRConfigDebugAPIView.as_view(), name='ibkr-config-debug'),
]
