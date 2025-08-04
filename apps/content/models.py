"""
Content models for PolitiekMatcher

These models represent political parties, programs, and content fragments.
"""

import hashlib
import json
from django.db import models
from django.utils import timezone
from pgvector.django import VectorField
from politiekmatcher.settings import PARTY_ABBREV_TO_NAME, PARTY_NAME_MAPPINGS


class PoliticalParty(models.Model):
    """Model representing a political party"""

    name = models.CharField(max_length=200, help_text="Volledige naam van de partij")
    abbreviation = models.CharField(
        max_length=100, unique=True, help_text="Afkorting (bijv. VVD, PvdA)"
    )
    description = models.TextField(blank=True, help_text="Beschrijving van de partij")
    website_url = models.URLField(blank=True, help_text="Website van de partij")
    logo_url = models.URLField(blank=True, help_text="URL naar logo")
    logo_object_position = models.CharField(max_length=50, blank=True, null=True)
    color_hex = models.CharField(
        max_length=7, blank=True, help_text="Partijkleur in hex (bijv. #FF0000)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Political Party"
        verbose_name_plural = "Political Parties"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"

    @staticmethod
    def get_or_create(name, **kwargs):
        """Get or create a PoliticalParty instance by name or abbreviation"""
        party_name, party_abbreviation = PoliticalParty.get_party_name(name)

        party, _ = PoliticalParty.objects.get_or_create(
            abbreviation=party_abbreviation,
            defaults={"name": party_name, **kwargs},
        )

        return party

    @staticmethod
    def get_party_name(name: str) -> str:
        """
        Normalize party names using predefined mappings.
        Returns the standardized abbreviation or the original name if no mapping exists.
        """
        candidate = name.strip().lower()
        for key, variations in PARTY_NAME_MAPPINGS.items():
            generic_variations = [
                v.strip().lower().replace(" ", "_") for v in variations
            ]
            if (
                candidate in variations
                or candidate == key
                or candidate.strip().lower().replace(" ", "_") in generic_variations
            ):
                candidate = key
                break

        # Use PARTY_ABBREV_TO_NAME dict to find out the full name and appropriate abbreviation
        party_name = candidate
        party_abbreviation = candidate
        for abbrev, name in PARTY_ABBREV_TO_NAME.items():
            if candidate == abbrev or candidate == name:
                party_name = name
                party_abbreviation = abbrev
                break

        return party_name, party_abbreviation

    def save(self, *args, **kwargs):
        # Normalize name and abbreviation
        self.name, self.abbreviation = PoliticalParty.get_party_name(self.name)

        super().save(*args, **kwargs)


class PartyPosition(models.Model):
    """Model representing a party's position on a specific topic"""

    party = models.ForeignKey(
        PoliticalParty, on_delete=models.CASCADE, related_name="party_positions"
    )
    topic = models.ForeignKey(
        "Topic", on_delete=models.CASCADE, related_name="party_positions"
    )
    ranking = models.IntegerField(
        default=0, help_text="Importance ranking of this position from the party's view"
    )
    short = models.TextField(
        blank=True, null=True, help_text="Short statement of the position"
    )
    explanation = models.TextField(
        blank=True, null=True, help_text="Detailed explanation of the position"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("party", "topic", "ranking")
        verbose_name = "Party Position"
        verbose_name_plural = "Party Positions"

    def __str__(self):
        return f"{self.party.abbreviation} - {self.topic.name} ({self.ranking})"


class PartyPositionSource(models.Model):
    """Model representing sources for a party position"""

    party_position = models.ForeignKey(
        PartyPosition, on_delete=models.CASCADE, related_name="sources"
    )

    # Source can be either a StatementPosition or ProgramFragment
    statement_position = models.ForeignKey(
        "StatementPosition",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Reference to a statement position used as source",
    )
    program_fragment = models.ForeignKey(
        "ProgramFragment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Reference to a program fragment used as source",
    )

    # Additional metadata
    relevance_score = models.FloatField(
        default=0.0, help_text="How relevant this source is to the position (0-1)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Party Position Source"
        verbose_name_plural = "Party Position Sources"
        # Ensure only one type of source is set
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(
                        statement_position__isnull=False, program_fragment__isnull=True
                    )
                    | models.Q(
                        statement_position__isnull=True, program_fragment__isnull=False
                    )
                ),
                name="exactly_one_source_type",
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.statement_position and not self.program_fragment:
            raise ValidationError(
                "Either statement_position or program_fragment must be set"
            )
        if self.statement_position and self.program_fragment:
            raise ValidationError("Only one source type can be set")

    def __str__(self):
        if self.statement_position:
            return f"StatementPosition-{self.statement_position.id} → {self.party_position}"
        elif self.program_fragment:
            return f"ProgramFragment-{self.program_fragment.id} → {self.party_position}"
        return f"Invalid source → {self.party_position}"

    @property
    def source_type(self):
        if self.statement_position:
            return "statement_position"
        elif self.program_fragment:
            return "program_fragment"
        return "unknown"

    @property
    def source_id(self):
        if self.statement_position:
            return self.statement_position.id
        elif self.program_fragment:
            return self.program_fragment.id
        return None


class ElectionProgram(models.Model):
    """Model representing an election program document"""

    party = models.ForeignKey(
        PoliticalParty, on_delete=models.CASCADE, related_name="programs"
    )
    title = models.CharField(
        max_length=300, help_text="Titel van het verkiezingsprogramma"
    )
    year = models.PositiveIntegerField(help_text="Verkiezingsjaar")
    election_type = models.CharField(
        max_length=50,
        choices=[
            ("tweede_kamer", "Tweede Kamer"),
            ("eerste_kamer", "Eerste Kamer"),
            ("europees", "Europees Parlement"),
            ("provinciale_staten", "Provinciale Staten"),
            ("gemeenteraad", "Gemeenteraad"),
        ],
        default="tweede_kamer",
    )

    source_url = models.URLField(help_text="URL naar het originele document")
    pdf_url = models.URLField(blank=True, help_text="URL naar PDF versie")
    url_type = models.CharField(
        max_length=20,
        choices=[
            ("pdf", "PDF Document"),
            ("webpage", "Webpagina"),
            ("doc", "Word Document"),
            ("docx", "Word Document (DOCX)"),
            ("html", "HTML Document"),
            ("other", "Anders"),
        ],
        default="webpage",
        help_text="Type van het bronmateriaal",
    )

    is_active = models.BooleanField(
        default=True, help_text="Is dit programma nog relevant?"
    )
    is_imported = models.BooleanField(
        default=False,
        help_text="Is dit programma al geïmporteerd vanuit de externe bron?",
    )
    fragments_created = models.BooleanField(
        default=False,
        help_text="Zijn er al fragmenten aangemaakt voor dit programma?",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Election Program"
        verbose_name_plural = "Election Programs"
        ordering = ["-year", "party__name"]
        unique_together = [("party", "year", "election_type")]

    def __str__(self):
        return f"{self.party.abbreviation} - {self.title} ({self.year})"

    def get_local_pdf_url(self):
        """Generate URL for locally served PDF file"""
        if self.url_type == "pdf":
            # Generate filename same as in process_election_programs.py
            party_name = self.party.name.lower().replace(" ", "_")
            filename = f"{party_name}_program_{self.year}.pdf"
            return f"/pdf/{filename}"
        return None

    def get_local_pdf_filename(self):
        """Generate filename for locally stored PDF file"""
        if self.url_type == "pdf":
            party_name = self.party.name.lower().replace(" ", "_")
            return f"{party_name}_program_{self.year}.pdf"
        return None


class ProgramFragment(models.Model):
    """Model representing a fragment from an election program"""

    program = models.ForeignKey(
        ElectionProgram, on_delete=models.CASCADE, related_name="fragments"
    )
    content = models.TextField(help_text="Inhoud van het fragment")
    raw_content = models.TextField(help_text="Ruwe inhoud van het fragment")

    # Fragment classification
    fragment_type = models.CharField(
        max_length=50,
        choices=[
            ("bullet_point", "Bullet Point"),
            ("title_section", "Titel Sectie"),
            ("heading_section", "Heading Sectie"),
            ("subtitle_section", "Subtitle Sectie"),
            ("text_block", "Tekstblok"),
        ],
        default="text_block",
        help_text="Type van het fragment",
    )

    # Single topic for compatibility
    topic = models.ForeignKey(
        "Topic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fragments",
        help_text="Enkelvoudig topic voor compatibiliteit (gebruik 'topics' voor meerdere)",
    )

    # Source citation fields
    source_page_start = models.PositiveIntegerField(
        null=True, blank=True, help_text="Startpagina in het originele document"
    )
    source_page_end = models.PositiveIntegerField(
        null=True, blank=True, help_text="Eindpagina in het originele document"
    )
    source_reference = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Volledige bronverwijzing (bijv. 'D66 Verkiezingsprogramma 2023, p. 42-44')",
    )
    source_url = models.URLField(
        blank=True,
        help_text="URL naar de bron waar dit fragment vandaan komt, als deze beschikbaar is",
    )

    # Political dimensions
    dimensions = models.OneToOneField(
        "PoliticalDimensions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="program_fragment",
    )

    # For search and retrieval
    word_count = models.PositiveIntegerField(default=0)
    char_count = models.PositiveIntegerField(default=0)
    relevance_score = models.FloatField(
        default=1.0,
        help_text="Relevantie score van het fragment ten opzichte van het topic",
    )
    embedding = VectorField(dimensions=768, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Program Fragment"
        verbose_name_plural = "Program Fragments"
        ordering = ["program", "source_page_start"]

    def __str__(self):
        return f"{self.program.party.abbreviation} - {self.content[:50]}..."

    def save(self, *args, **kwargs):
        # Auto-calculate word and character counts
        if self.content:
            self.word_count = len(self.content.split())
            self.char_count = len(self.content)
        super().save(*args, **kwargs)

    @staticmethod
    def search(query, limit=10, party=None, year=None):
        """
        Enhanced search fragments by content using semantic similarity
        with hybrid search combining vector similarity and text matching.
        """
        from django.db.models import Q, F, Case, When, FloatField
        from pgvector.django import CosineDistance
        from django.contrib.postgres.search import SearchVector, SearchRank

        # Embed query with enhanced preprocessing
        from apps.utils.llm import embed_text

        query_vector = embed_text(query)

        # Base queryset - only fragments with embeddings
        qs = ProgramFragment.objects.filter(embedding__isnull=False)

        # Apply filters
        if party:
            if isinstance(party, str):
                qs = qs.filter(program__party__abbreviation__iexact=party)
            else:
                qs = qs.filter(program__party=party)
        if year:
            qs = qs.filter(program__year=year)

        # Create semantic similarity score
        qs = qs.annotate(
            semantic_distance=CosineDistance("embedding", query_vector),
            semantic_score=Case(
                When(semantic_distance__lt=0.3, then=1.0),
                When(semantic_distance__lt=0.5, then=0.8),
                When(semantic_distance__lt=0.7, then=0.6),
                When(semantic_distance__lt=0.9, then=0.4),
                default=0.2,
                output_field=FloatField(),
            ),
        )

        # Add text search for keyword matching
        search_vector = SearchVector("content", weight="A") + SearchVector(
            "program__title", weight="B"
        )
        qs = qs.annotate(
            search_rank=SearchRank(search_vector, query),
            text_score=Case(
                When(search_rank__gt=0.3, then=1.0),
                When(search_rank__gt=0.1, then=0.7),
                When(search_rank__gt=0.05, then=0.5),
                default=0.0,
                output_field=FloatField(),
            ),
        )

        # Combine scores with weighted average
        qs = qs.annotate(
            combined_score=Case(
                When(
                    semantic_score__gt=0.6,
                    text_score__gt=0.5,
                    then=F("semantic_score") * 0.7 + F("text_score") * 0.3,
                ),
                When(
                    semantic_score__gt=0.6,
                    then=F("semantic_score") * 0.8 + F("text_score") * 0.2,
                ),
                When(
                    text_score__gt=0.5,
                    then=F("semantic_score") * 0.6 + F("text_score") * 0.4,
                ),
                default=F("semantic_score") * 0.7 + F("text_score") * 0.3,
                output_field=FloatField(),
            )
        )

        # Order by combined score and semantic distance
        fragments = qs.order_by("-combined_score", "semantic_distance")

        # Apply minimum relevance threshold
        fragments = fragments.filter(
            Q(combined_score__gte=0.3) | Q(semantic_distance__lt=0.7)
        )

        # Get up to 3 best fragments per party
        # Use a dictionary to track the best fragments for each party
        best_fragments_by_party = {}

        for fragment in fragments:
            party_id = fragment.program.party.id

            # Initialize list for this party if not exists
            if party_id not in best_fragments_by_party:
                best_fragments_by_party[party_id] = []

            # Add fragment if we have less than 3 for this party
            if len(best_fragments_by_party[party_id]) < 3:
                best_fragments_by_party[party_id].append(fragment)

        # Flatten the dictionary to a list, maintaining party grouping and order
        result_fragments = []

        # Sort parties by their best fragment's score (first fragment in each list)
        sorted_parties = sorted(
            best_fragments_by_party.items(),
            key=lambda x: x[1][0].combined_score if x[1] else 0,
            reverse=True,
        )

        # Add all fragments maintaining party order but interleaving
        for party_id, party_fragments in sorted_parties:
            result_fragments.extend(party_fragments)

        return result_fragments[:limit]


class ParliamentarySeats(models.Model):
    """Model representing the number of parliamentary seats for a party"""

    party = models.ForeignKey(
        PoliticalParty, on_delete=models.CASCADE, related_name="seats"
    )
    seats = models.PositiveIntegerField(help_text="Aantal zetels op dat moment")
    date = models.DateField(default=timezone.now, help_text="Datum van de zetelstand")
    year = models.PositiveIntegerField(
        help_text="Jaar van de zetelstand", default=timezone.now().year, blank=True
    )

    is_election_result = models.BooleanField(
        default=False,
        help_text="Is dit een verkiezingsuitslag of een tussentijdse stand",
    )

    source = models.CharField(
        max_length=25,
        choices=[
            ("mauricedehond", "Maurice de Hond"),
            ("other", "Overig"),
        ],
        help_text="Bron van deze zetelstand",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parliamentary Seats"
        verbose_name_plural = "Parliamentary Seats"
        unique_together = [("party", "date")]

    def __str__(self):
        return f"{self.party.abbreviation} - {self.seats} seats ({self.date})"


class Topic(models.Model):
    """Model representing a topic or theme in political content"""

    name = models.CharField(max_length=100, unique=True, help_text="Naam van het thema")
    slug = models.SlugField(unique=True, blank=True, null=True)
    description = models.TextField(
        blank=True, null=True, help_text="Beschrijving van het thema"
    )
    context = models.TextField(
        blank=True, null=True, help_text="Context of achtergrondinformatie"
    )
    embedding = VectorField(dimensions=768, null=True, blank=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)

        # Create embedding if not provided
        if self.embedding is None or len(self.embedding) == 0:
            from apps.utils.llm import embed_text

            self.embedding = embed_text(
                f"{self.name}: {self.description}\n\n{self.context}"
            )

        super().save(*args, **kwargs)


class TopicKeyword(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="keywords")
    keyword = models.CharField(max_length=100, help_text="Keyword related to the topic")
    relevance_score = models.FloatField(
        default=1.0, help_text="Relevance score for the keyword"
    )

    def __str__(self):
        return self.keyword


class Theme(models.Model):
    topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, related_name="themes", null=True, blank=True
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    context = models.TextField(blank=True, null=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    source = models.CharField(
        max_length=25,
        choices=[
            ("stemwijzer", "StemWijzer"),
            ("kieskompas", "Kieskompas"),
            ("AI", "AI Generated"),
            ("other", "Overig"),
        ],
        help_text="Bron van dit thema",
        null=True,
        blank=True,
    )

    def save(self, *args, **kwargs):
        # Auto-generate slug if not provided
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.name)

        # Create embedding if not provided
        if self.embedding is None or len(self.embedding) == 0:
            from apps.utils.llm import embed_text

            self.embedding = embed_text(
                f"{self.name}: {self.description}\n\n{self.context}"
            )

        super().save(*args, **kwargs)


class Statement(models.Model):
    theme = models.ForeignKey(
        Theme, on_delete=models.CASCADE, related_name="statements"
    )
    slug = models.SlugField(unique=True, blank=True, null=True)
    text = models.TextField(unique=True)
    explanation = models.TextField(blank=True, null=True)
    embedding = VectorField(dimensions=768, null=True, blank=True)
    source = models.CharField(
        max_length=25,
        choices=[
            ("stemwijzer", "StemWijzer"),
            ("kieskompas", "Kieskompas"),
            ("AI", "AI Generated"),
            ("other", "Overig"),
        ],
        help_text="Bron van deze stelling",
        null=True,
        blank=True,
    )

    example_opinions = models.ManyToManyField(
        "ExampleOpinion",
        related_name="statements",
        blank=True,
        help_text="Voorbeeld meningen over deze stelling",
    )

    def save(self, *args, **kwargs):
        # Create embedding if not provided
        if self.embedding is None or len(self.embedding) == 0:
            from apps.utils.llm import embed_text

            self.embedding = embed_text(f"{self.text}: {self.explanation}")

        # Auto-generate slug if not provided
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.text[:50])

        super().save(*args, **kwargs)


class ExampleOpinion(models.Model):
    """Model representing an example opinion on a statement"""

    text = models.TextField(help_text="Voorbeeld mening over een stelling")
    left_wing = models.BooleanField(
        default=False, help_text="Is deze mening links georiënteerd?"
    )
    right_wing = models.BooleanField(
        default=False, help_text="Is deze mening rechts georiënteerd?"
    )
    progressive = models.BooleanField(
        default=False, help_text="Is deze mening progressief georiënteerd?"
    )
    conservative = models.BooleanField(
        default=False, help_text="Is deze mening conservatief georiënteerd?"
    )

    dimensions = models.OneToOneField(
        "PoliticalDimensions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="example_opinion",
    )

    embedding = VectorField(dimensions=768, null=True, blank=True)
    source = models.CharField(
        max_length=25,
        choices=[
            ("stemwijzer", "StemWijzer"),
            ("kieskompas", "KiesKompas"),
            ("AI", "AI Generated"),
            ("other", "Overig"),
        ],
        help_text="Bron van deze voorbeeld mening",
        null=True,
        blank=True,
    )

    def __str__(self):
        return self.text[:50]  # Return first 50 characters as identifier

    def save(self, *args, **kwargs):
        # Create embedding if not provided
        if self.embedding is None or len(self.embedding) == 0:
            from apps.utils.llm import embed_text

            self.embedding = embed_text(self.text)

        super().save(*args, **kwargs)


class StatementPosition(models.Model):
    statement = models.ForeignKey(
        Statement, on_delete=models.CASCADE, related_name="positions"
    )
    party = models.ForeignKey(
        PoliticalParty, on_delete=models.CASCADE, related_name="positions"
    )
    stance = models.CharField(
        max_length=20,
        choices=[
            ("strongly_agree", "Strongly Agree"),
            ("agree", "Agree"),
            ("neutral", "Neutral"),
            ("disagree", "Disagree"),
            ("strongly_disagree", "Strongly Disagree"),
        ],
        default="neutral",
    )
    explanation = models.TextField()

    # Political dimensions
    dimensions = models.OneToOneField(
        "PoliticalDimensions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statement_position",
    )

    embedding = VectorField(dimensions=768, null=True, blank=True)
    source = models.CharField(
        max_length=25,
        choices=[
            ("stemwijzer", "StemWijzer"),
            ("kieskompas", "KiesKompas"),
            ("AI", "AI Generated"),
            ("other", "Overig"),
        ],
        help_text="Bron van deze stellingpositie",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("statement", "party")

    def save(self, *args, **kwargs):
        # Create embedding if not provided
        if self.embedding is None or len(self.embedding) == 0:
            from apps.utils.llm import embed_text

            self.embedding = embed_text(self.explanation)

        # Custom save logic can be added here
        super().save(*args, **kwargs)


class StatementContext(models.Model):
    """
    Model for storing AI-generated context about political statements
    Cached to avoid regenerating and save API tokens
    """

    statement = models.OneToOneField(
        Statement,
        on_delete=models.CASCADE,
        related_name="context",
        help_text="De stelling waarvoor deze context is gegenereerd",
    )

    # Context fields matching the AI response structure
    issue_background = models.TextField(help_text="Achtergrond van het onderwerp")
    current_state = models.TextField(help_text="Huidige situatie en stand van zaken")
    possible_solutions = models.TextField(
        help_text="Mogelijke oplossingen en beleidskeuzes"
    )
    different_perspectives = models.TextField(
        help_text="Verschillende perspectieven en standpunten"
    )
    why_relevant = models.TextField(help_text="Waarom dit onderwerp relevant is")

    # Metadata
    generated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Statement Context"
        verbose_name_plural = "Statement Contexts"

    def __str__(self):
        return f"Context voor: {self.statement.text[:50]}..."


class ThemePosition(models.Model):
    theme = models.ForeignKey(Theme, on_delete=models.CASCADE, related_name="positions")
    party = models.ForeignKey(
        PoliticalParty, on_delete=models.CASCADE, related_name="theme_positions"
    )
    progressive = models.FloatField(
        default=0.0, help_text="Progressive stance score for the party on this theme"
    )
    conservative = models.FloatField(
        default=0.0, help_text="Conservative stance score for the party on this theme"
    )
    left_wing = models.FloatField(
        default=0.0, help_text="Left-wing stance score for the party on this theme"
    )
    right_wing = models.FloatField(
        default=0.0, help_text="Right-wing stance score for the party on this theme"
    )
    source = models.CharField(
        max_length=25,
        choices=[
            ("stemwijzer", "StemWijzer"),
            ("kieskompas", "KiesKompas"),
            ("AI", "AI Generated"),
            ("other", "Overig"),
        ],
        help_text="Bron van deze themapositie",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("theme", "party")


class PoliticalDimensions(models.Model):
    """
    Model representing political dimensions to label to a statement or programfragment

    economic
    –1: left → +1: right
    social
    –1: progressive → +1: conservative
    environmental
    –1: green → +1: brown
    immigration
    –1: open → +1: closed
    europe
    –1: pro-EU → +1: anti-EU
    authority
    –1: libertarian → +1: authoritarian
    institutionality
    –1: institutional → +1: anti-elite/populist


    """

    economic = models.FloatField(
        default=0.0,
        help_text="Economische score: -1 (links) tot +1 (rechts)",
    )
    social = models.FloatField(
        default=0.0,
        help_text="Sociale score: -1 (progressief) tot +1 (conservatief)",
    )
    environmental = models.FloatField(
        default=0.0,
        help_text="Milieu score: -1 (groen) tot +1 (bruin)",
    )
    immigration = models.FloatField(
        default=0.0,
        help_text="Immigratie score: -1 (open) tot +1 (gesloten)",
    )
    europe = models.FloatField(
        default=0.0,
        help_text="Europa score: -1 (pro-EU) tot +1 (anti-EU)",
    )
    authority = models.FloatField(
        default=0.0,
        help_text="Autoriteit score: -1 (libertair) tot +1 (autoritaire)",
    )
    institutionality = models.FloatField(
        default=0.0,
        help_text="Institutionaliteit score: -1 (institutioneel) tot +1 (anti-elite/populistisch)",
    )

    confidence = models.FloatField(
        default=0.0,
        help_text="Vertrouwen in de dimensies, van 0.0 (laag) tot 1.0 (hoog)",
    )
    evidence = models.TextField(
        blank=True,
        null=True,
        help_text="Onderbouwing of bewijs voor deze dimensies",
    )

    created_at = models.DateTimeField(auto_now_add=True)


class OpinionComparison(models.Model):
    """
    Cached AI comparison results to avoid duplicate API calls
    """

    # Unique hash based on statement, user opinion, and selected parties
    comparison_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA256 hash van statement, gebruikersmening en geselecteerde partijen",
    )

    # AI response
    comparison_result = models.TextField(
        help_text="AI-gegenereerde vergelijking in markdown format"
    )

    # Metadata
    created_at = models.DateTimeField(
        auto_now_add=True, help_text="Wanneer de vergelijking werd aangemaakt"
    )

    model_used = models.CharField(
        max_length=100, default="gpt-4o", help_text="Welk AI model werd gebruikt"
    )

    class Meta:
        verbose_name = "Opinion Comparison"
        verbose_name_plural = "Opinion Comparisons"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Comparison {self.comparison_hash[:8]} - Statement {self.statement_id}"

    @classmethod
    def generate_hash(cls, statement_id, user_opinion, party_ids):
        """
        Generate a unique hash for a comparison based on input parameters
        """
        # Sort party IDs to ensure consistent hash regardless of selection order
        sorted_party_ids = sorted(party_ids)

        # Create a string representation of the key data
        hash_data = {
            "statement_id": statement_id,
            "user_opinion": user_opinion,
            "party_ids": sorted_party_ids,
        }

        # Convert to JSON string for consistent hashing
        hash_string = json.dumps(hash_data, sort_keys=True)

        # Generate SHA256 hash
        return hashlib.sha256(hash_string.encode()).hexdigest()

    @classmethod
    def get_or_create_comparison(
        cls, statement_id, user_opinion, party_ids, comparison_result=None
    ):
        """
        Get existing comparison or create new one
        """
        comparison_hash = cls.generate_hash(statement_id, user_opinion, party_ids)

        try:
            # Try to get existing comparison
            return cls.objects.get(comparison_hash=comparison_hash), False
        except cls.DoesNotExist:
            # Create new comparison if result is provided
            if comparison_result:
                comparison = cls.objects.create(
                    comparison_hash=comparison_hash,
                    comparison_result=comparison_result,
                )
                return comparison, True
            else:
                return None, False
