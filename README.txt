Smart Health Companion — UI Mockups (Django templates + Bootstrap 5, dummy data)

HOW TO USE
- Open any .html file in a browser (internet needed: Bootstrap/Icons/Chart.js load from CDN).
- Keep shc.css in the SAME folder — every page links to it (the shared design system).
- Start with landing.html or patient_dashboard.html.

CONVERT TO DJANGO LATER
- Move the <link href="shc.css"> + shared sidebar/topbar into base.html.
- Put each page's .content block into {% block content %}; replace dummy data with context vars.

SCREENS (32)
Auth/marketing: landing, login, register
Patient: patient_dashboard, patient_vitals, patient_medications, patient_prescription_upload,
  patient_order_medicines, patient_appointments, patient_find_providers, patient_lifestyle,
  patient_mind, patient_records_sharing, patient_profile
Caregiver: caregiver_dashboard, caregiver_patient_detail, caregiver_alerts, caregiver_orders
Provider/Wellness/Pharmacy: provider_dashboard, provider_appointments, provider_consult,
  provider_listings, provider_profile_verification, provider_announcements,
  wellness_clients, wellness_log_activity, pharmacy_orders
Admin: admin_dashboard, admin_verification, admin_users, admin_providers, admin_audit_log
