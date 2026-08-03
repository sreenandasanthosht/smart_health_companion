"""
adminpanel app views -- the platform Admin's management surface, per
CareNest_Admin_Module_Proposal.docx.

Two tiers share these pages:
  * Admin       -- verification, users, caregivers, complaints, events,
                   announcements, analytics, audit log
  * Super Admin -- all of the above, plus Admin account management and
                   system settings

Distinct from Django's own /admin/ site: this is the in-app admin surface,
restricted to users whose role is ADMIN.
"""
import datetime

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required, super_admin_required
from accounts.models import CaregiverLink, Notification, User
from adminpanel.models import Announcement, AuditLog, Complaint, PlatformSettings
from health.models import ConsentGrant, MoodLog, VitalRecord
from nursing.models import NurseAssignment, NursingVisit
from providers.models import Appointment, HealthEvent, ProviderProfile


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
    registered_providers = ProviderProfile.objects.count()
    pending_events = HealthEvent.objects.filter(status=HealthEvent.Status.PENDING).count()
    open_complaints = Complaint.objects.filter(status__in=Complaint.OPEN_STATUSES).count()

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

    if pending_events:
        needs_attention.append({
            'text': f"{pending_events} event{'s' if pending_events != 1 else ''} awaiting approval",
            'sub': 'Health camps and wellness programmes stay hidden until approved',
            'url_name': 'admin_events', 'cta': 'Review events',
        })

    if open_complaints:
        needs_attention.append({
            'text': f"{open_complaints} open complaint{'s' if open_complaints != 1 else ''}",
            'sub': 'Reports raised by users, not yet resolved',
            'url_name': 'admin_complaints', 'cta': 'Review complaints',
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
        'admin_tier': request.user.admin_tier_label,
        'is_super_admin': request.user.is_platform_super_admin,
        # The five cards the Admin Module proposal names, in its order.
        'cards': [
            {'label': 'Pending provider verifications', 'value': pending_count,
             'url_name': 'admin_verification', 'tint': 'tint-orange'},
            {'label': 'Pending event approvals', 'value': pending_events,
             'url_name': 'admin_events', 'tint': 'tint-purple'},
            {'label': 'Total users', 'value': total_users,
             'url_name': 'admin_users', 'tint': 'tint-green'},
            {'label': 'Registered providers', 'value': registered_providers,
             'url_name': 'admin_providers', 'tint': 'tint-green'},
            {'label': 'Open complaints', 'value': open_complaints,
             'url_name': 'admin_complaints', 'tint': 'tint-orange'},
        ],
        'total_users': total_users,
        'verified_providers': verified_count,
        'pending_verifications': pending_count,
        'pending_events': pending_events,
        'open_complaints': open_complaints,
        'registered_providers': registered_providers,
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
            Notification.send(
                profile.user,
                title='Your provider account is verified',
                body='You are now listed in the directory and can receive appointments.',
                kind=Notification.Kind.GENERAL,
                action_url_name='provider_dashboard',
            )
            messages.success(request, f'{profile.display_name()} is now verified and listed in the directory.')
        elif action == 'needs_info':
            note = request.POST.get('note', '').strip() or 'Documents incomplete or unclear.'
            profile.request_more_info(note)
            AuditLog.record(request.user, 'Requested more information',
                            f"{profile.display_name()} -- {note}", AuditLog.Tag.DANGER)
            Notification.send(
                profile.user,
                title='More information needed for verification',
                body=note,
                kind=Notification.Kind.GENERAL,
                level=Notification.Level.ACTION,
                action_url_name='provider_pending',
            )
            messages.info(request, f'{profile.display_name()} has been asked to resubmit.')
        elif action == 'reject':
            # The proposal's workflow is explicitly "approve or reject".
            # Rejection is distinct from asking for more information: it
            # ends the review rather than pausing it, and the provider
            # stays out of the directory.
            note = request.POST.get('note', '').strip() or 'Verification rejected.'
            profile.reject(note)
            AuditLog.record(request.user, 'Rejected provider',
                            f"{profile.display_name()} -- {note}", AuditLog.Tag.DANGER)
            Notification.send(
                profile.user,
                title='Your verification request was rejected',
                body=note,
                kind=Notification.Kind.GENERAL,
                level=Notification.Level.WARNING,
                action_url_name='provider_pending',
            )
            messages.info(request, f'{profile.display_name()} has been rejected.')
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


# --------------------------------------------------------------------------
# Caregiver management
# --------------------------------------------------------------------------

@role_required(User.Role.ADMIN)
def caregivers(request):
    """
    Oversight of caregiver links -- who is linked to whom, and what each
    one can actually see.

    An Admin can *revoke* a link (a safety valve, e.g. after an upheld
    complaint) but deliberately cannot approve one. Approval is the
    patient's decision alone; letting an Admin grant access on their
    behalf would hollow out the whole caregiver consent model.
    """
    if request.method == 'POST':
        link = get_object_or_404(CaregiverLink, pk=request.POST.get('link_id'))
        if request.POST.get('action') == 'revoke':
            link.status = CaregiverLink.Status.REJECTED
            link.decided_at = timezone.now()
            link.save(update_fields=['status', 'decided_at'])
            # Withdraw the consent that rode along with the link.
            for grant in ConsentGrant.objects.filter(
                    patient=link.patient, recipient=link.caregiver, revoked_at__isnull=True):
                grant.revoke()
            AuditLog.record(request.user, 'Revoked a caregiver link',
                            f'{link.caregiver.display_name} -> {link.patient.display_name}',
                            AuditLog.Tag.DANGER)
            Notification.send(
                link.patient,
                title='A caregiver link was removed by an administrator',
                body=f'{link.caregiver.display_name} no longer has access to your data.',
                kind=Notification.Kind.CAREGIVER_DECISION,
                level=Notification.Level.WARNING,
            )
            messages.info(request, f'Link between {link.caregiver.display_name} and '
                                   f'{link.patient.display_name} revoked.')
        return redirect('admin_caregivers')

    links = CaregiverLink.objects.select_related('patient', 'caregiver').order_by('-requested_at')
    rows = []
    for link in links:
        grant = ConsentGrant.objects.filter(
            patient=link.patient, recipient=link.caregiver, revoked_at__isnull=True).first()
        rows.append({
            'link': link,
            'scopes': grant.scope_label() if grant else 'Nothing shared',
            'restricted': ', '.join(grant.restricted_scope_list()) if grant else '',
        })

    context = {
        'rows': rows,
        'approved': sum(1 for r in rows if r['link'].status == CaregiverLink.Status.APPROVED),
        'pending': sum(1 for r in rows if r['link'].status == CaregiverLink.Status.PENDING),
    }
    return render(request, 'adminpanel/caregivers.html', context)


# --------------------------------------------------------------------------
# Reports & complaints
# --------------------------------------------------------------------------

@role_required(User.Role.ADMIN)
def complaints(request):
    if request.method == 'POST':
        complaint = get_object_or_404(Complaint, pk=request.POST.get('complaint_id'))
        action = request.POST.get('action')
        note = request.POST.get('note', '').strip()
        mapping = {
            'review': Complaint.Status.IN_REVIEW,
            'resolve': Complaint.Status.RESOLVED,
            'dismiss': Complaint.Status.DISMISSED,
        }
        status = mapping.get(action)
        if status is None:
            messages.error(request, 'Unknown action.')
        else:
            complaint.resolve(request.user, status, note)
            AuditLog.record(
                request.user, f'Marked complaint {complaint.get_status_display().lower()}',
                complaint.subject,
                AuditLog.Tag.OK if status == Complaint.Status.RESOLVED else AuditLog.Tag.WARN)
            if complaint.reporter and not complaint.is_open:
                Notification.send(
                    complaint.reporter,
                    title=f'Your report was {complaint.get_status_display().lower()}',
                    body=note or complaint.subject,
                    kind=Notification.Kind.GENERAL,
                )
            messages.success(request, f'Complaint marked {complaint.get_status_display().lower()}.')
        return redirect('admin_complaints')

    status_filter = request.GET.get('status', '').strip()
    items = Complaint.objects.select_related('reporter', 'against_user', 'handled_by')
    if status_filter:
        items = items.filter(status=status_filter)

    context = {
        'complaints': items[:150],
        'selected_status': status_filter,
        'statuses': Complaint.Status.choices,
        'open_count': Complaint.objects.filter(status__in=Complaint.OPEN_STATUSES).count(),
    }
    return render(request, 'adminpanel/complaints.html', context)


# --------------------------------------------------------------------------
# Health camp / event approval
# --------------------------------------------------------------------------

@role_required(User.Role.ADMIN)
def events(request):
    if request.method == 'POST':
        event = get_object_or_404(HealthEvent, pk=request.POST.get('event_id'))
        action = request.POST.get('action')
        note = request.POST.get('note', '').strip()
        if action == 'approve':
            event.approve(request.user, note)
            AuditLog.record(request.user, 'Approved a health event',
                            f'{event.title} -- {event.provider.display_name()}', AuditLog.Tag.OK)
            Notification.send(
                event.provider.user,
                title=f'"{event.title}" was approved',
                body='It is now visible to patients in the events listing.',
                kind=Notification.Kind.GENERAL,
            )
            messages.success(request, f'"{event.title}" is now public.')
        elif action == 'reject':
            event.reject(request.user, note or 'Did not meet platform guidelines.')
            AuditLog.record(request.user, 'Rejected a health event',
                            f'{event.title} -- {note}', AuditLog.Tag.WARN)
            Notification.send(
                event.provider.user,
                title=f'"{event.title}" was not approved',
                body=event.review_note,
                kind=Notification.Kind.GENERAL,
                level=Notification.Level.WARNING,
            )
            messages.info(request, f'"{event.title}" rejected.')
        return redirect('admin_events')

    queue = HealthEvent.objects.select_related('provider', 'provider__user').order_by(
        'status', 'starts_at')
    context = {
        'queue': queue,
        'pending_count': sum(1 for e in queue if e.status == HealthEvent.Status.PENDING),
        'approved_count': sum(1 for e in queue if e.status == HealthEvent.Status.APPROVED),
    }
    return render(request, 'adminpanel/events.html', context)


# --------------------------------------------------------------------------
# Announcements
# --------------------------------------------------------------------------

@role_required(User.Role.ADMIN)
def announcements(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action == 'publish':
            announcement = get_object_or_404(Announcement, pk=request.POST.get('announcement_id'))
            sent = announcement.publish()
            AuditLog.record(request.user, 'Published an announcement',
                            f'{announcement.title} -- {sent} recipients', AuditLog.Tag.OK)
            messages.success(request, f'Published to {sent} '
                                      f"{'person' if sent == 1 else 'people'}.")
            return redirect('admin_announcements')

        if action == 'delete':
            announcement = get_object_or_404(Announcement, pk=request.POST.get('announcement_id'))
            if announcement.is_published:
                messages.error(request, 'A published announcement can\'t be deleted -- people have already seen it.')
            else:
                announcement.delete()
                messages.info(request, 'Draft deleted.')
            return redirect('admin_announcements')

        title = request.POST.get('title', '').strip()
        body = request.POST.get('body', '').strip()
        if not (title and body):
            messages.error(request, 'An announcement needs both a title and a message.')
        else:
            Announcement.objects.create(
                author=request.user, title=title, body=body,
                audience=request.POST.get('audience', Announcement.Audience.ALL),
            )
            messages.success(request, 'Draft saved. Publish it when you are ready.')
        return redirect('admin_announcements')

    items = list(Announcement.objects.select_related('author'))
    context = {
        'drafts': [a for a in items if not a.is_published],
        'published': [a for a in items if a.is_published],
        'audiences': Announcement.Audience.choices,
    }
    return render(request, 'adminpanel/announcements.html', context)


# --------------------------------------------------------------------------
# Platform analytics
# --------------------------------------------------------------------------

@role_required(User.Role.ADMIN)
def analytics(request):
    """
    Aggregate platform health. Counts only -- no page here reaches into an
    individual's records, and mental-health entries are counted but never
    read, matching the hard exclusion in the consent framework.
    """
    now = timezone.now()
    month_ago = now - datetime.timedelta(days=30)
    week_ago = now - datetime.timedelta(days=7)

    role_rows = []
    total = User.objects.count() or 1
    for value, label in User.Role.choices:
        n = User.objects.filter(role=value).count()
        role_rows.append({'label': label, 'count': n, 'pct': int(round(n / total * 100))})

    verification_rows = []
    provider_total = ProviderProfile.objects.count() or 1
    for value, label in ProviderProfile.Verification.choices:
        n = ProviderProfile.objects.filter(verification_status=value).count()
        verification_rows.append({'label': label, 'count': n,
                                  'pct': int(round(n / provider_total * 100))})

    appointment_rows = []
    for value, label in Appointment.Status.choices:
        appointment_rows.append({'label': label,
                                 'count': Appointment.objects.filter(status=value).count()})

    context = {
        'growth': [
            {'label': 'New sign-ups (30 days)', 'value': User.objects.filter(date_joined__gte=month_ago).count()},
            {'label': 'New sign-ups (7 days)', 'value': User.objects.filter(date_joined__gte=week_ago).count()},
            {'label': 'Suspended accounts', 'value': User.objects.filter(is_suspended=True).count()},
            {'label': 'Total users', 'value': User.objects.count()},
        ],
        'activity': [
            {'label': 'Vitals logged (30 days)', 'value': VitalRecord.objects.filter(recorded_at__gte=month_ago).count()},
            {'label': 'Appointments booked (30 days)', 'value': Appointment.objects.filter(created_at__gte=month_ago).count()},
            {'label': 'Nursing visits (30 days)', 'value': NursingVisit.objects.filter(visited_at__gte=month_ago).count()},
            {'label': 'Mood check-ins (30 days)', 'value': MoodLog.objects.filter(date__gte=month_ago.date()).count()},
        ],
        'trust': [
            {'label': 'Active record shares', 'value': sum(1 for g in ConsentGrant.objects.all() if g.is_active())},
            {'label': 'Revoked shares', 'value': ConsentGrant.objects.filter(revoked_at__isnull=False).count()},
            {'label': 'Approved caregiver links', 'value': CaregiverLink.objects.filter(status=CaregiverLink.Status.APPROVED).count()},
            {'label': 'Open complaints', 'value': Complaint.objects.filter(status__in=Complaint.OPEN_STATUSES).count()},
        ],
        'role_rows': role_rows,
        'verification_rows': verification_rows,
        'appointment_rows': appointment_rows,
        'events_approved': HealthEvent.objects.filter(status=HealthEvent.Status.APPROVED).count(),
        'events_pending': HealthEvent.objects.filter(status=HealthEvent.Status.PENDING).count(),
        'events_rejected': HealthEvent.objects.filter(status=HealthEvent.Status.REJECTED).count(),
    }
    return render(request, 'adminpanel/analytics.html', context)


# --------------------------------------------------------------------------
# Super Admin only: admin accounts and system settings
# --------------------------------------------------------------------------

@super_admin_required
def admin_accounts(request):
    """
    "Additional Admin accounts can only be created by the Super Admin."

    This is the only place an ADMIN role can be granted anywhere in the
    codebase -- the public registration form excludes it, and the user
    management page can only promote to Nurse.
    """
    if request.method == 'POST':
        action = request.POST.get('action', 'create')

        if action in {'promote', 'demote', 'revoke'}:
            target = get_object_or_404(User, pk=request.POST.get('user_id'))
            if target == request.user:
                messages.error(request, "You can't change your own admin status.")
            elif action == 'promote':
                target.is_super_admin = True
                target.save(update_fields=['is_super_admin'])
                AuditLog.record(request.user, 'Promoted to Super Admin', target.display_name, AuditLog.Tag.DANGER)
                messages.success(request, f'{target.display_name} is now a Super Admin.')
            elif action == 'demote':
                target.is_super_admin = False
                target.save(update_fields=['is_super_admin'])
                AuditLog.record(request.user, 'Demoted to Admin', target.display_name, AuditLog.Tag.WARN)
                messages.info(request, f'{target.display_name} is now a standard Admin.')
            else:  # revoke admin entirely
                target.role = User.Role.PATIENT
                target.is_super_admin = False
                target.save(update_fields=['role', 'is_super_admin'])
                AuditLog.record(request.user, 'Revoked admin access', target.display_name, AuditLog.Tag.DANGER)
                messages.info(request, f'{target.display_name} no longer has admin access.')
            return redirect('admin_accounts')

        # Create a new Admin account.
        full_name = request.POST.get('full_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        make_super = bool(request.POST.get('is_super_admin'))

        if not (full_name and email and password):
            messages.error(request, 'Name, email and password are all required.')
            return redirect('admin_accounts')
        if User.objects.filter(username__iexact=email).exists():
            messages.error(request, 'An account with that email already exists.')
            return redirect('admin_accounts')
        try:
            validate_password(password)
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return redirect('admin_accounts')

        first_name, _, last_name = full_name.partition(' ')
        new_admin = User.objects.create_user(
            username=email, email=email, password=password,
            first_name=first_name, last_name=last_name,
            role=User.Role.ADMIN, is_super_admin=make_super,
        )
        AuditLog.record(
            request.user,
            'Created a Super Admin account' if make_super else 'Created an Admin account',
            new_admin.display_name, AuditLog.Tag.DANGER)
        Notification.send(
            new_admin,
            title='Your CareNest admin account is ready',
            body=f'Created by {request.user.display_name}.',
            kind=Notification.Kind.GENERAL,
            action_url_name='admin_dashboard',
        )
        messages.success(request, f'Admin account created for {new_admin.display_name}.')
        return redirect('admin_accounts')

    admins = User.objects.filter(role=User.Role.ADMIN).order_by('-is_super_admin', 'date_joined')
    context = {
        'admins': admins,
        'super_count': admins.filter(is_super_admin=True).count(),
    }
    return render(request, 'adminpanel/admin_accounts.html', context)


@super_admin_required
def settings_view(request):
    config = PlatformSettings.load()

    if request.method == 'POST':
        config.provider_self_registration_open = bool(request.POST.get('provider_self_registration_open'))
        config.caregiver_device_approval_required = bool(request.POST.get('caregiver_device_approval_required'))
        config.platform_notice = request.POST.get('platform_notice', '').strip()
        config.updated_by = request.user
        config.save()
        AuditLog.record(request.user, 'Updated platform settings', '', AuditLog.Tag.WARN)
        messages.success(request, 'Settings saved.')
        return redirect('admin_settings')

    return render(request, 'adminpanel/settings.html', {'config': config})
