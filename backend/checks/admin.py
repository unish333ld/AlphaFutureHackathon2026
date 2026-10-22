from django.contrib import admin

from checks.models import CheckResult
from common.admin import HistoryAdmin

admin.site.register(CheckResult, HistoryAdmin)
