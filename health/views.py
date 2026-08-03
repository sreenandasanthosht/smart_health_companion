"""
health app views -- patient-facing vitals, medications, lifestyle, mental
health, record sharing, and the caregiver's read-only view.

Everything here reads and writes real database rows. Nothing on these
pages is placeholder data any more.
"""
import datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import CaregiverLink, User
from adminpanel.models import AuditLog
from health import analytics
from health import extraction
from health.models import (
    ConsentGrant, ExtractedMedication, ExtractionJob, LifestyleLog, Medication,
    MedicationDose, MoodLog, VitalRecord, has_consent,
)
from providers.models import Appointment, ProviderProfile


def _refill_label(medication):
    if not medication.next_refill_date:
        return 'Not set'
    days_left = (medication.next_refill_date - timezone.localdate()).days
    if days_left < 0:
        return 'Overdue'
    if days_left == 0:
        return 'Today'
    return f"{days_left} days"


def _parse_decimal(raw):
    raw = (raw or '').strip()
    return float(raw) if raw else None


def _parse_int(raw):
    raw = (raw or '').strip()
    return int(raw) if raw else None


# --------------------------------------------------------------------------
# Patient dashboard
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def dashboard(request):
    patient = request.user
    today = timezone.localdate()

    # Refresh the generated insights so the summary reflects current data.
    insights = analytics.generate_insights(patient)
    score, band = analytics.health_score(patient)
    series = analytics.vital_series(patient)

    # Today's medication doses -- create the tick rows on first view of the day.
    active_meds = list(Medication.objects.filter(patient=patient, active=True))
    for med in active_meds:
        MedicationDose.objects.get_or_create(medication=med, date=today)
    todays_doses = (
        MedicationDose.objects.filter(medication__patient=patient, date=today)
        .select_related('medication').order_by('medication__name')
    )
    doses_due = todays_doses.filter(taken=False).count()

    next_appointment = (
        Appointment.objects.filter(
            patient=patient, scheduled_for__gte=timezone.now(),
            status__in=[Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED],
        ).select_related('provider', 'provider__user').first()
    )

    upcoming_refill = (
        Medication.objects.filter(patient=patient, active=True, next_refill_date__isnull=False)
        .order_by('next_refill_date').first()
    )

    recent_vitals = VitalRecord.objects.filter(patient=patient)[:4]
    recent_moods = MoodLog.objects.filter(patient=patient)[:1]

    # Recent activity feed, merged from several sources.
    activity = []
    for v in VitalRecord.objects.filter(patient=patient)[:3]:
        activity.append({'icon': 'i-heart', 'tint': 'tint-green',
                         'title': f"Vitals logged -- {v.bp_systolic}/{v.bp_diastolic}",
                         'when': v.recorded_at})
    for d in MedicationDose.objects.filter(medication__patient=patient, taken=True).select_related('medication')[:3]:
        activity.append({'icon': 'i-pill', 'tint': 'tint-orange',
                         'title': f"Took {d.medication.name}",
                         'when': d.taken_at or timezone.now()})
    for a in Appointment.objects.filter(patient=patient).select_related('provider')[:2]:
        activity.append({'icon': 'i-calendar-check', 'tint': 'tint-purple',
                         'title': f"Appointment {a.get_status_display().lower()} -- {a.provider.display_name()}",
                         'when': a.created_at})
    activity.sort(key=lambda x: x['when'], reverse=True)

    # Lifestyle goals for today.
    lifestyle_today = LifestyleLog.objects.filter(patient=patient, date=today).first()

    def goal(value, target):
        if not value:
            return 0
        return min(100, int(round(float(value) / float(target) * 100)))

    goals = [
        {'name': 'Drink 2 litres of water', 'icon': 'i-droplet', 'colour': '#3b82f6',
         'value': f"{lifestyle_today.water_litres if lifestyle_today and lifestyle_today.water_litres else 0} / 2.0 L",
         'pct': goal(lifestyle_today.water_litres if lifestyle_today else 0, 2.0)},
        {'name': f'Walk {analytics.STEPS_TARGET:,} steps', 'icon': 'i-footprints', 'colour': '#22c55e',
         'value': f"{lifestyle_today.steps if lifestyle_today and lifestyle_today.steps else 0:,} / {analytics.STEPS_TARGET:,}",
         'pct': goal(lifestyle_today.steps if lifestyle_today else 0, analytics.STEPS_TARGET)},
        {'name': 'Sleep 7 hours', 'icon': 'i-moon', 'colour': '#8b5cf6',
         'value': f"{lifestyle_today.sleep_hours if lifestyle_today and lifestyle_today.sleep_hours else 0} / 7 h",
         'pct': goal(lifestyle_today.sleep_hours if lifestyle_today else 0, 7.0)},
        {'name': 'Take all medicines', 'icon': 'i-pill', 'colour': '#f59e0b',
         'value': f"{todays_doses.filter(taken=True).count()} / {todays_doses.count()}",
         'pct': goal(todays_doses.filter(taken=True).count(), max(1, todays_doses.count()))},
    ]

    context = {
        'patient': patient,
        'today': today,
        'insights': insights,
        'health_score': score,
        'health_band': band,
        # SVG ring: 195 is the full circumference; the offset is the unfilled part.
        'score_offset': int(195 - (195 * score / 100)),
        'series': series,
        'sparklines': {
            'bp': analytics.sparkline_path(series['bp']['points']),
            'heart_rate': analytics.sparkline_path(series['heart_rate']['points']),
            'blood_sugar': analytics.sparkline_path(series['blood_sugar']['points']),
            'weight': analytics.sparkline_path(series['weight']['points']),
        },
        'doses_due': doses_due,
        'todays_doses': todays_doses,
        'next_appointment': next_appointment,
        'upcoming_refill': upcoming_refill,
        'recent_vitals': recent_vitals,
        'recent_mood': recent_moods[0] if recent_moods else None,
        'activity': activity[:5],
        'goals': goals,
        'adherence': analytics.medication_adherence(patient),
        'profile_completion': patient.profile_completion(),
        'missing_fields': patient.missing_profile_fields(),
        'show_profile_prompt': patient.profile_completion() < 100,
        'pending_caregivers': CaregiverLink.objects.filter(
            patient=patient, status=CaregiverLink.Status.PENDING).select_related('caregiver'),
    }
    return render(request, 'health/dashboard.html', context)


# --------------------------------------------------------------------------
# Vitals
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def vitals(request):
    if request.method == 'POST':
        try:
            bp_raw = request.POST.get('bp', '')
            systolic_raw, sep, diastolic_raw = bp_raw.partition('/')
            if not sep:
                raise ValueError('Enter blood pressure as systolic/diastolic, for example 120/80.')
            bp_systolic = int(systolic_raw.strip())
            bp_diastolic = int(diastolic_raw.strip())
            blood_sugar = _parse_decimal(request.POST.get('blood_sugar'))
            weight_kg = _parse_decimal(request.POST.get('weight_kg'))
            heart_rate = _parse_int(request.POST.get('heart_rate'))
        except ValueError as exc:
            messages.error(request, str(exc) or 'Please check the values you entered.')
        else:
            record = VitalRecord.objects.create(
                patient=request.user,
                bp_systolic=bp_systolic, bp_diastolic=bp_diastolic,
                blood_sugar=blood_sugar, weight_kg=weight_kg, heart_rate=heart_rate,
                source=VitalRecord.Source.SELF, entered_by=request.user,
            )
            analytics.generate_insights(request.user)
            if record.status == VitalRecord.Status.HIGH:
                messages.warning(request, 'Reading saved -- it is outside the normal range, so it has been flagged as High.')
            else:
                messages.success(request, 'Vitals saved.')
        return redirect('health_vitals')

    records = VitalRecord.objects.filter(patient=request.user)[:20]
    series = analytics.vital_series(request.user)
    context = {
        'records': records,
        'series': series,
        'sparkline_bp': analytics.sparkline_path(series['bp']['points']),
        'sparkline_hr': analytics.sparkline_path(series['heart_rate']['points']),
    }
    return render(request, 'health/vitals.html', context)


# --------------------------------------------------------------------------
# Medications
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def medications(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'add')

        if action == 'toggle_dose':
            dose = get_object_or_404(MedicationDose, pk=request.POST.get('dose_id'),
                                     medication__patient=request.user)
            dose.taken = not dose.taken
            dose.taken_at = timezone.now() if dose.taken else None
            dose.save(update_fields=['taken', 'taken_at'])
            analytics.generate_insights(request.user)
            return redirect('health_medications')

        if action == 'stop':
            med = get_object_or_404(Medication, pk=request.POST.get('medication_id'), patient=request.user)
            med.active = False
            med.save(update_fields=['active'])
            messages.info(request, f'{med.name} marked as no longer active.')
            return redirect('health_medications')

        name = request.POST.get('name', '').strip()
        dose_text = request.POST.get('dose', '').strip()
        schedule = request.POST.get('schedule', '').strip()
        start_date = request.POST.get('start_date', '').strip()
        refill = request.POST.get('next_refill_date', '').strip()
        if not (name and dose_text and schedule and start_date):
            messages.error(request, 'Please fill in the medicine name, dose, schedule and start date.')
        else:
            try:
                start = datetime.date.fromisoformat(start_date)
                refill_date = datetime.date.fromisoformat(refill) if refill else None
            except ValueError:
                messages.error(request, 'Please enter a valid date.')
            else:
                Medication.objects.create(
                    patient=request.user, name=name, dose=dose_text, schedule=schedule,
                    start_date=start, next_refill_date=refill_date,
                )
                messages.success(request, f'{name} added to your medicines.')
        return redirect('health_medications')

    today = timezone.localdate()
    active_meds = list(Medication.objects.filter(patient=request.user, active=True))
    for med in active_meds:
        MedicationDose.objects.get_or_create(medication=med, date=today)

    rows = []
    for med in active_meds:
        dose = MedicationDose.objects.filter(medication=med, date=today).first()
        rows.append({'med': med, 'refill_in': _refill_label(med), 'dose': dose})

    context = {
        'rows': rows,
        'past': Medication.objects.filter(patient=request.user, active=False),
        'adherence': analytics.medication_adherence(request.user),
        'today': today,
    }
    return render(request, 'health/medications.html', context)


# --------------------------------------------------------------------------
# Lifestyle
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def lifestyle(request):
    if request.method == 'POST':
        date_raw = request.POST.get('date', '').strip()
        try:
            log_date = datetime.date.fromisoformat(date_raw) if date_raw else timezone.localdate()
            sleep = _parse_decimal(request.POST.get('sleep_hours'))
            water = _parse_decimal(request.POST.get('water_litres'))
            steps = _parse_int(request.POST.get('steps'))
        except ValueError:
            messages.error(request, 'Please check the values you entered.')
        else:
            LifestyleLog.objects.update_or_create(
                patient=request.user, date=log_date,
                defaults={
                    'sleep_hours': sleep, 'water_litres': water, 'steps': steps,
                    'activity_note': request.POST.get('activity_note', '').strip(),
                },
            )
            analytics.generate_insights(request.user)
            messages.success(request, 'Lifestyle entry saved.')
        return redirect('health_lifestyle')

    logs = LifestyleLog.objects.filter(patient=request.user)[:21]
    sleeps = [l.sleep_hours for l in logs if l.sleep_hours is not None]
    waters = [l.water_litres for l in logs if l.water_litres is not None]
    steps_all = [l.steps for l in logs if l.steps is not None]

    context = {
        'logs': logs,
        'today': timezone.localdate().isoformat(),
        'avg_sleep': round(sum(sleeps) / len(sleeps), 1) if sleeps else None,
        'avg_water': round(sum(waters) / len(waters), 1) if waters else None,
        'avg_steps': int(sum(steps_all) / len(steps_all)) if steps_all else None,
    }
    return render(request, 'health/lifestyle.html', context)


# --------------------------------------------------------------------------
# Mental health -- private, never shareable
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def mental_health(request):
    if request.method == 'POST':
        mood = request.POST.get('mood', '').strip()
        if not mood:
            messages.error(request, 'Pick how you are feeling before saving.')
        else:
            MoodLog.objects.create(
                patient=request.user, date=timezone.localdate(),
                mood=mood, note=request.POST.get('note', '').strip(),
            )
            messages.success(request, 'Saved privately. Only you can see this.')
        return redirect('health_mental_health')

    entries = MoodLog.objects.filter(patient=request.user)[:30]
    counts = {}
    for e in entries:
        counts[e.mood] = counts.get(e.mood, 0) + 1
    context = {
        'entries': entries,
        'mood_options': ['Good', 'Calm', 'Stressed', 'Low', 'Anxious'],
        'mood_counts': sorted(counts.items(), key=lambda kv: -kv[1]),
        'total_entries': len(entries),
    }
    return render(request, 'health/mental_health.html', context)


# --------------------------------------------------------------------------
# Record sharing -- the consent engine's user-facing surface
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def share_records(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'grant')

        if action == 'revoke':
            grant = get_object_or_404(ConsentGrant, pk=request.POST.get('grant_id'), patient=request.user)
            grant.revoke()
            AuditLog.record(request.user, 'Revoked a record share',
                            f"{grant.recipient.display_name} -- {grant.scope_label()}",
                            AuditLog.Tag.WARN)
            messages.info(request, f'Access revoked for {grant.recipient.display_name}.')
            return redirect('health_share')

        recipient_id = request.POST.get('recipient')
        recipient = User.objects.filter(pk=recipient_id).first()
        if not recipient:
            messages.error(request, 'Choose who you want to share with.')
            return redirect('health_share')

        scopes = request.POST.getlist('scope')
        if not scopes:
            messages.error(request, 'Choose at least one category to share.')
            return redirect('health_share')

        hours = request.POST.get('expires_in', '2')
        expires_at = None
        if hours != 'never':
            try:
                expires_at = timezone.now() + datetime.timedelta(hours=int(hours))
            except ValueError:
                expires_at = timezone.now() + datetime.timedelta(hours=2)

        grant = ConsentGrant.objects.create(
            patient=request.user, recipient=recipient,
            scope_vitals='VITALS' in scopes,
            scope_medications='MEDICATIONS' in scopes,
            scope_records='RECORDS' in scopes,
            scope_lifestyle='LIFESTYLE' in scopes,
            expires_at=expires_at,
            action_context=request.POST.get('context', 'Manual share'),
        )
        AuditLog.record(request.user, 'Granted a record share',
                        f"{recipient.display_name} -- {grant.scope_label()}", AuditLog.Tag.OK)
        messages.success(request, f'Share created. Passcode: {grant.passcode}')
        return redirect('health_share')

    grants = ConsentGrant.objects.filter(patient=request.user).select_related('recipient')
    active = [g for g in grants if g.is_active()]
    history = [g for g in grants if not g.is_active()]

    # Who can a patient share with? Verified providers, plus their approved caregivers.
    provider_users = User.objects.filter(
        role=User.Role.PROVIDER,
        provider_profile__verification_status=ProviderProfile.Verification.VERIFIED,
    ).select_related('provider_profile')
    caregiver_users = User.objects.filter(
        patient_links__patient=request.user,
        patient_links__status=CaregiverLink.Status.APPROVED,
    )

    context = {
        'active_shares': active,
        'history': history,
        'recipients': list(provider_users) + list(caregiver_users),
    }
    return render(request, 'health/share_records.html', context)


# --------------------------------------------------------------------------
# Caregiver views
# --------------------------------------------------------------------------

@role_required(User.Role.CAREGIVER)
def caregiver_dashboard(request):
    link = (
        CaregiverLink.objects.filter(caregiver=request.user, status=CaregiverLink.Status.APPROVED)
        .select_related('patient').first()
    )
    pending = CaregiverLink.objects.filter(
        caregiver=request.user, status=CaregiverLink.Status.PENDING).select_related('patient').first()

    if not link:
        # No approved link yet -- show the waiting/link state instead of data.
        return render(request, 'health/caregiver_dashboard.html', {
            'link': None, 'pending': pending,
        })

    patient = link.patient

    # Consent gate: a caregiver sees vitals only if the patient granted it.
    can_see_vitals = has_consent(patient, request.user, ConsentGrant.Scope.VITALS)
    can_see_medications = has_consent(patient, request.user, ConsentGrant.Scope.MEDICATIONS)

    recent_vitals = VitalRecord.objects.filter(patient=patient)[:5] if can_see_vitals else []
    meds = Medication.objects.filter(patient=patient, active=True) if can_see_medications else []

    alerts = []
    if can_see_vitals:
        alerts = list(patient.insights.filter(
            level__in=['WARNING', 'CRITICAL'])[:4])

    missed = 0
    if can_see_medications:
        missed = MedicationDose.objects.filter(
            medication__patient=patient, taken=False,
            date__gte=timezone.localdate() - datetime.timedelta(days=7),
        ).count()

    context = {
        'link': link,
        'pending': None,
        'patient': patient,
        'can_see_vitals': can_see_vitals,
        'can_see_medications': can_see_medications,
        'recent_vitals': recent_vitals,
        'latest_vital': recent_vitals[0] if recent_vitals else None,
        'medications': meds,
        'alerts': alerts,
        'missed_doses': missed,
        'adherence': analytics.medication_adherence(patient) if can_see_medications else None,
    }
    return render(request, 'health/caregiver_dashboard.html', context)


@role_required(User.Role.CAREGIVER)
def caregiver_link_request(request):
    """A caregiver who registered without a valid patient ID can retry here."""
    if request.method == 'POST':
        code = request.POST.get('patient_id', '').strip().upper()
        patient = User.objects.filter(unique_id=code, role=User.Role.PATIENT).first()
        if not patient:
            messages.error(request, 'No patient found with that ID. Ask them to check their dashboard.')
        elif CaregiverLink.objects.filter(patient=patient, caregiver=request.user).exists():
            messages.info(request, 'You have already requested access to this patient.')
        else:
            CaregiverLink.objects.create(
                patient=patient, caregiver=request.user,
                relationship=request.POST.get('relationship', '').strip(),
            )
            messages.success(request, f'Request sent to {patient.display_name}. They need to approve it.')
        return redirect('health_caregiver_dashboard')
    return redirect('health_caregiver_dashboard')


@role_required(User.Role.PATIENT)
def caregiver_requests(request):
    """The patient approves or rejects caregiver link requests here."""
    if request.method == 'POST':
        link = get_object_or_404(CaregiverLink, pk=request.POST.get('link_id'), patient=request.user)
        decision = request.POST.get('decision')
        if decision == 'approve':
            link.status = CaregiverLink.Status.APPROVED
            link.decided_at = timezone.now()
            link.save(update_fields=['status', 'decided_at'])
            # Approving the link also grants the baseline consent to see vitals.
            ConsentGrant.objects.get_or_create(
                patient=request.user, recipient=link.caregiver, revoked_at__isnull=True,
                defaults={'scope_vitals': True, 'scope_medications': True,
                          'action_context': 'Caregiver monitoring'},
            )
            AuditLog.record(request.user, 'Approved a caregiver link',
                            link.caregiver.display_name, AuditLog.Tag.OK)
            messages.success(request, f'{link.caregiver.display_name} can now monitor your vitals.')
        else:
            link.status = CaregiverLink.Status.REJECTED
            link.decided_at = timezone.now()
            link.save(update_fields=['status', 'decided_at'])
            AuditLog.record(request.user, 'Rejected a caregiver link',
                            link.caregiver.display_name, AuditLog.Tag.MUTED)
            messages.info(request, 'Request declined.')
        return redirect('health_caregiver_requests')

    links = CaregiverLink.objects.filter(patient=request.user).select_related('caregiver')
    return render(request, 'health/caregiver_requests.html', {
        'pending': [l for l in links if l.status == CaregiverLink.Status.PENDING],
        'decided': [l for l in links if l.status != CaregiverLink.Status.PENDING],
    })


# --------------------------------------------------------------------------
# Prescription extraction — process and discard
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def prescription_upload(request):
    """
    Read an uploaded prescription, extract the medicines, and discard the file.

    The uploaded bytes are held in memory only. Settings force Django's
    in-memory upload handler so a large file cannot be spilled to a temp file,
    and nothing here ever calls save() on the upload.
    """
    if request.method == 'POST':
        uploaded = request.FILES.get('document')
        consented = bool(request.POST.get('consent'))

        if not uploaded:
            messages.error(request, 'Choose a photo of your prescription first.')
            return redirect('health_prescription_upload')

        # Consent gate. Refusals are logged too, so the audit trail shows
        # attempted-but-refused processing, not just what succeeded.
        if not consented:
            AuditLog.record(request.user, 'Refused consent for document extraction',
                            uploaded.name[:100], AuditLog.Tag.WARN)
            messages.error(request,
                           'We can only read your prescription if you tick the box to allow it.')
            return redirect('health_prescription_upload')

        # Keep the display name before we release the upload object. We store
        # the bare filename only -- never a path, and never the file itself.
        display_name = uploaded.name[:255]

        try:
            extraction.validate_upload(uploaded)
            file_bytes = uploaded.read()          # into memory, never to disk
            text, confidence = extraction.extract_text(file_bytes, display_name)
        except extraction.ExtractionError as exc:
            AuditLog.record(request.user, 'Document extraction failed',
                            str(exc)[:150], AuditLog.Tag.WARN)
            messages.error(request, str(exc))
            return redirect('health_prescription_upload')
        finally:
            # Release the bytes as early as possible, whatever happened.
            file_bytes = None
            uploaded = None

        job = ExtractionJob.objects.create(
            patient=request.user,
            source_type=request.POST.get('source_type', ExtractionJob.Source.PRESCRIPTION),
            original_filename=display_name,
            raw_text=text,
            ocr_confidence=confidence,
            file_deleted_at=timezone.now(),       # the bytes are already gone
        )

        if not text.strip():
            job.status = ExtractionJob.Status.FAILED
            job.parser_note = 'No readable text found in the image.'
            job.save(update_fields=['status', 'parser_note'])
            messages.error(request,
                           "We couldn't read any text in that image. Try a sharper, "
                           'better-lit photo taken straight on.')
            return redirect('health_prescription_upload')

        items, parser_used, note = extraction.parse_medications(text)
        job.parser_used = parser_used
        job.parser_note = note[:200]
        job.save(update_fields=['parser_used', 'parser_note'])

        for item in items:
            ExtractedMedication.objects.create(job=job, **item)

        AuditLog.record(request.user, 'Extracted a document',
                        f'{len(items)} medicine(s) found, parser={parser_used}',
                        AuditLog.Tag.OK)

        if not items:
            messages.warning(request,
                             'We read the image but could not identify any medicines. '
                             'You can add them by hand instead.')
        return redirect('health_extraction_verify', job_id=job.id)

    return render(request, 'health/prescription_upload.html', {
        'llm_in_use': extraction.llm_available(),
        'llm_model': getattr(settings, 'LLM_MODEL', ''),
        'recent': ExtractionJob.objects.filter(patient=request.user)[:5],
    })


@role_required(User.Role.PATIENT)
def extraction_verify(request, job_id):
    """The patient corrects what was extracted before anything is saved."""
    job = get_object_or_404(ExtractionJob, pk=job_id, patient=request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'discard':
            job.status = ExtractionJob.Status.DISCARDED
            job.save(update_fields=['status'])
            job.clear_text()
            AuditLog.record(request.user, 'Discarded an extraction', '', AuditLog.Tag.MUTED)
            messages.info(request, 'Discarded. Nothing was added to your medicines.')
            return redirect('health_prescription_upload')

        created = 0
        for item in job.medications.all():
            if not request.POST.get(f'keep_{item.id}'):
                continue
            name = request.POST.get(f'name_{item.id}', '').strip()
            if not name:
                continue
            item.name = name[:120]
            item.dose = request.POST.get(f'dose_{item.id}', '').strip()[:60]
            item.frequency = request.POST.get(f'frequency_{item.id}', '').strip()[:120]
            item.confirmed = True
            item.save(update_fields=['name', 'dose', 'frequency', 'confirmed'])

            Medication.objects.create(
                patient=request.user, name=item.name,
                dose=item.dose or 'As prescribed',
                schedule=item.frequency or 'As prescribed',
                start_date=timezone.localdate(),
            )
            created += 1

        job.status = ExtractionJob.Status.CONFIRMED
        job.save(update_fields=['status'])
        job.clear_text()          # transcribed text is no longer needed
        AuditLog.record(request.user, 'Confirmed extracted medicines',
                        f'{created} added', AuditLog.Tag.OK)

        if created:
            messages.success(request,
                             f'{created} medicine{"s" if created != 1 else ""} added.')
        else:
            messages.info(request, 'Nothing was added.')
        return redirect('health_medications')

    return render(request, 'health/extraction_verify.html', {
        'job': job,
        'items': job.medications.all(),
    })
