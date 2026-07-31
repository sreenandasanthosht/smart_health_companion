"""
adminpanel app views -- the platform Admin's dashboard: overview KPIs, the
provider verification queue, user management, provider management and the
audit log.

Distinct from Django's own /admin/ site: this is the in-app admin surface,
restricted to users whose role is ADMIN.
"""
import datetime

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from accounts.models import CaregiverLink, User
from adminpanel.models import AuditLog
from health.models import ConsentGrant, VitalRecord
from nursing.models import NurseAssignment, NursingVisit
from providers.models import Appointment, ProviderProfile


@role_required(User.Role.ADMIN)
def dashboard(request):
    today = timezone.localdate()
    start_of_today = timezone.make_aware(
        datetime.datetime.combine(today, datetime.time.min), timezone.get_current_timezone())

    total_users = User.objects.count()
    pending_profiles = ProviderProfile.objects.filter(
        verification_status=ProviderProfile.Verification.PENDING).select_related('user')
    pending_count = pending_profiles.count()
    verified_count = ProviderProfile.objects.filter(
        verification_status=ProviderProfile.Verification.VERIFIED).count()

    new_today = User.objects.filter(date_joined__gte=start_of_today)
    breakdown = new_today.values('role').annotate(n=Count('id'))
    breakdown_text = ', '.join(
        f"{row['n']} {User.Role(row['role']).label.lower()}{'s' if row['n'] != 1 else ''}"
        for row in breakdown
    ) or 'No sign-ups yet today'

    needs_attention = []
    if pending_count:
        oldest = pending_profiles.order_by('submitted_at').first()
        names = ', '.join(p.display_name() for p in pending_profiles[:3])
        days = (timezone.now() - oldest.submitted_at).days
        needs_attention.append({
            'text': f"{pending_count} provider verification{'s' if pending_count != 1 else ''} pending review",
            'sub': f"Oldest submitted {days} day{'s' if days != 1 else ''} ago -- {names}",
            'url_name': 'admin_verification', 'cta': 'Review queue',
        })

    incomplete = ProviderProfile.objects.filter(
        verification_status=ProviderProfile.Verification.NEEDS_INFO).count()
    if incomplete:
        needs_attention.append({
            'text': f"{incomplete} provider{'s' if incomplete != 1 else ''} asked for more information",
            'sub': 'Waiting on the provider to resubmit documents',
            'url_name': 'admin_providers', 'cta': 'View providers',
        })

    pending_links = CaregiverLink.objects.filter(status=CaregiverLink.Status.PENDING).count()
    if pending_links:
        needs_attention.append({
            'text': f"{pending_links} caregiver link request{'s' if pending_links != 1 else ''} awaiting patient approval",
            'sub': 'Patients approve these themselves -- shown here for visibility',
            'url_name': 'admin_users', 'cta': 'View users',
        })

    urgent_visits = NursingVisit.objects.filter(
        escalated=True, severity=NursingVisit.Severity.URGENT,
        visited_at__gte=timezone.now() - datetime.timedelta(days=7)).count()
    if urgent_visits:
        needs_attention.append({
            'text': f"{urgent_visits} urgent nursing escalation{'s' if urgent_visits != 1 else ''} this week",
            'sub': 'Raised by nurses during home visits',
            'url_name': None, 'cta': '',
        })

    suspended = User.objects.filter(is_suspended=True).count()
    if suspended:
        needs_attention.append({
            'text': f"{suspended} suspended account{'s' if suspended != 1 else ''}",
            'sub': 'Review whether these should be reinstated',
            'url_name': 'admin_users', 'cta': 'View users',
        })

    appts_today = Appointment.objects.filter(
        scheduled_for__gte=start_of_today,
        scheduled_for__lt=start_of_today + datetime.timedelta(days=1)).count()
    shares_active = sum(1 for g in ConsentGrant.objects.all() if g.is_active())
    shares_revoked = ConsentGrant.objects.filter(revoked_at__isnull=False).count()
    vitals_today = VitalRecord.objects.filter(recorded_at__gte=start_of_today).count()

    context = {
        'admin_name': request.user.display_name,
        'total_users': total_users,
        'verified_providers': verified_count,
        'pending_verifications': pending_count,
        'new_signups_today': new_today.count(),
        'new_signups_breakdown': breakdown_text,
        'needs_attention': needs_attention,
        'today': [
            {'label': f"{new_today.count()} new sign-ups", 'sub': breakdown_text},
            {'label': f"{vitals_today} vitals logged", 'sub': 'Across all patients today'},
            {'label': f"{appts_today} appointments scheduled", 'sub': f"Across {verified_count} verified providers"},
            {'label': f"{shares_active} active record shares", 'sub': f"{shares_revoked} revoked in total"},
        ],
        'recent_audit': AuditLog.objects.all()[:6],
        'role_counts': User.objects.values('role').annotate(n=Count('id')).order_by('-n'),
    }
    return render(request, 'adminpanel/dashboard.html', context)


@role_required(User.Role.ADMIN)
def verification(request):
    if request.method == 'POST':
        profile = get_object_or_404(ProviderProfile, pk=request.POST.get('profile_id'))
        action = request.POST.get('action')
        if action == 'approve':
            profile.approve()
            AuditLog.record(request.user, 'Approved provider', profile.display_name(), AuditLog.Tag.OK)
            messages.success(request, f'{profile.display_name()} is now verified and listed in the directory.')
        elif action == 'needs_info':
            note = request.POST.get('note', '').strip() or 'Documents incomplete or unclear.'
            profile.request_more_info(note)
            AuditLog.record(request.user, 'Requested more information',
                            f"{profile.display_name()} -- {note}", AuditLog.Tag.DANGER)
            messages.info(request, f'{profile.display_name()} has been asked to resubmit.')
        return redirect('admin_verification')

    queue = ProviderProfile.objects.select_related('user').order_by('verification_status', 'submitted_at')
    context = {
        'queue': queue,
        'pending_count': sum(1 for p in queue if p.verification_status == ProviderProfile.Verification.PENDING),
    }
    return render(request, 'adminpanel/verification.html', context)


@role_required(User.Role.ADMIN)
def users(request):
    if request.method == 'POST':
        target = get_object_or_404(User, pk=request.POST.get('user_id'))
        action = request.POST.get('action')
        if target == request.user:
            messages.error(request, "You can't change your own account from here.")
        elif action == 'suspend':
            target.is_suspended = True
            target.save(update_fields=['is_suspended'])
            AuditLog.record(request.user, 'Suspended user', target.display_name, AuditLog.Tag.DANGER)
            messages.info(request, f'{target.display_name} has been suspended.')
        elif action == 'reinstate':
            target.is_suspended = False
            target.save(update_fields=['is_suspended'])
            AuditLog.record(request.user, 'Reinstated user', target.display_name, AuditLog.Tag.OK)
            messages.success(request, f'{target.display_name} has been reinstated.')
        elif action == 'make_nurse':
            target.role = User.Role.NURSE
            target.save(update_fields=['role'])
            AuditLog.record(request.user, 'Assigned Nurse role', target.display_name, AuditLog.Tag.WARN)
            messages.success(request, f'{target.display_name} is now a Nurse.')
        return redirect('admin_users')

    query = request.GET.get('q', '').strip()
    role = request.GET.get('role', '').strip()
    people = User.objects.all().order_by('-date_joined')
    if query:
        people = people.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
            | Q(first_name__icontains=query) | Q(unique_id__icontains=query))
    if role:
        people = people.filter(role=role)

    context = {
        'users': people[:100],
        'query': query,
        'selected_role': role,
        'roles': User.Role.choices,
        'total': people.count(),
    }
    return render(request, 'adminpanel/users.html', context)


@role_required(User.Role.ADMIN)
def providers(request):
    profiles = ProviderProfile.objects.select_related('user').annotate(
        appointment_count=Count('appointments'))
    context = {
        'providers': profiles,
        'verified': sum(1 for p in profiles if p.is_verified),
    }
    return render(request, 'adminpanel/providers.html', context)


@role_required(User.Role.ADMIN)
def audit_log(request):
    tag = request.GET.get('tag', '').strip()
    entries = AuditLog.objects.select_related('actor')
    if tag:
        entries = entries.filter(tag=tag)
    context = {
        'entries': entries[:200],
        'selected_tag': tag,
        'tags': AuditLog.Tag.choices,
    }
    return render(request, 'adminpanel/audit_log.html', context)


@role_required(User.Role.ADMIN)
def nursing(request):
    """Assign nurses to patients and review escalations."""
    if request.method == 'POST':
        nurse = User.objects.filter(pk=request.POST.get('nurse_id'), role=User.Role.NURSE).first()
        patient = User.objects.filter(pk=request.POST.get('patient_id'), role=User.Role.PATIENT).first()
        if not (nurse and patient):
            messages.error(request, 'Pick both a nurse and a patient.')
        elif NurseAssignment.objects.filter(nurse=nurse, patient=patient, end_date__isnull=True).exists():
            messages.info(request, 'That nurse is already assigned to this patient.')
        else:
            NurseAssignment.objects.create(nurse=nurse, patient=patient, assigned_by=request.user)
            AuditLog.record(request.user, 'Assigned nurse',
                            f"{nurse.display_name} -> {patient.display_name}", AuditLog.Tag.OK)
            messages.success(request, f'{nurse.display_name} assigned to {patient.display_name}.')
        return redirect('admin_nursing')

    context = {
        'assignments': NurseAssignment.objects.select_related('nurse', 'patient'),
        'nurses': User.objects.filter(role=User.Role.NURSE),
        'patients': User.objects.filter(role=User.Role.PATIENT),
        'escalations': NursingVisit.objects.filter(escalated=True).select_related('nurse', 'patient')[:20],
    }
    return render(request, 'adminpanel/nursing.html', context)
