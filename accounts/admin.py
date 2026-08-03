from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import (
    CaregiverInvite, CaregiverLink, Notification, TrustedDevice, User,
)


class CustomUserAdmin(UserAdmin):
    model = User
    list_display = ('username', 'email', 'role', 'unique_id', 'is_staff', 'is_active')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'unique_id')
    readonly_fields = ('unique_id',)
    fieldsets = UserAdmin.fieldsets + (
        ('CareNest role', {'fields': ('role', 'unique_id', 'phone_number')}),
        ('Health profile', {'fields': (
            'date_of_birth', 'sex', 'blood_group', 'height_cm', 'address',
            'allergies', 'medical_conditions',
        )}),
        ('Emergency contact', {'fields': (
            'emergency_contact_name', 'emergency_contact_relation', 'emergency_contact',
        )}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CareNest role', {'fields': ('role', 'phone_number')}),
    )


@admin.register(CaregiverLink)
class CaregiverLinkAdmin(admin.ModelAdmin):
    list_display = ('caregiver', 'patient', 'status', 'requested_at')
    list_filter = ('status',)


@admin.register(CaregiverInvite)
class CaregiverInviteAdmin(admin.ModelAdmin):
    list_display = ('code', 'patient', 'label', 'status_label', 'created_at', 'expires_at')
    search_fields = ('code', 'patient__username')
    readonly_fields = ('code',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'level', 'title', 'created_at', 'read_at')
    list_filter = ('kind', 'level')
    search_fields = ('user__username', 'title')


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'patient', 'status', 'first_seen_at', 'last_seen_at')
    list_filter = ('status',)
    search_fields = ('user__username', 'label')


admin.site.register(User, CustomUserAdmin)
