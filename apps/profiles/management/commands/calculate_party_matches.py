"""
Management command to calculate party matches for user profiles.
"""

from django.core.management.base import BaseCommand
from apps.profiles.models import UserProfile, PartyMatch
from apps.profiles.services import PartyMatchService
from apps.content.models import PoliticalParty


class Command(BaseCommand):
    help = "Calculate party matches for user profiles based on their responses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile-uuid",
            type=str,
            help="Calculate matches for specific profile UUID only",
        )
        parser.add_argument(
            "--recalculate",
            action="store_true",
            help="Recalculate existing matches",
        )

    def handle(self, *args, **options):
        profile_uuid = options.get("profile_uuid")
        recalculate = options.get("recalculate", False)

        # Get profiles to process
        if profile_uuid:
            try:
                profiles = [UserProfile.objects.get(uuid=profile_uuid)]
                self.stdout.write(f"Processing specific profile: {profile_uuid}")
            except UserProfile.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f"Profile with UUID {profile_uuid} not found")
                )
                return
        else:
            # Get all profiles that have at least one response with a label
            profiles = UserProfile.objects.filter(
                responses__label__isnull=False
            ).distinct()
            self.stdout.write(
                f"Processing {profiles.count()} profiles with labeled responses"
            )

        # Get all parties for reporting
        parties_count = PoliticalParty.objects.count()
        self.stdout.write(f"Calculating matches against {parties_count} parties")

        total_processed = 0
        total_matches_created = 0

        for profile in profiles:
            # Count how many labeled responses this profile has
            labeled_responses = profile.responses.filter(label__isnull=False).count()

            if labeled_responses == 0:
                self.stdout.write(
                    f"Skipping profile {profile.uuid} (no labeled responses)"
                )
                continue

            self.stdout.write(
                f"\nProcessing profile {profile.uuid} ({labeled_responses} labeled responses)..."
            )

            # Check if matches already exist and whether to recalculate
            existing_matches = PartyMatch.objects.filter(profile=profile).count()
            if existing_matches > 0 and not recalculate:
                self.stdout.write(
                    f"  Skipping (already has {existing_matches} matches)"
                )
                continue

            # Use the service to recalculate matches
            matches_calculated = PartyMatchService.recalculate_profile_matches(profile)

            total_processed += 1
            total_matches_created += matches_calculated
            self.stdout.write(f"  Completed: {matches_calculated} matches calculated")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSummary: Processed {total_processed} profiles, "
                f"created/updated {total_matches_created} party matches"
            )
        )
