from django.contrib import admin

from health.models import (
    ConsentGrant, HealthInsight, LifestyleLog, Medication, MedicationDose,
    MoodLog, VitalRecord,
)


@admin.register(VitalRecord)
class VitalRecordAdmin(admin.ModelAdmin):
    list_display = ('patient', 'recorded_at', 'bp_systolic', 'bp_diastolic', 'heart_rate', 'status', 'source')
    list_filter = ('status', 'source')
    search_fields = ('patient__username',)


@admin.register(Medication)
class MedicationAdmin(admin.ModelAdmin):
    list_display = ('name', 'patient', 'dose', 'schedule', 'active')
    list_filter = ('active',)
    search_fields = ('name', 'patient__username')


@admin.register(MedicationDose)
class MedicationDoseAdmin(admin.ModelAdmin):
    list_display = ('medication', 'date', 'taken')
    list_filter = ('taken', 'date')


@admin.register(LifestyleLog)
class LifestyleLogAdmin(admin.ModelAdmin):
    list_display = ('patient', 'date', 'sleep_hours', 'water_litres', 'steps')


@admin.register(MoodLog)
class MoodLogAdmin(admin.ModelAdmin):
    # Listed for completeness, but note this data is never shareable.
    list_display = ('patient', 'date', 'mood')


@admin.register(ConsentGrant)
class ConsentGrantAdmin(admin.ModelAdmin):
    list_display = ('patient', 'recipient', 'scope_label', 'granted_at', 'expires_at', 'revoked_at')
    list_filter = ('scope_vitals', 'scope_medications', 'scope_lifestyle')
    search_fields = ('patient__username', 'recipient__username')


@admin.register(HealthInsight)
class HealthInsightAdmin(admin.ModelAdmin):
    list_display = ('patient', 'level', 'text', 'created_at')
    list_filter = ('level',)
