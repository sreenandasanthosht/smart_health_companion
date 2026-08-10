"""URL map for the providers app (directory, appointments, provider dashboard)."""
from django.urls import path
from . import views

urlpatterns = [
    path('directory/', views.directory, name='provider_directory'),
    path('appointments/', views.appointments, name='provider_appointments'),
    path('dashboard/', views.dashboard, name='provider_dashboard'),
    path('pending/', views.pending, name='provider_pending'),
    path('my-events/', views.my_events, name='provider_events'),
    path('events/', views.public_events, name='public_events'),
    path('previsit/<int:appointment_id>/', views.previsit_snapshot, name='provider_previsit_snapshot'),
    path('previsit/share/', views.share_previsit_consent, name='provider_previsit_share'),
    path('care-plans/', views.care_plans, name='provider_care_plans'),
    path('availability/', views.availability, name='provider_availability'),
]
