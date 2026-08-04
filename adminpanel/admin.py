from django.contrib import admin

from adminpanel.models import Announcement, AuditLog, Complaint, PlatformSettings


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_label', 'action', 'target', 'tag')
    list_filter = ('tag',)
    search_fields = ('action', 'target', 'actor_label')
    readonly_fields = ('created_at',)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('subject', 'category', 'reporter', 'against_user', 'status', 'created_at')
    list_filter = ('status', 'category')
    search_fields = ('subject', 'description', 'reporter__username')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'audience', 'is_published', 'recipients_notified', 'created_at')
    list_filter = ('audience', 'is_published')
    search_fields = ('title', 'body')


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'provider_self_registration_open',
                    'caregiver_device_approval_required', 'updated_at')

    def has_add_permission(self, request):
        # Singleton: edit the one row, never create a second.
        return not PlatformSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
