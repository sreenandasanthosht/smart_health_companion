"""
adminpanel app -- the platform Admin's management surface.

The only model here is the AuditLog: an append-only record of the actions
that matter for accountability (provider approvals, account suspensions,
record shares being granted or revoked). Consent design requires that
every share and revoke is written here.
"""
from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    class Tag(models.TextChoices):
        OK = 'ok', 'Success'
        WARN = 'warn', 'Warning'
        DANGER = 'danger', 'Critical'
        MUTED = 'muted', 'Routine'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='audit_entries',
    )
    actor_label = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=150)
    target = models.CharField(max_length=200, blank=True)
    tag = models.CharField(max_length=10, choices=Tag.choices, default=Tag.MUTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @classmethod
    def record(cls, actor, action, target='', tag=Tag.MUTED):
        """Write one audit entry. Safe to call from anywhere."""
        return cls.objects.create(
            actor=actor if getattr(actor, 'is_authenticated', False) else None,
            actor_label=getattr(actor, 'display_name', '') or 'System',
            action=action,
            target=target,
            tag=tag,
        )

    def __str__(self):
        return f"{self.created_at:%d %b %Y %H:%M} -- {self.actor_label}: {self.action}"
