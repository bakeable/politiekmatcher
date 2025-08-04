import json
import os
import re
import tempfile
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from openai import OpenAI

from apps.content.models import StatementPosition, ThemePosition, PoliticalDimensions
from apps.profiles.management.commands.apply_political_dimensions import SYSTEM
from politiekmatcher.settings import PARTY_NAME_MAPPINGS


SCHEMA = {
    "name": "political_axes",
    "schema": {
        "type": "object",
        "properties": {
            "economic": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "social": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "environmental": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "immigration": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "europe": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "authority": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "institutionality": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "evidence": {"type": "string", "maxLength": 80},
        },
        "required": [
            "economic",
            "social",
            "environmental",
            "immigration",
            "europe",
            "authority",
            "institutionality",
            "confidence",
            "evidence",
        ],
        "additionalProperties": False,
    },
    "strict": True,
}


def replace_party_names(text):
    """Replace party names in the text with 'partij' to avoid bias."""
    # Replace party names by "partij", to avoid bias
    for key, variations in PARTY_NAME_MAPPINGS.items():
        text = re.sub(key, "partij", text, flags=re.IGNORECASE)
        for variation in variations:
            text = re.sub(variation, "partij", text, flags=re.IGNORECASE)

    return text


class Command(BaseCommand):
    help = "Label StatementPosition explanations using OpenAI Batch API and save PoliticalDimensions."

    def handle(self, *args, **options):
        client = OpenAI()
        print("Creating batch input file...")
        # Check if batch ID file exists
        if os.path.exists("batch_id.txt"):
            with open("batch_id.txt", "r") as f:
                batch_id = f.read().strip()
            print(f"Using existing batch ID: {batch_id}")
        else:
            print("No existing batch ID found, creating a new batch...")

            # 1. Build input JSONL
            fd, path = tempfile.mkstemp(suffix=".jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for pos in StatementPosition.objects.select_related(
                    "statement", "statement__theme"
                ).all():
                    if not pos.statement.theme:
                        continue

                    text = replace_party_names(pos.explanation.strip())
                    content = f""""
                    Stelling: {pos.statement.text}
                    Reactie: {text}
                    """
                    prompt = {
                        "model": "gpt-4o-mini",
                        "temperature": 0,
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
                        "max_tokens": 200,
                    }
                    entry = {
                        "custom_id": f"sp_{pos.id}",
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": prompt,
                    }
                    f.write(json.dumps(entry) + "\n")

            # Have the user inspect the input file
            print(f"Input file created at {path}. Please inspect it before proceeding.")
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
        with open("batch_id.txt", "w") as f:
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

        # 6. Create examples using each result
        updated = 0
        output_path = "openai_finetune_political_dimensions_examples.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for row in results:
                custom_id = row.get("custom_id", "")
                if not custom_id.startswith("sp_"):
                    continue

                try:
                    pos_id = int(custom_id.split("_")[1])
                    body = row["response"]["body"]
                    message = body["choices"][0]["message"]["content"]
                    result = json.loads(message)

                    # Fill from ThemePosition if available
                    pos = StatementPosition.objects.get(id=pos_id)
                    theme = pos.statement.theme
                    theme_pos = ThemePosition.objects.filter(
                        party=pos.party, theme=theme
                    ).first()

                    economic = (
                        round(theme_pos.left_wing * -1 + theme_pos.right_wing * 1, 3)
                        if theme_pos
                        else result.get("economic", 0.0)
                    )
                    social = (
                        round(
                            theme_pos.progressive * -1 + theme_pos.conservative * 1, 3
                        )
                        if theme_pos
                        else result.get("social", 0.0)
                    )

                    # Create input object
                    text = replace_party_names(pos.explanation.strip())
                    content = f"""Stelling: {pos.statement.text}\nReactie: {text}"""

                    response = {
                        "economic": economic,
                        "social": social,
                        "environmental": result.get("environmental", 0.0),
                        "immigration": result.get("immigration", 0.0),
                        "europe": result.get("europe", 0.0),
                        "authority": result.get("authority", 0.0),
                        "institutionality": result.get("institutionality", 0.0),
                        "confidence": result.get("confidence", 1.0),
                        "evidence": result.get("evidence", ""),
                    }

                    example = {
                        "messages": [
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": content},
                            {
                                "role": "assistant",
                                "content": f"```json\n{json.dumps(response)}\n```",
                            },
                        ]
                    }

                    if pos.dimensions:
                        pos.dimensions.delete()

                    # Save it to the statement position PoliticalDimensions
                    dimensions = PoliticalDimensions.objects.create(
                        economic=economic,
                        social=social,
                        environmental=result.get("environmental", 0.0),
                        immigration=result.get("immigration", 0.0),
                        europe=result.get("europe", 0.0),
                        authority=result.get("authority", 0.0),
                        institutionality=result.get("institutionality", 0.0),
                        confidence=result.get("confidence", 1.0),
                        evidence=result.get("evidence", ""),
                    )
                    pos.dimensions = dimensions
                    pos.save()

                    # Write to output file
                    f.write(json.dumps(example) + "\n")
                    updated += 1

                except Exception as e:
                    print(f"Failed to process {custom_id}: {e}")

        # Remove local batch ID .txt
        os.remove("batch_id.txt")
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated {updated} StatementPosition entries with new dimensions."
            )
        )
