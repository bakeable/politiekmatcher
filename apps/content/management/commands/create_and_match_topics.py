import os
from openai import OpenAI
from django.core.management.base import BaseCommand
from apps.content.models import Theme, Topic
from django.utils.text import slugify

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


TOPIC_GENERATION_PROMPT = """
Je bent een politieke data-analist. Hieronder zie je een lijst met thematitels uit StemWijzer en Kieskompas. Je taak is om deze te groeperen onder bredere politieke onderwerpen ("topics").

1. Groepeer vergelijkbare thema's onder één overkoepelend topic.
2. Geef elk topic een naam, korte beschrijving, en context (max 2 zinnen).
3. Geef output in JSON formaat met keys: `name`, `description`, `context`
4. Zorg ervoor dat elk topic een lijst bevat van thema ID's die onder dat topic vallen en dat alle thema's worden opgenomen.
5. Elke topic moet uniek zijn, gebruik ook geen koppelingen zoals "en" of "of" in de naam.
6. Zorg ervoor dat de thema's die onder een topic vallen relevant zijn en logisch gegroepeerd.
7. Gebruik de volgende structuur voor de output:

```json
[
  {
    "name": "Naam van het topic",
    "description": "Korte beschrijving van het topic",
    "context": "Contextuele informatie over het topic",
    "themes": [**Lijst van thema ID's die onder dit topic vallen**]
  },
  ...
]
```

Hier is de lijst met thema’s:
"""


class Command(BaseCommand):
    help = (
        "Genereer overkoepelende topics uit alle stemwijzer/kieskompas thema’s met GPT"
    )

    def handle(self, *args, **kwargs):
        # Verzamel thema’s
        themes = Theme.objects.filter(source__in=["stemwijzer", "kieskompas"])
        theme_names = sorted(set(theme.name for theme in themes))

        if not theme_names:
            self.stdout.write(self.style.WARNING("Geen thema's gevonden."))
            return

        # Maak prompt
        prompt = (
            TOPIC_GENERATION_PROMPT
            + "\nStemwijzer thema's:\n"
            + "\n".join(
                f"-  ID: {theme.pk} => {theme.name}"
                for theme in Theme.objects.filter(source="stemwijzer")
            )
            + "\n\nKieskompas thema's:\n"
            + "\n".join(
                f"-  ID: {theme.pk} => {theme.name}"
                for theme in Theme.objects.filter(source="kieskompas")
            )
        )

        self.stdout.write("📡 Prompt sturen naar OpenAI...")
        self.stdout.write(prompt)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Je bent een slimme politiek analist."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )

        content = response.choices[0].message.content
        content = content.lstrip("```json")
        content = content.rstrip("```")

        # Probeer JSON eruit te parsen
        import json

        try:
            topics = json.loads(content)
        except json.JSONDecodeError:
            self.stderr.write(
                self.style.ERROR("❌ OpenAI antwoord is geen geldige JSON")
            )
            print(content)
            return

        # Delete old topics
        Topic.objects.all().delete()

        created = 0
        for topic_data in topics:
            name = topic_data.get("name")
            if not name:
                continue

            topic, created_flag = Topic.objects.get_or_create(
                name=name,
                defaults={
                    "slug": slugify(name),
                    "description": topic_data.get("description", ""),
                    "context": topic_data.get("context", ""),
                },
            )
            if created_flag:
                created += 1

            # Voeg thema's toe aan topic
            theme_ids = topic_data.get("themes", [])
            for theme_id in theme_ids:
                try:
                    theme = Theme.objects.get(id=int(theme_id))
                    theme.topic = topic
                    theme.save()
                except Theme.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"Thema met ID {theme_id} niet gevonden.")
                    )

        self.stdout.write(self.style.SUCCESS(f"✅ {created} nieuwe topics aangemaakt."))
