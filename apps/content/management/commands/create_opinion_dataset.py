import os
from openai import OpenAI
from django.core.management.base import BaseCommand
from apps.content.models import Statement

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


MAIN_PROMPT = """
Je bent een politieke data-analist. 
Je doel is om een lijst van meningen te genereren vanuit een bepaald politiek perspectief.
Er wordt gevraagd naar meningen over een politieke stelling, samen met een label voor de mening ten opzichte van de stelling (agree, neutral, disagree).
Bekijk deze stelling vanuit het perspectief van een {orientation} politiek georiënteerd persoon.
Alle antwoorden moeten kort en bondig zijn, maximaal 3 zinnen.
Gebruik geen jargon of moeilijke woorden, maar houd het begrijpelijk voor een breed publiek.

Geef je mening in de volgende JSON structuur:
```json
{{
  "opinions": [
    {{
        "text": "[mening en korte argumentatie]",
        "label": "agree|neutral|disagree",
    }}
  ]
}}

Genereer 10 verschillende meningen, elk vanuit ditzelfde {orientation}-politieke perspectief.

Begin 5 meningen met "Ja, want", "Nee, want", "Oneens, want", of "Neutraal, omdat".
Laat de andere meningen afwijken van deze structuur, maar zorg ervoor dat ze nog steeds duidelijk en begrijpelijk zijn.

Het thema is {theme}, waarbij de stelling luidt:
"{statement}"

"""


def build_prompt(statement: Statement, orientation: str) -> str:
    theme = statement.theme.name if statement.theme else "onbekend thema"
    return MAIN_PROMPT.format(
        orientation=orientation,
        theme=theme,
        statement=statement.text,
    )


OUTPUT_FILE = "data/example_opinions.jsonl"


class Command(BaseCommand):
    help = "Genereer voorbeeld meningen voor alle stellingen in de database"

    def handle(self, *args, **kwargs):
        # Verzamel statements
        statements = Statement.objects.all()

        # Reverse the order of statements to process them in reverse
        statements = list(statements)[::-1]

        for statement in statements:
            self.stdout.write(
                f"\n🔍 Genereren meningen voor statement: {statement.text}"
            )

            # Generate opinions for each orientation
            for orientation in ["links", "rechts", "conservatief", "progressief"]:
                prompt = build_prompt(statement, orientation)
                self.stdout.write(
                    f"📡 Prompt verzenden naar OpenAI voor {orientation}..."
                )
                response = client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": f"{statement.text}"},
                    ],
                )
                result = (
                    response.choices[0]
                    .message.content.strip()
                    .lstrip("```json")
                    .rstrip("```")
                )

                # Parse the JSON response
                import json

                try:
                    opinions = json.loads(result)["opinions"]
                except (json.JSONDecodeError, KeyError):
                    self.stdout.write(
                        self.style.ERROR(
                            f"Fout bij parsen van JSON voor statement {statement.id} en {orientation}."
                        )
                    )
                    continue

                # Save to JSON file
                for opinion in opinions:
                    opinion["statement"] = statement.text
                    opinion["orientation"] = orientation
                    with open(OUTPUT_FILE, "a") as f:
                        f.write(json.dumps(opinion) + "\n")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Voorbeeld meningen voor statement {statement.id} succesvol gegenereerd."
                )
            )
