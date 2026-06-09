from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from .views import StartIBKRSyncAPIView


class StartIBKRSyncAPIViewTests(SimpleTestCase):
    def test_default_start_uses_real_ibkr_sync(self):
        request = APIRequestFactory().post('/api/syncs/ibkr/start/', {}, format='json')

        with patch('apps.syncs.views._run_ibkr_sync', return_value=Response({})) as run_sync:
            StartIBKRSyncAPIView.as_view()(request)

        run_sync.assert_called_once_with(use_local_flex_xml=False, job_type='full_sync')

    def test_start_can_request_local_flex_xml_mode(self):
        request = APIRequestFactory().post(
            '/api/syncs/ibkr/start/',
            {'use_local_flex_xml': True},
            format='json',
        )

        with patch('apps.syncs.views._run_ibkr_sync', return_value=Response({})) as run_sync:
            StartIBKRSyncAPIView.as_view()(request)

        run_sync.assert_called_once_with(use_local_flex_xml=True, job_type='local_full_sync')
