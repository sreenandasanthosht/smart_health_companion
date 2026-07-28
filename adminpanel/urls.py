"""URL map for the adminpanel app (the platform Admin's own dashboard)."""
from django.urls import path
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='admin_dashboard'),
    path('verification/', views.verification, name='admin_verification'),
    path('users/', views.users, name='admin_users'),
    path('providers/', views.providers, name='admin_providers'),
    path('audit-log/', views.audit_log, name='admin_audit_log'),
]
