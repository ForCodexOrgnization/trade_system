from django.contrib import admin

from .models import Attempt, AuditEvent, Campaign, CampaignReview, DecisionContext, DecisionContextReview, DecisionSnapshot, DecisionUpdate, Scenario, TradingDay


admin.site.register(TradingDay)
admin.site.register(DecisionContext)
admin.site.register(Campaign)
admin.site.register(DecisionSnapshot)
admin.site.register(Scenario)
admin.site.register(Attempt)
admin.site.register(CampaignReview)
admin.site.register(DecisionContextReview)
admin.site.register(DecisionUpdate)
admin.site.register(AuditEvent)
