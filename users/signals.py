from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from chat.models import Message

from .models import Attendance, DayOffRequest, DayOffStatus


@receiver(post_save, sender=Attendance)
def reject_day_off_on_check_in(sender, instance, created, **kwargs):
    """
    When an employee checks in, reject any day-off for that same local date.

    Behaviour:
    - PENDING  -> deleted (they decided to work)
    - APPROVED -> flipped to REJECTED with an auto note,
                  and a self-notification Message is sent
    - REJECTED -> untouched
    - On attendance updates (check-out), nothing happens.
    """
    if not created:
        return  # only react to the initial check-in

    local_date = timezone.localtime(instance.check_in).date()

    with transaction.atomic():
        # Pending requests: delete silently.
        DayOffRequest.objects.filter(
            user=instance.user,
            date=local_date,
            status=DayOffStatus.PENDING,
        ).delete()

        # Approved requests: flip to REJECTED.
        # .update() bypasses DayOffRequest.save(), so the built-in
        # "rejected" Message logic there will NOT fire. We send our
        # own, correctly-worded Message below instead.
        updated = DayOffRequest.objects.filter(
            user=instance.user,
            date=local_date,
            status=DayOffStatus.APPROVED,
        ).update(
            status=DayOffStatus.REJECTED,
            review_note="Employee checked in on this day.",
            reviewed_at=timezone.now(),
        )

        # Only notify when an APPROVED day-off was actually cancelled.
        if updated:
            Message.objects.create(
                sender=instance.user,
                recipient=instance.user,
                content=(
                    f"Your approved day-off for {local_date:%Y-%m-%d} "
                    "was cancelled because you checked in."
                ),
            )