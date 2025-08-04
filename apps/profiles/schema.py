"""
GraphQL schema for user profiles
"""

import strawberry
from enum import Enum
from typing import Optional, List
from django.http import HttpRequest

from .models import (
    UserProfile,
    UserResponse,
    PartyMatch,
    PartyStatementMatch,
)
from .services import ProfileService, EmailService
from apps.content.models import Statement
from apps.api.types import PoliticalPartyType


@strawberry.enum
class ClassificationStatusEnum(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.enum
class MatchingStatusEnum(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@strawberry.type
class UserProfileType:
    id: str
    uuid: str
    email: Optional[str]
    is_completed: bool
    created_at: str
    response_count: int

    @staticmethod
    def from_model(profile: UserProfile) -> "UserProfileType":
        return UserProfileType(
            id=str(profile.id),
            uuid=str(profile.uuid),
            email=profile.email,
            is_completed=profile.is_completed,
            created_at=profile.created_at.isoformat(),
            response_count=profile.responses.count(),
        )


@strawberry.type
class UserResponseType:
    id: str
    statement_id: str
    opinion: str  # renamed from user_opinion to match frontend
    confidence: int
    importance: int
    createdAt: str  # Use camelCase for GraphQL
    statement: Optional["StatementDetailType"] = None  # Add nested statement data

    # Classification fields
    label: Optional[str] = None
    confidence_score: Optional[float] = None
    classified_label: Optional[str] = None
    label_set_by: Optional[str] = None

    @staticmethod
    def from_model(response: UserResponse) -> "UserResponseType":
        return UserResponseType(
            id=str(response.id),
            statement_id=str(response.statement.id),
            opinion=response.user_opinion,
            confidence=response.confidence,
            importance=response.importance,
            createdAt=response.created_at.isoformat(),
            statement=StatementDetailType.from_model(response.statement),
            label=response.label,
            confidence_score=response.confidence_score,
            classified_label=response.classified_label,
            label_set_by=response.label_set_by,
        )


@strawberry.type
class StatementDetailType:
    """Statement with theme information for profile responses"""

    id: str
    text: str
    explanation: Optional[str]
    theme: "ThemeDetailType"

    @staticmethod
    def from_model(statement: Statement) -> "StatementDetailType":
        return StatementDetailType(
            id=str(statement.id),
            text=statement.text,
            explanation=statement.explanation,
            theme=ThemeDetailType.from_model(statement.theme),
        )


@strawberry.type
class ThemeDetailType:
    """Theme information for nested statement data"""

    id: str
    name: str

    @staticmethod
    def from_model(theme) -> "ThemeDetailType":
        return ThemeDetailType(
            id=str(theme.id),
            name=theme.name,
        )


@strawberry.type
class TopicMatchType:
    """Party match data for a specific topic"""

    topic_id: str
    topic_name: str
    match_percentage: float
    statements_count: int
    matching_statements_count: int

    @staticmethod
    def from_data(topic_id: str, topic_name: str, matches: list) -> "TopicMatchType":
        if not matches:
            return TopicMatchType(
                topic_id=topic_id,
                topic_name=topic_name,
                match_percentage=0.0,
                statements_count=0,
                matching_statements_count=0,
            )

        total_score = sum(m.match_score for m in matches)
        avg_score = total_score / len(matches)
        matching_count = sum(1 for m in matches if m.match_score > 60)

        return TopicMatchType(
            topic_id=topic_id,
            topic_name=topic_name,
            match_percentage=avg_score,
            statements_count=len(matches),
            matching_statements_count=matching_count,
        )


@strawberry.type
class DetailedPartyMatchType:
    """Comprehensive party match with topic breakdown"""

    party_id: str
    party_name: str
    party_abbreviation: str
    party_color_hex: str
    party_logo_object_position: str
    match_percentage: float
    agreement_score: float
    confidence_weighted_score: float
    importance_weighted_score: float
    total_statements: int
    matching_statements: int
    calculated_at: str
    topic_matches: List["TopicMatchType"]
    explanation: Optional[str] = None

    @staticmethod
    def from_model_with_topics(match: PartyMatch) -> "DetailedPartyMatchType":
        # Get topic-specific matches
        statement_matches = (
            match.profile.statement_matches.filter(party=match.party)
            .select_related("statement__theme__topic")
            .order_by("statement__theme__topic__id")
        )

        # Group by topic
        from collections import defaultdict

        topic_groups = defaultdict(list)

        for stmt_match in statement_matches:
            topic = stmt_match.statement.theme.topic
            topic_groups[topic].append(stmt_match)

        # Create topic match objects
        topic_matches = []
        for topic, matches in topic_groups.items():
            topic_match = TopicMatchType.from_data(str(topic.id), topic.name, matches)
            topic_matches.append(topic_match)

        # Sort by match percentage descending
        topic_matches.sort(key=lambda x: x.match_percentage, reverse=True)

        return DetailedPartyMatchType(
            party_id=str(match.party.id),
            party_name=match.party.name,
            party_abbreviation=match.party.abbreviation,
            party_logo_object_position=match.party.logo_object_position,
            party_color_hex=match.party.color_hex or "#6b7280",
            match_percentage=match.match_percentage,
            agreement_score=match.agreement_score,
            confidence_weighted_score=match.confidence_weighted_score,
            importance_weighted_score=match.importance_weighted_score,
            total_statements=match.total_statements,
            matching_statements=match.matching_statements,
            calculated_at=match.calculated_at.isoformat(),
            topic_matches=topic_matches,
            explanation=match.explanation,
        )


@strawberry.type
class PartyMatchType:
    party_id: str
    party_name: str
    party_abbreviation: str
    party_color_hex: str
    match_percentage: float
    agreement_score: float
    confidence_weighted_score: float
    importance_weighted_score: float
    total_statements: int
    matching_statements: int
    calculated_at: str
    explanation: Optional[str] = None

    @staticmethod
    def from_model(match: PartyMatch) -> "PartyMatchType":
        return PartyMatchType(
            party_id=str(match.party.id),
            party_name=match.party.name,
            party_abbreviation=match.party.abbreviation,
            party_color_hex=match.party.color_hex or "#6b7280",
            match_percentage=match.match_percentage,
            agreement_score=match.agreement_score,
            confidence_weighted_score=match.confidence_weighted_score,
            importance_weighted_score=match.importance_weighted_score,
            total_statements=match.total_statements,
            matching_statements=match.matching_statements,
            calculated_at=match.calculated_at.isoformat(),
            explanation=match.explanation,
        )


@strawberry.type
class PartyStatementMatchType:
    party: PoliticalPartyType
    party_stance: str
    party_explanation: str
    match_score: float
    confidence_weighted_score: float
    importance_weighted_score: float
    final_score: float

    @staticmethod
    def from_model(match: PartyStatementMatch) -> "PartyStatementMatchType":
        return PartyStatementMatchType(
            party=match.party,  # strawberry_django type handles this automatically
            party_stance=match.party_stance,
            party_explanation=match.party_explanation,
            match_score=match.match_score,
            confidence_weighted_score=match.confidence_weighted_score,
            importance_weighted_score=match.importance_weighted_score,
            final_score=match.final_score,
        )


@strawberry.type
class StatementResultType:
    statement_id: str
    statement_text: str
    statement_explanation: Optional[str]
    statement_source: Optional[str]
    theme_id: str
    theme_name: str
    topic_id: str
    topic_name: str
    user_opinion: str
    user_confidence: int
    user_importance: int
    user_label: Optional[str]  # The current label (agree/neutral/disagree)
    user_confidence_score: Optional[float]  # AI confidence in the classification
    user_classified_label: Optional[str]  # Original AI classification
    user_label_set_by: Optional[str]  # Who set the label (user/AI)
    user_response_id: str  # ID of the UserResponse for editing
    party_matches: List[PartyStatementMatchType]

    @staticmethod
    def from_user_response(response: UserResponse) -> "StatementResultType":
        statement = response.statement
        theme = statement.theme
        topic = theme.topic if theme else None

        # Get all party matches for this statement and user
        party_matches = PartyStatementMatch.objects.filter(
            profile=response.profile, statement=statement
        ).order_by("-final_score")

        return StatementResultType(
            statement_id=str(statement.id),
            statement_text=statement.text,
            statement_explanation=statement.explanation,
            statement_source=statement.source,
            theme_id=str(theme.id) if theme else "",
            theme_name=theme.name if theme else "",
            topic_id=str(topic.id) if topic else "",
            topic_name=topic.name if topic else "",
            user_opinion=response.user_opinion,
            user_confidence=response.confidence,
            user_importance=response.importance,
            user_label=response.label,
            user_confidence_score=response.confidence_score,
            user_classified_label=response.classified_label,
            user_label_set_by=response.label_set_by,
            user_response_id=str(response.id),
            party_matches=[
                PartyStatementMatchType.from_model(match) for match in party_matches
            ],
        )


@strawberry.type
class TopicResultsType:
    topic_id: str
    topic_name: str
    topic_description: Optional[str]
    statements: List[StatementResultType]


@strawberry.type
class ClassificationStatusType:
    total_responses: int
    classified_responses: int
    pending_responses: int
    classification_percentage: float
    status: ClassificationStatusEnum


@strawberry.type
class MatchingStatusType:
    total_responses: int
    matched_responses: int
    pending_responses: int
    matching_percentage: float
    status: MatchingStatusEnum


@strawberry.input
class UserResponseInput:
    statement_id: str
    opinion: str  # renamed from user_opinion to match frontend expectations
    confidence: int = 3
    importance: int = 3


@strawberry.input
class UpdateUserLabelInput:
    response_id: str
    label: str  # agree, neutral, disagree


@strawberry.input
class ExplainPartyMatchInput:
    party_id: str


@strawberry.type
class CreateProfileResult:
    success: bool
    profile: Optional[UserProfileType] = None
    error: Optional[str] = None


@strawberry.type
class SaveResponseResult:
    success: bool
    response: Optional[UserResponseType] = None
    error: Optional[str] = None


@strawberry.type
class SendMagicLinkResult:
    success: bool
    message: str


@strawberry.type
class VerifyMagicLinkResult:
    success: bool
    profile: Optional[UserProfileType] = None
    error: Optional[str] = None


@strawberry.type
class GenerateProfileLinkResult:
    success: bool
    profile_link: Optional[str] = None
    error: Optional[str] = None


@strawberry.type
class AccessProfileByLinkResult:
    success: bool
    profile: Optional[UserProfileType] = None
    error: Optional[str] = None


@strawberry.input
class AccessProfileByLinkInput:
    profile_uuid: str


@strawberry.type
class UpdateEmailResult:
    success: bool
    profile: Optional[UserProfileType] = None
    error: Optional[str] = None


@strawberry.type
class ExplainPartyMatchResult:
    success: bool
    explanation: Optional[str] = None
    error: Optional[str] = None


@strawberry.type
class ClassifyResponsesResult:
    success: bool
    message: str
    pending_classifications: int


@strawberry.type
class UpdateUserLabelResult:
    success: bool
    error: Optional[str] = None
    response: Optional[UserResponseType] = None


@strawberry.type
class ForcePartyMatchingResult:
    success: bool
    message: str
    matches_calculated: int
    error: Optional[str] = None


def get_current_profile(info) -> Optional[UserProfile]:
    """Get current user profile from session or UUID"""
    request: HttpRequest = info.context["request"]

    # Try to get profile UUID from header (for testing)
    profile_uuid = request.headers.get("X-User-Profile-UUID")
    if profile_uuid:
        try:
            return UserProfile.objects.get(uuid=profile_uuid)
        except UserProfile.DoesNotExist:
            pass

    # Try to get profile UUID from session
    profile_uuid = request.session.get("profile_uuid")
    if profile_uuid:
        return ProfileService.get_profile_by_uuid(profile_uuid)

    # Try to get profile from session key
    session_key = request.session.session_key
    if session_key:
        return ProfileService.get_or_create_profile_by_session(session_key)

    return None


@strawberry.type
class ProfileQuery:

    @strawberry.field
    def current_profile(self, info) -> Optional[UserProfileType]:
        """Get current user profile"""
        profile = get_current_profile(info)
        if profile:
            return UserProfileType.from_model(profile)
        return None

    @strawberry.field
    def profile_responses(self, info) -> List[UserResponseType]:
        """Get all responses for current profile"""
        profile = get_current_profile(info)
        if not profile:
            return []

        # Use select_related to avoid N+1 queries
        responses = profile.responses.select_related("statement__theme").order_by(
            "created_at"
        )
        return [UserResponseType.from_model(r) for r in responses]

    @strawberry.field
    def profile_matches(self, info) -> List[PartyMatchType]:
        """Get party matches for current profile"""
        profile = get_current_profile(info)
        if not profile:
            return []

        matches = profile.party_matches.all().order_by("-match_percentage")
        return [PartyMatchType.from_model(m) for m in matches]

    @strawberry.field
    def detailed_profile_matches(self, info) -> List[DetailedPartyMatchType]:
        """Get detailed party matches with topic breakdown for current profile"""
        profile = get_current_profile(info)
        if not profile:
            return []

        matches = profile.party_matches.select_related("party").order_by(
            "-match_percentage"
        )
        return [DetailedPartyMatchType.from_model_with_topics(m) for m in matches]

    @strawberry.field
    def profile_results_by_topic(self, info) -> List[TopicResultsType]:
        """Get detailed results grouped by topic for current profile"""
        profile = get_current_profile(info)
        if not profile:
            return []

        # Get all user responses with their statements
        responses = profile.responses.select_related(
            "statement__theme__topic"
        ).order_by("statement__theme__topic__id", "statement__id")

        # Group by topic
        from collections import defaultdict

        topics_dict = defaultdict(list)

        for response in responses:
            statement = response.statement
            theme = statement.theme
            topic = theme.topic if theme else None

            if topic:
                topics_dict[topic].append(response)

        # Convert to TopicResultsType
        results = []
        for topic, topic_responses in topics_dict.items():
            statements = [
                StatementResultType.from_user_response(resp) for resp in topic_responses
            ]

            results.append(
                TopicResultsType(
                    topic_id=str(topic.id),
                    topic_name=topic.name,
                    topic_description=topic.description,
                    statements=statements,
                )
            )

        return results

    @strawberry.field
    def classification_status(self, info) -> "ClassificationStatusType":
        """Get classification status for current profile"""
        profile = get_current_profile(info)
        if not profile:
            return ClassificationStatusType(
                total_responses=0,
                classified_responses=0,
                pending_responses=0,
                classification_percentage=0.0,
                status=ClassificationStatusEnum.COMPLETED,
            )

        total = profile.responses.count()
        classified = profile.responses.filter(
            user_label__isnull=False, user_confidence_score__isnull=False
        ).count()
        pending = total - classified
        percentage = (classified / total * 100) if total > 0 else 0.0

        # Determine status
        if pending == 0:
            status = ClassificationStatusEnum.COMPLETED
        elif classified == 0:
            status = ClassificationStatusEnum.PENDING
        else:
            status = ClassificationStatusEnum.PROCESSING

        return ClassificationStatusType(
            total_responses=total,
            classified_responses=classified,
            pending_responses=pending,
            classification_percentage=round(percentage, 1),
            status=status,
        )

    @strawberry.field
    def matching_status(self, info) -> "MatchingStatusType":
        """Get matching status for current profile - checks if all user responses have corresponding party statement matches"""
        profile = get_current_profile(info)
        if not profile:
            return MatchingStatusType(
                total_responses=0,
                matched_responses=0,
                pending_responses=0,
                matching_percentage=0.0,
                status=MatchingStatusEnum.COMPLETED,
            )

        # Get all user responses (not just labeled ones)
        all_responses = profile.responses.all()
        total = all_responses.count()

        if total == 0:
            return MatchingStatusType(
                total_responses=0,
                matched_responses=0,
                pending_responses=0,
                matching_percentage=0.0,
                status=MatchingStatusEnum.COMPLETED,
            )

        # Count how many of these responses have at least one party statement match
        matched_count = 0
        for response in all_responses:
            has_matches = PartyStatementMatch.objects.filter(
                profile=profile, statement=response.statement, user_response=response
            ).exists()
            if has_matches:
                matched_count += 1

        pending = total - matched_count
        percentage = (matched_count / total * 100) if total > 0 else 0.0

        # Determine status
        if pending == 0:
            status = MatchingStatusEnum.COMPLETED
        elif matched_count == 0:
            status = MatchingStatusEnum.PENDING
        else:
            status = MatchingStatusEnum.PROCESSING

        return MatchingStatusType(
            total_responses=total,
            matched_responses=matched_count,
            pending_responses=pending,
            matching_percentage=round(percentage, 1),
            status=status,
        )


@strawberry.type
class ProfileMutation:

    @strawberry.mutation
    def create_profile(self, info) -> CreateProfileResult:
        """Create a new anonymous profile"""
        try:
            request: HttpRequest = info.context["request"]

            # Ensure session exists
            if not request.session.session_key:
                request.session.create()

            profile = ProfileService.create_anonymous_profile(
                session_key=request.session.session_key
            )

            # Store profile UUID in session
            request.session["profile_uuid"] = str(profile.uuid)

            return CreateProfileResult(
                success=True, profile=UserProfileType.from_model(profile)
            )
        except Exception as e:
            return CreateProfileResult(success=False, error=str(e))

    @strawberry.mutation
    def save_response(
        self, info, response_input: UserResponseInput
    ) -> SaveResponseResult:
        """Save user response to a statement"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return SaveResponseResult(success=False, error="Geen profiel gevonden")

            # Get statement
            try:
                statement = Statement.objects.get(id=response_input.statement_id)
            except Statement.DoesNotExist:
                return SaveResponseResult(
                    success=False, error="Statement niet gevonden"
                )

            # Create or update response (without classification first for speed)
            user_response, created = UserResponse.objects.update_or_create(
                profile=profile,
                statement=statement,
                defaults={
                    "user_opinion": response_input.opinion,
                    "confidence": response_input.confidence,
                    "importance": response_input.importance,
                },
            )

            # If updating, reset classification fields
            if not created:
                user_response.label = None
                user_response.confidence_score = None
                user_response.classified_label = None
                user_response.label_set_by = None
                user_response.save()

                # Remove party statement matches for this response
                PartyStatementMatch.objects.filter(user_response=user_response).delete()

                # Remove party matches for this user
                PartyMatch.objects.filter(profile=profile).delete()

            # Trigger asynchronous classification
            from apps.profiles.tasks import classify_user_response_async

            classify_user_response_async.delay(user_response.id)

            return SaveResponseResult(
                success=True, response=UserResponseType.from_model(user_response)
            )

        except Exception as e:
            return SaveResponseResult(success=False, error=str(e))

    @strawberry.mutation
    def update_profile_email(self, info, email: str) -> UpdateEmailResult:
        """Update the email address for the current profile"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return UpdateEmailResult(success=False, error="Geen profiel gevonden")

            # Update the email
            profile.email = email
            profile.save()

            return UpdateEmailResult(
                success=True, profile=UserProfileType.from_model(profile)
            )

        except Exception as e:
            return UpdateEmailResult(success=False, error=str(e))

    @strawberry.mutation
    def send_magic_link(self, info, email: str) -> SendMagicLinkResult:
        """Send magic link to email"""
        try:
            request: HttpRequest = info.context["request"]

            # Ensure session exists
            if not request.session.session_key:
                request.session.create()

            verification = EmailService.send_magic_link(email, request)

            return SendMagicLinkResult(
                success=True, message=f"Een link is verstuurd naar {email}"
            )

        except Exception as e:
            return SendMagicLinkResult(
                success=False, message=f"Fout bij verzenden: {str(e)}"
            )

    @strawberry.mutation
    def verify_magic_link(self, info, token: str) -> VerifyMagicLinkResult:
        """Verify magic link token"""
        try:
            profile, error = EmailService.verify_magic_link(token)

            if error:
                return VerifyMagicLinkResult(success=False, error=error)

            if profile:
                request: HttpRequest = info.context["request"]
                # Store profile UUID in session
                request.session["profile_uuid"] = str(profile.uuid)

                return VerifyMagicLinkResult(
                    success=True, profile=UserProfileType.from_model(profile)
                )

            return VerifyMagicLinkResult(success=False, error="Onbekende fout")

        except Exception as e:
            return VerifyMagicLinkResult(success=False, error=str(e))

    @strawberry.mutation
    def classify_pending_responses(self, info) -> ClassifyResponsesResult:
        """Manually trigger classification for all pending responses"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return ClassifyResponsesResult(
                    success=False,
                    message="Geen profiel gevonden",
                    pending_classifications=0,
                )

            # Get unclassified responses for this profile
            unclassified = profile.responses.filter(label__isnull=True)
            count = unclassified.count()

            if count == 0:
                return ClassifyResponsesResult(
                    success=True,
                    message="Alle reacties zijn al geclassificeerd",
                    pending_classifications=0,
                )

            # Trigger classification for each response
            from apps.profiles.tasks import classify_user_response_async

            for response in unclassified:
                classify_user_response_async.delay(response.id)

            return ClassifyResponsesResult(
                success=True,
                message=f"Classificatie gestart voor {count} reacties",
                pending_classifications=count,
            )

        except Exception as e:
            return ClassifyResponsesResult(
                success=False,
                message=f"Fout bij starten classificatie: {str(e)}",
                pending_classifications=0,
            )

    @strawberry.mutation
    def update_user_label(
        self, info, input: UpdateUserLabelInput
    ) -> UpdateUserLabelResult:
        """Update the user-set label for a response and recalculate party matches"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return UpdateUserLabelResult(
                    success=False, error="Geen profiel gevonden"
                )

            # Validate label
            valid_labels = ["agree", "neutral", "disagree"]
            if input.label not in valid_labels:
                return UpdateUserLabelResult(
                    success=False,
                    error=f"Ongeldige label. Gebruik een van: {', '.join(valid_labels)}",
                )

            # Get the user response
            try:
                response = UserResponse.objects.get(
                    id=input.response_id, profile=profile
                )
            except UserResponse.DoesNotExist:
                return UpdateUserLabelResult(
                    success=False, error="Reactie niet gevonden"
                )

            # Update the label and set label_set_by appropriately
            response.label = input.label

            # If user label matches the original classified label, revert to AI
            if input.label == response.classified_label:
                response.label_set_by = "AI"
            else:
                response.label_set_by = "user"

            response.save()

            # Recalculate party matches synchronously
            from .utils import recalculate_party_matches_for_response

            recalculate_party_matches_for_response(response)

            return UpdateUserLabelResult(
                success=True, response=UserResponseType.from_model(response)
            )

        except Exception as e:
            return UpdateUserLabelResult(
                success=False, error=f"Fout bij bijwerken label: {str(e)}"
            )

    @strawberry.mutation
    def force_party_matching(self, info) -> ForcePartyMatchingResult:
        """Force synchronous party matching calculation for the current profile"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return ForcePartyMatchingResult(
                    success=False,
                    message="Geen profiel gevonden",
                    matches_calculated=0,
                    error="Geen profiel gevonden in sessie",
                )

            # Find ALL responses that are missing PartyStatementMatch objects (not just labeled ones)
            from .utils import bulk_create_missing_party_matches

            all_responses = profile.responses.all().select_related("statement")
            missing_responses = []

            for response in all_responses:
                # Check if this response already has PartyStatementMatch objects
                has_matches = PartyStatementMatch.objects.filter(
                    profile=profile,
                    statement=response.statement,
                    user_response=response,
                ).exists()

                if not has_matches:
                    missing_responses.append(response)

            # Bulk create missing matches (much faster than individual processing)
            responses_processed = 0
            if missing_responses:
                responses_processed = bulk_create_missing_party_matches(
                    missing_responses
                )

            # Then recalculate party matches using all statement matches
            from .services import PartyMatchService

            matches_calculated = PartyMatchService.recalculate_profile_matches(profile)

            message = f"Geforceerde party matching voltooid voor {matches_calculated} partijen"
            if responses_processed > 0:
                message += (
                    f" (verwerkte {responses_processed} ontbrekende statement matches)"
                )

            return ForcePartyMatchingResult(
                success=True,
                message=message,
                matches_calculated=matches_calculated,
            )

        except Exception as e:
            return ForcePartyMatchingResult(
                success=False,
                message=f"Fout bij geforceerde party matching: {str(e)}",
                matches_calculated=0,
                error=str(e),
            )

    @strawberry.mutation
    def explain_party_match(
        self, info, input: ExplainPartyMatchInput
    ) -> ExplainPartyMatchResult:
        """Generate detailed explanation of why a party matches with user opinions"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return ExplainPartyMatchResult(
                    success=False, error="Geen profiel gevonden"
                )

            # Get the party
            try:
                from apps.content.models import PoliticalParty

                party = PoliticalParty.objects.get(id=input.party_id)
            except PoliticalParty.DoesNotExist:
                return ExplainPartyMatchResult(
                    success=False, error="Partij niet gevonden"
                )

            # Get the party match
            try:
                party_match = PartyMatch.objects.get(profile=profile, party=party)
            except PartyMatch.DoesNotExist:
                return ExplainPartyMatchResult(
                    success=False, error="Geen match data gevonden voor deze partij"
                )

            # Get all statement matches for this party and profile
            statement_matches = (
                PartyStatementMatch.objects.filter(profile=profile, party=party)
                .select_related("statement__theme__topic", "user_response")
                .order_by("-final_score")
            )

            if not statement_matches.exists():
                return ExplainPartyMatchResult(
                    success=False, error="Geen statement matches gevonden"
                )

            # Generate explanation using AI
            from .services import PartyExplanationService

            explanation = PartyExplanationService.generate_explanation(
                party_match, statement_matches
            )

            return ExplainPartyMatchResult(success=True, explanation=explanation)

        except Exception as e:
            return ExplainPartyMatchResult(
                success=False, error=f"Fout bij genereren uitleg: {str(e)}"
            )

    @strawberry.mutation
    def generate_profile_link(self, info) -> GenerateProfileLinkResult:
        """Generate anonymous profile link for current user"""
        try:
            profile = get_current_profile(info)
            if not profile:
                return GenerateProfileLinkResult(
                    success=False, error="Geen profiel gevonden"
                )

            request: HttpRequest = info.context["request"]
            profile_link = ProfileService.generate_anonymous_profile_link(
                profile, request
            )

            return GenerateProfileLinkResult(success=True, profile_link=profile_link)

        except Exception as e:
            return GenerateProfileLinkResult(
                success=False, error=f"Fout bij genereren profiel link: {str(e)}"
            )

    @strawberry.mutation
    def access_profile_by_link(
        self, info, input: AccessProfileByLinkInput
    ) -> AccessProfileByLinkResult:
        """Access profile using anonymous link"""
        try:
            request: HttpRequest = info.context["request"]

            # Ensure session exists
            if not request.session.session_key:
                request.session.create()

            profile, error = ProfileService.access_profile_by_link(
                input.profile_uuid, request
            )

            if error:
                return AccessProfileByLinkResult(success=False, error=error)

            if profile:
                return AccessProfileByLinkResult(
                    success=True, profile=UserProfileType.from_model(profile)
                )

            return AccessProfileByLinkResult(success=False, error="Onbekende fout")

        except Exception as e:
            return AccessProfileByLinkResult(
                success=False, error=f"Fout bij toegang profiel: {str(e)}"
            )
