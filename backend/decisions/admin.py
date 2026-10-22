from django.contrib import admin

from common.admin import HistoryAdmin
from decisions.models import Assessment, CreditDecision

admin.site.register([Assessment, CreditDecision], HistoryAdmin)
