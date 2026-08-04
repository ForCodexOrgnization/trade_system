from rest_framework import serializers
from .models import SyncJob


class SyncJobSerializer(serializers.ModelSerializer):
    broker_account_code = serializers.CharField(source='broker_account.account_code', read_only=True)

    class Meta:
        model = SyncJob
        fields = [
            'id', 'source', 'broker_account', 'broker_account_code', 'job_type', 'status',
            'started_at', 'finished_at', 'raw_count', 'inserted_count', 'duplicate_count',
            'error_count', 'cursor', 'error_message', 'metadata', 'created_at', 'updated_at',
        ]
