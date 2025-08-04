"""
Django management command to import election programs from RUG University repository
"""

import json

from politiekmatcher import settings
import requests
import re
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.content.models import PoliticalParty, ElectionProgram


class RUGElectionProgramImporter:
    """Importer for RUG University election program repository"""

    def __init__(self):
        # Mapping variations of party names to standardized abbreviations
        self.party_name_mappings = settings.PARTY_NAME_MAPPINGS

    def fetch_rug_data(self, url: str) -> Dict:
        """Fetch election program data from RUG repository"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }

            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # The response might be JSONP, so we need to extract the JSON
            content = response.text

            # Remove JSONP wrapper if present (e.g., "callback({...})")
            if content.startswith("(") and content.endswith(")"):
                content = content[1:-1]
            elif "(" in content and content.endswith(")"):
                # Handle "functionName({...})" format
                start_idx = content.find("(")
                if start_idx != -1:
                    content = content[start_idx + 1 : -1]

            return json.loads(content)

        except requests.RequestException as e:
            raise CommandError(f"Failed to fetch data from RUG: {e}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Failed to parse JSON response: {e}")

    def normalize_party_name(self, party_name: str) -> str:
        """Normalize party name for comparison"""
        if not party_name:
            return ""

        # Remove common prefixes/suffixes and normalize
        normalized = party_name.strip()
        normalized = re.sub(r"\s+", " ", normalized)  # Normalize whitespace
        normalized = normalized.replace("-", " ")
        normalized = normalized.replace("_", " ")

        return normalized

    def find_matching_party(
        self, rug_party_name: str, rug_party_variant: str = None
    ) -> Optional[PoliticalParty]:
        """Find matching PoliticalParty in database using fuzzy matching"""
        if not rug_party_name and not rug_party_variant:
            return None

        # Combine party name and variant for search
        search_terms = []
        if rug_party_name:
            search_terms.append(self.normalize_party_name(rug_party_name))
        if rug_party_variant and rug_party_variant != rug_party_name:
            search_terms.append(self.normalize_party_name(rug_party_variant))

        # Get all parties from database
        db_parties = PoliticalParty.objects.all()

        best_match = None
        best_score = 0.0

        for db_party in db_parties:
            # Check against abbreviation and name
            db_terms = [db_party.abbreviation, self.normalize_party_name(db_party.name)]

            # Also check against known mappings
            for abbrev, variations in self.party_name_mappings.items():
                if db_party.abbreviation == abbrev:
                    db_terms.extend([self.normalize_party_name(v) for v in variations])

            # Calculate similarity scores
            for search_term in search_terms:
                for db_term in db_terms:
                    if not search_term or not db_term:
                        continue

                    # Exact match (case insensitive)
                    if search_term.lower() == db_term.lower():
                        return db_party

                    # Fuzzy match
                    similarity = SequenceMatcher(
                        None, search_term.lower(), db_term.lower()
                    ).ratio()
                    if similarity > best_score:
                        best_score = similarity
                        best_match = db_party

        # Only return match if confidence is high enough
        if best_score >= 0.8:
            return best_match

        return None

    def select_best_document(self, documents: List[Dict], year: int) -> Optional[Dict]:
        """Select the best document from available options"""
        if not documents:
            return None

        # Score documents based on various criteria
        scored_docs = []

        for doc in documents:
            score = 0

            # Check format description and main file name
            format_desc = doc.get("formatdesc", "").lower()
            main_file = doc.get("main", "").lower()

            # Prefer final versions over concepts
            if "concept" in format_desc or "concept" in main_file:
                score -= 20
            elif "definitief" in format_desc or "final" in format_desc:
                score += 10

            # Prefer documents with year in title
            if str(year) in format_desc or str(year) in main_file:
                score += 5

            # Prefer PDF format
            if doc.get("mime_type") == "application/pdf":
                score += 5

            # Prefer larger files (usually more complete)
            files = doc.get("files", [])
            if files:
                max_size = max(f.get("filesize", 0) for f in files)
                score += min(max_size / 100000, 10)  # Cap at 10 points

            # Prefer higher placement
            placement = doc.get("placement", 999)
            score += max(0, 10 - placement)

            scored_docs.append((score, doc))

        # Return document with highest score
        scored_docs.sort(key=lambda x: x[0], reverse=True)
        return scored_docs[0][1]

    def extract_file_url(self, document: Dict) -> Optional[str]:
        """Extract the best file URL from a document"""
        files = document.get("files", [])
        if not files:
            return None

        # Prefer PDF files
        pdf_files = [f for f in files if f.get("mime_type") == "application/pdf"]
        if pdf_files:
            # Return largest PDF file
            best_file = max(pdf_files, key=lambda f: f.get("filesize", 0))
            return best_file.get("uri")

        # Fallback to any file
        best_file = max(files, key=lambda f: f.get("filesize", 0))
        return best_file.get("uri")

    def determine_url_type(self, url: str, mime_type: str = None) -> str:
        """Determine URL type based on URL and MIME type"""
        if mime_type:
            if "pdf" in mime_type.lower():
                return "pdf"
            elif "word" in mime_type.lower() or "msword" in mime_type.lower():
                return "docx"
            elif "html" in mime_type.lower():
                return "html"

        # Fallback to URL extension
        url_lower = url.lower()
        if url_lower.endswith(".pdf"):
            return "pdf"
        elif url_lower.endswith((".doc", ".docx")):
            return "docx" if url_lower.endswith(".docx") else "doc"
        elif url_lower.endswith(".html"):
            return "html"

        return "pdf"  # Most RUG documents are PDFs


class Command(BaseCommand):
    help = "Import election programs from RUG University repository"

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=2023,
            help="Election year to import (default: 2023)",
        )
        parser.add_argument(
            "--url",
            type=str,
            default="https://dnpprepo.ub.rug.nl/cgi/exportview/verkiezingsprogramma/tweede=5Fkamerverkiezingen/JSON/tweede=5Fkamerverkiezingen.js",
            help="RUG JSON export URL",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without saving to database",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing election programs if found",
        )

    def handle(self, *args, **options):
        importer = RUGElectionProgramImporter()
        year = options["year"]

        self.stdout.write(
            f"🏛️  Importing election programs for {year} from RUG repository..."
        )

        # Fetch data from RUG
        try:
            data = importer.fetch_rug_data(options["url"])
        except CommandError as e:
            self.stdout.write(self.style.ERROR(f"❌ {e}"))
            return

        if not isinstance(data, list):
            self.stdout.write(
                self.style.ERROR("❌ Expected a list of programs from RUG API")
            )
            return

        self.stdout.write(f"📥 Fetched {len(data)} programs from RUG repository")

        # Filter for the specified year and type
        filtered_programs = []
        for program in data:
            if (
                program.get("date") == year
                and program.get("type") == "verkiezingsprogramma"
                and program.get("purpose") == "tweede_kamerverkiezingen"
            ):
                filtered_programs.append(program)

        self.stdout.write(f"🎯 Found {len(filtered_programs)} programs for {year}")

        if not filtered_programs:
            self.stdout.write(
                self.style.WARNING(f"⚠️  No programs found for year {year}")
            )
            return

        imported_count = 0
        updated_count = 0
        skipped_count = 0
        no_match_count = 0

        for rug_program in filtered_programs:
            party_name = rug_program.get("party", "")
            party_variant = rug_program.get("party_variant", "")
            title = rug_program.get("title", "")

            self.stdout.write(f"\n🔍 Processing: {party_variant or party_name}")
            self.stdout.write(f"   Title: {title}")

            # Find matching party in database
            db_party = importer.find_matching_party(party_name, party_variant)

            if not db_party:
                self.stdout.write(
                    f"   ❌ No matching party found for: {party_variant or party_name}"
                )
                no_match_count += 1
                continue

            self.stdout.write(
                f"   ✅ Matched with: {db_party.name} ({db_party.abbreviation})"
            )

            # Check if program already exists
            existing_program = ElectionProgram.objects.filter(
                party=db_party, year=year
            ).first()

            if existing_program and not options["update_existing"]:
                self.stdout.write(f"   📋 Already exists: {existing_program.title}")
                skipped_count += 1
                continue

            # Select best document
            documents = rug_program.get("documents", [])
            best_doc = importer.select_best_document(documents, year)

            if not best_doc:
                self.stdout.write(f"   ❌ No suitable document found")
                continue

            # Extract file URL
            file_url = importer.extract_file_url(best_doc)
            if not file_url:
                self.stdout.write(f"   ❌ No file URL found in document")
                continue

            # Determine URL type
            mime_type = best_doc.get("mime_type")
            url_type = importer.determine_url_type(file_url, mime_type)

            self.stdout.write(
                f"   📄 Document: {best_doc.get('formatdesc', 'Unknown')}"
            )
            self.stdout.write(f"   🔗 URL: {file_url}")
            self.stdout.write(f"   📋 Type: {url_type}")

            # Create or update program
            if not options["dry_run"]:
                try:
                    with transaction.atomic():
                        if existing_program:
                            # Update existing
                            existing_program.title = (
                                title
                                or f"{db_party.abbreviation} Verkiezingsprogramma {year}"
                            )
                            existing_program.source_url = file_url
                            existing_program.pdf_url = (
                                file_url if url_type == "pdf" else ""
                            )
                            existing_program.url_type = url_type
                            existing_program.is_imported = False  # Mark for re-import
                            existing_program.save()

                            updated_count += 1
                            self.stdout.write(
                                f"   🔄 Updated: {existing_program.title}"
                            )
                        else:
                            # Create new
                            program = ElectionProgram.objects.create(
                                party=db_party,
                                title=title
                                or f"{db_party.abbreviation} Verkiezingsprogramma {year}",
                                year=year,
                                source_url=file_url,
                                pdf_url=file_url if url_type == "pdf" else "",
                                url_type=url_type,
                                is_imported=False,
                                is_active=True,
                            )

                            imported_count += 1
                            self.stdout.write(f"   ✅ Created: {program.title}")

                except Exception as e:
                    self.stdout.write(f"   ❌ Database error: {e}")
                    continue
            else:
                self.stdout.write(
                    f"   🔍 DRY RUN: Would {'update' if existing_program else 'create'} program"
                )

        # Summary
        self.stdout.write(f"\n🎉 Import complete!")
        if not options["dry_run"]:
            self.stdout.write(f"   ✅ Imported: {imported_count} new programs")
            self.stdout.write(f"   🔄 Updated: {updated_count} existing programs")
        self.stdout.write(f"   ⏭️  Skipped: {skipped_count} existing programs")
        self.stdout.write(f"   ❌ No match: {no_match_count} programs")

        if (imported_count > 0 or updated_count > 0) and not options["dry_run"]:
            self.stdout.write(
                f"\n💡 Next step: Run 'python manage.py import_election_programs' to download and process the content"
            )
