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
]
