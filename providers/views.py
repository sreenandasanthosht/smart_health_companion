"""
providers app views -- the provider directory, appointment booking, the
provider's own dashboard, and the verification status page.

All data here comes from the database.
"""
import datetime

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from django.contrib.auth.decorators import login_required

from accounts.decorators import role_required
from accounts.models import User
from adminpanel.models import AuditLog
from providers.dashboards import GROUP_DASHBOARDS, services_page
from providers.models import Appointment, HealthEvent, ProviderProfile


@role_required(User.Role.PATIENT, User.Role.CAREGIVER)
def directory(request):
    query = request.GET.get('q', '').strip()
    ptype = request.GET.get('type', '').strip()
    group = request.GET.get('group', '').strip()

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

    context = {
        'providers': providers,
        'query': query,
        'selected_type': ptype,
        'selected_group': group,
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
                if when < timezone.now():
                    messages.error(request, 'Pick a time in the future.')
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
