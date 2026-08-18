"""
Top-level URL routing (the "waiter" that maps web addresses to code).
/admin/          -> Django's built-in admin site (used by the single superuser)
/                -> handled by the core app (home page)
/accounts/       -> register, login, onboarding
/health/         -> patient vitals, medications, lifestyle, mental health, sharing, caregiver dashboard
/providers/      -> provider directory, appointments, provider dashboard
/admin-panel/    -> the platform Admin's own dashboard (verification, users, providers, audit log)
/nursing/        -> nurse dashboard, assigned patients, visit logging
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('core.urls')),
    path('accounts/', include('accounts.urls')),
    path('health/', include('health.urls')),
    path('providers/', include('providers.urls')),
    path('admin-panel/', include('adminpanel.urls')),
    path('nursing/', include('nursing.urls')),
    path('datascience/', include('datascience.urls')),
]
