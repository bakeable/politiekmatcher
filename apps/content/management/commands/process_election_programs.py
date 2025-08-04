from collections import defaultdict
import os
import re
import statistics
from apps.utils.llm import embed_text_batch
import requests
from unstructured.partition.pdf import partition_pdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

import nltk

nltk.download("punkt")
nltk.download("punkt_tab")
from nltk.tokenize import sent_tokenize

from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.content.models import ElectionProgram, ProgramFragment, Topic, TopicKeyword


class Command(BaseCommand):
    help = (
        "Extract all paragraphs and list items from election program PDFs into a list"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--relevance_threshold",
            type=float,
            default=1.5,
            help="Minimum relevance score to keep a fragment",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without applying changes (for testing)",
            default=False,
        )
        parser.add_argument(
            "--skip-fragments",
            action="store_true",
            help="Skip fragment extraction and only classify existing fragments",
            default=False,
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=800,
            help="Target chunk size in characters (default: 800)",
        )
        parser.add_argument(
            "--chunk-overlap",
            type=int,
            default=200,
            help="Overlap between chunks in characters (default: 200)",
        )

    def sanitize_text(self, text: str) -> str:
        """Enhanced text sanitization for Dutch political documents."""
        # Merge hyphenated word splits that are NOT part of compound lists
        text = re.sub(r"(?<!\w)-(?:\s+)(?=\w)", "", text)  # "opge- doekt" → "opgedoekt"

        # Don't join things like "arbeids-, studie- en gezinsmigratie" → keep those
        text = re.sub(r"(\w+)-,", r"\1-,", text)  # preserve compound separators

        # Remove paragraph numbers and section references
        text = re.sub(r"^\d+\.\d*\s*", "", text)  # "12.1 Text" → "Text"
        text = re.sub(
            r"\b\d+\.\d+\.\s*", "", text
        )  # Remove section numbers within text

        # Remove standalone page numbers at end of lines
        text = re.sub(r"\s+\d{1,3}\s*$", "", text)  # Remove trailing page numbers

        # Remove common PDF artifacts
        text = re.sub(r"terug naar inhoudsopgave", "", text)
        text = re.sub(r"^\s*\.\s*", "", text)  # Remove leading dots
        text = re.sub(r"^\s*,\s*", "", text)  # Remove leading commas

        # Clean up multiple spaces and normalize punctuation
        text = re.sub(r"\s+", " ", text)  # Multiple spaces to single space
        text = re.sub(r"\.{2,}", ".", text)  # Multiple dots to single dot

        # Remove words that are all-caps (heuristic for headers/noise)
        def is_all_caps(word):
            alpha = "".join(c for c in word if c.isalpha())
            return len(alpha) > 2 and alpha.isupper()

        words = text.split()
        cleaned_words = [word for word in words if not is_all_caps(word)]
        text = " ".join(cleaned_words)

        return text.strip()

    def correct_fragment_text(self, raw_text):
        """Advanced fragment correction and cleaning."""
        # First apply basic sanitization
        text = self.sanitize_text(raw_text)

        # Remove list style markers
        text = re.sub(r"^[\u2022\-•▶]\s*", "", text)

        # Remove incomplete sentences at the beginning (fragments starting with lowercase)
        if text and not text[0].isupper() and not text[0].isdigit():
            # If it starts with lowercase, try to find the first sentence
            sentences = re.split(r"[.!?]+\s+", text)
            if len(sentences) > 1:
                # Skip the first incomplete sentence
                text = ". ".join(sentences[1:])

        # Remove incomplete sentences at the end (fragments ending without proper punctuation)
        text = text.strip()
        if text and text[-1] not in ".!?":
            # Find the last complete sentence
            sentences = re.split(r"([.!?]+)", text)
            complete_parts = []
            for i in range(0, len(sentences) - 1, 2):
                if i + 1 < len(sentences):
                    complete_parts.append(sentences[i] + sentences[i + 1])
            if complete_parts:
                text = "".join(complete_parts).strip()

        # Ensure the text starts with a capital letter
        if text and text[0].islower():
            text = text[0].upper() + text[1:]

        return text.strip()

    def count_tokens(self, text):
        return len(text.split())

    def create_semantic_fragments(
        self, text, page_num, chunk_size=1200, chunk_overlap=300
    ):
        """
        Create fragments using semantic-aware splitting with substantial overlap.

        Args:
            text: Input text to split
            page_num: Page number for tracking
            chunk_size: Target chunk size in characters (increased from 600 to 1200)
            chunk_overlap: Overlap between chunks in characters (increased from 120 to 300)

        Returns:
            List of fragments with text and page information
        """
        # First, clean the entire text before splitting
        cleaned_text = self.sanitize_text(text)
        self.stdout.write(
            self.style.NOTICE(
                f"🔍 Processing page {page_num}: {len(cleaned_text)} characters"
            )
        )

        # Skip if text is too short after cleaning
        if len(cleaned_text.strip()) < 100:
            return []

        # Try RecursiveCharacterTextSplitter if available, otherwise fall back to paragraph splitting
        try:
            # Initialize semantic text splitter with Dutch-aware separators
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=len,
                separators=[
                    "\n\n",  # Paragraph breaks (highest priority)
                    "\n",  # Line breaks
                    ". ",  # Sentence ends
                    "! ",  # Exclamation ends
                    "? ",  # Question ends
                    "; ",  # Semicolon breaks
                    ", ",  # Comma breaks (lower priority to avoid mid-sentence splits)
                    " ",  # Word breaks (lowest priority)
                    "",  # Character-level (last resort)
                ],
                is_separator_regex=False,
            )

            chunks = text_splitter.split_text(cleaned_text)
            self.stdout.write(
                self.style.NOTICE(
                    f"📄 Page {page_num}: Split into {len(chunks)} semantic chunks"
                )
            )

        except ImportError:
            # Fallback to paragraph-aware splitting if LangChain not available
            self.stdout.write(
                self.style.WARNING(
                    "⚠️ LangChain not available, using fallback splitting"
                )
            )
            chunks = self._fallback_semantic_split(
                cleaned_text, chunk_size, chunk_overlap
            )

        fragments = []
        for i, chunk in enumerate(chunks):
            # Apply final correction to each chunk
            corrected_chunk = self.correct_fragment_text(chunk)

            # Only include fragments with meaningful content
            token_count = self.count_tokens(corrected_chunk)
            if (
                token_count >= 30 and len(corrected_chunk.strip()) >= 100
            ):  # Increased minimum thresholds
                fragments.append(
                    {
                        "text": corrected_chunk,
                        "page": page_num,
                        "token_count": token_count,
                        "chunk_index": i,
                    }
                )

        return fragments

    def _fallback_semantic_split(self, text, chunk_size, chunk_overlap):
        """
        Fallback semantic splitting when LangChain is not available.
        Uses paragraph and sentence boundaries with overlap.
        """
        # Split by double newlines (paragraphs) first
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        current_chunk = ""

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            # If adding this paragraph would exceed chunk size, finalize current chunk
            if len(current_chunk) + len(paragraph) > chunk_size and current_chunk:
                chunks.append(current_chunk.strip())

                # Start new chunk with overlap from previous chunk
                if chunk_overlap > 0:
                    sentences = sent_tokenize(current_chunk)
                    overlap_text = ""
                    # Take last few sentences for overlap
                    for sent in reversed(sentences):
                        if len(overlap_text) + len(sent) <= chunk_overlap:
                            overlap_text = sent + " " + overlap_text
                        else:
                            break
                    current_chunk = overlap_text.strip()
                else:
                    current_chunk = ""

            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + paragraph
            else:
                current_chunk = paragraph

        # Add the last chunk if it has content
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def create_fragments(self, options):
        chunk_size = options["chunk_size"]
        chunk_overlap = options["chunk_overlap"]

        # Ensure output directory exists
        output_dir = Path(settings.BASE_DIR) / "scraped_content"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Fetch all imported PDF programs
        programs = ElectionProgram.objects.filter(is_imported=True, url_type="pdf")
        if not programs.exists():
            self.stdout.write(self.style.WARNING("❌ No imported PDF programs found."))
            return

        for program in programs:
            party = program.party.name
            title = program.title
            year = program.year
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"\n🎯 Processing: {party} – {title} ({year})"
                )
            )
            self.stdout.write(
                self.style.NOTICE(
                    f"📊 Using chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
                )
            )

            # Download PDF via HTTP
            pdf_name = f"{party.lower().replace(' ', '_')}_program_{year}.pdf"
            pdf_path = output_dir / pdf_name
            response = requests.get(program.pdf_url)
            response.raise_for_status()
            with open(pdf_path, "wb") as f:
                f.write(response.content)

            self.stdout.write(self.style.SUCCESS(f"✅ Downloaded PDF to {pdf_path}"))
            # Open PDF and extract fragments
            fragments = []

            # Parse layout-aware elements from PDF
            elements = partition_pdf(filename=str(pdf_path))
            self.stdout.write(
                self.style.NOTICE(
                    f"📄 Found {len(elements)} layout-aware elements in PDF"
                )
            )
            page_texts = defaultdict(list)
            for el in elements:
                if hasattr(el, "text") and el.text:
                    page_num = getattr(el.metadata, "page_number", None)
                    if page_num:
                        page_texts[page_num].append(el.text.strip())

            self.stdout.write(
                self.style.NOTICE(
                    f"📄 Parsed {len(page_texts)} pages with text content"
                )
            )

            # Process each page's text with semantic-aware splitting
            for pg_num, lines in sorted(page_texts.items()):
                page_text = " ".join(lines).strip()
                if not page_text:
                    continue

                # Use semantic-aware splitting with overlap
                page_fragments = self.create_semantic_fragments(
                    text=page_text,
                    page_num=pg_num,
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )

                fragments.extend(page_fragments)

                self.stdout.write(
                    self.style.NOTICE(
                        f"📄 Page {pg_num}: Created {len(page_fragments)} fragments"
                    )
                )

            # Clean up formatting of each fragment with local LLM
            cleaned_fragments = []
            for frag in fragments:
                self.stdout.write(
                    self.style.NOTICE(
                        f"🔍 Cleaning fragment on page {frag['page']}:\n\n{frag['text']}\n"
                    )
                )
                sanitized = self.sanitize_text(frag["text"])
                clean_frag = self.correct_fragment_text(sanitized)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Cleaned fragment on page {frag['page']}: \n\n{clean_frag}\n"
                    )
                )
                cleaned_fragments.append(
                    {"raw": frag["text"], "clean": clean_frag, "page": frag["page"]}
                )

            # Save fragments
            ProgramFragment.objects.filter(program=program).delete()
            ProgramFragment.objects.bulk_create(
                [
                    ProgramFragment(
                        program=program,
                        raw_content=frag["raw"],
                        content=frag["clean"],
                        source_page_start=frag["page"],
                        source_page_end=frag["page"],
                    )
                    for frag in cleaned_fragments
                ]
            )

    def clean_fragments_by_topics(self, options):
        threshold = options["relevance_threshold"]
        apply_changes = not options["dry_run"]

        # Load all topic keywords and sum of relevance for normalization
        topic_keywords = defaultdict(
            list
        )  # topic_id -> list of (keyword, relevance_score)
        topic_score_sums = defaultdict(float)  # topic_id -> sum of relevance_score

        for tk in TopicKeyword.objects.select_related("topic").all():
            kw = tk.keyword.lower()
            topic_keywords[tk.topic_id].append((kw, tk.relevance_score))
            topic_score_sums[tk.topic_id] += tk.relevance_score

        # Classify each fragment
        for frag in ProgramFragment.objects.all():
            text = frag.content.lower()
            scores = {}
            # Compute raw score per topic
            for topic_id, kws in topic_keywords.items():
                score = 0.0
                for kw, rel in kws:
                    # count occurrences of the exact keyword
                    count = len(re.findall(rf"\b{re.escape(kw)}\b", text))
                    score += rel * count
                scores[topic_id] = score

            # Pick best topic
            best_topic_id, best_score = max(
                scores.items(), key=lambda x: x[1], default=(None, 0.0)
            )

            # Compute median of all topic scores for this fragment
            score_values = list(scores.values())
            median_score = statistics.median(score_values) if score_values else 0.0

            # Apply both static and relative thresholds:
            # - static: best_score >= threshold
            # - relative: best_score >= 2 * median_score
            if best_score > threshold or best_score > 2 * median_score:
                topic = Topic.objects.get(id=best_topic_id)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Fragment {frag.id}: assigned to topic '{topic.name}' with score {best_score:.2f}"
                    )
                )
                if apply_changes:
                    # assumes ProgramFragment has `topic` and `relevance_score` fields
                    frag.topic = topic
                    frag.relevance_score = best_score
                    frag.save()

    def embed_fragments(self):
        fragments = ProgramFragment.objects.filter(embedding__isnull=True)

        self.stdout.write(
            self.style.NOTICE(
                f"🧠 Embedding {fragments.count()} unembedded fragments..."
            )
        )

        texts = [frag.content for frag in fragments]
        embeddings = embed_text_batch(texts)

        for frag, embedding in zip(fragments, embeddings):
            frag.embedding = embedding
            frag.save(update_fields=["embedding"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Embedded fragment {frag.id} with embedding size {len(embedding)}"
                )
            )

        self.stdout.write(self.style.SUCCESS("✅ Embedding complete!"))

    def handle(self, *args, **options):
        if options["skip_fragments"]:
            self.stdout.write(
                self.style.WARNING("Skipping fragment extraction as requested.")
            )
        else:
            self.stdout.write(
                self.style.MIGRATE_HEADING("📄 Extracting fragments from PDFs...")
            )
            self.create_fragments(options)

        self.stdout.write(
            self.style.MIGRATE_HEADING("📊 Classifying fragments by topics...")
        )
        self.clean_fragments_by_topics(options)

        self.stdout.write(
            self.style.MIGRATE_HEADING("🔍 Embedding fragments for search...")
        )
        self.embed_fragments()

        self.stdout.write(self.style.SUCCESS("✅ Fragment processing complete!"))
