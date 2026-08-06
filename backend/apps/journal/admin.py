from django.contrib import admin

from .models import Attempt, AuditEvent, Campaign, CampaignReview, DecisionSnapshot, Scenario, Session, SessionReview, TradingDay


admin.site.register(TradingDay)
admin.site.register(Session)
admin.site.register(Campaign)
admin.site.register(DecisionSnapshot)
admin.site.register(Scenario)
admin.site.register(Attempt)
admin.site.register(CampaignReview)
admin.site.register(SessionReview)
admin.site.register(AuditEvent)
