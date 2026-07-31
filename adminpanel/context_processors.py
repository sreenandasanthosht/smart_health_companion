"""
Makes a few live platform counts available to every template, so the
Admin sidebar's "Platform at a glance" box shows real numbers instead of
hardcoded ones.

Only runs the queries for signed-in Admin users -- every other request
gets an empty dict and pays no database cost.
"""
from accounts.models import User


def platform_stats(request):
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated and user.role == User.Role.ADMIN):
        return {}

    from health.models import ConsentGrant
    from nursing.models import NursingVisit
    from providers.models import ProviderProfile

    return {
        'stat_total_users': User.objects.count(),
        'stat_pending_verifications': ProviderProfile.objects.filter(
            verification_status=ProviderProfile.Verification.PENDING).count(),
        'stat_active_shares': ConsentGrant.objects.filter(revoked_at__isnull=True).count(),
        'stat_escalations': NursingVisit.objects.filter(escalated=True).count(),
    }
