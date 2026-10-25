from django.contrib import admin

from applications.models import (
    Application,
    ApplicationEvent,
    ApplicationRevision,
    InformationRequest,
)
from common.admin import HistoryAdmin


@admin.register(Application)
class ApplicationAdmin(HistoryAdmin):
    list_display = (
        "number",
        "company",
        "product",
        "status",
        "assigned_to",
        "lock_version",
        "created_at",
    )
    list_filter = ("status",)
    list_select_related = ("company", "product", "assigned_to")


admin.site.register([ApplicationRevision, ApplicationEvent, InformationRequest], HistoryAdmin)
