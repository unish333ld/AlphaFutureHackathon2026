from django.contrib import admin

from companies.models import Company, CompanyMember


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "inn", "kind", "status", "demo_scenario")
    search_fields = ("name", "inn")
    list_filter = ("status", "kind")


@admin.register(CompanyMember)
class CompanyMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "can_submit", "can_sign", "active")
    autocomplete_fields = ("user", "company")
    list_select_related = ("user", "company")
