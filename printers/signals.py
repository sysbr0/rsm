from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PrintJob


@receiver(post_save, sender=PrintJob)
def process_new_print_job(
    sender,
    instance,
    created,
    **kwargs,
):
    if not created:
        return

    # Import inside handler to avoid circular imports
    from .services import process_print_job

    # Execute sending to socket ONLY after current DB transaction commits
    transaction.on_commit(lambda: process_print_job(instance))