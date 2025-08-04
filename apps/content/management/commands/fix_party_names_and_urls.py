from django.core.management.base import BaseCommand
from apps.content.models import PoliticalParty
import openai


class Command(BaseCommand):
    help = "Fix party names"

    def handle(self, *args, **options):
        parties = PoliticalParty.objects.all()

        for party in parties:
            name, abbreviation = PoliticalParty.get_party_name(party.name)
            if name != party.name or abbreviation != party.abbreviation:
                party.name = name
                party.abbreviation = abbreviation
                party.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated party {party.id}: {party.name} ({party.abbreviation})"
                    )
                )

            # Try to find the Party URL
            if not party.website_url:

                prompt = (
                    f"Wat is de officiële website URL van de Nederlandse politieke partij '{party.name}'?"
                    " Geef alleen de volledige URL als antwoord."
                )
                try:
                    response = openai.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {
                                "role": "system",
                                "content": "Je bent een behulpzame assistent die alleen URLs van Nederlandse politieke partijen geeft.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        max_tokens=50,
                        temperature=0,
                    )
                    url = response.choices[0].message.content.strip()
                    if url.startswith("http"):
                        party.website_url = url
                        party.save()
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Website URL toegevoegd voor {party.name}: {url}"
                            )
                        )
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Kon geen website URL vinden voor {party.name}: {e}"
                        )
                    )
