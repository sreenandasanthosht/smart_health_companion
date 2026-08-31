"""
providers app views -- the provider directory, appointment booking, the
provider's own dashboard, and the verification status page.

All data here comes from the database.
"""
import datetime
import re

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from django.contrib.auth.decorators import login_required

from accounts.decorators import role_required
from accounts.models import User
from adminpanel.models import AuditLog
from health import analytics
from health.models import ConsentGrant, Medication, has_consent
from providers.dashboards import GROUP_DASHBOARDS, services_page
from providers.models import (
    Appointment,
    CarePlan,
    HealthEvent,
    ProviderAvailability,
    ProviderProfile,
)


# The only location information this project holds is ProviderProfile.address --
# one free-text line, written at whatever level of detail the provider chose
# ("Indiranagar, Bengaluru"). A patient's own saved address is written at a
# different level again ("Bengaluru, Karnataka"), so comparing the two strings
# whole matches nothing even when they describe the same city. Matching on any
# single word of what was typed is what makes both a typed area name and the
# "use my saved address" shortcut work against the data as it is actually
# stored, without adding a field or asking every provider to re-enter anything.
#
# Words shorter than three characters are dropped ("of", "nr") because they
# match almost any address, and the list is capped so a pasted paragraph
# cannot turn into a hundred-clause OR.
LOCATION_MIN_TOKEN = 3
LOCATION_MAX_TOKENS = 4


def _location_tokens(text, limit=LOCATION_MAX_TOKENS):
    """The words worth matching an address against, lower-cased and de-duplicated."""
    tokens = []
    for word in re.split(r'[^0-9A-Za-z]+', text or ''):
        word = word.lower()
        if len(word) >= LOCATION_MIN_TOKEN and word not in tokens:
            tokens.append(word)
        if len(tokens) >= limit:
            break
    return tokens


@role_required(User.Role.PATIENT, User.Role.CAREGIVER)
def directory(request):
    query = request.GET.get('q', '').strip()
    ptype = request.GET.get('type', '').strip()
    group = request.GET.get('group', '').strip()
    location = request.GET.get('location', '').strip()

    providers = ProviderProfile.objects.filter(
        verification_status=ProviderProfile.Verification.VERIFIED,
    ).select_related('user')

    if query:
        providers = providers.filter(
            Q(clinic_name__icontains=query) | Q(specialty__icontains=query)
            | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
        )
    # Group is the broad filter ("show me anything to do with wellness"),
    # type is the narrow one ("yoga centres only").
    if group in ProviderProfile.ServiceGroup.values:
        providers = providers.filter(provider_type__in=ProviderProfile.types_in_group(group))
    if ptype:
        providers = providers.filter(provider_type=ptype)

    # Location is applied last, on top of the verified-only queryset built
    # above, so it can only ever narrow the set of providers a patient is
    # already allowed to see -- never widen it. There is deliberately no
    # separate "eligible provider" query here.
    if location:
        tokens = _location_tokens(location)
        if tokens:
            matches = Q(address__icontains=tokens[0])
            for token in tokens[1:]:
                matches |= Q(address__icontains=token)
        else:
            # Nothing long enough to tokenise (e.g. "GK"): fall back to the
            # literal string rather than silently ignoring what was typed.
            matches = Q(address__icontains=location)
        providers = providers.filter(matches)

    context = {
        'providers': providers,
        'query': query,
        'selected_type': ptype,
        'selected_group': group,
        'location_query': location,
        # Offered as a one-click shortcut, not used automatically: the patient
        # decides whether to search on their own saved address.
        'my_address': (request.user.address or '').strip(),
        'types': ProviderProfile.ProviderType.choices,
        'groups': ProviderProfile.ServiceGroup.choices,
    }
    return render(request, 'providers/directory.html', context)


@role_required(User.Role.PATIENT)
def appointments(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'book')

        if action == 'cancel':
            appt = get_object_or_404(Appointment, pk=request.POST.get('appointment_id'), patient=request.user)
            appt.status = Appointment.Status.CANCELLED
            appt.save(update_fields=['status'])
            messages.info(request, 'Appointment cancelled.')
            return redirect('provider_appointments')

        provider_id = request.POST.get('provider')
        date_raw = request.POST.get('date', '').strip()
        time_raw = request.POST.get('time', '').strip()
        provider = ProviderProfile.objects.filter(
            pk=provider_id, verification_status=ProviderProfile.Verification.VERIFIED).first()

        if not provider:
            messages.error(request, 'Choose a verified provider.')
        elif not (date_raw and time_raw):
            messages.error(request, 'Pick both a date and a time.')
        else:
            try:
                naive = datetime.datetime.fromisoformat(f"{date_raw}T{time_raw}")
            except ValueError:
                messages.error(request, 'That date or time was not valid.')
            else:
                when = timezone.make_aware(naive, timezone.get_current_timezone())
                windows = list(ProviderAvailability.objects.filter(provider=provider))
                if when < timezone.now():
                    messages.error(request, 'Pick a time in the future.')
                elif windows and not any(w.covers(when) for w in windows):
                    hours = ', '.join(
                        f"{w.get_weekday_display()} {w.start_time:%H:%M}-{w.end_time:%H:%M}" for w in windows
                    )
                    messages.error(
                        request,
                        f"{provider.display_name()} isn't available then. Their hours: {hours}.",
                    )
                else:
                    Appointment.objects.create(
                        patient=request.user, provider=provider, scheduled_for=when,
                        reason=request.POST.get('reason', '').strip(),
                    )
                    messages.success(request, f'Request sent to {provider.display_name()}.')
        return redirect('provider_appointments')

    all_appts = Appointment.objects.filter(patient=request.user).select_related('provider', 'provider__user')
    now = timezone.now()
    context = {
        'upcoming': [a for a in all_appts if a.scheduled_for >= now and a.status in
                     {Appointment.Status.REQUESTED, Appointment.Status.CONFIRMED}],
        'past': [a for a in all_appts if a.scheduled_for < now or a.status in
                 {Appointment.Status.COMPLETED, Appointment.Status.DECLINED, Appointment.Status.CANCELLED}],
        'providers': ProviderProfile.objects.filter(
            verification_status=ProviderProfile.Verification.VERIFIED).select_related('user'),
        'today': timezone.localdate().isoformat(),
    }
    return render(request, 'providers/appointments.html', context)


def _verified_profile_or_redirect(request):
    """
    Shared gate for every provider-only page.

    Returns (profile, None) when the caller may proceed, or
    (None, redirect) when they may not -- no profile yet, or still waiting
    on verification.
    """
    profile = ProviderProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.info(request, 'Complete your provider profile to get started.')
        return None, redirect('provider_pending')
    if not profile.is_verified:
        return None, redirect('provider_pending')
    return profile, None


@role_required(User.Role.PROVIDER)
def dashboard(request):
    """
    One URL, six dashboards.

    Which one a provider sees is decided entirely by the service they
    chose at registration. Keeping a single `provider_dashboard` URL name
    means the login redirect, the role decorators and every existing
    template link keep working untouched.
    """
    profile, bounce = _verified_profile_or_redirect(request)
    if bounce:
        return bounce

    handler = GROUP_DASHBOARDS.get(profile.service_group)
    if handler is None:
        # Unreachable while GROUP_OF_TYPE covers every type, but a provider
        # is better served by the clinical screen than by a 500.
        handler = GROUP_DASHBOARDS[ProviderProfile.ServiceGroup.CLINICAL]
    return handler(request, profile)


@role_required(User.Role.PROVIDER)
def services(request):
    """The service / price list, shared by all six groups."""
    profile, bounce = _verified_profile_or_redirect(request)
    if bounce:
        return bounce
    return services_page(request, profile)


@role_required(User.Role.PROVIDER)
def pending(request):
    profile = ProviderProfile.objects.filter(user=request.user).first()

    if request.method == 'POST' and profile:
        # Providers can (re)submit their documents from this page.
        profile.registration_number = request.POST.get('registration_number', '').strip()
        profile.specialty = request.POST.get('specialty', '').strip()
        profile.clinic_name = request.POST.get('clinic_name', '').strip()
        profile.address = request.POST.get('address', '').strip()
        years = request.POST.get('years_experience', '').strip()
        profile.years_experience = int(years) if years.isdigit() else None
        profile.doc_registration_certificate = bool(request.POST.get('doc_registration_certificate'))
        profile.doc_government_id = bool(request.POST.get('doc_government_id'))
        profile.doc_organization_info = bool(request.POST.get('doc_organization_info'))
        profile.doc_address_proof = bool(request.POST.get('doc_address_proof'))
        if profile.verification_status == ProviderProfile.Verification.NEEDS_INFO:
            profile.verification_status = ProviderProfile.Verification.PENDING
            profile.verification_note = ''
        profile.save()
        AuditLog.record(request.user, 'Submitted verification documents',
                        profile.display_name(), AuditLog.Tag.WARN)
        messages.success(request, 'Details submitted. An administrator will review them.')
        return redirect('provider_pending')

    return render(request, 'providers/pending.html', {'profile': profile})


# --------------------------------------------------------------------------
# Pre-visit snapshot
# --------------------------------------------------------------------------

@role_required(User.Role.PATIENT)
def share_previsit_consent(request):
    """
    The patient's one-click "share a pre-visit snapshot with Dr X" action.

    Creates (or refreshes) a ConsentGrant scoped to vitals + medications
    only, expiring 24 hours after the appointment so it cannot be used
    indefinitely -- the Phase 3 plan's recommended default for the open
    question CONSENT_FRAMEWORK_DESIGN.md left unresolved. Shown from both
    the appointments page and the dashboard, hence the redirect-to-`next`.
    """
    if request.method != 'POST':
        return redirect('provider_appointments')

    appt = get_object_or_404(Appointment, pk=request.POST.get('appointment_id'), patient=request.user)
    expires = appt.scheduled_for + datetime.timedelta(hours=24)

    grant = ConsentGrant.objects.filter(
        patient=request.user, recipient=appt.provider.user,
        action_context='Pre-visit snapshot', revoked_at__isnull=True,
    ).first()
    if grant:
        grant.scope_vitals = True
        grant.scope_medications = True
        grant.expires_at = expires
        grant.save(update_fields=['scope_vitals', 'scope_medications', 'expires_at'])
    else:
        ConsentGrant.objects.create(
            patient=request.user, recipient=appt.provider.user,
            scope_vitals=True, scope_medications=True,
            expires_at=expires, action_context='Pre-visit snapshot',
        )

    AuditLog.record(
        request.user, 'Shared a pre-visit snapshot',
        f"With {appt.provider.display_name()}", AuditLog.Tag.OK,
    )
    messages.success(request, f'Vitals and medications will be visible to {appt.provider.display_name()} for this visit.')
    next_url = request.POST.get('next', '')
    return redirect(next_url or 'provider_appointments')


@role_required(User.Role.PROVIDER)
def previsit_snapshot(request, appointment_id):
    """
    What a provider sees before a visit: recent vitals, medication
    adherence, active care plans and any recent nursing escalations --
    but ONLY for scopes the patient has actually granted this provider.

    A provider having an appointment with a patient is not by itself
    permission to see their data; that is exactly the mistake the consent
    framework exists to prevent. Every view of a snapshot is logged,
    including when a scope is withheld, so the audit trail shows both
    what was seen and what was asked for and refused.
    """
    profile = get_object_or_404(ProviderProfile, user=request.user)
    appt = get_object_or_404(Appointment, pk=appointment_id, provider=profile)
    patient = appt.patient
    provider_user = request.user

    can_see_vitals = has_consent(patient, provider_user, ConsentGrant.Scope.VITALS)
    can_see_meds = has_consent(patient, provider_user, ConsentGrant.Scope.MEDICATIONS)

    scopes_seen = []
    if can_see_vitals:
        scopes_seen.append('Vital signs')
    if can_see_meds:
        scopes_seen.append('Medication status')

    if scopes_seen:
        AuditLog.record(
            provider_user, 'Viewed pre-visit snapshot',
            f"{patient.display_name} ({', '.join(scopes_seen)})", AuditLog.Tag.WARN,
        )
    else:
        AuditLog.record(
            provider_user, 'Pre-visit snapshot blocked -- no consent',
            patient.display_name, AuditLog.Tag.DANGER,
        )

    context = {
        'appointment': appt,
        'patient': patient,
        'can_see_vitals': can_see_vitals,
        'can_see_meds': can_see_meds,
    }

    if can_see_vitals:
        context['series'] = analytics.vital_series(patient)
        context['recent_vitals'] = patient.vital_records.all()[:10]

    if can_see_meds:
        context['active_meds'] = Medication.objects.filter(patient=patient, active=True)
        context['adherence'] = analytics.medication_adherence(patient)

    # Care plans and nursing escalations are shown alongside vitals/meds
    # rather than behind their own scope -- they are the provider's own
    # notes, and nursing escalations already went through the care team.
    if can_see_vitals or can_see_meds:
        context['care_plans'] = CarePlan.objects.filter(patient=patient, active=True).select_related('provider')
        try:
            from nursing.models import NursingVisit
            since = timezone.now() - datetime.timedelta(days=30)
            context['recent_escalations'] = NursingVisit.objects.filter(
                patient=patient, escalated=True, visited_at__gte=since,
            ).order_by('-visited_at')
        except ImportError:
            context['recent_escalations'] = []

    return render(request, 'providers/previsit_snapshot.html', context)


# --------------------------------------------------------------------------
# Care plans
# --------------------------------------------------------------------------

@role_required(User.Role.PROVIDER)
def care_plans(request):
    profile = get_object_or_404(ProviderProfile, user=request.user)
    treated_patient_ids = set(
        Appointment.objects.filter(provider=profile).values_list('patient_id', flat=True)
    )

    if request.method == 'POST':
        if request.POST.get('action') == 'end':
            plan = get_object_or_404(CarePlan, pk=request.POST.get('plan_id'), provider=profile)
            plan.active = False
            plan.save(update_fields=['active'])
            messages.info(request, 'Care plan ended.')
            return redirect('provider_care_plans')

        patient_id = request.POST.get('patient_id')
        if int(patient_id or 0) not in treated_patient_ids:
            messages.error(request, "You can only set a care plan for a patient you've had an appointment with.")
            return redirect('provider_care_plans')

        patient = get_object_or_404(User, pk=patient_id, role=User.Role.PATIENT)
        target_raw = request.POST.get('target_value', '').strip()
        try:
            target_value = float(target_raw)
        except ValueError:
            messages.error(request, 'Enter a numeric target value.')
            return redirect('provider_care_plans')

        review_raw = request.POST.get('review_date', '').strip()
        review_date = None
        if review_raw:
            try:
                review_date = datetime.date.fromisoformat(review_raw)
            except ValueError:
                pass

        CarePlan.objects.create(
            patient=patient, provider=profile,
            metric=request.POST.get('metric', CarePlan.Metric.BP_SYSTOLIC),
            target_value=target_value,
            target_direction=request.POST.get('target_direction', CarePlan.Direction.BELOW),
            review_date=review_date,
            note=request.POST.get('note', '').strip(),
        )
        AuditLog.record(request.user, 'Set a care plan', patient.display_name, AuditLog.Tag.WARN)
        messages.success(request, f'Care plan set for {patient.display_name}.')
        return redirect('provider_care_plans')

    treated_patients = User.objects.filter(id__in=treated_patient_ids).order_by('first_name')
    plans = CarePlan.objects.filter(provider=profile).select_related('patient')
    context = {
        'plans': plans,
        'patients': treated_patients,
        'metrics': CarePlan.Metric.choices,
        'directions': CarePlan.Direction.choices,
    }
    return render(request, 'providers/care_plans.html', context)


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------

@role_required(User.Role.PROVIDER)
def availability(request):
    profile = get_object_or_404(ProviderProfile, user=request.user)

    if request.method == 'POST':
        if request.POST.get('action') == 'remove':
            row = get_object_or_404(ProviderAvailability, pk=request.POST.get('row_id'), provider=profile)
            row.delete()
            messages.info(request, 'Availability window removed.')
            return redirect('provider_availability')

        weekday = request.POST.get('weekday', '').strip()
        start_raw = request.POST.get('start_time', '').strip()
        end_raw = request.POST.get('end_time', '').strip()
        if not (weekday.isdigit() and start_raw and end_raw):
            messages.error(request, 'Pick a day and both a start and end time.')
            return redirect('provider_availability')
        try:
            start_time = datetime.time.fromisoformat(start_raw)
            end_time = datetime.time.fromisoformat(end_raw)
        except ValueError:
            messages.error(request, 'Those times were not valid.')
            return redirect('provider_availability')
        if end_time <= start_time:
            messages.error(request, 'End time must be after start time.')
            return redirect('provider_availability')

        ProviderAvailability.objects.create(
            provider=profile, weekday=int(weekday), start_time=start_time, end_time=end_time,
        )
        messages.success(request, 'Availability window added.')
        return redirect('provider_availability')

    context = {
        'windows': ProviderAvailability.objects.filter(provider=profile),
        'weekdays': ProviderAvailability.Weekday.choices,
    }
    return render(request, 'providers/availability.html', context)


# --------------------------------------------------------------------------
# Health camps & wellness events
# --------------------------------------------------------------------------

@role_required(User.Role.PROVIDER)
def my_events(request):
    """
    Where a provider submits health camps and wellness programmes.

    Submitting always lands at PENDING. There is deliberately no code path
    here that sets APPROVED -- only `adminpanel.views.events` can do that.
    """
    profile = ProviderProfile.objects.filter(user=request.user).first()
    if profile is None:
        messages.error(request, 'Complete your provider profile first.')
        return redirect('provider_dashboard')

    if request.method == 'POST':
        if request.POST.get('action') == 'withdraw':
            event = get_object_or_404(HealthEvent, pk=request.POST.get('event_id'), provider=profile)
            event.delete()
            messages.info(request, 'Event withdrawn.')
            return redirect('provider_events')

        title = request.POST.get('title', '').strip()
        starts_raw = request.POST.get('starts_at', '').strip()
        if not (title and starts_raw):
            messages.error(request, 'An event needs at least a title and a start date/time.')
            return redirect('provider_events')
        try:
            starts_at = datetime.datetime.fromisoformat(starts_raw)
            if timezone.is_naive(starts_at):
                starts_at = timezone.make_aware(starts_at)
        except ValueError:
            messages.error(request, 'Please enter a valid start date and time.')
            return redirect('provider_events')

        capacity = request.POST.get('capacity', '').strip()
        event = HealthEvent.objects.create(
            provider=profile, title=title,
            kind=request.POST.get('kind', HealthEvent.Kind.CAMP),
            description=request.POST.get('description', '').strip(),
            venue=request.POST.get('venue', '').strip(),
            starts_at=starts_at,
            capacity=int(capacity) if capacity.isdigit() else None,
            is_free=bool(request.POST.get('is_free')),
        )
        AuditLog.record(request.user, 'Submitted a health event', event.title, AuditLog.Tag.WARN)
        messages.success(request, 'Submitted. An administrator reviews it before it goes public.')
        return redirect('provider_events')

    events = HealthEvent.objects.filter(provider=profile)
    context = {
        'profile': profile,
        'events': events,
        'pending_count': sum(1 for e in events if e.status == HealthEvent.Status.PENDING),
        'kinds': HealthEvent.Kind.choices,
    }
    return render(request, 'providers/events.html', context)


@login_required
def public_events(request):
    """
    The patient-facing listing. Reads `HealthEvent.public()` and nothing
    else, so an unapproved or expired event has no route to this page.
    """
    events = HealthEvent.public()
    kind = request.GET.get('kind', '').strip()
    if kind:
        events = events.filter(kind=kind)
    context = {
        'events': events,
        'selected_kind': kind,
        'kinds': HealthEvent.Kind.choices,
    }
    return render(request, 'providers/public_events.html', context)