from django.contrib import admin

from agreements.models import Agreement, Disbursement
from common.admin import HistoryAdmin

admin.site.register([Agreement, Disbursement], HistoryAdmin)
