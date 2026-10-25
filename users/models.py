from django.db import models

# Create your models here.

# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    MANAGER = "MANAGER", "Manager"
    WAITER = "WAITER", "Waiter"
    CASHIER = "CASHIER", "Cashier"
    KITCHEN = "KITCHEN", "Kitchen"
    EMPLOYEE =  "EMPLOYEE" , "Employee"


class BaseAuth(AbstractUser):
    class Meta:
        abstract = True


class User(BaseAuth):
    full_name = models.CharField(
        max_length=150,
        blank=True,
    )

    pin_hash = models.CharField(
        max_length=255,
        blank=True,
    )

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.WAITER,
    )

    is_active = models.BooleanField(
        default=True,
    )
    is_working = models.BooleanField(default=True)
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username


class Waiter(User):
    class Meta:
        proxy = True
        verbose_name = "Waiter"
        verbose_name_plural = "Waiters"

    def save(self, *args, **kwargs):
        self.role = UserRole.WAITER
        super().save(*args, **kwargs)