"""
AI Service for PolitiekMatcher Chat

This module handles the interaction with the language model
to generate answers based on political programs.
"""

from apps.utils.search import fuzzy_match_parties
import openai
from django.conf import settings
from typing import List, Tuple

from apps.content.models import ProgramFragment


def build_relevant_fragments(session, question: str, limit: int = 5) -> str:
    """
    Find the most relevant program fragments for a given question.

    This is a placeholder implementation using simple keyword matching.
    A more advanced version would use semantic search/embeddings.
    """
    # Find out which parties are relevant to the question
    parties = fuzzy_match_parties(question)
    if len(parties) == 0:
        # Get parties from previous message
        prev_message = session.previous_message()
        if prev_message:
            parties = list(prev_message.parties.all())

    if len(parties) > 0:
        # We want at most 2 parties to avoid too many fragments
        parties = parties[:2]
        fragment_by_party = {}
        for party in parties:
            # Get fragments for each party
            fragments = ProgramFragment.search(
                question,
                party=party,
                limit=limit,
            )
            fragment_by_party[party] = fragments

        # Combine fragments from all parties in formatted text
        output = ""
        for party, fragments in fragment_by_party.items():
            output += f"**Partij: {party.name}**\n\n"
            if not fragments:
                output += "Geen relevante fragmenten gevonden.\n\n"
            else:
                output += r"\---".join(
                    [f"Bron {f.source_reference}:\n{f.content}" for f in fragments]
                )
            output += "\n\n"

        return list(fragment_by_party.values()), output

    else:
        # Find all fragments related to the question
        fragments = ProgramFragment.search(question, limit=limit)
        if not fragments:
            return [], "Geen relevante fragmenten gevonden."

        # Combine fragments in formatted text
        output = "\n\n".join(
            [
                f"Bron {f.source_reference} (Partij: {f.program.party.name}):\n{f.content}"
                for f in fragments
            ]
        )
        return list(fragments), output


def build_chat_context(session, current_question: str) -> List[dict]:
    """
    Get the conversation context including the last 3 messages from the session.
    Returns a list of messages formatted for OpenAI API.
    """
    messages = []

    # Get the last 3 messages from the session (excluding the current one being processed)
    if session:
        recent_messages = session.messages.order_by("-created_at")[:3]

        # Reverse to get chronological order
        for msg in reversed(recent_messages):
            messages.extend(
                [
                    {"role": "user", "content": msg.question},
                    {"role": "assistant", "content": msg.answer},
                ]
            )

    # Interpret the question
    fragments, textual_info = build_relevant_fragments(session, current_question)

    # System prompt that defines the AI's role and behavior
    system_prompt = f"""Je bent een neutrale politieke assistent voor de website PolitiekMatcher. 

    BELANGRIJKE INSTRUCTIES:
    - Beantwoord vragen uitsluitend op basis van de verstrekte context uit Nederlandse verkiezingsprogramma's
    - Wees objectief en neutraal, vermijd persoonlijke meningen
    - Citeer niet direct, maar parafraseer de informatie
    - Verwijs naar partijen bij naam wanneer je hun standpunt beschrijft
    - Als je onvoldoende informatie hebt, zeg dat eerlijk
    - Houd je antwoorden bondig en informatief
    - Gebruik Nederlandse taal

    BESCHIKBARE INFORMATIE:
    {textual_info}

    Beantwoord de gebruiker op basis van bovenstaande context en het gespreksverloop."""

    # Build the context messages
    messages.append({"role": "system", "content": system_prompt})

    # Add the current question
    messages.append({"role": "user", "content": current_question})

    return messages, fragments


def get_ai_response(question: str, session=None) -> Tuple[str, List[ProgramFragment]]:
    """
    Generates an AI response to a user's question, using program fragments as context
    and previous conversation history.
    """
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "YOUR_API_KEY_HERE":
        return (
            "AI is niet geconfigureerd. Er moet een geldige OpenAI API-sleutel worden ingesteld om antwoorden te kunnen genereren.",
            [],
        )

    # Configure OpenAI client
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    try:
        # Get conversation context
        messages, fragments = build_chat_context(session, question)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.3,
            max_tokens=500,
        )

        answer = response.choices[0].message.content
        return answer, fragments

    except Exception as e:
        # Return a more informative error message
        return (
            f"Er is een technische fout opgetreden bij het genereren van een antwoord: {str(e)}",
            [],
        )
