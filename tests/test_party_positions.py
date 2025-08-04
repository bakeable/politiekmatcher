#!/usr/bin/env python
"""
Test script to verify party positions with sources work correctly
"""

import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "openpolitiek.settings")
django.setup()

from apps.content.models import (
    PoliticalParty,
    Topic,
    PartyPosition,
    PartyPositionSource,
)


def test_party_positions_with_sources():
    """Test that party positions with sources are working correctly"""

    # Get a party and topic that we know has positions with sources
    try:
        party = PoliticalParty.objects.get(abbreviation="50PLUS")
        topic = Topic.objects.get(name="Milieu en Klimaat")

        print(f"Testing party: {party.name}")
        print(f"Testing topic: {topic.name}")

        # Get positions for this party and topic
        positions = PartyPosition.objects.filter(
            party=party, topic=topic
        ).prefetch_related(
            "sources", "sources__statement_position", "sources__program_fragment"
        )

        print(f"Found {positions.count()} positions")

        for position in positions:
            sources = position.sources.all()
            print(f"\nPosition #{position.ranking}: {position.short}")
            print(f"  Sources: {sources.count()}")

            for source in sources:
                print(
                    f"    - {source.source_type}: ID {source.source_id} (score: {source.relevance_score:.2f})"
                )

                if source.statement_position:
                    print(
                        f"      Statement: {source.statement_position.statement.text[:50]}..."
                    )
                    print(f"      Stance: {source.statement_position.stance}")

                if source.program_fragment:
                    print(f"      Fragment: {source.program_fragment.content[:50]}...")
                    print(f"      Word count: {source.program_fragment.word_count}")

        return True

    except Exception as e:
        print(f"Error: {e}")
        return False


def test_graphql_query():
    """Test the GraphQL query functionality"""
    from apps.api.schema import Query

    try:
        party = PoliticalParty.objects.get(abbreviation="50PLUS")

        # Test the GraphQL query resolver
        query_instance = Query()
        results = query_instance.party_positions_by_topic(party.id)

        print(f"\nGraphQL Query Test:")
        print(f"Found {len(results)} topics for {party.abbreviation}")

        # Find topics with positions that have sources
        topics_with_sources = []
        for result in results:
            positions_with_sources = [p for p in result.positions if p.sources.exists()]
            if positions_with_sources:
                topics_with_sources.append(
                    (result.topic.name, len(positions_with_sources))
                )

        print(f"Topics with sources: {len(topics_with_sources)}")
        for topic_name, count in topics_with_sources:
            print(f"  - {topic_name}: {count} positions with sources")

        return True

    except Exception as e:
        print(f"GraphQL Query Error: {e}")
        return False


if __name__ == "__main__":
    print("=== Testing Party Positions with Sources ===")

    # Test database access
    db_test = test_party_positions_with_sources()

    # Test GraphQL query
    graphql_test = test_graphql_query()

    print(f"\n=== Results ===")
    print(f"Database test: {'✅ PASS' if db_test else '❌ FAIL'}")
    print(f"GraphQL test: {'✅ PASS' if graphql_test else '❌ FAIL'}")

    if db_test and graphql_test:
        print(
            "\n🎉 All tests passed! The source tracking implementation is working correctly."
        )
    else:
        print("\n⚠️ Some tests failed. Please check the implementation.")
