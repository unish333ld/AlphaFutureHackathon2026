from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class AccountAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Кредитный кабинет", {"fields": ("system_role",)}),)
    list_display = ("username", "system_role", "is_active", "is_staff")
