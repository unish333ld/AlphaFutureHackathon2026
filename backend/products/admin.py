from django.contrib import admin

from products.models import CreditProduct


@admin.register(CreditProduct)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "min_amount", "max_amount", "annual_rate", "active")
    search_fields = ("code", "name")
