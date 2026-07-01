"""
accounts app -- everything about USERS.
We define ONE custom user that covers all user types via a `role` field,
and give every user a short unique_id (used for caregiver linking and for
patients finding providers).
"""
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        PATIENT = 'PATIENT', 'Patient'
        CAREGIVER = 'CAREGIVER', 'Caregiver'
        PROVIDER = 'PROVIDER', 'Provider'

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.PATIENT
    )
    unique_id = models.CharField(max_length=12, unique=True, blank=True)

    def save(self, *args, **kwargs):
        # auto-generate a unique id the first time the user is saved
        if not self.unique_id:
            self.unique_id = uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
