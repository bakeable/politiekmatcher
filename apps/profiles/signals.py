"""
Signal handlers for automatic party match recalculation.
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import UserResponse
from .services import PartyMatchService


@receiver(post_save, sender=UserResponse)
def recalculate_matches_on_response_save(sender, instance, created, **kwargs):
    """
    Automatically recalculate party matches when a user response is created or updated.

    This ensures that the party matches are always up-to-date with the latest user responses.
    """
    # Only recalculate if the response has a label (classification)
    if instance.label:
        try:
            PartyMatchService.recalculate_on_response_change(instance)
        except Exception as e:
            # Log the error but don't break the save operation
            print(f"Error recalculating party matches for response {instance.id}: {e}")


@receiver(post_delete, sender=UserResponse)
def recalculate_matches_on_response_delete(sender, instance, **kwargs):
    """
    Automatically recalculate party matches when a user response is deleted.
    """
    if instance.label:
        try:
            PartyMatchService.recalculate_profile_matches(instance.profile)
        except Exception as e:
            # Log the error but don't break the delete operation
            print(
                f"Error recalculating party matches after deleting response {instance.id}: {e}"
            )
