from django.contrib import admin

from adminpanel.models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor_label', 'action', 'target', 'tag')
    list_filter = ('tag',)
    search_fields = ('action', 'target', 'actor_label')
    readonly_fields = ('created_at',)
