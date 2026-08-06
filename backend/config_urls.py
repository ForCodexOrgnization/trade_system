from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/trades/', include('apps.trades.urls')),
    path('api/common/', include('apps.common.urls')),
    path('api/journal/', include('apps.journal.urls')),
    path('api/syncs/', include('apps.syncs.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
