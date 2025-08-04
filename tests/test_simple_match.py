#!/usr/bin/env python3
"""
Simple test to debug the matching logic
"""

import sys
import os

sys.path.append("/Users/robinbakker/GitHub/open-politiek/backend")

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "openpolitiek.settings")
import django

django.setup()

from apps.utils.match_opinions import rank_parties


def test_simple_case():
    """Test with very clear opinions"""

    user_opinion = "Ik ben volledig voor klimaatbeleid"
    statement_text = (
        "Klimaatbeleid is belangrijk"  # Provide statement for better classification
    )

    party_items = [
        (
            "pro",
            "strongly_agree",
            "Wij zijn volledig voor klimaatbeleid en willen het uitbreiden.",
        ),
        (
            "anti",
            "strongly_disagree",
            "Wij zijn volledig tegen klimaatbeleid en willen het afschaffen.",
        ),
        ("neutral", "neutral", "Wij hebben geen sterke mening over klimaatbeleid."),
    ]

    print("🧪 Simple matching test...")
    print(f"Statement: {statement_text}")
    print(f"User opinion: {user_opinion}")
    print()

    scores = rank_parties(user_opinion, "", party_items, statement_text)

    print("📊 Matching scores:")
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    for party, score in sorted_scores:
        explanation = next(item[2] for item in party_items if item[0] == party)
        stance = next(item[1] for item in party_items if item[0] == party)
        print(f"{party.upper():8} | {score:5.1f}% | {stance:15} | {explanation}")

    # Check if pro scores highest
    if scores["pro"] > scores["anti"] and scores["pro"] > scores["neutral"]:
        print("\n✅ Simple test passed!")
    else:
        print(f"\n❌ Simple test failed!")
        print(f"   Pro: {scores['pro']:.1f}% should be highest")


if __name__ == "__main__":
    test_simple_case()
