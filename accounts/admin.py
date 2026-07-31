from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import CaregiverLink, User


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'unique_id', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'unique_id')
    readonly_fields = ('unique_id',)
    fieldsets = UserAdmin.fieldsets + (
        ('CareNest role', {'fields': ('role', 'unique_id', 'phone_number')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CareNest role', {'fields': ('role', 'phone_number')}),
    )


@admin.register(CaregiverLink)
class CaregiverLinkAdmin(admin.ModelAdmin):
    list_display = ('caregiver', 'patient', 'status', 'requested_at')
    list_filter = ('status',)


admin.site.register(User, CustomUserAdmin)
