import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone


class LocalLicense(models.Model):
    """
    Local mirror of a license issued by the remote licensing server.
    Only ONE row should exist per installation.
    """

    # ---- Status constants ----
    STATUS_UNKNOWN          = "UNKNOWN"
    STATUS_ACTIVE           = "ACTIVE"
    STATUS_TRIAL            = "TRIAL"
    STATUS_ALREADY_ACTIVE   = "ALREADY_ACTIVE"    # <- new
    STATUS_EXPIRED          = "EXPIRED"
    STATUS_SUSPENDED        = "SUSPENDED"
    STATUS_REVOKED          = "REVOKED"

    STATUS_CHOICES = [
        (STATUS_UNKNOWN,        "Unknown"),
        (STATUS_ACTIVE,         "Active"),
        (STATUS_TRIAL,          "Trial"),
        (STATUS_ALREADY_ACTIVE, "Already active"),
        (STATUS_EXPIRED,        "Expired"),
        (STATUS_SUSPENDED,      "Suspended"),
        (STATUS_REVOKED,        "Revoked"),
    ]

    # Statuses that count as "the app may run"
    VALID_STATUSES = (STATUS_ACTIVE, STATUS_TRIAL, STATUS_ALREADY_ACTIVE)

    # Statuses the server may send that mean "ACTIVE" — normalized on save
    STATUS_ALIASES = {
        "ALREADY_ACTIVE": "ACTIVE",
        "ACTIVE":         "ACTIVE",
        "VALID":          "ACTIVE",
        "OK":             "ACTIVE",
        "TRIAL":          "TRIAL",
        "EXPIRED":        "EXPIRED",
        "SUSPENDED":      "SUSPENDED",
        "REVOKED":        "REVOKED",
    }

    GRACE_PERIOD_DAYS      = 7
    STALE_AFTER_HOURS      = 24
    WARNING_THRESHOLD_DAYS = 14

    # ---- Fields ----
    license_key = models.CharField(max_length=64, unique=True)

    installation_id = models.UUIDField(
        default=uuid.uuid4, unique=True, editable=False,
    )

    customer_name = models.CharField(max_length=255, blank=True, default="")
    product       = models.CharField(max_length=100, blank=True, default="")
    plan          = models.CharField(max_length=50,  blank=True, default="")

    status = models.CharField(
        max_length=30, choices=STATUS_CHOICES, default=STATUS_UNKNOWN,
    )

    expires_at       = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)

    last_warning_shown_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Last time an expiry warning was surfaced to the user.",
    )

    is_active  = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Local License"
        verbose_name_plural = "Local License"
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["license_key"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.license_key} ({self.status})"

    # ---- Save override: normalize status + set is_active coherently ----
    def save(self, *args, **kwargs):
        # Normalize status from aliases the server may send
        if self.status:
            raw = str(self.status).strip().upper()
            self.status = self.STATUS_ALIASES.get(raw, raw)

        # Keep is_active consistent with the status
        if self.status in self.VALID_STATUSES:
            self.is_active = True
        elif self.status in (self.STATUS_EXPIRED,
                            self.STATUS_SUSPENDED,
                            self.STATUS_REVOKED,
                            self.STATUS_UNKNOWN):
            self.is_active = False

        super().save(*args, **kwargs)

    # ---- Expiry helpers ----
    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return timezone.now() > self.expires_at

    @property
    def grace_period_ends_at(self):
        if not self.expires_at:
            return None
        return self.expires_at + timedelta(days=self.GRACE_PERIOD_DAYS)

    @property
    def in_grace_period(self) -> bool:
        if not self.expires_at:
            return False
        now = timezone.now()
        return self.expires_at < now <= self.grace_period_ends_at

    @property
    def days_remaining(self) -> int:
        if not self.expires_at:
            return 0
        delta = self.expires_at - timezone.now()
        return max(delta.days, 0)

    @property
    def needs_reverification(self) -> bool:
        if not self.last_verified_at:
            return True
        age = timezone.now() - self.last_verified_at
        return age > timedelta(hours=self.STALE_AFTER_HOURS)

    # ---- Warning helpers ----
    @property
    def should_warn(self) -> bool:
        if not self.expires_at or not self.is_valid():
            return False
        return self.days_remaining <= self.WARNING_THRESHOLD_DAYS

    @property
    def warning_level(self) -> str:
        """
        'critical' — 0-3 days
        'urgent'   — 4-7 days
        'warning'  — 8-14 days
        ''         — fine / not applicable
        """
        if not self.should_warn:
            return ""
        d = self.days_remaining
        if d <= 3:
            return "critical"
        if d <= 7:
            return "urgent"
        return "warning"

    # ---- Core check ----
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.status not in self.VALID_STATUSES:
            return False
        if self.is_expired and not self.in_grace_period:
            return False
        return True

    # ---- Mutation helpers ----
    def apply_server_payload(self, payload: dict) -> None:
        from django.utils.dateparse import parse_datetime

        if "status" in payload:
            # Normalize here too, so it's clean before save()
            raw = str(payload["status"] or "").strip().upper()
            self.status = self.STATUS_ALIASES.get(raw, raw)

        if "is_active" in payload:
            self.is_active = bool(payload["is_active"])
        if "customer_name" in payload:
            self.customer_name = payload["customer_name"] or ""
        if "plan" in payload:
            self.plan = payload["plan"] or ""
        if "product" in payload:
            self.product = payload["product"] or ""

        if payload.get("expires_at"):
            parsed = parse_datetime(payload["expires_at"])
            if parsed:
                self.expires_at = parsed

        self.last_verified_at = timezone.now()

    def mark_verified(self) -> None:
        self.last_verified_at = timezone.now()
        self.save(update_fields=["last_verified_at", "updated_at"])

    def invalidate(self, reason_status: str = STATUS_UNKNOWN) -> None:
        self.status = reason_status
        self.is_active = False
        self.save(update_fields=["status", "is_active", "updated_at"])