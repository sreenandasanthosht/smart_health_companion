"""
nursing app -- implements NURSING_ROLE_DESIGN.md.

Two entities, exactly as that document specifies in section 5:
  * NurseAssignment -- which nurse is caring for which patient, and when
  * NursingVisit    -- what happened during one visit

Boundary rule from section 4: nursing is logging and coordination only.
A nurse can record observations and raise an escalation, but cannot
prescribe medication or change a care plan -- those stay Provider actions.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class NurseAssignment(models.Model):
    """
    A time-bounded engagement between a nurse and a patient. Modelled as
    its own record (not a foreign key on either user) because assignments
    start and end, while the user accounts persist.
    """
    nurse = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nurse_assignments')
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nursing_assignments')
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='nurse_assignments_made',
    )
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-start_date']

    def is_active(self):
        return self.end_date is None or self.end_date >= timezone.localdate()

    def __str__(self):
        return f"{self.nurse} caring for {self.patient}"


class NursingVisit(models.Model):
    """
    One logged visit. Vitals taken during the visit are written into the
    shared health.VitalRecord table (tagged source=NURSE) and linked here,
    rather than duplicated into a nursing-only table.
    """
    class Severity(models.TextChoices):
        ROUTINE = 'ROUTINE', 'Routine note'
        URGENT = 'URGENT', 'Urgent -- needs provider attention'

    nurse = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nursing_visits')
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='nursing_visits_received')
    visited_at = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)
    medications_administered = models.CharField(max_length=255, blank=True)
    vitals = models.ForeignKey(
        'health.VitalRecord', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='nursing_visit',
    )
    escalated = models.BooleanField(default=False)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.ROUTINE)
    escalation_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-visited_at']

    def __str__(self):
        return f"Visit to {self.patient} on {self.visited_at:%d %b %Y}"
