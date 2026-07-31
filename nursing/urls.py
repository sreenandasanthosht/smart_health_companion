"""URL map for the nursing app (nurse dashboard, visit logging)."""
from django.urls import path

from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='nurse_dashboard'),
    path('patient/<int:patient_id>/', views.patient_detail, name='nurse_patient_detail'),
    path('patient/<int:patient_id>/log-visit/', views.log_visit, name='nurse_log_visit'),
    path('visits/', views.visits, name='nurse_visits'),
]
