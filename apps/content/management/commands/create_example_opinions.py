import os
from openai import OpenAI
from django.core.management.base import BaseCommand
from apps.content.models import Statement, Theme, Topic
from django.utils.text import slugify

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


MAIN_PROMPT = """
Er wordt gevraagd naar een mening over een politieke stelling.
Formatter je antwoord volgens een van deze voorbeelden:
"Ja, want [jouw argument]."
"Nee, want [jouw argument]."
"Oneens, want [jouw argument]."
"Neutraal, omdat [jouw argument]."

Je bent een {orientation} politiek georiënteerde persoon.
Je antwoord moet kort en bondig zijn, maximaal 3 zinnen.
Gebruik geen jargon of moeilijke woorden, maar houd het begrijpelijk voor een breed publiek.

Het thema is {theme}, waarbij de stelling luidt:
"{statement}"

Geef je mening, gebruikmakend van de bovenstaande voorbeelden.
"""


def build_prompt(statement: Statement, orientation: str) -> str:
    theme = statement.theme.name if statement.theme else "onbekend thema"
    return MAIN_PROMPT.format(
        orientation=orientation,
        theme=theme,
        statement=statement.text,
    )


class Command(BaseCommand):
    help = "Genereer voorbeeld meningen voor alle stellingen in de database"

    def handle(self, *args, **kwargs):
        # Verzamel statements
        statements = Statement.objects.all()

        for statement in statements:
            # Check if we already have 4 example opinions
            if statement.example_opinions.count() >= 4:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Statement {statement.id} heeft al 4 voorbeeld meningen, overslaan."
                    )
                )
                continue

            self.stdout.write(
                f"\n🔍 Genereren voorbeeld meningen voor statement: {statement.text}"
            )
            # Remove existing example opinions
            statement.example_opinions.all().delete()

            # Generate opinions for each orientation
            for orientation in ["links", "rechts", "conservatief", "progressief"]:
                prompt = build_prompt(statement, orientation)
                try:
                    self.stdout.write(
                        f"📡 Prompt verzenden naar OpenAI voor {orientation}..."
                    )
                    response = client.chat.completions.create(
                        model="gpt-4.1-mini",
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": f"{statement.text}"},
                        ],
                        max_tokens=100,
                    )
                    opinion_text = (
                        response.choices[0]
                        .message.content.strip()
                        .lstrip('"')
                        .rstrip('"')
                        .lstrip("'")
                        .rstrip("'")
                    )
                    self.stdout.write(
                        f"📝 Voorbeeld mening gegenereerd: {opinion_text}"
                    )

                    # Create ExampleOpinion instance
                    example_opinion = statement.example_opinions.create(
                        text=opinion_text,
                        left_wing=orientation == "links",
                        right_wing=orientation == "rechts",
                        conservative=orientation == "conservatief",
                        progressive=orientation == "progressief",
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Voorbeeld mening toegevoegd: {example_opinion.text}"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Fout bij genereren mening: {e}")
                    )
