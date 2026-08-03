"""URL map for the health app (patient vitals, medications, lifestyle, mental health, sharing)."""
from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='health_dashboard'),
    path('vitals/', views.vitals, name='health_vitals'),
    path('medications/', views.medications, name='health_medications'),
    path('lifestyle/', views.lifestyle, name='health_lifestyle'),
    path('mental-health/', views.mental_health, name='health_mental_health'),
    path('share/', views.share_records, name='health_share'),
    path('caregiver-dashboard/', views.caregiver_dashboard, name='health_caregiver_dashboard'),
    path('caregiver-link/', views.caregiver_link_request, name='health_caregiver_link'),
    path('caregiver-requests/', views.caregiver_requests, name='health_caregiver_requests'),
    path('prescription/', views.prescription_upload, name='health_prescription_upload'),
    path('prescription/<int:job_id>/verify/', views.extraction_verify, name='health_extraction_verify'),
]
