"""
nursing app views -- the Nurse's dashboard, assigned patients and visit
logging, per NURSING_ROLE_DESIGN.md.

Boundary: a nurse records observations and can raise an escalation, but
cannot prescribe or change a care plan. There is deliberately no view here
that writes to Medication.
"""
import datetime

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import User
from adminpanel.models import AuditLog
from health.models import Medication, VitalRecord
from nursing.models import NurseAssignment, NursingVisit


def _assigned_patient_or_404(nurse, patient_id):
    assignment = get_object_or_404(
        NurseAssignment, nurse=nurse, patient_id=patient_id, end_date__isnull=True)
    return assignment.patient


@role_required(User.Role.NURSE)
def dashboard(request):
    assignments = NurseAssignment.objects.filter(
        nurse=request.user, end_date__isnull=True).select_related('patient')

    cards = []
    for a in assignments:
        latest = VitalRecord.objects.filter(patient=a.patient).first()
        cards.append({
            'assignment': a,
            'patient': a.patient,
            'latest_vital': latest,
            'last_visit': NursingVisit.objects.filter(nurse=request.user, patient=a.patient).first(),
        })

    week_ago = timezone.now() - datetime.timedelta(days=7)
    context = {
        'cards': cards,
        'assignment_count': len(cards),
        'visits_this_week': NursingVisit.objects.filter(nurse=request.user, visited_at__gte=week_ago).count(),
        'open_escalations': NursingVisit.objects.filter(
            nurse=request.user, escalated=True, visited_at__gte=week_ago).count(),
        'recent_visits': NursingVisit.objects.filter(nurse=request.user).select_related('patient')[:5],
    }
    return render(request, 'nursing/dashboard.html', context)


@role_required(User.Role.NURSE)
def patient_detail(request, patient_id):
    patient = _assigned_patient_or_404(request.user, patient_id)
    context = {
        'patient': patient,
        'vitals': VitalRecord.objects.filter(patient=patient)[:10],
        'medications': Medication.objects.filter(patient=patient, active=True),
        'visits': NursingVisit.objects.filter(patient=patient).select_related('nurse')[:10],
        'now': timezone.now(),
    }
    return render(request, 'nursing/patient_detail.html', context)


@role_required(User.Role.NURSE)
def log_visit(request, patient_id):
    patient = _assigned_patient_or_404(request.user, patient_id)

    if request.method != 'POST':
        return redirect('nurse_patient_detail', patient_id=patient_id)

    vital = None
    bp_raw = request.POST.get('bp', '').strip()
    if bp_raw:
        systolic_raw, sep, diastolic_raw = bp_raw.partition('/')
        if not sep:
            messages.error(request, 'Enter blood pressure as systolic/diastolic, for example 120/80.')
            return redirect('nurse_patient_detail', patient_id=patient_id)
        try:
            heart_rate = request.POST.get('heart_rate', '').strip()
            sugar = request.POST.get('blood_sugar', '').strip()
            weight = request.POST.get('weight_kg', '').strip()
            vital = VitalRecord.objects.create(
                patient=patient,
                bp_systolic=int(systolic_raw.strip()),
                bp_diastolic=int(diastolic_raw.strip()),
                heart_rate=int(heart_rate) if heart_rate else None,
                blood_sugar=float(sugar) if sugar else None,
                weight_kg=float(weight) if weight else None,
                source=VitalRecord.Source.NURSE,
                entered_by=request.user,
            )
        except ValueError:
            messages.error(request, 'Please check the vitals you entered.')
            return redirect('nurse_patient_detail', patient_id=patient_id)

    escalated = bool(request.POST.get('escalated'))
    visit = NursingVisit.objects.create(
        nurse=request.user, patient=patient,
        notes=request.POST.get('notes', '').strip(),
        medications_administered=request.POST.get('medications_administered', '').strip(),
        vitals=vital,
        escalated=escalated,
        severity=NursingVisit.Severity.URGENT if escalated else NursingVisit.Severity.ROUTINE,
        escalation_reason=request.POST.get('escalation_reason', '').strip() if escalated else '',
    )

    if escalated:
        AuditLog.record(request.user, 'Raised a nursing escalation',
                        f"{patient.display_name} -- {visit.escalation_reason or 'urgent'}",
                        AuditLog.Tag.DANGER)
        messages.warning(request, 'Visit logged and escalated for provider attention.')
    else:
        AuditLog.record(request.user, 'Logged a nursing visit', patient.display_name, AuditLog.Tag.MUTED)
        messages.success(request, 'Visit logged.')

    return redirect('nurse_patient_detail', patient_id=patient_id)


@role_required(User.Role.NURSE)
def visits(request):
    context = {
        'visits': NursingVisit.objects.filter(nurse=request.user).select_related('patient', 'vitals'),
    }
    return render(request, 'nursing/visits.html', context)
