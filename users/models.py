

# Create your models here.

# Create your models here.
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from chat.models import Message
from datetime import timedelta





class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    MANAGER = "MANAGER", "Manager"
    WAITER = "WAITER", "Waiter"
    CASHIER = "CASHIER", "Cashier"
    KITCHEN = "KITCHEN", "Kitchen"
    EMPLOYEE =  "EMPLOYEE" , "Employee"



class UserState(models.TextChoices):
    WORKING = "WORKING", "Working"
    HOLIDAY = "HOLIDAY", "Holiday"
    SICK_LEAVE = "SICK_LEAVE", "Sick Leave"
    STOPPED = "STOPPED", "Stopped"
    RESIGNED = "RESIGNED", "Resigned"
    ABSENT = "ABSENT", "Absent"

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
    state = models.CharField(
    max_length=20,
    choices=UserState.choices,
    default=UserState.WORKING,
)

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.WAITER,
    )

    is_active = models.BooleanField(
        default=True,
    )
   
    REQUIRED_FIELDS = ["email"]

    def __str__(self):
        return self.username

    daily_working_hours = models.DecimalField(
    max_digits=4,
    decimal_places=2,
    default=8.00,
    help_text="Required working hours per day."
)

    


    def check_in_user(self):
        self.state = UserState.WORKING   # ✅ works
        self.save(update_fields=["state"])  # ✅ works (saves only `state`)
        self.save()
    
    
        # ⚠️ redundant, possibly harmful

    def check_out_user(self):
        self.state = UserState.RESIGNED   # ✅ works
        self.save(update_fields=["state"])  # ✅ works (saves only `state`)
        self.save()
        





class Waiter(User):
    class Meta:
        proxy = True
        verbose_name = "Waiter"
        verbose_name_plural = "Waiters"

    def save(self, *args, **kwargs):
        self.role = UserRole.WAITER   
        super().save(*args, **kwargs)




class Attendance(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )

    check_in = models.DateTimeField(default=timezone.now)
    check_out = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-check_in"]
        indexes = [
            models.Index(fields=["user", "check_in"]),
        ]

    @property
    def is_working(self):
        """True when the employee has not checked out."""
        return self.check_out is None

    @property
    def working_duration(self):
        """Total duration of this attendance session."""
        end_time = self.check_out or timezone.now()
        return max(end_time - self.check_in, timedelta(0))

    @property
    def working_hours(self):
        """Total session duration in hours, rounded to 2 decimals."""
        return round(
            self.working_duration.total_seconds() / 3600,
            2,
        )

    @property
    def working_time_display(self):
        """Human-readable session duration."""
        total_minutes = int(
            self.working_duration.total_seconds() // 60
        )
        hours, minutes = divmod(total_minutes, 60)
        return f"{hours}h {minutes}m"

    @property
    def daily_target_hours(self):
        """The employee's configured daily working-hours target."""
        target = getattr(self.user, "daily_working_hours", 8)
        return max(float(target or 0), 0)

    @property
    def expected_checkout(self):
        """
        Expected checkout time based on check-in plus the
        employee's daily working-hours target.
        """
        return self.check_in + timedelta(
            hours=self.daily_target_hours
        )

    @property
    def is_overtime(self):
        """True when an active session has passed its expected checkout."""
        if not self.is_working:
            return False

        return timezone.now() >= self.expected_checkout

    @property
    def overtime_duration(self):
        """Overtime duration, or zero if the target has not been reached."""
        if not self.is_overtime:
            return timedelta(0)

        return max(
            timezone.now() - self.expected_checkout,
            timedelta(0),
        )

    @property
    def overtime_seconds(self):
        return int(self.overtime_duration.total_seconds())

    @property
    def overtime_display(self):
        """Human-readable overtime duration."""
        total_minutes = self.overtime_seconds // 60
        hours, minutes = divmod(total_minutes, 60)

        if hours:
            return f"{hours}h {minutes}m"

        return f"{minutes}m"

    @property
    def shift_status(self):
        """
        Status for the attendance session.

        This does not automatically check the employee out.
        """
        if not self.is_working:
            return "completed"

        if self.is_overtime:
            return "overtime"

        return "working"

    def __str__(self):
        return (
            f"{self.user.username} - "
            f"{timezone.localtime(self.check_in):%Y-%m-%d %H:%M}"
        )




class WeekDay(models.TextChoices):
    MONDAY = "MONDAY", "Monday"
    TUESDAY = "TUESDAY", "Tuesday"
    WEDNESDAY = "WEDNESDAY", "Wednesday"
    THURSDAY = "THURSDAY", "Thursday"
    FRIDAY = "FRIDAY", "Friday"
    SATURDAY = "SATURDAY", "Saturday"
    SUNDAY = "SUNDAY", "Sunday"


class EmployeeSchedule(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_schedules",
    )

    day_of_week = models.CharField(
        max_length=10,
        choices=WeekDay.choices,
    )

    is_day_off = models.BooleanField(default=False)

    start_time = models.TimeField(
        null=True,
        blank=True,
    )

    end_time = models.TimeField(
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "day_of_week"],
                name="unique_employee_weekday_schedule",
            )
        ]

    def __str__(self):
        return f"{self.user} - {self.get_day_of_week_display()}"
    




from django.conf import settings
from django.db import models
from django.utils import timezone


class DayOffStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class DayOffRequest(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="day_off_requests",
    )

    date = models.DateField()

    reason = models.CharField(
        max_length=500,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=DayOffStatus.choices,
        default=DayOffStatus.PENDING,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_day_off_requests",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    review_note = models.CharField(
        max_length=500,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["date", "-created_at"]
        indexes = [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["status", "date"]),
        ]

    def save(self, *args, **kwargs):
        previous_status = None

        # Check the previous status when updating an existing request.
        if self.pk:
            previous_status = (
                DayOffRequest.objects
                .filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )

        with transaction.atomic():
            super().save(*args, **kwargs)

            # Send a message only when the request becomes approved/rejected.
            status_changed = previous_status != self.status

            if (
                status_changed
                and self.status in [
                    DayOffStatus.APPROVED,
                    DayOffStatus.REJECTED,
                ]
            ):
                if self.status == DayOffStatus.APPROVED:
                    message_text = (
                        f"Your day-off request for {self.date:%Y-%m-%d} "
                        "has been approved."
                    )
                else:
                    message_text = (
                        f"Your day-off request for {self.date:%Y-%m-%d} "
                        "has been rejected."
                    )

                if self.review_note:
                    message_text += (
                        f"\nManager's note: {self.review_note}"
                    )

                # Use the manager as sender when available.
                if self.reviewed_by_id:
                    Message.objects.create(
                        sender_id=self.reviewed_by_id,
                        recipient_id=self.user_id,
                        content=message_text,
                    )

    def __str__(self):
        return f"{self.user} - {self.date} ({self.status})"


