"""
Services for user profile management and email authentication
"""

from collections import defaultdict
import uuid
from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
import logging
import openai
from .models import UserProfile, EmailVerification

from typing import List, Optional, Dict, Any
from .models import UserProfile, UserResponse, PartyMatch, PartyStatementMatch
from apps.content.models import PoliticalParty

logger = logging.getLogger(__name__)


class ProfileService:
    """Service for managing user profiles"""

    @staticmethod
    def create_anonymous_profile(session_key=None):
        """Create a new anonymous user profile"""
        profile = UserProfile.objects.create(session_key=session_key)
        return profile

    @staticmethod
    def get_or_create_profile_by_session(session_key):
        """Get or create profile by session key"""
        profile, created = UserProfile.objects.get_or_create(session_key=session_key)
        if not created:
            profile.last_active = timezone.now()
            profile.save()
        return profile

    @staticmethod
    def get_profile_by_uuid(profile_uuid):
        """Get profile by UUID"""
        try:
            return UserProfile.objects.get(uuid=profile_uuid)
        except UserProfile.DoesNotExist:
            return None

    @staticmethod
    def generate_anonymous_profile_link(profile: UserProfile, request) -> str:
        """Generate anonymous profile link for later access"""
        from django.conf import settings

        # Build frontend URL using the profile UUID
        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
        profile_link = f"{frontend_url}/profile/{profile.uuid}"
        return profile_link

    @staticmethod
    def access_profile_by_link(
        profile_uuid: str, request
    ) -> tuple[Optional[UserProfile], Optional[str]]:
        """Access profile using anonymous link"""
        try:
            profile = UserProfile.objects.get(uuid=profile_uuid)

            # Update last active timestamp
            profile.last_active = timezone.now()
            profile.save(update_fields=["last_active"])

            # Set profile in session for current visit
            request.session["profile_uuid"] = str(profile.uuid)

            return profile, None
        except UserProfile.DoesNotExist:
            return (
                None,
                "Profiel niet gevonden. Deze link is mogelijk verlopen of ongeldig.",
            )


class EmailService:
    """Service for email verification and magic links"""

    @staticmethod
    def send_magic_link(email, request):
        """Send magic link to user's email"""
        # Find existing profile with this email or get from session
        profile = None

        # First try to find existing profile with this email
        try:
            profile = UserProfile.objects.get(email=email)
        except UserProfile.DoesNotExist:
            # Try to get profile from current session
            session_key = request.session.session_key
            if session_key:
                try:
                    profile = UserProfile.objects.get(session_key=session_key)
                    # Check if email is already taken by another profile
                    if (
                        UserProfile.objects.filter(email=email)
                        .exclude(id=profile.id)
                        .exists()
                    ):
                        raise ValueError(
                            f"Email {email} is al in gebruik door een ander profiel."
                        )
                    # Update email on existing profile
                    profile.email = email
                    profile.save()
                except UserProfile.DoesNotExist:
                    pass

        # If no profile found, create new one
        if not profile:
            # Check if email is already taken by another profile
            if UserProfile.objects.filter(email=email).exists():
                raise ValueError(
                    f"Email {email} is al in gebruik door een ander profiel."
                )
            profile = UserProfile.objects.create(
                email=email, session_key=request.session.session_key
            )

        # Create or update email verification
        verification, created = EmailVerification.objects.get_or_create(
            profile=profile,
            email=email,
            defaults={"expires_at": timezone.now() + timedelta(hours=24)},
        )

        if not created:
            # Update expiration for existing verification
            verification.expires_at = timezone.now() + timedelta(hours=24)
            verification.token = uuid.uuid4()  # Generate new token
            verification.is_verified = False
            verification.save()

        # Send email
        EmailService._send_verification_email(verification, request)

        return verification

    @staticmethod
    def verify_magic_link(token):
        """Verify magic link token and return profile"""
        try:
            verification = EmailVerification.objects.get(token=token)

            if verification.is_expired():
                return None, "Link verlopen. Vraag een nieuwe link aan."

            # Mark as verified
            verification.is_verified = True
            verification.save()

            # Update profile email if needed
            profile = verification.profile
            if profile.email != verification.email:
                # Check if email is already taken by another profile
                if (
                    UserProfile.objects.filter(email=verification.email)
                    .exclude(id=profile.id)
                    .exists()
                ):
                    return (
                        None,
                        f"Email {verification.email} is al in gebruik door een ander profiel.",
                    )
                profile.email = verification.email
                profile.save()

            return profile, None

        except EmailVerification.DoesNotExist:
            return None, "Ongeldige link."

    @staticmethod
    def _send_verification_email(verification, request):
        """Send verification email with magic link"""

        # Build magic link URL
        magic_link = request.build_absolute_uri(f"/auth/verify/{verification.token}/")

        subject = "Toegang tot je PolitiekMatcher profiel"

        # Email content
        html_message = f"""
        <h2>Welkom bij PolitiekMatcher</h2>
        <p>Klik op de onderstaande link om toegang te krijgen tot je profiel:</p>
        <p><a href="{magic_link}" style="background-color: #3b82f6; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">Toegang tot profiel</a></p>
        <p>Deze link is 24 uur geldig.</p>
        <p>Als je dit niet hebt aangevraagd, kun je deze email negeren.</p>
        """

        plain_message = f"""
        Welkom bij PolitiekMatcher
        
        Klik op de onderstaande link om toegang te krijgen tot je profiel:
        {magic_link}
        
        Deze link is 24 uur geldig.
        
        Als je dit niet hebt aangevraagd, kun je deze email negeren.
        """

        send_mail(
            subject=subject,
            message=plain_message,
            html_message=html_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[verification.email],
            fail_silently=False,
        )


class PartyMatchService:
    """Service for calculating party matches from existing statement matches"""

    @staticmethod
    def calculate_party_match_from_statements(
        profile: UserProfile, party: PoliticalParty
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate party match statistics from existing PartyStatementMatch objects.
        """
        # Get all statement matches for this profile-party combination
        statement_matches = PartyStatementMatch.objects.filter(
            profile=profile, party=party
        ).select_related("user_response")

        if not statement_matches.exists():
            return None

        total_statements = statement_matches.count()
        total_score = 0.0
        confidence_weighted_score = 0.0
        importance_weighted_score = 0.0
        confidence_weight_sum = 0.0
        importance_weight_sum = 0.0
        matching_statements = 0

        for stmt_match in statement_matches:
            user_response = stmt_match.user_response
            base_score = stmt_match.match_score

            # Get confidence and importance from the user response
            confidence = user_response.confidence / 5.0  # Normalize to 0-1
            importance = user_response.importance / 5.0  # Normalize to 0-1

            # Accumulate scores
            total_score += base_score
            confidence_weighted_score += base_score * confidence
            importance_weighted_score += base_score * importance

            # Accumulate weights for proper averaging
            confidence_weight_sum += confidence
            importance_weight_sum += importance

            # Count as matching if score > 60%
            if base_score > 60:
                matching_statements += 1

        # Calculate averages
        match_percentage = total_score / total_statements
        avg_confidence_weighted = confidence_weighted_score / max(
            confidence_weight_sum, 1.0
        )
        avg_importance_weighted = importance_weighted_score / max(
            importance_weight_sum, 1.0
        )

        # Calculate coverage penalty
        total_user_responses = profile.responses.filter(label__isnull=False).count()
        coverage_ratio = (
            total_statements / total_user_responses if total_user_responses > 0 else 0
        )

        # Apply coverage penalty: reduce score for parties with low coverage
        if coverage_ratio < 0.8:
            penalty_factor = max(0.5, coverage_ratio / 0.8)  # Range: 0.5-1.0
        else:
            penalty_factor = 1.0

        # Apply penalty to all scores
        match_percentage *= penalty_factor
        avg_confidence_weighted *= penalty_factor
        avg_importance_weighted *= penalty_factor

        return {
            "match_percentage": match_percentage,
            "agreement_score": total_score
            / total_statements,  # Raw score without penalty
            "confidence_weighted_score": avg_confidence_weighted,
            "importance_weighted_score": avg_importance_weighted,
            "total_statements": total_statements,
            "matching_statements": matching_statements,
        }

    @staticmethod
    def save_party_match(
        profile: UserProfile, party: PoliticalParty, match_data: Dict[str, Any]
    ) -> PartyMatch:
        """Save calculated party match to database."""
        party_match, created = PartyMatch.objects.update_or_create(
            profile=profile,
            party=party,
            defaults={
                "match_percentage": match_data["match_percentage"],
                "agreement_score": match_data["agreement_score"],
                "confidence_weighted_score": match_data["confidence_weighted_score"],
                "importance_weighted_score": match_data["importance_weighted_score"],
                "total_statements": match_data["total_statements"],
                "matching_statements": match_data["matching_statements"],
                "explanation": None,  # Clear cached explanation
            },
        )
        return party_match

    @staticmethod
    def recalculate_profile_matches(profile: UserProfile) -> int:
        """
        Recalculate all party matches for a profile using existing PartyStatementMatch data.
        Returns the number of matches calculated.
        """
        # Get all parties that have statement matches for this profile
        parties_with_matches = PoliticalParty.objects.filter(
            partystatementmatch__profile=profile
        ).distinct()

        matches_calculated = 0

        for party in parties_with_matches:
            match_data = PartyMatchService.calculate_party_match_from_statements(
                profile, party
            )

            if match_data:
                PartyMatchService.save_party_match(profile, party, match_data)
                matches_calculated += 1

        return matches_calculated

    @staticmethod
    def recalculate_on_response_change(user_response: UserResponse) -> int:
        """
        Recalculate party matches when a user response changes.
        This should be called whenever a UserResponse is created or updated.
        Note: This assumes PartyStatementMatch objects already exist and are up to date.
        """
        return PartyMatchService.recalculate_profile_matches(user_response.profile)


class PartyExplanationService:
    """Service for generating AI-powered explanations of party matches with caching"""

    @staticmethod
    def generate_explanation(
        party_match: PartyMatch, statement_matches: List[PartyStatementMatch]
    ) -> str:
        """
        Generate a comprehensive explanation of why a party matches with user opinions.
        Uses cached explanation if available, otherwise generates new one via OpenAI.

        Args:
            party_match: The overall party match object
            statement_matches: List of individual statement matches

        Returns:
            Markdown-formatted explanation string
        """
        # Check if explanation is already cached
        if party_match.explanation:
            logger.info(f"Using cached explanation for {party_match.party.name}")
            return party_match.explanation

        # Generate new explanation
        logger.info(f"Generating new explanation for {party_match.party.name}")
        explanation = PartyExplanationService._generate_ai_explanation(
            party_match, statement_matches
        )

        # Cache the explanation
        party_match.explanation = explanation
        party_match.save(update_fields=["explanation"])

        return explanation

    @staticmethod
    def _generate_ai_explanation(
        party_match: PartyMatch, statement_matches: List[PartyStatementMatch]
    ) -> str:
        """Generate explanation using OpenAI API with improved prompt structure"""
        try:
            party_name = party_match.party.name
            match_percentage = round(party_match.match_percentage, 1)

            # Organize statements by topic for better structure
            topic_groups = defaultdict(list)
            for stmt_match in statement_matches:
                topic = stmt_match.statement.theme.topic
                topic_groups[topic.name].append(stmt_match)

            # Sort topics by average match score (highest first)
            sorted_topics = sorted(
                topic_groups.items(),
                key=lambda x: (
                    sum(m.match_score for m in x[1]) / len(x[1]) if x[1] else 0
                ),
                reverse=True,
            )

            # Build structured prompt
            prompt = PartyExplanationService._build_structured_prompt(
                party_name, match_percentage, party_match, sorted_topics
            )

            # Call OpenAI API
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": "Je bent een neutrale politieke analist die heldere, gestructureerde uitleg geeft over partij-matches. Je schrijft in begrijpelijk Nederlands en blijft objectief.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=1200,
                temperature=0.2,  # Lower temperature for more consistent results
            )

            explanation = response.choices[0].message.content.strip()

            # Add disclaimer
            explanation += "\n\n---\n*Deze uitleg is automatisch gegenereerd op basis van uw antwoorden en de verkiezingsprogramma's. Voor de meest actuele standpunten raadpleegt u de partijwebsites.*"

            return explanation

        except Exception as e:
            logger.error(f"Error generating AI explanation: {str(e)}")
            return PartyExplanationService._generate_fallback_explanation(party_match)

    @staticmethod
    def _build_structured_prompt(
        party_name: str,
        match_percentage: float,
        party_match: PartyMatch,
        sorted_topics: List,
    ) -> str:
        """Build a structured, logical prompt for consistent AI responses"""

        prompt = f"""Genereer een heldere uitleg waarom {party_name} {match_percentage}% overeenkomst heeft met de politieke voorkeuren van een Nederlandse kiezer.

**GEGEVENS:**
- Partij: {party_name}
- Overall match: {match_percentage}%
- Totaal stellingen: {party_match.total_statements}
- Overeenkomende stellingen: {party_match.matching_statements}
- Confidence gewogen score: {party_match.confidence_weighted_score:.1f}%
- Belang gewogen score: {party_match.importance_weighted_score:.1f}%

**ONDERWERPEN PER MATCH-SCORE:**
"""

        # Add top 5 topics with details
        for topic_name, matches in sorted_topics[:5]:
            avg_score = sum(m.match_score for m in matches) / len(matches)
            high_matches = [m for m in matches if m.match_score >= 70]

            prompt += f"\n**{topic_name}** (gemiddeld {avg_score:.0f}% match, {len(high_matches)}/{len(matches)} stellingen hoge match):\n"

            # Add 2-3 most representative statements
            top_matches = sorted(matches, key=lambda x: x.match_score, reverse=True)[:3]
            for match in top_matches:
                user_stance = match.user_response.label or "onbekend"
                prompt += f"- Stelling: {match.statement.text[:100]}...\n"
                prompt += f"  Jouw standpunt: {user_stance} | {party_name}: {match.party_stance} | Match: {match.match_score:.0f}%\n"

        prompt += f"""

**GEVRAAGDE UITLEG STRUCTUUR:**

Maak een uitleg met deze exacte structuur:

## Match Overzicht
- Korte samenvatting van de {match_percentage}% match
- Korte beschrijving van de partij en haar kernwaarden

## Belangrijkste Overeenkomsten
- Top 3 onderwerpen waar je en {party_name} het meest overeenkomen
- Concrete voorbeelden van stellingen waar jullie hetzelfde denken

## Grootste Verschillen  
- Top 3 onderwerpen waar jullie verschillen, alleen als deze er zijn
- Concrete voorbeelden van stellingen waar jullie verschillend denken

## Conclusie
- Korte afweging waarom de match {match_percentage}% is
- Of deze partij wel/niet geschikt zou zijn voor deze kiezer

**SCHRIJFINSTRUCTIES:**
- Gebruik markdown headers (##)
- Maximaal 600 woorden
- Schrijf neutraal en objectief
- Gebruik concrete voorbeelden, maak er een lopend verhaal van
- Vermijd jargon
- Richt je op de kiezer die dit leest, praat in de tweede persoon ("jij")
- Gebruik actieve stem
- Vermijd onnodige herhaling, vermijd opsommingen van stellingen en standpunten
- Gebruik duidelijke zinnen"""

        return prompt

    @staticmethod
    def _generate_fallback_explanation(party_match: PartyMatch) -> str:
        """Generate a simple fallback explanation when AI fails"""
        return f"""## Match Overzicht

Je hebt een {party_match.match_percentage:.1f}% overeenkomst met {party_match.party.name}.

## Samenvatting

Van de {party_match.total_statements} stellingen die je hebt beantwoord, stemmen er {party_match.matching_statements} overeen met de standpunten van {party_match.party.name}.

## Technische Details

- **Match percentage:** {party_match.match_percentage:.1f}%
- **Vertrouwen gewogen:** {party_match.confidence_weighted_score:.1f}%
- **Belang gewogen:** {party_match.importance_weighted_score:.1f}%

---
*Er is een fout opgetreden bij het genereren van een gedetailleerde uitleg. Deze basis-informatie geeft een overzicht van je match met deze partij.*"""

    @staticmethod
    def clear_cached_explanation(party_match: PartyMatch) -> None:
        """Clear cached explanation to force regeneration"""
        party_match.explanation = None
        party_match.save(update_fields=["explanation"])
        logger.info(f"Cleared cached explanation for {party_match.party.name}")

    @staticmethod
    def clear_all_cached_explanations() -> int:
        """Clear all cached explanations (useful for prompt improvements)"""
        count = PartyMatch.objects.filter(explanation__isnull=False).update(
            explanation=None
        )
        logger.info(f"Cleared {count} cached explanations")
        return count
