import json
import os
import re
import tempfile
import time

tempfile, time
from django.core.management.base import BaseCommand
from openai import OpenAI
from apps.content.models import (
    StatementPosition,
    ProgramFragment,
    ExampleOpinion,
    PoliticalDimensions,
)

BATCH_ID_FILE = "political_axes_batch_id.txt"

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

SYSTEM = (
    "Label the statement or fragment on six axes in [-1,1]. "
    "\nLabel measurements on the following axes:\n"
    "economic: –1: left → +1: right\n"
    "social: –1: progressive → +1: conservative\n"
    "environmental: –1: green → +1: brown\n"
    "immigration: –1: open → +1: closed\n"
    "europe: –1: pro-EU → +1: anti-EU\n"
    "authority: –1: libertarian → +1: authoritarian\n"
    "institutionality: –1: institutional → +1: anti-elite/populist\n"
    "Use rubrics with anchors at -1, -0.5, 0, +0.5, +1. "
    "Output strictly as JSON (no text). Keep evidence ≤ 80 chars if provided. "
    "Not all dimensions apply to all fragments; infer which are relevant using context. "
    "If a dimension is not inferable, set confidence to 0.0 and leave evidence empty."
)


class Command(BaseCommand):
    help = (
        "Batch-label StatementPosition, ProgramFragment, and ExampleOpinion objects "
        "with political axes using OpenAI batch API."
    )

    def build_content(self, obj):
        if isinstance(obj, StatementPosition):
            return f"Stelling: {obj.statement.text}\nReactie: {obj.explanation}\n"
        elif isinstance(obj, ProgramFragment):
            return f"Tekst: {obj.content}\n"
        elif isinstance(obj, ExampleOpinion):
            stmt = obj.statements.first()
            if stmt:
                return f"Stelling: {stmt.text}\nReactie: {obj.text}\n"
            return f"{obj.text}\n"
        return ""

    def handle(self, *args, **options):
        client = OpenAI()
        # Gather objects needing labels
        statement_qs = StatementPosition.objects.filter(dimensions__isnull=True)
        fragment_qs = ProgramFragment.objects.filter(dimensions__isnull=True)
        opinion_qs = ExampleOpinion.objects.filter(dimensions__isnull=True)
        objects = list(statement_qs) + list(fragment_qs) + list(opinion_qs)

        total = len(objects)
        self.stdout.write(f"Found {total} objects to label with political dimensions.")
        if total == 0:
            return

        # Check for existing batch
        if os.path.exists(BATCH_ID_FILE):
            with open(BATCH_ID_FILE, "r") as f:
                batch_id = f.read().strip()
            self.stdout.write(f"Using existing batch ID: {batch_id}")
        else:
            # Build JSONL input
            fd, path = tempfile.mkstemp(suffix=".jsonl")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for obj in objects:
                    content = self.build_content(obj)
                    prompt = {
                        "model": "ft:gpt-4.1-nano-2025-04-14:personal:open-politiek:BzP3XuMZ",
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
                    custom_id = f"{obj._meta.model_name}_{obj.id}"
                    entry = {
                        "custom_id": custom_id,
                        "method": "POST",
                        "url": "/v1/chat/completions",
                        "body": prompt,
                    }
                    f.write(json.dumps(entry) + "\n")

            self.stdout.write(
                f"Input file created at {path}. Please inspect before continuing."
            )
            input("Press Enter to continue or Ctrl+C to cancel...")

            # Upload and create batch
            input_file = client.files.create(file=open(path, "rb"), purpose="batch")
            self.stdout.write(f"Uploaded file: {input_file.id}")
            batch = client.batches.create(
                input_file_id=input_file.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            batch_id = batch.id
            with open(BATCH_ID_FILE, "w") as f:
                f.write(batch_id)
            self.stdout.write(f"Batch ID: {batch_id}")

        # Poll for completion
        self.stdout.write("Waiting for batch to complete...")
        while True:
            b = client.batches.retrieve(batch_id)
            self.stdout.write(
                f"[{b.status}] {b.request_counts.completed}/{b.request_counts.total} completed, {b.request_counts.failed} failed"
            )
            if b.status in ("completed", "failed", "cancelled"):
                break
            time.sleep(300)

        if b.status != "completed":
            self.stdout.write(self.style.ERROR(f"Batch failed: {b.status}"))
            return

        # Download and process results
        output = client.files.content(b.output_file_id)
        output_str = output.text
        results = [json.loads(line) for line in output_str.splitlines()]
        updated = 0

        for row in results:
            cid = row.get("custom_id", "")
            parts = cid.split("_")
            if len(parts) != 2:
                continue
            model_name, obj_id = parts[0], parts[1]
            try:
                obj_id = int(obj_id)
            except ValueError:
                continue
            # Retrieve object
            if model_name == "statementposition":
                obj = StatementPosition.objects.get(id=obj_id)
            elif model_name == "programfragment":
                obj = ProgramFragment.objects.get(id=obj_id)
            elif model_name == "exampleopinion":
                obj = ExampleOpinion.objects.get(id=obj_id)
            else:
                continue

            body = row["response"]["body"]
            msg = body["choices"][0]["message"]["content"]
            # Remove markdown fences and whitespace
            msg = msg.strip()
            msg = re.sub(r"^```json\\s*", "", msg)
            msg = re.sub(r"```$", "", msg)
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                print("Invalid JSON from OpenAI:", msg)
                msg += '"}'
                try:
                    data = json.loads(msg)
                except json.JSONDecodeError:
                    print("Still invalid JSON:", msg)
                    continue

            # Create or update dimensions
            dims = obj.dimensions
            if not dims:
                dims = PoliticalDimensions.objects.create(
                    economic=data.get("economic", 0),
                    social=data.get("social", 0),
                    environmental=data.get("environmental", 0),
                    immigration=data.get("immigration", 0),
                    europe=data.get("europe", 0),
                    authority=data.get("authority", 0),
                    institutionality=data.get("institutionality", 0),
                    confidence=data.get("confidence", 0.0),
                    evidence=data.get("evidence", "").replace("\x00", ""),
                )
                obj.dimensions = dims
            else:
                PoliticalDimensions.objects.filter(id=dims.id).update(
                    economic=data.get("economic", 0),
                    social=data.get("social", 0),
                    environmental=data.get("environmental", 0),
                    immigration=data.get("immigration", 0),
                    europe=data.get("europe", 0),
                    authority=data.get("authority", 0),
                    institutionality=data.get("institutionality", 0),
                    confidence=data.get("confidence", 0.0),
                    evidence=data.get("evidence", "").replace("\x00", ""),
                )
            obj.save()
            updated += 1

        # Cleanup
        os.remove(BATCH_ID_FILE)
        self.stdout.write(
            self.style.SUCCESS(f"Updated {updated} objects with political dimensions.")
        )
