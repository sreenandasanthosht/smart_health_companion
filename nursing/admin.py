from django.contrib import admin

from nursing.models import NurseAssignment, NursingVisit


@admin.register(NurseAssignment)
class NurseAssignmentAdmin(admin.ModelAdmin):
    list_display = ('nurse', 'patient', 'start_date', 'end_date')
    list_filter = ('start_date',)
    search_fields = ('nurse__username', 'patient__username')


@admin.register(NursingVisit)
class NursingVisitAdmin(admin.ModelAdmin):
    list_display = ('patient', 'nurse', 'visited_at', 'escalated', 'severity')
    list_filter = ('escalated', 'severity')
