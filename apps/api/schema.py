import strawberry
from typing import List, Optional
from .types import (
    PoliticalPartyType,
    PoliticalPartyWithSeatsType,
    ChatMessageType,
    SendChatMessageResponse,
    SearchResultsType,
    SearchResultType,
    PartySearchSummaryType,
    StatementType,
    ThemeType,
    TopicType,
    TopicWithStatsType,
    CompareOpinionsInput,
    CompareOpinionsResponse,
    PartyPositionsByTopicType,
    StatementContextType,
    GenerateContextInput,
    GenerateContextResponse,
)
from ..chat.models import ChatSession, ChatMessage, MessageSource
from ..content.models import (
    PartyPosition,
    PoliticalParty,
    ProgramFragment,
    Statement,
    Theme,
    Topic,
)
from ..chat.ai import get_ai_response
from .services import compare_political_opinions
from ..profiles.schema import (
    ProfileQuery,
    ProfileMutation,
    UserProfileType,
    UserResponseType,
    PartyMatchType,
    DetailedPartyMatchType,
    TopicResultsType,
    CreateProfileResult,
    SaveResponseResult,
    SendMagicLinkResult,
    VerifyMagicLinkResult,
    UpdateEmailResult,
    UpdateUserLabelResult,
    MatchingStatusType,
    ForcePartyMatchingResult,
    ExplainPartyMatchResult,
    GenerateProfileLinkResult,
    AccessProfileByLinkResult,
)
import uuid


@strawberry.type
class PartyQuery:

    @strawberry.field
    def party_by_id(self, party_id: int) -> Optional[PoliticalPartyType]:
        """Get a specific political party by ID"""
        try:
            party = PoliticalParty.objects.get(id=party_id)
            return party
        except PoliticalParty.DoesNotExist:
            return None

    @strawberry.field
    def party_positions_by_topic(
        self, party_id: int
    ) -> List[PartyPositionsByTopicType]:
        """Get party positions grouped by topic for a specific party"""
        try:
            party = PoliticalParty.objects.get(id=party_id)
        except PoliticalParty.DoesNotExist:
            return []

        # Get all topics that have positions for this party
        topics_with_positions = (
            Topic.objects.filter(party_positions__party=party)
            .distinct()
            .order_by("name")
        )

        results = []
        for topic in topics_with_positions:
            # Get all positions for this party and topic, ordered by ranking
            # Prefetch sources to avoid N+1 queries
            positions = (
                PartyPosition.objects.filter(party=party, topic=topic)
                .prefetch_related(
                    "sources",
                    "sources__statement_position",
                    "sources__program_fragment",
                    "sources__program_fragment__program",
                )
                .order_by("ranking")
            )

            if positions.exists():
                results.append(
                    PartyPositionsByTopicType(topic=topic, positions=list(positions))
                )

        return results


@strawberry.type
class Query:
    """GraphQL Query root"""

    @strawberry.field
    def hello(self) -> str:
        return "Hello from PolitiekMatcher GraphQL API!"

    @strawberry.field
    def political_parties(self) -> List[PoliticalPartyType]:
        """Get all political parties"""
        return PoliticalParty.objects.all()

    @strawberry.field
    def statements_by_topics(
        self, topic_ids: Optional[List[str]] = None
    ) -> List[StatementType]:
        """Get all statements for the questionnaire, optionally filtered by topics"""
        queryset = Statement.objects.select_related("theme", "theme__topic")

        if topic_ids:
            queryset = queryset.filter(theme__topic__id__in=topic_ids)

        # Implements selection logic based on number of topics:
        # - If 1 topic: select all statements for that topic
        # - If <= 3 topics: select 3 statements per topic randomly (no duplicates)
        # - If <= 5 topics: select 2 statements per topic randomly (no duplicates)
        # - If > 5 topics: select 1 statement per topic randomly

        from collections import defaultdict
        import random

        if topic_ids:
            # Group statements by topic
            statements_by_topic = defaultdict(list)
            for statement in queryset:
                topic_id = str(statement.theme.topic.id)
                statements_by_topic[topic_id].append(statement)

                selected_statements = []

                num_topics = len(topic_ids)
                if num_topics == 1:
                    # Select all statements for the single topic
                    for statements in statements_by_topic.values():
                        selected_statements.extend(statements)
                elif num_topics <= 3:
                    # Select up to 3 statements per topic randomly
                    for statements in statements_by_topic.values():
                        count = min(3, len(statements))
                        selected_statements.extend(random.sample(statements, count))
                elif num_topics <= 5:
                    # Select up to 2 statements per topic randomly
                    for statements in statements_by_topic.values():
                        count = min(2, len(statements))
                        selected_statements.extend(random.sample(statements, count))
                else:
                    # Select 1 statement per topic randomly
                    for statements in statements_by_topic.values():
                        count = min(1, len(statements))
                        selected_statements.extend(random.sample(statements, count))

            # Make sure to remove duplicates
            selected_statements = list({s.id: s for s in selected_statements}.values())

            return selected_statements
        else:
            # No topic filter: return all statements
            return list(queryset)

    @strawberry.field
    def topics(self) -> List[TopicType]:
        """Get all topics"""
        return Topic.objects.all()

    @strawberry.field
    def topics_with_stats(self, info) -> List[TopicWithStatsType]:
        """Get all topics with statement counts and user progress"""
        from django.db.models import Count
        from apps.profiles.schema import get_current_profile

        # Get current user profile
        profile = get_current_profile(info)

        topics = Topic.objects.annotate(
            total_statements=Count("themes__statements", distinct=True)
        ).all()

        result_topics = []
        for topic in topics:
            # Count answered statements for this user and topic
            answered_count = 0
            if profile:
                answered_count = profile.responses.filter(
                    statement__theme__topic=topic
                ).count()

            # Create enhanced topic object
            enhanced_topic = TopicWithStatsType()
            enhanced_topic.id = topic.id
            enhanced_topic.name = topic.name
            enhanced_topic.description = topic.description
            enhanced_topic._total_statements = topic.total_statements
            enhanced_topic._answered_statements = answered_count

            result_topics.append(enhanced_topic)

        return result_topics

    @strawberry.field
    def statements_by_topics_prioritized(
        self, info, topic_ids: Optional[List[str]] = None
    ) -> List[StatementType]:
        """Get statements for questionnaire, prioritizing unanswered statements"""
        from django.db.models import Q
        from apps.profiles.schema import get_current_profile
        from collections import defaultdict
        import random

        # Get current user profile
        profile = get_current_profile(info)

        queryset = Statement.objects.select_related("theme", "theme__topic")

        if topic_ids:
            queryset = queryset.filter(theme__topic__id__in=topic_ids)

        # Group statements by topic
        statements_by_topic = defaultdict(lambda: {"answered": [], "unanswered": []})

        for statement in queryset:
            topic_id = str(statement.theme.topic.id)

            # Check if user has answered this statement
            if profile and profile.responses.filter(statement=statement).exists():
                statements_by_topic[topic_id]["answered"].append(statement)
            else:
                statements_by_topic[topic_id]["unanswered"].append(statement)

        selected_statements = []
        num_topics = len(topic_ids) if topic_ids else 1

        # Determine statements per topic based on number of topics
        if num_topics == 1:
            statements_per_topic = None  # All statements
        elif num_topics <= 3:
            statements_per_topic = 3
        elif num_topics <= 5:
            statements_per_topic = 2
        else:
            statements_per_topic = 1

        for topic_id, topic_statements in statements_by_topic.items():
            unanswered = topic_statements["unanswered"]
            answered = topic_statements["answered"]

            if statements_per_topic is None:
                # Select all unanswered first, then answered
                selected_statements.extend(unanswered)
                selected_statements.extend(answered)
            else:
                # First, try to get statements from unanswered
                if len(unanswered) >= statements_per_topic:
                    # Enough unanswered statements
                    selected_statements.extend(
                        random.sample(unanswered, statements_per_topic)
                    )
                else:
                    # Not enough unanswered, take all unanswered + some answered
                    selected_statements.extend(unanswered)
                    remaining_needed = statements_per_topic - len(unanswered)
                    if answered and remaining_needed > 0:
                        remaining_count = min(remaining_needed, len(answered))
                        selected_statements.extend(
                            random.sample(answered, remaining_count)
                        )

        # Remove duplicates while preserving order
        seen = set()
        unique_statements = []
        for stmt in selected_statements:
            if stmt.id not in seen:
                seen.add(stmt.id)
                unique_statements.append(stmt)

        return unique_statements

    @strawberry.field
    def themes(self) -> List[ThemeType]:
        """Get all themes"""
        return Theme.objects.select_related("topic").all()

    # Profile queries
    current_profile: Optional[UserProfileType] = strawberry.field(
        resolver=ProfileQuery.current_profile
    )
    profile_responses: List[UserResponseType] = strawberry.field(
        resolver=ProfileQuery.profile_responses
    )
    profile_matches: List[PartyMatchType] = strawberry.field(
        resolver=ProfileQuery.profile_matches
    )
    detailed_profile_matches: List[DetailedPartyMatchType] = strawberry.field(
        resolver=ProfileQuery.detailed_profile_matches
    )
    profile_results_by_topic: List[TopicResultsType] = strawberry.field(
        resolver=ProfileQuery.profile_results_by_topic
    )
    matching_status: MatchingStatusType = strawberry.field(
        resolver=ProfileQuery.matching_status
    )

    # Party queries
    party_by_id: Optional[PoliticalPartyType] = strawberry.field(
        resolver=PartyQuery.party_by_id
    )
    party_positions_by_topic: List[PartyPositionsByTopicType] = strawberry.field(
        resolver=PartyQuery.party_positions_by_topic
    )

    @strawberry.field
    def parties_by_seats(self) -> List[PoliticalPartyWithSeatsType]:
        """Get political parties ordered by latest parliamentary seats (descending)"""
        from django.db.models import Max, IntegerField, Value
        from django.db.models.functions import Coalesce

        # Annotate latest seat count, treat NULL as 0 using Coalesce
        parties = (
            PoliticalParty.objects.prefetch_related("seats")
            .annotate(
                latest_seat_count=Coalesce(
                    Max("seats__seats"), Value(0), output_field=IntegerField()
                ),
                latest_seat_date=Max("seats__date"),
            )
            .order_by("-latest_seat_count", "name")
        )

        return parties

    @strawberry.field
    def chat_history(self, sessionId: str) -> List[ChatMessageType]:
        """Get chat history for a given session"""
        try:
            session = ChatSession.objects.get(session_id=uuid.UUID(sessionId))
            return session.messages.all()
        except ChatSession.DoesNotExist:
            return []

    @strawberry.field
    def search_programs(
        self,
        query: str,
        limit: Optional[int] = 60,  # Increased to accommodate 3 per party
        party_filter: Optional[str] = None,  # New filter for specific party
        year: Optional[int] = None,
    ) -> SearchResultsType:
        """Search election program fragments with party summaries"""
        try:
            from collections import defaultdict

            # Use the static search method from ProgramFragment
            fragments = ProgramFragment.search(
                query=query,
                limit=limit or 60,
                party=None,
                year=year,  # Always get all parties first
            )

            # Convert to search results with distance scores
            results = []
            party_fragments = defaultdict(list)

            for fragment in fragments:
                # Get the distance annotation if it exists
                distance = getattr(fragment, "semantic_distance", 0.0)
                relevance = getattr(
                    fragment, "combined_score", fragment.relevance_score or 0.0
                )

                search_result = SearchResultType(
                    fragment=fragment,
                    distance=float(distance) if distance else 0.0,
                    relevance=float(relevance),
                )

                results.append(search_result)
                party_fragments[fragment.program.party].append(search_result)

            # Filter by party if specified
            if party_filter:
                results = [
                    r
                    for r in results
                    if r.fragment.program.party.abbreviation.lower()
                    == party_filter.lower()
                ]

            # Create party summaries ordered by best relevance
            party_summaries = []
            for party, party_results in party_fragments.items():
                if party_results:  # Only include parties with results
                    best_relevance = max(r.relevance for r in party_results)
                    party_summaries.append(
                        PartySearchSummaryType(
                            party=party,
                            fragment_count=len(party_results),
                            best_relevance=best_relevance,
                            fragments=party_results,
                        )
                    )

            # Sort party summaries by best relevance (descending)
            party_summaries.sort(key=lambda x: x.best_relevance, reverse=True)

            return SearchResultsType(
                results=results,
                party_summaries=party_summaries,
                total_count=len(results),
                query=query,
            )
        except Exception as e:
            # Return empty results on error
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error in search_programs: {e}", exc_info=True)

            return SearchResultsType(
                results=[], party_summaries=[], total_count=0, query=query
            )


@strawberry.type
class Mutation:
    """GraphQL Mutation root"""

    # Profile mutations
    create_profile: CreateProfileResult = strawberry.field(
        resolver=ProfileMutation.create_profile
    )
    save_response: SaveResponseResult = strawberry.field(
        resolver=ProfileMutation.save_response
    )
    send_magic_link: SendMagicLinkResult = strawberry.field(
        resolver=ProfileMutation.send_magic_link
    )
    verify_magic_link: VerifyMagicLinkResult = strawberry.field(
        resolver=ProfileMutation.verify_magic_link
    )
    update_profile_email: UpdateEmailResult = strawberry.field(
        resolver=ProfileMutation.update_profile_email
    )
    update_user_label: UpdateUserLabelResult = strawberry.field(
        resolver=ProfileMutation.update_user_label
    )
    force_party_matching: ForcePartyMatchingResult = strawberry.field(
        resolver=ProfileMutation.force_party_matching
    )
    explain_party_match: ExplainPartyMatchResult = strawberry.field(
        resolver=ProfileMutation.explain_party_match
    )
    generate_profile_link: GenerateProfileLinkResult = strawberry.field(
        resolver=ProfileMutation.generate_profile_link
    )
    access_profile_by_link: AccessProfileByLinkResult = strawberry.field(
        resolver=ProfileMutation.access_profile_by_link
    )

    @strawberry.mutation
    def send_chat_message(
        self, message: str, sessionId: Optional[str] = None
    ) -> SendChatMessageResponse:
        """
        Send a chat message.
        If sessionId is provided, continues the existing chat session.
        Otherwise, starts a new session.
        """
        try:
            if sessionId:
                try:
                    session = ChatSession.objects.get(session_id=uuid.UUID(sessionId))
                except (ChatSession.DoesNotExist, ValueError):
                    session = ChatSession.objects.create()
            else:
                session = ChatSession.objects.create()

            # Get response from AI (pass session for context)
            answer, source_fragments = get_ai_response(message, session)

            chat_message = ChatMessage.objects.create(
                session=session,
                question=message,
                answer=answer,
            )

            # Create MessageSource objects based on AI response
            for i, fragment in enumerate(source_fragments):
                MessageSource.objects.create(
                    message=chat_message,
                    program_fragment=fragment,
                    order=i,
                    relevance_score=0.99,  # Placeholder
                )

            return SendChatMessageResponse(
                message=chat_message,
                sessionId=str(session.session_id),
            )
        except Exception as e:
            # Log the error for debugging
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error in send_chat_message: {e}", exc_info=True)

            # Create a session anyway to return an error message
            session = ChatSession.objects.create()
            error_message = ChatMessage.objects.create(
                session=session,
                question=message,
                answer=f"Er is een technische fout opgetreden: {str(e)}",
            )

            return SendChatMessageResponse(
                message=error_message,
                sessionId=str(session.session_id),
            )

    @strawberry.mutation
    def compare_opinions(self, input: CompareOpinionsInput) -> CompareOpinionsResponse:
        """
        Compare political party opinions using AI analysis
        """
        try:
            # Get the user profile
            try:
                from apps.profiles.models import UserProfile

                profile = UserProfile.objects.get(uuid=input.profile_uuid)
            except UserProfile.DoesNotExist:
                return CompareOpinionsResponse(
                    comparison="",
                    success=False,
                    error="Profiel niet gevonden",
                )

            # Validate input
            if (
                not input.statement
                or not input.user_opinion
                or len(input.party_statements) < 1
            ):
                return CompareOpinionsResponse(
                    comparison="",
                    success=False,
                    error="Incomplete data. Need statement, user opinion, and at least 1 party statement.",
                )

            # Convert input to dict format for the service
            statement_data = {
                "id": input.statement.id,
                "text": input.statement.text,
                "explanation": input.statement.explanation,
                "theme": input.statement.theme,
                "topic": input.statement.topic,
            }

            party_statements_data = []
            for ps in input.party_statements:
                party_statements_data.append(
                    {
                        "party": {
                            "id": ps.party.id,
                            "name": ps.party.name,
                            "abbreviation": ps.party.abbreviation,
                        },
                        "stance": ps.stance,
                        "explanation": ps.explanation,
                        "match_score": ps.match_score,
                    }
                )

            # Call the comparison service
            comparison_text = compare_political_opinions(
                statement_data, input.user_opinion, party_statements_data
            )

            return CompareOpinionsResponse(
                comparison=comparison_text, success=True, error=None
            )

        except Exception as e:
            return CompareOpinionsResponse(comparison="", success=False, error=str(e))

    @strawberry.mutation
    def generate_statement_context(
        self, input: GenerateContextInput
    ) -> GenerateContextResponse:
        """Generate historical and political context for a statement"""
        try:
            from apps.profiles.models import UserProfile
            from apps.content.models import Statement
            from apps.chat.context_ai import context_ai
            from decimal import Decimal

            # Get the user profile
            try:
                profile = UserProfile.objects.get(uuid=input.profile_uuid)
            except UserProfile.DoesNotExist:
                return GenerateContextResponse(
                    success=False, error="Profiel niet gevonden"
                )

            # Get the statement
            try:
                statement = Statement.objects.get(id=input.statement_id)
            except Statement.DoesNotExist:
                return GenerateContextResponse(
                    success=False, error="Stelling niet gevonden"
                )

            # Generate or get cached context using AI
            result = context_ai.get_or_generate_statement_context(statement)

            if not result["success"]:
                return GenerateContextResponse(success=False, error=result["error"])

            # Convert context data to response type
            context_data = result["context"]
            context = StatementContextType(
                issue_background=context_data.get("issue_background", ""),
                current_state=context_data.get("current_state", ""),
                possible_solutions=context_data.get("possible_solutions", ""),
                different_perspectives=context_data.get("different_perspectives", ""),
                why_relevant=context_data.get("why_relevant", ""),
            )

            return GenerateContextResponse(context=context, success=True, error=None)

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.error(f"Error generating statement context: {str(e)}")
            return GenerateContextResponse(
                success=False, error=f"Fout bij het genereren van context: {str(e)}"
            )


schema = strawberry.Schema(query=Query, mutation=Mutation)
