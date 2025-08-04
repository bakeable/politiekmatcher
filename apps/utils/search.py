from politiekmatcher.settings import PARTY_NAME_MAPPINGS


def fuzzy_match_parties(text: str, threshold: int = 85) -> list:
    """
    Fuzzy match user input text to known party aliases.

    Args:
        text (str): The user input.
        party_name_mappings (dict): A dictionary where keys are canonical party names and values are lists of aliases.
        threshold (int): Minimum matching score for fuzzy matching.

    Returns:
        list: List of matched canonical party names.
    """
    from fuzzywuzzy import fuzz

    matches = set()
    parties = {}
    text_lower = text.lower()

    for canonical_name, aliases in PARTY_NAME_MAPPINGS.items():
        parties[canonical_name] = {
            "matches": 0,
            "avg_score": 0,
            "highest_score": 0,
        }
        for alias in aliases:
            score = fuzz.partial_ratio(text_lower, alias.lower())
            if score >= threshold:
                matches.add(canonical_name)
                parties[canonical_name]["avg_score"] += score
                parties[canonical_name]["highest_score"] = max(
                    parties[canonical_name]["highest_score"], score
                )
                parties[canonical_name]["matches"] += 1

    # Compute average scores
    for party in parties.values():
        party["avg_score"] = (
            party["avg_score"] / party["matches"] if party["matches"] > 0 else 0
        )

    # Sort matches by highest score
    matches = sorted(matches, key=lambda x: parties[x]["avg_score"], reverse=True)

    # Get matches in database
    from apps.content.models import PoliticalParty

    db_parties = PoliticalParty.objects.filter(name__in=matches)

    return list(db_parties)
