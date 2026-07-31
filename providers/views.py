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

from accounts.decorators import role_required
from accounts.models import User
from adminpanel.models import AuditLog
from providers.models import Appointment, ProviderProfile


@role_required(User.Role.PATIENT, User.Role.CAREGIVER)
def directory(request):
    query = request.GET.get('q', '').strip()
    ptype = request.GET.get('type', '').strip()

    providers = ProviderProfile.objects.filter(
        verification_status=ProviderProfile.Verification.VERIFIED,
    ).select_related('user')

    if query:
        providers = providers.filter(
            Q(clinic_name__icontains=query) | Q(specialty__icontains=query)
            | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query)
        )
    if ptype:
        providers = providers.filter(provider_type=ptype)

    context = {
        'providers': providers,
        'query': query,
        'selected_type': ptype,
        'types': ProviderProfile.ProviderType.choices,
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


@role_required(User.Role.PROVIDER)
def dashboard(request):
    profile = ProviderProfile.objects.filter(user=request.user).first()
    if not profile:
        messages.info(request, 'Complete your provider profile to get started.')
        return redirect('provider_pending')
    if not profile.is_verified:
        return redirect('provider_pending')

    if request.method == 'POST':
        appt = get_object_or_404(Appointment, pk=request.POST.get('appointment_id'), provider=profile)
        action = request.POST.get('action')
        if action == 'accept':
            appt.status = Appointment.Status.CONFIRMED
            appt.save(update_fields=['status'])
            messages.success(request, f'Appointment with {appt.patient.display_name} confirmed.')
        elif action == 'decline':
            appt.status = Appointment.Status.DECLINED
            appt.save(update_fields=['status'])
            messages.info(request, 'Request declined.')
        elif action == 'complete':
            appt.status = Appointment.Status.COMPLETED
            appt.save(update_fields=['status'])
            messages.success(request, 'Marked as completed.')
        elif action == 'note':
            appt.provider_note = request.POST.get('note', '').strip()
            appt.save(update_fields=['provider_note'])
            messages.success(request, 'Note saved.')
        return redirect('provider_dashboard')

    appts = Appointment.objects.filter(provider=profile).select_related('patient')
    now = timezone.now()
    context = {
        'profile': profile,
        'requests': [a for a in appts if a.status == Appointment.Status.REQUESTED],
        'upcoming': [a for a in appts if a.status == Appointment.Status.CONFIRMED and a.scheduled_for >= now],
        'completed_count': sum(1 for a in appts if a.status == Appointment.Status.COMPLETED),
        'total_patients': len({a.patient_id for a in appts}),
    }
    return render(request, 'providers/dashboard.html', context)


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
