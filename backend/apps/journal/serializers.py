from rest_framework import serializers
from apps.trades.models import TradeGroup
from .models import (
    DailyReview,
    DailyReviewImage,
    MistakeTag,
    PositionCheckpoint,
    PreTradePlan,
    SetupSnapshot,
    SetupTag,
    TradeJournal,
    TradeReview,
)


def _serializer_request_account(serializer):
    view = serializer.context.get('view')
    if view and hasattr(view, 'get_request_account'):
        return view.get_request_account()
    return None


class DailyReviewImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyReviewImage
        fields = ['id', 'image_url', 'sort_order', 'created_at']
        read_only_fields = ['id', 'created_at']


class SetupTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = SetupTag
        fields = '__all__'


class MistakeTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = MistakeTag
        fields = '__all__'


class DailyReviewSerializer(serializers.ModelSerializer):
    related_trade_group_display = serializers.SerializerMethodField(read_only=True)
    related_trade_groups_display = serializers.SerializerMethodField(read_only=True)
    related_trade_group = serializers.PrimaryKeyRelatedField(queryset=TradeGroup.objects.all(), allow_null=True, required=False)
    related_trade_groups = serializers.PrimaryKeyRelatedField(queryset=TradeGroup.objects.all(), many=True, required=False)
    images = DailyReviewImageSerializer(many=True, read_only=True)
    image_urls = serializers.ListField(child=serializers.CharField(max_length=500), write_only=True, required=False, allow_empty=True)

    class Meta:
        model = DailyReview
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        account = _serializer_request_account(self) or attrs.get('account') or getattr(self.instance, 'account', None)
        groups = list(attrs.get('related_trade_groups', []))
        direct_group = attrs.get('related_trade_group')
        if direct_group:
            groups.append(direct_group)
        if account and any(group.account_id != account.id for group in groups):
            raise serializers.ValidationError('All related trades must belong to the review account.')
        return attrs

    def _trade_group_display(self, trade_group):
        return {
            'id': trade_group.id,
            'symbol': trade_group.symbol,
            'trade_date': trade_group.trade_date,
            'status': trade_group.status,
            'direction': trade_group.direction,
            'realized_pnl': trade_group.realized_pnl,
        }

    def get_related_trade_group_display(self, obj):
        if not obj.related_trade_group:
            return None
        return self._trade_group_display(obj.related_trade_group)

    def get_related_trade_groups_display(self, obj):
        return [self._trade_group_display(item) for item in obj.related_trade_groups.all().order_by('opened_at', 'id')]

    def create(self, validated_data):
        image_urls = validated_data.pop('image_urls', [])
        related_trade_groups = validated_data.pop('related_trade_groups', [])
        instance = super().create(validated_data)
        if related_trade_groups:
            instance.related_trade_groups.set(related_trade_groups)
        elif instance.related_trade_group:
            instance.related_trade_groups.set([instance.related_trade_group])
        self._replace_images(instance, image_urls)
        return instance

    def update(self, instance, validated_data):
        image_urls = validated_data.pop('image_urls', None)
        related_trade_groups = validated_data.pop('related_trade_groups', None)
        instance = super().update(instance, validated_data)
        if related_trade_groups is not None:
            instance.related_trade_groups.set(related_trade_groups)
        elif instance.related_trade_group and not instance.related_trade_groups.filter(id=instance.related_trade_group_id).exists():
            instance.related_trade_groups.add(instance.related_trade_group)
        if image_urls is not None:
            self._replace_images(instance, image_urls)
        return instance

    def _replace_images(self, instance, image_urls):
        instance.images.all().delete()
        normalized = [url for url in image_urls if url]
        for idx, url in enumerate(normalized):
            DailyReviewImage.objects.create(daily_review=instance, image_url=url, sort_order=idx)
        instance.image_url = normalized[0] if normalized else ''
        instance.save(update_fields=['image_url'])


class TradeJournalSerializer(serializers.ModelSerializer):
    trade_group_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = TradeJournal
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        account = _serializer_request_account(self)
        trade_group = attrs.get('trade_group') or getattr(self.instance, 'trade_group', None)
        if account and trade_group and trade_group.account_id != account.id:
            raise serializers.ValidationError('The trade belongs to another account.')
        return attrs

    def get_trade_group_display(self, obj):
        group = obj.trade_group
        return {
            'id': group.id,
            'symbol': group.symbol,
            'trade_date': group.trade_date,
            'status': group.status,
            'direction': group.direction,
            'realized_pnl': group.realized_pnl,
        }


class TradeReviewSerializer(serializers.ModelSerializer):
    trade_group_display = serializers.SerializerMethodField(read_only=True)
    setup_display = SetupTagSerializer(source='setup', read_only=True)
    mistake_tags_display = MistakeTagSerializer(source='mistake_tags', many=True, read_only=True)
    selected_snapshot = serializers.PrimaryKeyRelatedField(
        queryset=SetupSnapshot.objects.select_related('pretrade_plan').all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = TradeReview
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        trade_group = attrs.get('trade_group') or getattr(self.instance, 'trade_group', None)
        request_account = _serializer_request_account(self)
        if request_account and trade_group and trade_group.account_id != request_account.id:
            raise serializers.ValidationError('The trade belongs to another account.')
        selected_snapshot = attrs.get('selected_snapshot')
        if not trade_group:
            return attrs
        if not selected_snapshot:
            attrs['resolved_snapshot'] = None
            return attrs
        snapshot_symbol = (selected_snapshot.symbol or '').strip().lower()
        trade_symbol = (trade_group.symbol or '').strip().lower()
        symbol_match = (
            snapshot_symbol == trade_symbol
            or snapshot_symbol.startswith(trade_symbol)
            or trade_symbol.startswith(snapshot_symbol)
        )
        if not symbol_match:
            attrs['resolved_snapshot'] = None
            return attrs
        if selected_snapshot.pretrade_plan.account_id != trade_group.account_id:
            raise serializers.ValidationError('The selected snapshot belongs to another account.')
        attrs['resolved_snapshot'] = selected_snapshot
        return attrs

    def _bind_selected_snapshot(self, instance, resolved_snapshot):
        if not resolved_snapshot:
            return
        previous = getattr(instance.trade_group, 'pretrade_snapshot', None)
        if previous and previous.id != resolved_snapshot.id:
            previous.trade_group = None
            previous.save(update_fields=['trade_group', 'updated_at'])
        if resolved_snapshot.trade_group_id != instance.trade_group_id:
            resolved_snapshot.trade_group = instance.trade_group
            resolved_snapshot.save(update_fields=['trade_group', 'updated_at'])

    def create(self, validated_data):
        resolved_snapshot = validated_data.pop('resolved_snapshot', None) or validated_data.pop('selected_snapshot', None)
        instance = super().create(validated_data)
        self._bind_selected_snapshot(instance, resolved_snapshot)
        return instance

    def update(self, instance, validated_data):
        resolved_snapshot = validated_data.pop('resolved_snapshot', None) or validated_data.pop('selected_snapshot', None)
        instance = super().update(instance, validated_data)
        self._bind_selected_snapshot(instance, resolved_snapshot)
        return instance

    def get_trade_group_display(self, obj):
        group = obj.trade_group
        return {
            'id': group.id,
            'symbol': group.symbol,
            'trade_date': group.trade_date,
            'status': group.status,
            'direction': group.direction,
            'realized_pnl': group.realized_pnl,
        }


class PositionCheckpointSerializer(serializers.ModelSerializer):
    trade_group_display = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = PositionCheckpoint
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        trade_group = attrs.get('trade_group') or getattr(self.instance, 'trade_group', None)
        account = _serializer_request_account(self)
        if account and trade_group and trade_group.account_id != account.id:
            raise serializers.ValidationError('The trade belongs to another account.')
        return attrs

    def get_trade_group_display(self, obj):
        group = obj.trade_group
        return {
            'id': group.id,
            'symbol': group.symbol,
            'trade_date': group.trade_date,
            'status': group.status,
            'direction': group.direction,
            'open_qty': group.open_qty,
        }


class PreTradePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreTradePlan
        fields = '__all__'


class SetupSnapshotSerializer(serializers.ModelSerializer):
    setup_display = SetupTagSerializer(source='setup', read_only=True)

    class Meta:
        model = SetupSnapshot
        fields = '__all__'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        plan = attrs.get('pretrade_plan') or getattr(self.instance, 'pretrade_plan', None)
        trade_group = attrs.get('trade_group') or getattr(self.instance, 'trade_group', None)
        account = _serializer_request_account(self)
        if account and plan and plan.account_id != account.id:
            raise serializers.ValidationError('The pre-trade plan belongs to another account.')
        if plan and trade_group and plan.account_id != trade_group.account_id:
            raise serializers.ValidationError('The snapshot and trade must belong to the same account.')
        return attrs
