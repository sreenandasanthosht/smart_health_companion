"""
Role-based access control (task 3.2).

`@login_required` only checks that SOMEONE is logged in. These decorators
additionally check WHICH role they are, so a patient can't open the
provider dashboard just by typing the URL.

Usage:
    @role_required(User.Role.PATIENT)
    def my_view(request): ...

    @role_required(User.Role.PROVIDER, User.Role.ADMIN)
    def another_view(request): ...
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

from accounts.models import User

# Where each role gets sent if they land somewhere they're not allowed.
ROLE_HOME = {
    User.Role.PATIENT: 'health_dashboard',
    User.Role.CAREGIVER: 'health_caregiver_dashboard',
    User.Role.PROVIDER: 'provider_dashboard',
    User.Role.ADMIN: 'admin_dashboard',
    User.Role.NURSE: 'nurse_dashboard',
}


def super_admin_required(view_func):
    """
    Stricter than `role_required(ADMIN)`: only the Super Admin tier.

    Guards the two things the Admin Module proposal reserves to the Super
    Admin -- creating Admin accounts, and system settings. A plain Admin
    hitting one of these is bounced to their dashboard with an
    explanation, not a 403, since they are legitimately signed in.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_suspended:
            messages.error(request, 'Your account has been suspended. Please contact support.')
            return redirect('logout')
        if not request.user.is_platform_super_admin:
            messages.error(request, 'That page is restricted to the Super Admin.')
            return redirect(ROLE_HOME.get(request.user.role, 'home'))
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    allowed = {str(r) for r in roles}

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if request.user.is_suspended:
                messages.error(request, 'Your account has been suspended. Please contact support.')
                return redirect('logout')
            # A Django superuser can open anything -- handy while marking/demoing.
            if request.user.role in allowed or request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            messages.error(request, "You don't have access to that page.")
            return redirect(ROLE_HOME.get(request.user.role, 'home'))
        return wrapper
    return decorator
