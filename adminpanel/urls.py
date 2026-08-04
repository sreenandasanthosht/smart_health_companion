"""
URL map for the adminpanel app -- the platform Admin's own dashboard.
Note this is NOT Django's built-in /admin/ site; these are app pages.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='admin_dashboard'),
    path('verification/', views.verification, name='admin_verification'),
    path('users/', views.users, name='admin_users'),
    path('providers/', views.providers, name='admin_providers'),
    path('audit-log/', views.audit_log, name='admin_audit_log'),
    path('nursing/', views.nursing, name='admin_nursing'),
    path('caregivers/', views.caregivers, name='admin_caregivers'),
    path('complaints/', views.complaints, name='admin_complaints'),
    path('events/', views.events, name='admin_events'),
    path('announcements/', views.announcements, name='admin_announcements'),
    path('analytics/', views.analytics, name='admin_analytics'),
    # Super Admin only.
    path('admins/', views.admin_accounts, name='admin_accounts'),
    path('settings/', views.settings_view, name='admin_settings'),
]
