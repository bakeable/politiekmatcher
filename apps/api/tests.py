"""
Tests for the PolitiekMatcher GraphQL API
"""

from django.test import TestCase, Client
from strawberry.django.test import GraphQLTestClient
from apps.content.models import PoliticalParty, ElectionProgram, ProgramFragment
from apps.chat.models import ChatSession, ChatMessage
import uuid


class ChatAPITest(TestCase):
    def setUp(self):
        """Set up test data"""
        self.client = GraphQLTestClient(client=Client())

        # Create some content to be used as a source
        self.party = PoliticalParty.objects.create(
            name="Test Partij", abbreviation="TP"
        )
        self.program = ElectionProgram.objects.create(
            party=self.party,
            title="Test Verkiezingsprogramma",
            year=2023,
            source_url="http://example.com/programma.pdf",
        )
        self.fragment = ProgramFragment.objects.create(
            program=self.program,
            title="Hoofdstuk 1: Testen",
            content="Dit is een test fragment over het belang van testen.",
            topic="democratie",
        )

    def test_send_chat_message_mutation_new_session(self):
        """
        Tests the sendChatMessage mutation for a new chat session.
        """
        self.assertEqual(ChatSession.objects.count(), 0)
        self.assertEqual(ChatMessage.objects.count(), 0)

        mutation = """
            mutation SendChatMessage($message: String!, $sessionId: String) {
                sendChatMessage(message: $message, sessionId: $sessionId) {
                    sessionId
                    message {
                        id
                        question
                        answer
                        topic
                        sources {
                            id
                            title
                            content
                            party {
                                abbreviation
                            }
                            sourceUrl
                        }
                    }
                }
            }
        """

        response = self.client.query(
            query=mutation,
            variables={"message": "Wat is het standpunt over testen?"},
        )

        self.assertIsNone(response.errors)
        data = response.data["sendChatMessage"]

        self.assertEqual(
            data["message"]["question"], "Wat is het standpunt over testen?"
        )
        self.assertIn("geïmplementeerd", data["message"]["answer"])
        self.assertIsNotNone(data["sessionId"])

        # Verify database state
        self.assertEqual(ChatSession.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.count(), 1)

        chat_message = ChatMessage.objects.first()
        self.assertEqual(chat_message.question, "Wat is het standpunt over testen?")
        self.assertEqual(chat_message.session.id, ChatSession.objects.first().id)

    def test_send_chat_message_mutation_existing_session(self):
        """
        Tests the sendChatMessage mutation for an existing chat session.
        """
        session = ChatSession.objects.create()
        self.assertEqual(ChatSession.objects.count(), 1)

        mutation = """
            mutation SendChatMessage($message: String!, $sessionId: String!) {
                sendChatMessage(message: $message, sessionId: $sessionId) {
                    sessionId
                    message {
                        id
                        question
                    }
                }
            }
        """

        response = self.client.query(
            query=mutation,
            variables={
                "message": "Een vervolgvraag.",
                "sessionId": str(session.session_id),
            },
        )

        self.assertIsNone(response.errors)
        data = response.data["sendChatMessage"]
        self.assertEqual(str(session.session_id), data["sessionId"])

        # Verify database state
        self.assertEqual(
            ChatSession.objects.count(), 1
        )  # No new session should be created
        self.assertEqual(ChatMessage.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.first().session.id, session.id)
