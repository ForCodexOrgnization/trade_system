from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.generics import ListAPIView

from apps.brokers.ibkr_client import IBKRClient
from apps.brokers.services import IBKRSyncService
from apps.common.models import BrokerAccount
from apps.trades.models import RawIBKRExecution
from apps.trades.services import rebuild_all_trade_groups
from .models import SyncJob
from .serializers import SyncJobSerializer


def _run_ibkr_sync(*, use_local_flex_xml: bool, job_type: str):
    client = IBKRClient(use_local_flex_xml=use_local_flex_xml)
    if use_local_flex_xml and not client.has_flex_statement_cache:
        cache_path = client.flex_statement_cache_path
        return Response(
            {
                'error': (
                    f'Local IBKR Flex XML cache not found at {cache_path}. '
                    'Run a real IBKR sync once before using local sync.'
                ),
                'code': 'local_flex_xml_cache_missing',
                'cache_path': str(cache_path),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if SyncJob.objects.filter(source='ibkr', status='running').exists():
        return Response(
            {'error': 'A sync job is already running. Please wait for it to finish.'},
            status=status.HTTP_409_CONFLICT,
        )

    job = SyncJob.objects.create(
        source='ibkr',
        job_type=job_type,
        status='running',
        started_at=timezone.now(),
    )
    try:
        service = IBKRSyncService(client=client)
        result = service.run_full_sync(job)
        job.finished_at = timezone.now()
        if job.status == 'running':
            job.status = 'success'
        job.save(update_fields=['finished_at', 'status', 'updated_at'])
        return Response({'job_id': job.id, 'result': result})
    except FileNotFoundError as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response({'error': str(exc), 'code': 'local_flex_xml_cache_missing'}, status=status.HTTP_400_BAD_REQUEST)
    except RuntimeError as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at', 'updated_at'])
        return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StartIBKRSyncAPIView(APIView):
    def post(self, request):
        use_local_flex_xml = request.data.get('use_local_flex_xml') is True
        return _run_ibkr_sync(
            use_local_flex_xml=use_local_flex_xml,
            job_type='local_full_sync' if use_local_flex_xml else 'full_sync',
        )


class StartLocalIBKRSyncAPIView(APIView):
    def post(self, request):
        return _run_ibkr_sync(use_local_flex_xml=True, job_type='local_full_sync')


class DeleteIBKRAccountDataAPIView(APIView):
    """Remove every locally imported execution for one IBKR account."""

    def delete(self, request):
        account = str(request.data.get('account') or '').strip()
        if not account:
            return Response({'error': 'An account is required.'}, status=status.HTTP_400_BAD_REQUEST)

        executions = RawIBKRExecution.objects.filter(account=account)
        deleted_execution_count = executions.count()
        executions.delete()
        # Raw executions cascade to fills. Rebuild groups from the accounts that remain
        # so deleted-account positions and PnL cannot remain visible in the dashboard.
        rebuild_all_trade_groups()
        BrokerAccount.objects.filter(
            broker='ibkr',
            account_code=account,
        ).update(is_active=False)
        return Response({'account': account, 'deleted_execution_count': deleted_execution_count})


class SyncJobListAPIView(ListAPIView):
    queryset = SyncJob.objects.all()
    serializer_class = SyncJobSerializer


class IBKRConfigDebugAPIView(APIView):
    def get(self, request):
        token = settings.IBKR_FLEX_TOKEN or ""
        query_id = settings.IBKR_FLEX_QUERY_ID or ""
        client = IBKRClient(use_local_flex_xml=True)
        cache_path = client.flex_statement_cache_path
        return Response({
            "token_exists": bool(token),
            "query_id_exists": bool(query_id),
            "token_preview": f"{token[:6]}...{token[-4:]}" if len(token) >= 10 else "",
            "query_id": query_id,
            "history_years": settings.IBKR_FLEX_HISTORY_YEARS,
            "send_request_url": settings.IBKR_FLEX_SEND_REQUEST_URL,
            "local_flex_xml_cache_exists": client.has_flex_statement_cache,
            "local_flex_xml_cache_path": str(cache_path),
        })
