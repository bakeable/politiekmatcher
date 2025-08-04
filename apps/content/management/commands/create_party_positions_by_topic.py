import json
import os
import re
import tempfile
import time

from django.core.management.base import BaseCommand
from openai import OpenAI
import tiktoken

from apps.content.models import (
    PartyPosition,
    PoliticalParty,
    ProgramFragment,
    StatementPosition,
    ThemePosition,
    PoliticalDimensions,
    Topic,
)


BATCH_ID_FILE = "party_positions_batch_id.txt"
SYSTEM = """
Je bent een politieke data-analist.

Je moet de belangrijkste partijstandpunten over het onderwerp "{topic_name}" bepalen en ordenen voor de {party_name}.

Dit is alle informatie die we hebben over dit onderwerp, van deze partij:

{content}

Opdracht:
1. Bepaal voor elke partij de belangrijkste standpunten over het onderwerp.
2. Geef de partijstandpunten in JSON formaat.
3. Geef bij elk partijstandpunt de volgende informatie:
    - short_explanation: Een speerpunt of kort bulletpoint om het standpunt te beschrijven.
    - long_explanation: Een uitgebreide uitleg van het standpunt.   
    - ranking: Een nummer dat aangeeft hoe belangrijk dit standpunt is voor de partij, waarbij 1 de belangrijkste is.
    - sources: Een lijst van source objecten met ID en relevantiescore.
4. Voor elke source, geef een relevantiescore (0.0-1.0) die aangeeft hoe relevant de bron is voor dit specifieke standpunt:
    - 0.9-1.0: Zeer relevant, directe ondersteuning van het standpunt
    - 0.7-0.8: Relevant, goede ondersteuning
    - 0.5-0.6: Matig relevant, gedeeltelijke ondersteuning
    - 0.3-0.4: Beperkt relevant, zwakke ondersteuning
    - 0.0-0.2: Niet relevant
5. Gebruik de volgende structuur:
```json
{{
    "topic": "[topic_name]",
    "positions": [
        {{
            "short_explanation": "[statement_text]",
            "long_explanation": "[stance]",
            "ranking": 1,
            "sources": [
                {{"id": "StatementPosition-123", "relevance_score": 0.9}},
                {{"id": "ProgramFragment-456", "relevance_score": 0.8}}
            ]
        }},
        {{
            "short_explanation": "[statement_text]",
            "long_explanation": "[stance]",
            "ranking": 2,
            "sources": [
                {{"id": "StatementPosition-789", "relevance_score": 0.7}}
            ]
        }}
        ...
    ]
}}
```
6. Zorg ervoor dat de partijstandpunten relevant zijn voor het onderwerp.
7. Maximaal 8 standpunten per partij, alleen de belangrijkste. Het liefst ongeveer 6, maar zeker niet meer dan 8.
8. Gebruik alleen source ID's die daadwerkelijk in de content voorkomen.
9. Een standpunt moet tenminste 1 source hebben, maar mag meerdere sources combineren als ze gerelateerd zijn.
10. Beoordeel zorgvuldig de relevantiescore van elke bron voor het specifieke standpunt.
"""

SCHEMA = {
    "name": "party_positions_by_topic",
    "schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string"},
            "positions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "short_explanation": {"type": "string"},
                        "long_explanation": {"type": "string"},
                        "ranking": {"type": "integer", "minimum": 1},
                        "sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {
                                        "type": "string",
                                        "description": "Source ID (e.g., 'StatementPosition-123', 'ProgramFragment-456')",
                                    },
                                    "relevance_score": {
                                        "type": "number",
                                        "minimum": 0.0,
                                        "maximum": 1.0,
                                        "description": "Relevance score for this source (0.0-1.0)",
                                    },
                                },
                                "required": ["id", "relevance_score"],
                                "additionalProperties": False,
                            },
                            "minItems": 1,
                            "description": "List of source objects with IDs and relevance scores",
                        },
                    },
                    "required": [
                        "short_explanation",
                        "long_explanation",
                        "ranking",
                        "sources",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["topic", "positions"],
        "additionalProperties": False,
    },
    "strict": True,
}


class Command(BaseCommand):
    help = (
        "Get the most important party positions by topic and save them to the database."
    )

    def format_stance(self, stance):
        """Format the stance for output."""
        if stance == "strongly_agree":
            return "helemaal eens"
        elif stance == "agree":
            return "eens"
        elif stance == "neutral":
            return "neutraal"
        elif stance == "disagree":
            return "oneens"
        elif stance == "strongly_disagree":
            return "helemaal oneens"

        return stance

    def collect_party_positions(self, topic, party):
        """Collect all party positions for a given topic."""
        positions = StatementPosition.objects.filter(
            statement__theme__topic=topic, party=party
        ).select_related("statement", "statement__theme")

        if not positions:
            self.stdout.write(
                self.style.WARNING(f"No positions found for topic: {topic.name}")
            )
            return []

        return [
            {
                "topic": pos.statement.theme.topic.name,
                "statement_id": pos.statement.id,
                "statement": pos.statement.text,
                "party": party.name,
                "id": pos.id,
                "stance": self.format_stance(pos.stance),
                "explanation": pos.explanation,
            }
            for pos in positions
        ]

    def augment_party_position_with_program_fragments(self, party, topic):
        """Augment the party position with program fragments."""
        fragments = ProgramFragment.objects.filter(
            program__party=party, topic=topic
        ).order_by("-relevance_score")

        return (
            [{"id": f.id, "content": f.content} for f in fragments]
            if fragments.exists()
            else []
        )

    def build_content(self, topic, party, max_tokens=30000):
        """
        Build the content for the OpenAI request, adding program fragments only until the token limit is reached.
        Uses tiktoken to count tokens for gpt-4.1-mini.
        """
        party_positions = self.collect_party_positions(topic, party)
        if not party_positions:
            raise ValueError(
                f"No positions found for topic: {topic.name} and party: {party.name}"
            )

        # Get program fragments for this party and topic
        program_fragments = self.augment_party_position_with_program_fragments(
            party, topic
        )

        encoding = tiktoken.get_encoding("cl100k_base")
        frag_divider = "-" * 10 + "\n"
        content = ""
        token_count = len(encoding.encode(content))

        # Add program fragments first
        if program_fragments:
            frag_header = f"Programma fragmenten ({len(program_fragments)}):\n"
            content += frag_header

            for fragment in program_fragments:
                frag_text = (
                    "\n"
                    + ("_" * 5)
                    + f"START ID: ProgramFragment-{fragment['id']}"
                    + ("_" * 5)
                    + "\n"
                )
                frag_text += f"{fragment['content']}\n"
                frag_text += (
                    ("_" * 5)
                    + f"END ID: ProgramFragment-{fragment['id']}"
                    + ("_" * 5)
                    + "\n"
                )
                frag_tokens = len(encoding.encode(frag_text))
                if token_count + frag_tokens > max_tokens:
                    break
                content += frag_text
                token_count += frag_tokens

            content += "\n"

        # Add statement positions
        content += "\nBij de volgende stellingen hebben we uitleg:\n"
        for pos in party_positions:
            pos_text = (
                "\n"
                + ("_" * 5)
                + f"START ID: StatementPosition-{pos['id']}"
                + ("_" * 5)
                + "\n"
            )
            pos_text = frag_divider + (
                f"Stelling: {pos['statement']}\n"
                f"Standpunt: {party.name} is {pos['stance']}\n"
                f"Uitleg: {pos['explanation']}\n"
            )
            pos_text += (
                ("_" * 5) + f"END ID: StatementPosition-{pos['id']}" + ("_" * 5) + "\n"
            )
            token_count += len(encoding.encode(pos_text))
            if token_count > max_tokens:
                break
            content += pos_text

        content = content.strip()
        prompt = SYSTEM.format(
            topic_name=topic.name, party_name=party.name, content=content
        )
        token_count += len(encoding.encode(prompt))
        return prompt, token_count

    def validate_and_parse_sources(self, sources, party_id, topic_id):
        """
        Validate source objects with IDs and relevance scores.
        Returns dict with valid sources and their relevance scores.
        """
        valid_sources = {"statement_positions": [], "program_fragments": []}

        for source in sources:
            if (
                not isinstance(source, dict)
                or "id" not in source
                or "relevance_score" not in source
            ):
                print(
                    f"Warning: Invalid source format, expected object with 'id' and 'relevance_score': {source}"
                )
                continue

            source_id = source["id"]
            relevance_score = source["relevance_score"]

            # Validate relevance score
            if not isinstance(relevance_score, (int, float)) or not (
                0.0 <= relevance_score <= 1.0
            ):
                print(
                    f"Warning: Invalid relevance score {relevance_score} for source {source_id}, must be between 0.0 and 1.0"
                )
                continue

            if source_id.startswith("StatementPosition-"):
                try:
                    statement_id = int(source_id.split("-")[1])
                    # Verify this StatementPosition exists for this party and topic
                    if StatementPosition.objects.filter(
                        id=statement_id,
                        party_id=party_id,
                        statement__theme__topic_id=topic_id,
                    ).exists():
                        valid_sources["statement_positions"].append(
                            {"id": statement_id, "relevance_score": relevance_score}
                        )
                    else:
                        print(
                            f"Warning: StatementPosition {statement_id} not found for party {party_id} and topic {topic_id}"
                        )
                except (ValueError, IndexError):
                    print(f"Warning: Invalid StatementPosition ID format: {source_id}")

            elif source_id.startswith("ProgramFragment-"):
                try:
                    fragment_id = int(source_id.split("-")[1])
                    # Verify this ProgramFragment exists for this party and topic
                    if ProgramFragment.objects.filter(
                        id=fragment_id, program__party_id=party_id, topic_id=topic_id
                    ).exists():
                        valid_sources["program_fragments"].append(
                            {"id": fragment_id, "relevance_score": relevance_score}
                        )
                    else:
                        print(
                            f"Warning: ProgramFragment {fragment_id} not found for party {party_id} and topic {topic_id}"
                        )
                except (ValueError, IndexError):
                    print(f"Warning: Invalid ProgramFragment ID format: {source_id}")
            else:
                print(f"Warning: Unknown source format: {source_id}")

        return valid_sources

    def create_party_position_sources(self, party_position, valid_sources):
        """
        Create PartyPositionSource records for valid sources with LLM-generated relevance scores
        """
        from apps.content.models import PartyPositionSource

        created_count = 0

        # Create sources for StatementPositions
        for source_data in valid_sources["statement_positions"]:
            source, created = PartyPositionSource.objects.get_or_create(
                party_position=party_position,
                statement_position_id=source_data["id"],
                defaults={"relevance_score": source_data["relevance_score"]},
            )
            # Update relevance score if record already exists but with different score
            if not created and source.relevance_score != source_data["relevance_score"]:
                source.relevance_score = source_data["relevance_score"]
                source.save()
            if created:
                created_count += 1

        # Create sources for ProgramFragments
        for source_data in valid_sources["program_fragments"]:
            source, created = PartyPositionSource.objects.get_or_create(
                party_position=party_position,
                program_fragment_id=source_data["id"],
                defaults={"relevance_score": source_data["relevance_score"]},
            )
            # Update relevance score if record already exists but with different score
            if not created and source.relevance_score != source_data["relevance_score"]:
                source.relevance_score = source_data["relevance_score"]
                source.save()
            if created:
                created_count += 1

        return created_count

    def handle(self, *args, **options):
        client = OpenAI()
        print("Creating batch input file...")
        # Check if batch ID file exists
        if os.path.exists(BATCH_ID_FILE):
            with open(BATCH_ID_FILE, "r") as f:
                batch_id = f.read().strip()
            print(f"Using existing batch ID: {batch_id}")
        else:
            print("No existing batch ID found, creating a new batch...")

            # 1. Build input JSONL
            fd, path = tempfile.mkstemp(suffix=".jsonl")
            total_tokens = 0
            with open(path, "w", encoding="utf-8") as f:
                for party in PoliticalParty.objects.all():
                    for topic in Topic.objects.all():
                        content, tokens = self.build_content(topic, party)
                        total_tokens += tokens

                        prompt = {
                            "model": "gpt-4.1-mini",
                            "temperature": 0.2,
                            "top_p": 1,
                            "seed": 7,
                            "response_format": {
                                "type": "json_schema",
                                "json_schema": SCHEMA,
                            },
                            "messages": [
                                {"role": "system", "content": SYSTEM},
                                {"role": "user", "content": content},
                            ],
                        }
                        entry = {
                            "custom_id": f"p_{party.id}-t_{topic.id}",
                            "method": "POST",
                            "url": "/v1/chat/completions",
                            "body": prompt,
                        }
                        f.write(json.dumps(entry) + "\n")

            # Have the user inspect the input file
            print(
                f"Input file created at {path}. Total tokens: {total_tokens}. Please inspect it before proceeding."
            )
            input("Press Enter to continue or Ctrl+C to cancel...")

            # 2. Upload input file
            print("Uploading file to OpenAI...")
            input_file = client.files.create(file=open(path, "rb"), purpose="batch")
            print("Uploaded file:", input_file.id)

            # 3. Submit batch
            batch = client.batches.create(
                input_file_id=input_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            print("Batch ID:", batch.id)
            batch_id = batch.id

        # Save Batch ID to local .txt file
        with open("party_positions_batch_id.txt", "w") as f:
            f.write(batch_id)

        # 4. Poll until completion
        print("Waiting for batch to complete...")
        while True:
            b = client.batches.retrieve(batch_id)
            print(
                f"[{b.status}] processed: {b.request_counts.completed}/{b.request_counts.total}, errors: {b.request_counts.failed}"
            )
            if b.status in ("completed", "failed", "cancelled"):
                break
            time.sleep(300)

        if b.status != "completed":
            print(f"Batch failed with status: {b.status}")
            return

        # 5. Download results
        print("Downloading results...")
        output = client.files.content(b.output_file_id)
        output_str = output.text
        results = [json.loads(line) for line in output_str.splitlines()]

        self.stdout.write(
            self.style.SUCCESS(f"Downloaded {len(results)} results from OpenAI batch.")
        )

        # 6. Apply results to PartyPositions
        updated = 0
        sources_created = 0
        cleanup = True
        for row in results:
            custom_id = row.get("custom_id", "")
            if not custom_id.startswith("p_"):
                continue

            try:
                parts = custom_id.split("-")
                if len(parts) != 2:
                    print(f"Invalid custom_id format: {custom_id}")
                    continue
                party_id = int(parts[0].split("_")[1])
                topic_id = int(parts[1].split("_")[1])
                body = row["response"]["body"]
                message = (
                    body["choices"][0]["message"]["content"]
                    .rstrip("```json")
                    .lstrip("```")
                )
                result = json.loads(message)

                positions = result.get("positions", [])
                if not positions:
                    print(f"No positions found for {custom_id}")
                    continue

                for pos in positions:
                    short_explanation = pos.get("short_explanation", "")
                    long_explanation = pos.get("long_explanation", "")
                    ranking = pos.get("ranking", 1)
                    sources = pos.get("sources", [])

                    # Validate sources
                    if not sources:
                        print(
                            f"Warning: No sources provided for position {ranking} in {custom_id}"
                        )
                        continue

                    valid_sources = self.validate_and_parse_sources(
                        sources, party_id, topic_id
                    )
                    if (
                        not valid_sources["statement_positions"]
                        and not valid_sources["program_fragments"]
                    ):
                        print(
                            f"Warning: No valid sources found for position {ranking} in {custom_id}"
                        )
                        continue

                    # Create or update the PartyPosition
                    party_position, created = PartyPosition.objects.update_or_create(
                        party_id=party_id,
                        topic_id=topic_id,
                        ranking=ranking,
                        defaults={
                            "short": short_explanation,
                            "explanation": long_explanation,
                        },
                    )

                    if created:
                        updated += 1

                    # Create source relationships
                    created_sources = self.create_party_position_sources(
                        party_position, valid_sources
                    )
                    sources_created += created_sources

                    # Debug information about relevance scores
                    total_sources = len(valid_sources["statement_positions"]) + len(
                        valid_sources["program_fragments"]
                    )
                    avg_relevance = 0.0
                    if total_sources > 0:
                        all_scores = [
                            s["relevance_score"]
                            for s in valid_sources["statement_positions"]
                        ]
                        all_scores.extend(
                            [
                                s["relevance_score"]
                                for s in valid_sources["program_fragments"]
                            ]
                        )
                        avg_relevance = sum(all_scores) / len(all_scores)

                    print(
                        f"Processed position {ranking} for {custom_id}: {created_sources} sources created, avg relevance: {avg_relevance:.3f}"
                    )

            except Exception as e:
                print(f"Failed to process {custom_id}: {e}")
                cleanup = False

        # Remove local batch ID .txt

        if cleanup:
            os.remove(BATCH_ID_FILE)

        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} PartyPosition entries and created {sources_created} source connections."
            )
        )
