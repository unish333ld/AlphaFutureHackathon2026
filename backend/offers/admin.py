from django.contrib import admin

from common.admin import HistoryAdmin
from offers.models import Offer

admin.site.register(Offer, HistoryAdmin)
