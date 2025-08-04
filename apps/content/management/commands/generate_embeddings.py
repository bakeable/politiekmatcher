"""
Management command to generate embeddings for program fragments.
This improves search accuracy by creating semantic embeddings.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.content.models import ProgramFragment
from apps.utils.llm import embed_text
import time


class Command(BaseCommand):
    help = "Generate embeddings for program fragments to improve search accuracy"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Number of fragments to process in each batch",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenerate embeddings for fragments that already have them",
        )
        parser.add_argument(
            "--min-words",
            type=int,
            default=10,
            help="Minimum word count for fragments to process",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        force = options["force"]
        min_words = options["min_words"]

        # Get fragments to process
        if force:
            queryset = ProgramFragment.objects.filter(word_count__gte=min_words)
            self.stdout.write(
                f"Processing ALL fragments with at least {min_words} words..."
            )
        else:
            queryset = ProgramFragment.objects.filter(
                embedding__isnull=True, word_count__gte=min_words
            )
            self.stdout.write(
                f"Processing fragments WITHOUT embeddings with at least {min_words} words..."
            )

        total_count = queryset.count()
        self.stdout.write(f"Found {total_count} fragments to process")

        if total_count == 0:
            self.stdout.write(self.style.SUCCESS("No fragments to process"))
            return

        processed = 0
        batch_start_time = time.time()

        # Process in batches
        for i in range(0, total_count, batch_size):
            batch = queryset[i : i + batch_size]

            batch_fragments = []
            for fragment in batch:
                try:
                    # Create enhanced text for embedding
                    enhanced_text = self.create_enhanced_text(fragment)

                    # Generate embedding
                    embedding = embed_text(enhanced_text)

                    # Update fragment
                    fragment.embedding = embedding
                    batch_fragments.append(fragment)

                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Error processing fragment {fragment.id}: {e}"
                        )
                    )
                    continue

            # Bulk update embeddings
            if batch_fragments:
                with transaction.atomic():
                    ProgramFragment.objects.bulk_update(
                        batch_fragments, ["embedding"], batch_size=batch_size
                    )

            processed += len(batch_fragments)
            batch_time = time.time() - batch_start_time

            # Progress update
            percentage = (processed / total_count) * 100
            rate = processed / batch_time if batch_time > 0 else 0

            self.stdout.write(
                f"Progress: {processed}/{total_count} ({percentage:.1f}%) - "
                f"{rate:.1f} fragments/sec"
            )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully processed {processed} fragments")
        )

    def create_enhanced_text(self, fragment):
        """
        Create enhanced text for better embedding by including context.
        """
        parts = []

        # Add party context
        parts.append(f"Partij: {fragment.program.party.name}")

        # Add program context
        parts.append(f"Programma: {fragment.program.title} {fragment.program.year}")

        # Add topic if available
        if fragment.topic:
            parts.append(f"Onderwerp: {fragment.topic.name}")

        # Add fragment type context
        type_mapping = {
            "bullet_point": "Beleidspunt",
            "title_section": "Hoofdtitel",
            "heading_section": "Hoofdstuk",
            "subtitle_section": "Sectie",
            "text_block": "Tekst",
        }
        fragment_type = type_mapping.get(fragment.fragment_type, fragment.fragment_type)
        parts.append(f"Type: {fragment_type}")

        # Add the main content
        parts.append(f"Inhoud: {fragment.content}")

        # Join with newlines for better embedding
        return "\n".join(parts)
