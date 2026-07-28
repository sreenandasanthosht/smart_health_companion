"""
adminpanel app views -- the platform Admin's dashboard: overview KPIs,
provider verification queue, user management, provider management and
the audit log.

Like the rest of the app right now, every context dict below is
placeholder/demo data. This app doesn't have its own models -- once the
real User/Provider/audit-log data exists (Phase 3/4 of the task plan),
these views will query the database instead of returning fixed demo
values. These pages exist now purely to preview the Admin experience.
"""
from django.shortcuts import render


def dashboard(request):
    context = {
        'admin_name': 'Admin',
        'total_users': '3,240',
        'verified_providers': 179,
        'pending_verifications': 7,
        'new_signups_today': 42,
        'new_signups_breakdown': '38 patients, 4 providers',
        'needs_attention': [
            {
                'text': '7 provider verifications pending review',
                'sub': 'Oldest submitted 4 days ago -- Prakash Diagnostics, Serene Minds, +5 more',
                'url_name': 'admin_verification',
                'cta': 'Review queue',
            },
            {
                'text': '2 announcements flagged for review',
                'sub': 'Reported by users -- "Monsoon health camp" & "Free BP check-up" posts',
                'url_name': None,
                'cta': 'Open announcements',
            },
            {
                'text': '3 user accounts awaiting support response',
                'sub': 'Password & account recovery tickets -- SLA under 24h',
                'url_name': 'admin_users',
                'cta': 'View users',
            },
        ],
        'today': [
            {'label': '42 new sign-ups', 'sub': '38 patients, 4 providers'},
            {'label': '94 medicine orders', 'sub': '81 delivered, 13 in progress'},
            {'label': '158 appointments booked', 'sub': 'Across 62 providers'},
            {'label': '27 record shares granted', 'sub': '6 revoked by patients'},
        ],
    }
    return render(request, 'adminpanel/dashboard.html', context)


def verification(request):
    context = {
        'queue': [
            {'name': 'Prakash Diagnostics', 'meta': 'Jayanagar, Bengaluru', 'type': 'Diagnostics', 'submitted': '20 Jul 2026', 'status': 'pending'},
            {'name': 'Serene Minds Wellness', 'meta': 'Indiranagar, Bengaluru', 'type': 'Wellness', 'submitted': '21 Jul 2026', 'status': 'pending'},
            {'name': 'Dr. Ravi Shankar', 'meta': 'Cardiologist', 'type': 'Doctor', 'submitted': '22 Jul 2026', 'status': 'pending'},
            {'name': 'HealWell Pharmacy', 'meta': 'Malleshwaram, Bengaluru', 'type': 'Pharmacy', 'submitted': '22 Jul 2026', 'status': 'pending'},
            {'name': 'FitLife Centre', 'meta': 'Koramangala, Bengaluru', 'type': 'Wellness', 'submitted': '18 Jul 2026', 'status': 'approved'},
        ],
    }
    return render(request, 'adminpanel/verification.html', context)


def users(request):
    context = {
        'users': [
            {'name': 'Latha R.', 'email': 'latha.r@gmail.com', 'role': 'Patient', 'status': 'active', 'joined': '12 Feb 2026', 'last_active': 'Today, 09:14'},
            {'name': 'Ramesh K.', 'email': 'ramesh.kumar@gmail.com', 'role': 'Patient', 'status': 'active', 'joined': '03 Mar 2026', 'last_active': 'Yesterday, 18:40'},
            {'name': 'Meera R.', 'email': 'meera.r@gmail.com', 'role': 'Caregiver', 'status': 'active', 'joined': '03 Mar 2026', 'last_active': 'Today, 08:02'},
            {'name': 'Dr. A. Nair', 'email': 'dr.anair@citycare.in', 'role': 'Provider', 'status': 'active', 'joined': '15 Jan 2026', 'last_active': 'Today, 07:55'},
            {'name': 'Suresh V.', 'email': 'suresh.v@gmail.com', 'role': 'Patient', 'status': 'suspended', 'joined': '09 Apr 2026', 'last_active': '02 Jul 2026'},
            {'name': 'Prakash Diagnostics', 'email': 'lab@prakashdiag.in', 'role': 'Provider', 'status': 'pending', 'joined': '20 Jul 2026', 'last_active': 'Today, 10:41'},
        ],
    }
    return render(request, 'adminpanel/users.html', context)


def providers(request):
    context = {
        'providers': [
            {'name': 'Dr. A. Nair', 'meta': 'General Physician, Indiranagar', 'type': 'Doctor', 'verification': 'verified', 'rating': '4.8', 'listings': 3},
            {'name': 'City Care Clinic', 'meta': 'Multi-speciality, Koramangala', 'type': 'Clinic', 'verification': 'verified', 'rating': '4.4', 'listings': 12},
            {'name': 'Prakash Diagnostics', 'meta': 'Pathology & Imaging, Jayanagar', 'type': 'Diagnostics', 'verification': 'pending', 'rating': None, 'listings': 0},
            {'name': 'MedPlus Pharmacy', 'meta': '24x7 Store, HSR Layout', 'type': 'Pharmacy', 'verification': 'verified', 'rating': '4.2', 'listings': None},
            {'name': 'FitLife Centre', 'meta': 'Gym & Personal Training, Koramangala', 'type': 'Fitness', 'verification': 'verified', 'rating': '4.7', 'listings': 6},
            {'name': 'Dr. Ravi Shankar', 'meta': 'Cardiologist, Whitefield', 'type': 'Doctor', 'verification': 'rejected', 'rating': None, 'listings': 0},
        ],
    }
    return render(request, 'adminpanel/providers.html', context)


def audit_log(request):
    context = {
        'entries': [
            {'date': '24 Jul 2026', 'time': '10:42', 'actor': 'Admin', 'action': 'Approved provider', 'tag': 'ok', 'target': 'Dr. A. Nair'},
            {'date': '24 Jul 2026', 'time': '10:15', 'actor': 'Latha R.', 'action': 'Revoked a record share', 'tag': 'muted', 'target': 'Dr. A. Nair -- BP report'},
            {'date': '24 Jul 2026', 'time': '09:58', 'actor': 'MedPlus', 'action': 'Marked order delivered', 'tag': 'muted', 'target': 'Order #1042 -- Ramesh K.'},
            {'date': '24 Jul 2026', 'time': '09:31', 'actor': 'Admin', 'action': 'Suspended user', 'tag': 'danger', 'target': 'Suresh V. -- spam reports'},
            {'date': '23 Jul 2026', 'time': '16:05', 'actor': 'Admin', 'action': 'Rejected provider', 'tag': 'danger', 'target': 'Dr. Ravi Shankar -- invalid licence'},
            {'date': '22 Jul 2026', 'time': '19:47', 'actor': 'Prakash Diagnostics', 'action': 'Submitted documents', 'tag': 'warn', 'target': 'NABL cert, GST reg'},
        ],
    }
    return render(request, 'adminpanel/audit_log.html', context)
