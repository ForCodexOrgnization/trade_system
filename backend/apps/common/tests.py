from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import BrokerAccount


class BrokerAccountAPITests(TestCase):
    def test_create_encrypts_token_and_never_returns_it(self):
        response = APIClient().post(
            '/api/common/broker-accounts/',
            {
                'account_code': 'du-test-1',
                'display_name': 'Test Account',
                'flex_query_id': 'query-1',
                'flex_token': 'secret-token-1234',
                'is_active': True,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn('flex_token', response.data)
        self.assertEqual(response.data['account_code'], 'DU-TEST-1')
        self.assertEqual(response.data['token_preview'], '****1234')
        account = BrokerAccount.objects.get(account_code='DU-TEST-1')
        self.assertNotIn('secret-token-1234', account.flex_token_encrypted)
        self.assertEqual(account.get_flex_token(), 'secret-token-1234')

    @patch('apps.common.views.IBKRClient.fetch_flex_statement_xml')
    def test_connection_rejects_query_for_another_account(self, fetch_xml):
        account = BrokerAccount.objects.create(
            account_code='DU-EXPECTED',
            flex_query_id='query-1',
        )
        account.set_flex_token('secret-token')
        account.save()
        fetch_xml.return_value = (
            '<FlexQueryResponse><FlexStatements>'
            '<FlexStatement accountId="DU-OTHER" />'
            '</FlexStatements></FlexQueryResponse>'
        )

        response = APIClient().post(
            f'/api/common/broker-accounts/{account.id}/test-connection/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('did not return configured account', response.data['error'])
        account.refresh_from_db()
        self.assertEqual(account.connection_status, 'error')
