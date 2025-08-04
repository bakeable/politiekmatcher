import os
from apps.profiles.models import UserResponse
from apps.utils.match_opinions import rank_parties
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Match statement opinions with topics"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Remove old party_matches before matching",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        user_responses = UserResponse.objects.all()

        for response in user_responses:
            if response.party_matches.exists():
                if force:
                    count = response.party_matches.count()
                    response.party_matches.all().delete()
                    self.stdout.write(
                        self.style.WARNING(
                            f"Removed {count} old PartyStatementMatch(es) for user response {response.id}."
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"User response {response.id} already matched, skipping."
                        )
                    )
                    continue

            self.stdout.write(
                self.style.NOTICE(f"Matching user response {response.id}...")
            )

            positions = response.statement.positions.all()

            scores = rank_parties(
                user_opinion=response.user_opinion,
                party_items=positions,
                statement_text=response.statement.text,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Matching scores for user response {response.id}: {scores}"
                )
            )

            if not response.label_set_by and response.label:
                response.classified_label = response.label
                response.label_set_by = "AI"
                response.save(update_fields=["classified_label", "label_set_by"])

            from apps.profiles.models import PartyStatementMatch
            from apps.content.models import PoliticalParty

            for party_id, score in scores.items():
                party = PoliticalParty.objects.get(id=party_id)
                position = positions.filter(party=party).first()

                if position:
                    base_score = float(score)
                    confidence_weight = response.confidence / 5.0
                    importance_weight = response.importance / 5.0

                    party_match, created = PartyStatementMatch.objects.get_or_create(
                        profile=response.profile,
                        statement=response.statement,
                        party=party,
                        defaults={
                            "user_response": response,
                            "party_stance": position.stance,
                            "party_explanation": position.explanation or "",
                            "match_score": base_score,
                            "confidence_weighted_score": base_score * confidence_weight,
                            "importance_weighted_score": base_score * importance_weight,
                            "final_score": base_score
                            * confidence_weight
                            * importance_weight,
                        },
                    )

                    if created:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Created PartyStatementMatch: {party.abbreviation} - {base_score:.1f}%"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"PartyStatementMatch already exists: {party.abbreviation}"
                            )
                        )

            self.stdout.write(
                self.style.SUCCESS(
                    f"Completed matching for user response {response.id}"
                )
            )
