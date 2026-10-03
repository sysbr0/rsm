
import uuid

from django.db import models


class LocalLicense(models.Model):

    license_key = models.CharField(
        max_length=64,
        unique=True,
    )

    installation_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    customer_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    product = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    plan = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    status = models.CharField(
        max_length=30,
        default="UNKNOWN",
    )

    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_verified_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.license_key

