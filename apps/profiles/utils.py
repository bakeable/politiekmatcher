"""
Utility functions for profiles app
"""

from typing import Dict, List
from apps.profiles.models import UserResponse, PartyStatementMatch
from apps.content.models import PoliticalParty
from apps.utils.match_opinions import rank_parties


def recalculate_party_matches_for_response(response: UserResponse) -> Dict[str, float]:
    """
    Recalculate party matches for a specific user response.

    This function:
    1. Deletes existing party matches for this response
    2. Calculates new match scores using the updated label
    3. Creates new PartyStatementMatch objects
    4. Returns the calculated scores

    Args:
        response: UserResponse object to recalculate matches for

    Returns:
        Dictionary of party_id -> final_score
    """
    # Delete existing party matches for this response
    response.party_matches.all().delete()

    # Get all party positions for this statement
    positions = response.statement.positions.all()

    # Calculate new scores using the current label as the stance
    # Use the label (potentially user-updated) as the stance parameter
    # If no label exists, rank_parties will classify the opinion automatically
    scores = rank_parties(
        user_opinion=response.user_opinion,
        user_stance=response.label or "",  # Pass empty string if no label
        party_items=positions,
        statement_text=response.statement.text,
    )

    # Bulk fetch all parties to avoid N+1 queries
    party_ids = list(scores.keys())
    parties = {p.id: p for p in PoliticalParty.objects.filter(id__in=party_ids)}

    # Create PartyStatementMatch objects in bulk
    party_matches = []
    for party_id, score in scores.items():
        # Convert party_id to int since rank_parties returns string IDs but DB uses int IDs
        try:
            party_id_int = int(party_id)
        except (ValueError, TypeError):
            continue

        party = parties.get(party_id_int)
        if not party:
            continue

        position = positions.filter(party=party).first()
        if position:
            base_score = float(score)
            confidence_weight = response.confidence / 5.0
            importance_weight = response.importance / 5.0

            party_matches.append(
                PartyStatementMatch(
                    profile=response.profile,
                    statement=response.statement,
                    party=party,
                    user_response=response,
                    party_stance=position.stance,
                    party_explanation=position.explanation or "",
                    match_score=base_score,
                    confidence_weighted_score=base_score * confidence_weight,
                    importance_weighted_score=base_score * importance_weight,
                    final_score=base_score * confidence_weight * importance_weight,
                )
            )

    # Bulk create all matches at once
    if party_matches:
        PartyStatementMatch.objects.bulk_create(party_matches)

    return scores


def bulk_create_missing_party_matches(responses: List[UserResponse]) -> int:
    """
    Efficiently create missing PartyStatementMatch objects for multiple responses.
    This is much faster than calling recalculate_party_matches_for_response for each response.

    Returns:
        Number of responses processed
    """
    if not responses:
        return 0

    all_party_matches = []
    processed_count = 0

    # Prefetch all parties to avoid repeated queries
    all_parties = {p.id: p for p in PoliticalParty.objects.all()}

    for i, response in enumerate(responses, 1):
        # Get all party positions for this statement
        positions = response.statement.positions.select_related("party").all()

        if not positions.exists():
            continue

        # Calculate new scores using the current label as the stance
        # If no label exists, rank_parties will classify the opinion automatically
        try:
            scores = rank_parties(
                user_opinion=response.user_opinion,
                user_stance=response.label or "",  # Pass empty string if no label
                party_items=positions,
                statement_text=response.statement.text,
            )

            # Create PartyStatementMatch objects for this response
            matches_for_this_response = 0
            for party_id, score in scores.items():
                # Convert party_id to int since rank_parties returns string IDs but DB uses int IDs
                try:
                    party_id_int = int(party_id)
                except (ValueError, TypeError):
                    continue

                party = all_parties.get(party_id_int)
                if not party:
                    continue

                position = next(
                    (p for p in positions if p.party_id == party_id_int), None
                )
                if position:
                    # Check if this specific match already exists to avoid duplicates
                    existing_match = PartyStatementMatch.objects.filter(
                        profile=response.profile,
                        statement=response.statement,
                        party_id=party_id_int,
                        user_response=response,
                    ).exists()

                    if existing_match:
                        continue

                    base_score = float(score)
                    confidence_weight = response.confidence / 5.0
                    importance_weight = response.importance / 5.0

                    all_party_matches.append(
                        PartyStatementMatch(
                            profile=response.profile,
                            statement=response.statement,
                            party=party,
                            user_response=response,
                            party_stance=position.stance,
                            party_explanation=position.explanation or "",
                            match_score=base_score,
                            confidence_weighted_score=base_score * confidence_weight,
                            importance_weighted_score=base_score * importance_weight,
                            final_score=base_score
                            * confidence_weight
                            * importance_weight,
                        )
                    )
                    matches_for_this_response += 1

            processed_count += 1

        except Exception as e:
            print(f"Error processing response {response.id}: {e}")
            continue

    # Bulk create all matches at once
    if all_party_matches:
        PartyStatementMatch.objects.bulk_create(all_party_matches, batch_size=1000)

    return processed_count
