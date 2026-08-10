"""
The six provider service-group dashboards.

`providers.views.dashboard` is a thin dispatcher: it loads the signed-in
provider's profile, checks verification, then hands off to whichever
function below matches `profile.service_group`. Each function owns one
module's screen and the POST actions on it.

Why one file instead of six apps: every group shares the same profile,
the same verification flow and the same directory listing. Only the core
working flow differs, and that is exactly what lives here.

    CLINICAL       small clinics, small hospitals   -> appointments, departments
    MENTAL_HEALTH  psychologists / counsellors      -> counselling sessions
    DIAGNOSTICS    diagnostic labs                  -> test catalogue, bookings, results
    PHARMACY       pharmacies                       -> medicine orders
    WELLNESS       gyms, dieticians, yoga centres   -> programmes, enrolments, sessions
    HOME_CARE      home nurse providers             -> staff, care requests
"""
import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from providers.models import (
    Appointment, CounsellingSession, Department, HomeCareRequest, HomeCareStaff,
    LabTest, MedicineOrder, OrderItem, ProgrammeEnrolment, ProgrammeSession,
    ProviderProfile, ServiceOffering, TestBooking, TestResultValue,
    WellnessProgramme,
)


# --------------------------------------------------------------------------
# Small parsing helpers. Every dashboard reads plain POST fields, so these
# keep "the user typed nonsense" from becoming a 500.
# --------------------------------------------------------------------------

def _to_int(raw, default=None):
    raw = (raw or '').strip()
    return int(raw) if raw.isdigit() else default


def _to_decimal(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _to_date(raw):
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _to_datetime(date_raw, time_raw='00:00'):
    date_raw = (date_raw or '').strip()
    time_raw = (time_raw or '').strip() or '00:00'
    if not date_raw:
        return None
    try:
        naive = datetime.datetime.fromisoformat(f"{date_raw}T{time_raw}")
    except ValueError:
        return None
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _base_context(profile, active):
    """Everything the shared sidebar and page header need."""
    return {
        'profile': profile,
        'active': active,
        'group': profile.service_group,
        'group_label': profile.service_group_label,
        'services': profile.services.filter(is_active=True),
    }


# ==========================================================================
# 1. Clinical Care -- small clinics and small hospitals
# ==========================================================================

def clinical_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_department':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'A department needs a name.')
            elif profile.departments.filter(name__iexact=name).exists():
                messages.error(request, f'You already have a department called {name}.')
            else:
                Department.objects.create(
                    provider=profile, name=name,
                    head_name=request.POST.get('head_name', '').strip(),
                    description=request.POST.get('description', '').strip(),
                    consulting_hours=request.POST.get('consulting_hours', '').strip(),
                )
                messages.success(request, f'Department "{name}" added.')
            return redirect('provider_dashboard')

        if action == 'remove_department':
            dept = get_object_or_404(Department, pk=request.POST.get('department_id'), provider=profile)
            dept.delete()
            messages.info(request, 'Department removed.')
            return redirect('provider_dashboard')

        # Everything else acts on one appointment.
        appt = get_object_or_404(Appointment, pk=request.POST.get('appointment_id'), provider=profile)
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
        elif action == 'consult_note':
            appt.diagnosis = request.POST.get('diagnosis', '').strip()
            appt.advice = request.POST.get('advice', '').strip()
            appt.provider_note = request.POST.get('note', '').strip()
            appt.follow_up_on = _to_date(request.POST.get('follow_up_on'))
            appt.save(update_fields=['diagnosis', 'advice', 'provider_note', 'follow_up_on'])
            messages.success(request, 'Consultation record saved.')
        return redirect('provider_dashboard')

    appts = Appointment.objects.filter(provider=profile).select_related('patient', 'department')
    now = timezone.now()
    context = _base_context(profile, 'dashboard')
    context.update({
        'requests': [a for a in appts if a.status == Appointment.Status.REQUESTED],
        'upcoming': [a for a in appts if a.status == Appointment.Status.CONFIRMED and a.scheduled_for >= now],
        'completed': [a for a in appts if a.status == Appointment.Status.COMPLETED][:10],
        'completed_count': sum(1 for a in appts if a.status == Appointment.Status.COMPLETED),
        'total_patients': len({a.patient_id for a in appts}),
        'follow_ups': [a for a in appts if a.follow_up_on and a.follow_up_on >= timezone.localdate()],
        'departments': profile.departments.all(),
    })
    return render(request, 'providers/dash_clinical.html', context)


# ==========================================================================
# 2. Mental Health -- psychologists and counsellors
# ==========================================================================

def mental_health_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')
        session = get_object_or_404(
            CounsellingSession, pk=request.POST.get('session_id'), provider=profile)

        if action == 'accept':
            session.status = CounsellingSession.Status.CONFIRMED
            session.save(update_fields=['status'])
            messages.success(request, 'Session confirmed.')
        elif action == 'decline':
            session.status = CounsellingSession.Status.DECLINED
            session.save(update_fields=['status'])
            messages.info(request, 'Session declined.')
        elif action == 'complete':
            session.status = CounsellingSession.Status.COMPLETED
            session.save(update_fields=['status'])
            messages.success(request, 'Session marked complete.')
        elif action == 'notes':
            # private_notes is never rendered outside this dashboard.
            session.private_notes = request.POST.get('private_notes', '').strip()
            session.shared_summary = request.POST.get('shared_summary', '').strip()
            session.follow_up_on = _to_date(request.POST.get('follow_up_on'))
            session.save(update_fields=['private_notes', 'shared_summary', 'follow_up_on'])
            messages.success(request, 'Session notes saved.')
        return redirect('provider_dashboard')

    sessions = CounsellingSession.objects.filter(provider=profile).select_related('patient')
    now = timezone.now()
    context = _base_context(profile, 'dashboard')
    context.update({
        'requests': [s for s in sessions if s.status == CounsellingSession.Status.REQUESTED],
        'upcoming': [s for s in sessions if s.status == CounsellingSession.Status.CONFIRMED
                     and s.scheduled_for >= now],
        'recent': [s for s in sessions if s.status == CounsellingSession.Status.COMPLETED][:10],
        'completed_count': sum(1 for s in sessions
                               if s.status == CounsellingSession.Status.COMPLETED),
        'client_count': len({s.patient_id for s in sessions}),
        'follow_ups': [s for s in sessions if s.follow_up_on and s.follow_up_on >= timezone.localdate()],
        'modes': CounsellingSession.Mode.choices,
    })
    return render(request, 'providers/dash_mental_health.html', context)


# ==========================================================================
# 3. Diagnostics -- diagnostic labs
# ==========================================================================

def diagnostics_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_test':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'A test needs a name.')
            elif profile.lab_tests.filter(name__iexact=name).exists():
                messages.error(request, f'"{name}" is already on your catalogue.')
            else:
                LabTest.objects.create(
                    provider=profile, name=name,
                    category=request.POST.get('category', LabTest.Category.BLOOD),
                    sample_type=request.POST.get('sample_type', '').strip(),
                    preparation=request.POST.get('preparation', '').strip(),
                    price=_to_decimal(request.POST.get('price')),
                    report_hours=_to_int(request.POST.get('report_hours')),
                    home_collection=bool(request.POST.get('home_collection')),
                )
                messages.success(request, f'"{name}" added to your catalogue.')
            return redirect('provider_dashboard')

        if action == 'toggle_test':
            test = get_object_or_404(LabTest, pk=request.POST.get('test_id'), provider=profile)
            test.is_active = not test.is_active
            test.save(update_fields=['is_active'])
            messages.info(request, f'"{test.name}" is now {"listed" if test.is_active else "hidden"}.')
            return redirect('provider_dashboard')

        booking = get_object_or_404(TestBooking, pk=request.POST.get('booking_id'), provider=profile)
        if action == 'confirm':
            booking.status = TestBooking.Status.CONFIRMED
            booking.save(update_fields=['status'])
            messages.success(request, 'Booking confirmed.')
        elif action == 'collected':
            booking.status = TestBooking.Status.COLLECTED
            booking.collected_at = timezone.now()
            booking.save(update_fields=['status', 'collected_at'])
            messages.success(request, 'Sample marked collected.')
        elif action == 'cancel':
            booking.status = TestBooking.Status.CANCELLED
            booking.save(update_fields=['status'])
            messages.info(request, 'Booking cancelled.')
        elif action == 'add_value':
            analyte = request.POST.get('analyte', '').strip()
            value = request.POST.get('value', '').strip()
            if not (analyte and value):
                messages.error(request, 'A result needs both a name and a value.')
            else:
                TestResultValue.objects.create(
                    booking=booking, analyte=analyte, value=value,
                    unit=request.POST.get('unit', '').strip(),
                    reference_range=request.POST.get('reference_range', '').strip(),
                    flag=request.POST.get('flag', TestResultValue.Flag.NORMAL),
                )
                messages.success(request, f'{analyte} recorded.')
        elif action == 'release':
            if not booking.values.exists():
                messages.error(request, 'Enter at least one result value before releasing the report.')
            else:
                booking.summary = request.POST.get('summary', '').strip()
                booking.save(update_fields=['summary'])
                booking.release_report()
                messages.success(request, f'Report released to {booking.patient.display_name}.')
        return redirect('provider_dashboard')

    bookings = TestBooking.objects.filter(provider=profile).select_related('patient', 'test').prefetch_related('values')
    context = _base_context(profile, 'dashboard')
    context.update({
        'tests': profile.lab_tests.all(),
        'requests': [b for b in bookings if b.status == TestBooking.Status.REQUESTED],
        'in_progress': [b for b in bookings if b.status in {
            TestBooking.Status.CONFIRMED, TestBooking.Status.COLLECTED}],
        'reported': [b for b in bookings if b.status == TestBooking.Status.READY][:10],
        'reported_count': sum(1 for b in bookings if b.status == TestBooking.Status.READY),
        'patient_count': len({b.patient_id for b in bookings}),
        'categories': LabTest.Category.choices,
        'flags': TestResultValue.Flag.choices,
    })
    return render(request, 'providers/dash_diagnostics.html', context)


# ==========================================================================
# 4. Pharmacy
# ==========================================================================

# Which status a pharmacy may move an order to next. Keeping this as data
# rather than a chain of ifs means an invalid jump simply is not offered.
PHARMACY_NEXT_STATUS = {
    MedicineOrder.Status.PLACED: [MedicineOrder.Status.ACCEPTED, MedicineOrder.Status.REJECTED],
    MedicineOrder.Status.ACCEPTED: [MedicineOrder.Status.PREPARING],
    MedicineOrder.Status.PREPARING: [MedicineOrder.Status.READY],
    MedicineOrder.Status.READY: [MedicineOrder.Status.DISPATCHED, MedicineOrder.Status.DELIVERED],
    MedicineOrder.Status.DISPATCHED: [MedicineOrder.Status.DELIVERED],
}


def pharmacy_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'item':
            item = get_object_or_404(
                OrderItem, pk=request.POST.get('item_id'), order__pharmacy=profile)
            item.is_available = bool(request.POST.get('is_available'))
            item.unit_price = _to_decimal(request.POST.get('unit_price'))
            item.substitute_note = request.POST.get('substitute_note', '').strip()
            item.save(update_fields=['is_available', 'unit_price', 'substitute_note'])
            messages.success(request, f'{item.medicine_name} updated.')
            return redirect('provider_dashboard')

        order = get_object_or_404(MedicineOrder, pk=request.POST.get('order_id'), pharmacy=profile)
        if action == 'status':
            new_status = request.POST.get('status')
            allowed = PHARMACY_NEXT_STATUS.get(order.status, [])
            if new_status not in allowed:
                messages.error(request, 'That is not a valid next step for this order.')
            else:
                order.status = new_status
                order.pharmacy_note = request.POST.get('pharmacy_note', order.pharmacy_note).strip()
                order.save(update_fields=['status', 'pharmacy_note'])
                messages.success(request, f'Order #{order.pk} is now {order.get_status_display().lower()}.')
        return redirect('provider_dashboard')

    orders = (MedicineOrder.objects.filter(pharmacy=profile)
              .select_related('patient').prefetch_related('items'))
    for order in orders:
        order.next_options = [
            (s, MedicineOrder.Status(s).label) for s in PHARMACY_NEXT_STATUS.get(order.status, [])
        ]
    context = _base_context(profile, 'dashboard')
    context.update({
        'new_orders': [o for o in orders if o.status == MedicineOrder.Status.PLACED],
        'active_orders': [o for o in orders if o.status in {
            MedicineOrder.Status.ACCEPTED, MedicineOrder.Status.PREPARING,
            MedicineOrder.Status.READY, MedicineOrder.Status.DISPATCHED}],
        'closed_orders': [o for o in orders if not o.is_open][:10],
        'delivered_count': sum(1 for o in orders if o.status == MedicineOrder.Status.DELIVERED),
        'patient_count': len({o.patient_id for o in orders}),
    })
    return render(request, 'providers/dash_pharmacy.html', context)


# ==========================================================================
# 5. Wellness Programmes -- gyms, dieticians, yoga centres
# ==========================================================================

def wellness_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_programme':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'A programme needs a name.')
            elif profile.programmes.filter(name__iexact=name).exists():
                messages.error(request, f'You already run a programme called "{name}".')
            else:
                WellnessProgramme.objects.create(
                    provider=profile, name=name,
                    kind=request.POST.get('kind', WellnessProgramme.Kind.GENERAL),
                    level=request.POST.get('level', WellnessProgramme.Level.BEGINNER),
                    description=request.POST.get('description', '').strip(),
                    duration_weeks=_to_int(request.POST.get('duration_weeks'), 4),
                    sessions_per_week=_to_int(request.POST.get('sessions_per_week'), 3),
                    fee=_to_decimal(request.POST.get('fee')),
                    capacity=_to_int(request.POST.get('capacity')),
                )
                messages.success(request, f'"{name}" is now on your programme list.')
            return redirect('provider_dashboard')

        if action == 'toggle_programme':
            prog = get_object_or_404(WellnessProgramme, pk=request.POST.get('programme_id'), provider=profile)
            prog.is_active = not prog.is_active
            prog.save(update_fields=['is_active'])
            messages.info(request, f'"{prog.name}" is now {"open" if prog.is_active else "closed"} for enrolment.')
            return redirect('provider_dashboard')

        enrolment = get_object_or_404(
            ProgrammeEnrolment, pk=request.POST.get('enrolment_id'), programme__provider=profile)
        if action == 'accept':
            enrolment.status = ProgrammeEnrolment.Status.ACTIVE
            enrolment.started_on = timezone.localdate()
            enrolment.ends_on = enrolment.started_on + datetime.timedelta(
                weeks=enrolment.programme.duration_weeks)
            enrolment.save(update_fields=['status', 'started_on', 'ends_on'])
            messages.success(request, f'{enrolment.patient.display_name} enrolled.')
        elif action == 'decline':
            enrolment.status = ProgrammeEnrolment.Status.DECLINED
            enrolment.save(update_fields=['status'])
            messages.info(request, 'Enrolment declined.')
        elif action == 'complete':
            enrolment.status = ProgrammeEnrolment.Status.COMPLETED
            enrolment.save(update_fields=['status'])
            messages.success(request, 'Programme marked complete.')
        elif action == 'plan':
            enrolment.plan_notes = request.POST.get('plan_notes', '').strip()
            enrolment.save(update_fields=['plan_notes'])
            messages.success(request, 'Plan saved.')
        elif action == 'log_session':
            on_date = _to_date(request.POST.get('on_date')) or timezone.localdate()
            ProgrammeSession.objects.create(
                enrolment=enrolment, on_date=on_date,
                duration_minutes=_to_int(request.POST.get('duration_minutes'), 60),
                activity=request.POST.get('activity', '').strip(),
                attended=bool(request.POST.get('attended')),
                trainer_note=request.POST.get('trainer_note', '').strip(),
                weight_kg=_to_decimal(request.POST.get('weight_kg')),
            )
            messages.success(request, f'Session logged for {enrolment.patient.display_name}.')
        return redirect('provider_dashboard')

    enrolments = (ProgrammeEnrolment.objects.filter(programme__provider=profile)
                  .select_related('patient', 'programme'))
    context = _base_context(profile, 'dashboard')
    context.update({
        'programmes': profile.programmes.all(),
        'requests': [e for e in enrolments if e.status == ProgrammeEnrolment.Status.REQUESTED],
        'active': [e for e in enrolments if e.status == ProgrammeEnrolment.Status.ACTIVE],
        'finished': [e for e in enrolments if e.status == ProgrammeEnrolment.Status.COMPLETED][:10],
        'completed_count': sum(1 for e in enrolments if e.status == ProgrammeEnrolment.Status.COMPLETED),
        'client_count': len({e.patient_id for e in enrolments}),
        'kinds': WellnessProgramme.Kind.choices,
        'levels': WellnessProgramme.Level.choices,
        'today': timezone.localdate().isoformat(),
    })
    return render(request, 'providers/dash_wellness.html', context)


# ==========================================================================
# 6. Home Care -- home nurse providers
# ==========================================================================

def home_care_dashboard(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'add_staff':
            nurse = User.objects.filter(pk=request.POST.get('nurse_id'), role=User.Role.NURSE).first()
            if nurse is None:
                messages.error(request, 'Pick a nurse account to add.')
            elif profile.care_staff.filter(nurse=nurse).exists():
                messages.error(request, f'{nurse.display_name} is already on your team.')
            else:
                HomeCareStaff.objects.create(
                    provider=profile, nurse=nurse,
                    designation=request.POST.get('designation', '').strip(),
                    qualification=request.POST.get('qualification', '').strip(),
                    years_experience=_to_int(request.POST.get('years_experience')),
                )
                messages.success(request, f'{nurse.display_name} added to your team.')
            return redirect('provider_dashboard')

        if action == 'toggle_staff':
            staff = get_object_or_404(HomeCareStaff, pk=request.POST.get('staff_id'), provider=profile)
            staff.is_available = not staff.is_available
            staff.save(update_fields=['is_available'])
            messages.info(request, f'{staff.nurse.display_name} marked '
                                   f'{"available" if staff.is_available else "unavailable"}.')
            return redirect('provider_dashboard')

        care = get_object_or_404(HomeCareRequest, pk=request.POST.get('request_id'), provider=profile)
        if action == 'assign':
            staff = profile.care_staff.filter(pk=request.POST.get('staff_id')).first()
            if staff is None:
                messages.error(request, 'Choose one of your own staff members.')
            else:
                care.assigned_staff = staff
                care.status = HomeCareRequest.Status.ASSIGNED
                care.provider_note = request.POST.get('provider_note', care.provider_note).strip()
                care.save(update_fields=['assigned_staff', 'status', 'provider_note'])
                messages.success(request, f'{staff.nurse.display_name} assigned to '
                                          f'{care.patient.display_name}.')
        elif action == 'start':
            if care.assigned_staff is None:
                messages.error(request, 'Assign a nurse before starting the care.')
            else:
                care.status = HomeCareRequest.Status.ONGOING
                care.save(update_fields=['status'])
                messages.success(request, 'Care marked as ongoing.')
        elif action == 'complete':
            care.status = HomeCareRequest.Status.COMPLETED
            care.save(update_fields=['status'])
            messages.success(request, 'Care completed.')
        elif action == 'decline':
            care.status = HomeCareRequest.Status.DECLINED
            care.provider_note = request.POST.get('provider_note', '').strip()
            care.save(update_fields=['status', 'provider_note'])
            messages.info(request, 'Request declined.')
        return redirect('provider_dashboard')

    care_requests = (HomeCareRequest.objects.filter(provider=profile)
                     .select_related('patient', 'assigned_staff', 'assigned_staff__nurse'))
    staff = profile.care_staff.select_related('nurse')
    context = _base_context(profile, 'dashboard')
    context.update({
        'staff': staff,
        'available_staff': [s for s in staff if s.is_available],
        'requests': [c for c in care_requests if c.status == HomeCareRequest.Status.REQUESTED],
        'assigned': [c for c in care_requests if c.status in {
            HomeCareRequest.Status.ASSIGNED, HomeCareRequest.Status.ONGOING}],
        'finished': [c for c in care_requests if c.status == HomeCareRequest.Status.COMPLETED][:10],
        'completed_count': sum(1 for c in care_requests
                               if c.status == HomeCareRequest.Status.COMPLETED),
        'patient_count': len({c.patient_id for c in care_requests}),
        # Nurses not yet employed by any agency -- the pool this provider
        # can recruit from.
        'free_nurses': User.objects.filter(role=User.Role.NURSE).exclude(
            home_care_employment__provider=profile),
    })
    return render(request, 'providers/dash_home_care.html', context)


# ==========================================================================
# Shared: the service / price list every group keeps
# ==========================================================================

def services_page(request, profile):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            name = request.POST.get('name', '').strip()
            if not name:
                messages.error(request, 'A service needs a name.')
            elif profile.services.filter(name__iexact=name).exists():
                messages.error(request, f'"{name}" is already on your list.')
            else:
                ServiceOffering.objects.create(
                    provider=profile, name=name,
                    description=request.POST.get('description', '').strip(),
                    price=_to_decimal(request.POST.get('price')),
                    duration_minutes=_to_int(request.POST.get('duration_minutes')),
                )
                messages.success(request, f'"{name}" added.')
        elif action == 'toggle':
            service = get_object_or_404(ServiceOffering, pk=request.POST.get('service_id'), provider=profile)
            service.is_active = not service.is_active
            service.save(update_fields=['is_active'])
            messages.info(request, f'"{service.name}" is now '
                                   f'{"listed" if service.is_active else "hidden"}.')
        elif action == 'remove':
            service = get_object_or_404(ServiceOffering, pk=request.POST.get('service_id'), provider=profile)
            service.delete()
            messages.info(request, 'Service removed.')
        return redirect('provider_services')

    context = _base_context(profile, 'services')
    context['all_services'] = profile.services.all()
    return render(request, 'providers/services.html', context)


# The dispatcher table `providers.views.dashboard` reads.
GROUP_DASHBOARDS = {
    ProviderProfile.ServiceGroup.CLINICAL: clinical_dashboard,
    ProviderProfile.ServiceGroup.MENTAL_HEALTH: mental_health_dashboard,
    ProviderProfile.ServiceGroup.DIAGNOSTICS: diagnostics_dashboard,
    ProviderProfile.ServiceGroup.PHARMACY: pharmacy_dashboard,
    ProviderProfile.ServiceGroup.WELLNESS: wellness_dashboard,
    ProviderProfile.ServiceGroup.HOME_CARE: home_care_dashboard,
}
