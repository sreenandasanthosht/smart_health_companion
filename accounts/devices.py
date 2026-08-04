"""
New-device login approval for caregivers.

From the Caregiver Module proposal, "Secure Login":

    Once linked, the caregiver can log in normally from a trusted device.
    If a new device is used, the patient can be asked to approve the
    login for additional security.

A device is identified by a random opaque token kept in a cookie on the
caregiver's browser. That is deliberate: browser fingerprinting would be
both less reliable and more invasive, and this token means nothing to
anyone who doesn't already hold the caregiver's session.

The gate is on *reading patient data*, not on signing in. A caregiver on
an unapproved device can still reach their own account and see that they
are waiting -- they just can't see anything about the patient.
"""
from django.utils import timezone

from accounts.models import CaregiverLink, Notification, TrustedDevice

COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year


def _label_for(request):
    """A short, human-recognisable name for the browser signing in."""
    agent = request.META.get('HTTP_USER_AGENT', '')
    browser = 'Browser'
    for name in ('Edg', 'Chrome', 'Firefox', 'Safari'):
        if name in agent:
            browser = 'Edge' if name == 'Edg' else name
            break
    platform = 'device'
    for token, name in (('Windows', 'Windows'), ('Android', 'Android'), ('iPhone', 'iPhone'),
                        ('iPad', 'iPad'), ('Mac OS', 'Mac'), ('Linux', 'Linux')):
        if token in agent:
            platform = name
            break
    return f'{browser} on {platform}'


def register_device(request, user):
    """
    Find or create the TrustedDevice for this browser.

    Returns (device, token_to_set). `token_to_set` is non-empty only when
    a new cookie needs writing, so the caller can attach it to whatever
    response it was going to send anyway.
    """
    from adminpanel.models import PlatformSettings

    token = request.COOKIES.get(TrustedDevice.COOKIE_NAME, '')
    if token:
        device = TrustedDevice.objects.filter(user=user, token=token).first()
        if device is not None:
            device.last_seen_at = timezone.now()
            device.save(update_fields=['last_seen_at'])
            return device, ''

    link = (
        CaregiverLink.objects.filter(caregiver=user, status=CaregiverLink.Status.APPROVED)
        .select_related('patient').first()
    )
    patient = link.patient if link else None

    # The very first device is trusted implicitly: there is no earlier
    # device for it to be suspicious relative to, and an unlinked
    # caregiver has nothing to see regardless.
    first_ever = not TrustedDevice.objects.filter(user=user).exists()
    # A Super Admin can turn the whole check off from platform settings.
    gate_on = PlatformSettings.load().caregiver_device_approval_required
    approved = first_ever or patient is None or not gate_on

    new_token = TrustedDevice.new_token()
    device = TrustedDevice.objects.create(
        user=user, patient=patient, token=new_token, label=_label_for(request),
        status=TrustedDevice.Status.APPROVED if approved else TrustedDevice.Status.PENDING,
        decided_at=timezone.now() if approved else None,
    )

    if not approved:
        Notification.send(
            patient,
            title=f'New sign-in by {user.display_name}',
            body=f'{device.label} tried to open your caregiver view. Approve it only if you recognise it.',
            kind=Notification.Kind.DEVICE_APPROVAL,
            level=Notification.Level.WARNING,
            action_url_name='health_caregiver_requests',
        )
    return device, new_token


def set_device_cookie(response, token):
    """Attach a freshly issued device token to an outgoing response."""
    if token:
        response.set_cookie(
            TrustedDevice.COOKIE_NAME, token,
            max_age=COOKIE_MAX_AGE, httponly=True, samesite='Lax',
        )
    return response


def current_device(request):
    """The TrustedDevice this request is coming from, or None."""
    token = request.COOKIES.get(TrustedDevice.COOKIE_NAME, '')
    if not token or not request.user.is_authenticated:
        return None
    return TrustedDevice.objects.filter(user=request.user, token=token).first()


def device_is_trusted(request):
    """
    True if this browser may see patient data.

    A missing device row is treated as trusted rather than blocked --
    cookies get cleared, and locking a caregiver out of an account they
    legitimately hold is a worse failure than the one this guards against.
    Any *known* device that is pending or rejected is blocked.
    """
    device = current_device(request)
    return device is None or device.is_approved
