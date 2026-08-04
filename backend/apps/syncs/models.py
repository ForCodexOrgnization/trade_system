from django.db import models


class SyncJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('partial', 'Partial'),
        ('failed', 'Failed'),
    ]

    source = models.CharField(max_length=50, default='ibkr')
    broker_account = models.ForeignKey(
        'common.BrokerAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sync_jobs',
    )
    job_type = models.CharField(max_length=50, default='full_sync')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    raw_count = models.IntegerField(default=0)
    inserted_count = models.IntegerField(default=0)
    duplicate_count = models.IntegerField(default=0)
    error_count = models.IntegerField(default=0)
    cursor = models.CharField(max_length=255, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"SyncJob #{self.id} ({self.status})"
