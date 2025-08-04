"""
AI Context Service for providing historical and political context about statements
"""

import logging
from typing import Optional, Dict, Any
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)


class ContextAI:
    """Service for generating contextual information about political statements"""

    def __init__(self):
        if not settings.OPENAI_API_KEY:
            logger.warning(
                "⚠️ OpenAI API key not configured. Context generation will not work."
            )
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    def get_or_generate_statement_context(self, statement) -> Dict[str, Any]:
        """
        Get cached context from database or generate new context for a statement

        Args:
            statement: Statement model instance

        Returns:
            Dict containing context data
        """
        from apps.content.models import StatementContext

        # First, check if context already exists in database
        try:
            existing_context = StatementContext.objects.get(statement=statement)
            logger.info(f"Using cached context for statement {statement.id}")

            return {
                "success": True,
                "context": {
                    "issue_background": existing_context.issue_background,
                    "current_state": existing_context.current_state,
                    "possible_solutions": existing_context.possible_solutions,
                    "different_perspectives": existing_context.different_perspectives,
                    "why_relevant": existing_context.why_relevant,
                },
                "error": None,
            }
        except StatementContext.DoesNotExist:
            # Generate new context
            logger.info(f"Generating new context for statement {statement.id}")
            return self._generate_and_save_context(statement)

    def _generate_and_save_context(self, statement) -> Dict[str, Any]:
        """Generate new context and save it to database"""
        from apps.content.models import StatementContext

        if not self.client:
            return {
                "success": False,
                "error": "AI service not configured",
                "context": None,
            }

        try:
            # Generate context using AI
            context_result = self.generate_statement_context(
                statement.text, statement.explanation
            )

            if not context_result.get("success"):
                return context_result

            context_data = context_result.get("context", {})

            # Save to database
            statement_context = StatementContext.objects.create(
                statement=statement,
                issue_background=context_data.get("issue_background", ""),
                current_state=context_data.get("current_state", ""),
                possible_solutions=context_data.get("possible_solutions", ""),
                different_perspectives=context_data.get("different_perspectives", ""),
                why_relevant=context_data.get("why_relevant", ""),
            )

            logger.info(f"Saved new context for statement {statement.id}")
            return context_result

        except Exception as e:
            logger.error(
                f"Error generating/saving context for statement {statement.id}: {str(e)}"
            )
            return {
                "success": False,
                "error": f"Failed to generate context: {str(e)}",
                "context": None,
            }

    def generate_statement_context(
        self, statement_text: str, statement_explanation: str = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive contextual information about a political statement

        Args:
            statement_text: The main statement text
            statement_explanation: Optional explanation of the statement

        Returns:
            Dict containing generated context sections
        """
        if not self.client:
            return {
                "success": False,
                "error": "AI service not configured",
                "context": None,
            }

        try:
            # Build the prompt
            prompt = self._build_context_prompt(statement_text, statement_explanation)

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a neutral political analyst providing factual, educational context about political issues. You must remain completely objective and never favor any political ideology or party. Provide clear, accurate information that helps citizens understand complex political topics.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for more factual, consistent responses
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            # Parse the response
            content = response.choices[0].message.content
            import json

            context_data = json.loads(content)

            logger.info(f"✅ Generated context for statement: {statement_text[:50]}...")

            return {"success": True, "error": None, "context": context_data}

        except Exception as e:
            logger.error(f"❌ Error generating context: {str(e)}")
            return {
                "success": False,
                "error": f"Fout bij het genereren van context: {str(e)}",
                "context": None,
            }

    def _build_context_prompt(
        self, statement_text: str, statement_explanation: str = None
    ) -> str:
        """Build the prompt for context generation"""

        prompt = f"""
Analyseer de volgende politieke stelling en geef uitgebreide, neutrale context. Geef je antwoord in JSON format met de volgende structuur:

{{
    "issue_background": "Historische achtergrond van dit onderwerp",
    "current_state": "Huidige stand van zaken en recente ontwikkelingen", 
    "possible_solutions": "Mogelijke oplossingsrichtingen die worden voorgesteld",
    "different_perspectives": "Verschillende denkwijzen en perspectieven op dit onderwerp",
    "why_relevant": "Waarom dit onderwerp relevant is in het huidige politieke klimaat"
}}

STELLING: "{statement_text}"
"""

        if statement_explanation:
            prompt += f"""
UITLEG: "{statement_explanation}"
"""

        prompt += """

INSTRUCTIES:
- Blijf volledig neutraal en objectief
- Vermeld NOOIT specifieke partijnamen
- Gebruik heldere, begrijpelijke taal
- Focus op feiten en vermijd speculatie
- Leg uit waarom dit onderwerp belangrijk is
- Beschrijf verschillende standpunten zonder ze te beoordelen
- Gebruik Nederlandse taal
- Elke sectie moet minimaal 2-3 zinnen bevatten
- Zorg dat alle informatie feitelijk correct is

Geef alleen de JSON response terug, geen andere tekst.
"""

        return prompt


# Global instance
context_ai = ContextAI()
