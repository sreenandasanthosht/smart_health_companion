from django.contrib import admin

from providers.models import Appointment, ProviderProfile


@admin.register(ProviderProfile)
class ProviderProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'provider_type', 'verification_status', 'submitted_at')
    list_filter = ('provider_type', 'verification_status')
    search_fields = ('user__username', 'user__email', 'clinic_name', 'specialty')
    readonly_fields = ('submitted_at',)


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ('patient', 'provider', 'scheduled_for', 'status')
    list_filter = ('status',)
    search_fields = ('patient__username', 'provider__clinic_name')
