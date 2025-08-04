"""
Opinion comparison service using OpenAI API with caching
"""

from openai import OpenAI
from django.conf import settings
from ..content.models import OpinionComparison


def translate_opinion_to_dutch(opinion):
    """
    Translate opinion codes to Dutch text
    """
    translations = {
        "strongly_agree": "Helemaal mee eens",
        "agree": "Mee eens",
        "neutral": "Neutraal",
        "disagree": "Mee oneens",
        "strongly_disagree": "Helemaal mee oneens",
    }
    return translations.get(opinion, opinion)


def compare_political_opinions(statement_data, user_opinion, party_statements):
    """
    Compare political party opinions using OpenAI API with caching
    Returns the comparison text or raises an exception
    """
    try:
        # Extract data for cache key
        statement_id = statement_data.get("id")
        party_ids = [
            party_stmt.get("party", {}).get("id") for party_stmt in party_statements
        ]

        # Get party and

        # Check if we have a cached comparison
        cached_comparison, created = OpinionComparison.get_or_create_comparison(
            statement_id=statement_id, user_opinion=user_opinion, party_ids=party_ids
        )

        if cached_comparison and not created:
            # Return cached result
            return cached_comparison.comparison_result

        # No cache found, make API call
        # Translate user opinion to Dutch for the prompt
        user_opinion_text = translate_opinion_to_dutch(user_opinion)
        prompt = build_comparison_prompt(
            statement_data, user_opinion_text, party_statements
        )

        # Call OpenAI API
        client = OpenAI(api_key=settings.OPENAI_API_KEY)

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Je bent een objectieve politieke analist die partijstandpunten vergelijkt. Geef altijd een neutrale, informatieve analyse in het Nederlands. Gebruik markdown formatting voor een nette presentatie.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.3,
        )

        ai_result = response.choices[0].message.content

        # Cache the result
        OpinionComparison.get_or_create_comparison(
            statement_id=statement_id,
            user_opinion=user_opinion,
            party_ids=party_ids,
            comparison_result=ai_result,
        )

        return ai_result

    except Exception as e:
        raise Exception(f"Er is een fout opgetreden bij het vergelijken: {str(e)}")


def build_comparison_prompt(statement, user_opinion, party_statements):
    """
    Build a structured prompt for comparing political opinions
    """

    prompt = f"""
**POLITIEKE MENINGSVERGELIJKING**

**Stelling:**
"{statement.get('text', '')}"

**Context:** {statement.get('theme', '')} - {statement.get('topic', '')}

**Stellinguitleg:**
{statement.get('explanation', 'Geen uitleg beschikbaar.')}

**Gebruikersmening:**
"{user_opinion}"

**Partijstandpunten:**

"""

    for i, party_stmt in enumerate(party_statements, 1):
        party = party_stmt.get("party", {})
        stance_translation = {
            "strongly_agree": "Helemaal eens",
            "agree": "Eens",
            "neutral": "Neutraal",
            "disagree": "Oneens",
            "strongly_disagree": "Helemaal oneens",
        }

        stance_text = stance_translation.get(
            party_stmt.get("stance", ""), party_stmt.get("stance", "")
        )

        prompt += f"""
{i}. **{party.get('name', '')} ({party.get('abbreviation', '')})**
   - Standpunt: {stance_text}
   - Uitleg: {party_stmt.get('explanation', 'Geen uitleg beschikbaar.')}

"""

    prompt += """

**ANALYSEOPDRACHT:**

Geef een gestructureerde vergelijking in markdown format met de volgende onderdelen:

## 📊 Partijstandpunten Samenvatting
Geef voor elke partij een korte, objectieve samenvatting van hun standpunt (2-3 zinnen).

## 🔍 Belangrijkste Verschillen
Benoem de kernverschillen tussen de partijstandpunten. Waar verschillen ze het meest van elkaar?

## ⚖️ Jouw Mening
Benoem kort wat de gebruikersmening is. Analyseer daarna hoe de gebruikersmening zich verhoudt tot elk partijstandpunt:
- Welke partij komt het dichtst bij de gebruikersmening?
- Waar zitten de grootste overeenkomsten en verschillen?
- Geef concrete redenen waarom bepaalde partijen beter aansluiten.

## 🎯 Conclusie
Geef een korte, objectieve conclusie over welke partij(en) het beste aansluiten bij de gegeven mening en waarom. Benoem of de gebruiker een match is met een partij of dat er geen duidelijke overeenkomsten zijn.

**Let op:** Blijf objectief en informatief. Geef geen politieke voorkeur aan, maar leg uit waarom bepaalde standpunten beter aansluiten bij de gebruikersmening. Praat tegen de gebruiker in de tweede persoon ("jij" ) en gebruik een professionele, neutrale toon.
"""

    return prompt
