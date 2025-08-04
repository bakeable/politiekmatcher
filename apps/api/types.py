"""
GraphQL Types for PolitiekMatcher API
"""

import strawberry
import strawberry_django
from typing import List, Optional
from ..chat import models as chat_models
from ..content import models as content_models


@strawberry_django.type(chat_models.ChatSession)
class ChatSessionType:
    session_id: strawberry.auto
    created_at: strawberry.auto
    updated_at: strawberry.auto


@strawberry_django.type(content_models.PoliticalParty)
class PoliticalPartyType:
    id: strawberry.auto
    name: strawberry.auto
    abbreviation: strawberry.auto
    description: strawberry.auto
    logo_url: strawberry.auto
    logo_object_position: strawberry.auto
    color_hex: strawberry.auto


@strawberry_django.type(content_models.ParliamentarySeats)
class ParliamentarySeatsType:
    id: strawberry.auto
    seats: strawberry.auto
    date: strawberry.auto
    year: strawberry.auto
    is_election_result: strawberry.auto


@strawberry.type
class PoliticalPartyWithSeatsType:
    """Political party with latest parliamentary seats data"""

    @strawberry.field
    def id(self) -> int:
        return self.id

    @strawberry.field
    def name(self) -> str:
        return self.name

    @strawberry.field
    def website_url(self) -> Optional[str]:
        return self.website_url

    @strawberry.field
    def abbreviation(self) -> str:
        return self.abbreviation

    @strawberry.field
    def description(self) -> str:
        return self.description or ""

    @strawberry.field
    def logo_object_position(self) -> Optional[str]:
        return self.logo_object_position

    @strawberry.field
    def color_hex(self) -> Optional[str]:
        return self.color_hex

    @strawberry.field
    def latest_seats(self) -> int:
        """Get the most recent number of parliamentary seats"""
        latest_seat_record = self.seats.order_by("-date").first()
        return latest_seat_record.seats if latest_seat_record else 0

    @strawberry.field
    def latest_seats_date(self) -> Optional[str]:
        """Get the date of the most recent seats data"""
        latest_seat_record = self.seats.order_by("-date").first()
        return latest_seat_record.date.isoformat() if latest_seat_record else None


@strawberry_django.type(content_models.ElectionProgram)
class ElectionProgramType:
    id: strawberry.auto
    title: strawberry.auto
    year: strawberry.auto
    party: PoliticalPartyType
    source_url: strawberry.auto


@strawberry_django.type(content_models.Topic)
class TopicType:
    @strawberry.field
    def id(self) -> int:
        return self.id

    @strawberry.field
    def name(self) -> str:
        return self.name

    @strawberry.field
    def description(self) -> Optional[str]:
        return self.description


@strawberry.type
class TopicWithStatsType:
    """Topic with statement counts and user progress"""

    @strawberry.field
    def id(self) -> int:
        return self.id

    @strawberry.field
    def name(self) -> str:
        return self.name

    @strawberry.field
    def description(self) -> Optional[str]:
        return self.description

    @strawberry.field
    def total_statements(self) -> int:
        """Total number of statements in this topic"""
        return getattr(self, "_total_statements", 0)

    @strawberry.field
    def answered_statements(self) -> int:
        """Number of statements answered by the current user"""
        return getattr(self, "_answered_statements", 0)

    @strawberry.field
    def unanswered_statements(self) -> int:
        """Number of statements not yet answered by the current user"""
        total = getattr(self, "_total_statements", 0)
        answered = getattr(self, "_answered_statements", 0)
        return total - answered


@strawberry_django.type(content_models.Theme)
class ThemeType:
    id: strawberry.auto
    name: strawberry.auto
    slug: strawberry.auto
    source: strawberry.auto

    @strawberry.field
    def description(self) -> Optional[str]:
        return self.description

    @strawberry.field
    def topic(self) -> Optional[TopicType]:
        return self.topic


@strawberry_django.type(content_models.Statement)
class StatementType:
    id: strawberry.auto
    text: strawberry.auto
    slug: strawberry.auto

    @strawberry.field
    def explanation(self) -> Optional[str]:
        return self.explanation

    @strawberry.field
    def source(self) -> Optional[str]:
        return self.source

    @strawberry.field
    def theme(self) -> ThemeType:
        return self.theme

    @strawberry.field
    def topic(self) -> Optional[TopicType]:
        return self.theme.topic if self.theme else None

    @strawberry.field
    def example_opinions(self) -> List[str]:
        """Get example opinions on this statement"""
        return [opinion.text for opinion in self.example_opinions.all()]


@strawberry_django.type(content_models.StatementPosition)
class StatementPositionType:
    id: strawberry.auto
    stance: strawberry.auto
    explanation: strawberry.auto
    source: strawberry.auto
    created_at: strawberry.auto

    @strawberry.field
    def statement(self) -> StatementType:
        return self.statement

    @strawberry.field
    def party(self) -> PoliticalPartyType:
        return self.party


@strawberry_django.type(content_models.ProgramFragment)
class ProgramFragmentType:
    id: strawberry.auto
    content: strawberry.auto
    raw_content: strawberry.auto
    fragment_type: strawberry.auto
    word_count: strawberry.auto
    char_count: strawberry.auto
    relevance_score: strawberry.auto

    @strawberry.field
    def source_page_start(self) -> Optional[int]:
        """Resolves the source page start."""
        return self.source_page_start

    @strawberry.field
    def source_page_end(self) -> Optional[int]:
        """Resolves the source page end."""
        return self.source_page_end

    @strawberry.field
    def source_reference(self) -> Optional[str]:
        """Resolves the source reference."""
        return self.source_reference

    @strawberry.field
    def source_url(self) -> str:
        """Resolves the source URL from the fragment or program."""
        return self.source_url or self.program.source_url

    @strawberry.field
    def topic(self) -> Optional[TopicType]:
        """Resolves the topic from the fragment."""
        return self.topic if self.topic else None

    @strawberry.field
    def party(self) -> PoliticalPartyType:
        """Resolves the party from the program."""
        return self.program.party

    @strawberry.field
    def title(self) -> str:
        """Resolves the title from the program."""
        return self.program.title

    @strawberry.field
    def year(self) -> int:
        """Resolves the year from the program."""
        return self.program.year

    @strawberry.field
    def program(self) -> ElectionProgramType:
        """Resolves the program from the fragment."""
        return self.program

    @strawberry.field
    def source_url(self) -> str:
        """Resolves the source URL from the program."""
        return self.program.source_url

    @strawberry.field
    def pdf_url(self) -> Optional[str]:
        """Resolves the local PDF URL from the program."""
        return self.program.get_local_pdf_url()


@strawberry_django.type(chat_models.ChatMessage)
class ChatMessageType:
    id: strawberry.auto
    question: strawberry.auto
    answer: strawberry.auto
    created_at: strawberry.auto

    @strawberry.field
    def sources(self) -> List[ProgramFragmentType]:
        """Resolves the sources from the MessageSource model."""
        if self.id and self.sources.exists():
            return [source.program_fragment for source in self.sources.all()]
        return []


@strawberry.type
class SearchResultType:
    """Type for search results containing fragments with distance scores"""

    fragment: ProgramFragmentType
    distance: float
    relevance: float


@strawberry.type
class PartySearchSummaryType:
    """Summary of search results for a specific party"""

    party: PoliticalPartyType
    fragment_count: int
    best_relevance: float
    fragments: List[SearchResultType]


@strawberry.type
class SearchResultsType:
    """Type for search results response with party summaries"""

    results: List[SearchResultType]
    party_summaries: List[PartySearchSummaryType]
    total_count: int
    query: str


@strawberry.type
class SendChatMessageResponse:
    """Response type for the sendChatMessage mutation."""

    message: ChatMessageType
    sessionId: str


# Opinion Comparison Types
@strawberry.input
class StatementInput:
    """Input type for statement data in opinion comparison"""

    id: str
    text: str
    explanation: Optional[str] = None
    theme: Optional[str] = None
    topic: Optional[str] = None


@strawberry.input
class PartyStatementInput:
    """Input type for party statement data in opinion comparison"""

    party: "PartyInput"
    stance: str
    explanation: str
    match_score: float


@strawberry.input
class PartyInput:
    """Input type for party data in opinion comparison"""

    id: str
    name: str
    abbreviation: str


@strawberry_django.type(content_models.PartyPositionSource)
class PartyPositionSourceType:
    id: strawberry.auto
    relevance_score: strawberry.auto
    created_at: strawberry.auto

    @strawberry.field
    def source_type(self) -> str:
        return self.source_type

    @strawberry.field
    def source_id(self) -> Optional[int]:
        return self.source_id

    @strawberry.field
    def statement_position(self) -> Optional[StatementPositionType]:
        return self.statement_position

    @strawberry.field
    def program_fragment(self) -> Optional[ProgramFragmentType]:
        return self.program_fragment


@strawberry_django.type(content_models.PartyPosition)
class PartyPositionType:
    id: strawberry.auto
    ranking: strawberry.auto
    short: strawberry.auto
    explanation: strawberry.auto
    created_at: strawberry.auto
    updated_at: strawberry.auto

    @strawberry.field
    def party(self) -> PoliticalPartyType:
        return self.party

    @strawberry.field
    def topic(self) -> TopicType:
        return self.topic

    @strawberry.field
    def sources(self) -> List[PartyPositionSourceType]:
        return list(self.sources.all())


@strawberry.type
class PartyPositionsByTopicType:
    """Party positions grouped by topic"""

    topic: TopicType
    positions: List[PartyPositionType]


@strawberry.input
class CompareOpinionsInput:
    """Input type for comparing political opinions"""

    statement: StatementInput
    user_opinion: str
    party_statements: List[PartyStatementInput]
    profile_uuid: str


@strawberry.type
class CompareOpinionsResponse:
    """Response type for opinion comparison"""

    comparison: str
    success: bool
    error: Optional[str] = None


@strawberry.type
class StatementContextType:
    """Contextual information about a political statement"""

    issue_background: str
    current_state: str
    possible_solutions: str
    different_perspectives: str
    why_relevant: str


@strawberry.input
class GenerateContextInput:
    """Input for generating statement context"""

    statement_id: int
    profile_uuid: str


@strawberry.type
class GenerateContextResponse:
    """Response type for context generation"""

    context: Optional[StatementContextType] = None
    success: bool
    error: Optional[str] = None
