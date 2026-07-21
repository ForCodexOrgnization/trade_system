from datetime import datetime, timezone
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory

from apps.trades.models import RawIBKRExecution
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


class DeleteIBKRAccountDataTests(TestCase):
    def _execution(self, account, execution_id):
        return RawIBKRExecution.objects.create(
            account=account, execution_id=execution_id, symbol='MES', side='BUY',
            quantity='1', price='100', executed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
            dedupe_key=f'{account}-{execution_id}',
        )

    @patch('apps.syncs.views.rebuild_all_trade_groups')
    def test_deleting_an_account_removes_only_its_executions_and_rebuilds_groups(self, rebuild):
        old = self._execution('DU-OLD', 'old-1')
        current = self._execution('DU-NEW', 'new-1')

        response = APIClient().delete('/api/syncs/ibkr/account-data/', {'account': 'DU-OLD'}, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'account': 'DU-OLD', 'deleted_execution_count': 1})
        self.assertFalse(RawIBKRExecution.objects.filter(pk=old.pk).exists())
        self.assertTrue(RawIBKRExecution.objects.filter(pk=current.pk).exists())
        rebuild.assert_called_once_with()

    def test_deleting_without_an_account_is_rejected(self):
        response = APIClient().delete('/api/syncs/ibkr/account-data/', {}, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['error'], 'An account is required.')
