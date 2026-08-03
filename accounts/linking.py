"""
Resolving the identifier a caregiver types into a real patient.

The registration spec accepts three different things in one field --
"Patient ID / Patient Email / Invite Code" -- and both the sign-up form
and the retry form on the caregiver dashboard have to interpret them the
same way. That shared logic lives here so the two entry points can't
drift apart.
"""
from django.utils import timezone

from accounts.models import CaregiverInvite, CaregiverLink, Notification, User


def resolve_patient(reference):
    """
    Turn a caregiver-supplied reference into (patient, invite, error).

    Exactly one of `patient` or `error` is ever set. `invite` is the
    CaregiverInvite that matched, if the reference was an invite code --
    the caller consumes it once the link is actually created, so a failed
    registration doesn't burn the code.
    """
    ref = (reference or '').strip()
    if not ref:
        return None, None, "Enter the patient's ID, email address or invite code."

    # An invite code is the only form with a 'CN-' prefix, so check it
    # first -- it is also the only one that can be expired or used up,
    # and those deserve their own message.
    if ref.upper().startswith('CN-'):
        invite = CaregiverInvite.objects.filter(code__iexact=ref).select_related('patient').first()
        if invite is None:
            return None, None, "That invite code isn't recognised. Check it with the patient."
        if invite.used_at is not None:
            return None, None, 'That invite code has already been used.'
        if invite.expires_at is not None and invite.expires_at <= timezone.now():
            return None, None, 'That invite code has expired. Ask the patient for a new one.'
        return invite.patient, invite, None

    # An email address is the only form containing '@'.
    if '@' in ref:
        patient = User.objects.filter(email__iexact=ref, role=User.Role.PATIENT).first()
        if patient is None:
            return None, None, 'No patient account uses that email address.'
        return patient, None, None

    # Otherwise treat it as the patient's CareNest ID.
    patient = User.objects.filter(unique_id__iexact=ref, role=User.Role.PATIENT).first()
    if patient is None:
        return None, None, ("No patient found with that ID. They'll find it at the top "
                            'of their own dashboard.')
    return patient, None, None


def create_link_request(patient, caregiver, relationship='', invite=None):
    """
    Create the pending CaregiverLink and notify the patient.

    Returns (link, created). Never silently makes a second request for a
    pair that already has one.
    """
    link, created = CaregiverLink.objects.get_or_create(
        patient=patient, caregiver=caregiver,
        defaults={'relationship': relationship},
    )
    if not created:
        return link, False

    if relationship and not link.relationship:
        link.relationship = relationship
        link.save(update_fields=['relationship'])

    if invite is not None:
        invite.consume(caregiver)

    Notification.send(
        patient,
        title=f'{caregiver.display_name} wants to be your caregiver',
        body=(f"{relationship or 'They'} asked for access to your CareNest account. "
              'Nothing is shared until you approve.'),
        kind=Notification.Kind.CAREGIVER_REQUEST,
        level=Notification.Level.ACTION,
        action_url_name='health_caregiver_requests',
    )
    return link, True
