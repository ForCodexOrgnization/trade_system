from django.contrib import admin

from .models import Attempt, AuditEvent, Campaign, CampaignReview, CorrectionRecord, DecisionContext, DecisionContextReview, DecisionSnapshot, DecisionUpdate, DecisionVersion, Scenario, TradingDay


admin.site.register(TradingDay)
admin.site.register(DecisionContext)
admin.site.register(Campaign)
admin.site.register(DecisionSnapshot)
admin.site.register(DecisionVersion)
admin.site.register(Scenario)
admin.site.register(Attempt)
admin.site.register(CampaignReview)
admin.site.register(DecisionContextReview)
admin.site.register(DecisionUpdate)
admin.site.register(CorrectionRecord)
admin.site.register(AuditEvent)
