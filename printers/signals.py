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

    # Import here to avoid circular imports during Django startup.
    from .services import process_print_job

    process_print_job(instance)