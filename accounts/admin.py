from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "is_online", "last_seen", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Presence", {"fields": ("active_connections", "last_seen")}),
    )

    @admin.display(boolean=True)
    def is_online(self, obj):
        return obj.is_online
