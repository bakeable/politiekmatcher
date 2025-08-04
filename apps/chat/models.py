"""
Chat models for PolitiekMatcher

These models handle chat conversations and AI responses.
"""

from django.db import models
from django.utils import timezone
import uuid


class ChatSession(models.Model):
    """Model representing a chat session"""

    session_id = models.UUIDField(default=uuid.uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional user tracking (for future auth implementation)
    user_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = "Chat Session"
        verbose_name_plural = "Chat Sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Chat Session {self.session_id} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    def previous_message(self):
        """Get the last message in this session, if any."""
        try:
            return self.messages.latest("created_at")
        except ChatMessage.DoesNotExist:
            return None


class ChatMessage(models.Model):
    """Model representing a single chat message exchange"""

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )

    # The conversation
    question = models.TextField(help_text="De vraag van de gebruiker")
    answer = models.TextField(help_text="Het AI-gegenereerde antwoord")

    # Metadata
    topic = models.ForeignKey(
        "content.Topic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Het hoofd-onderwerp van de vraag, indien van toepassing",
    )
    parties = models.ManyToManyField(
        "content.PoliticalParty",
        blank=True,
        help_text="Lijst van politieke partijen voor context",
    )

    # AI processing info
    model_used = models.CharField(
        max_length=100,
        default="gpt-3.5-turbo",
        help_text="AI model gebruikt voor antwoord",
    )
    processing_time_ms = models.PositiveIntegerField(
        null=True, blank=True, help_text="Verwerkingstijd in milliseconden"
    )

    # Quality metrics
    helpful_rating = models.IntegerField(
        null=True,
        blank=True,
        choices=[(i, i) for i in range(1, 6)],
        help_text="Gebruiker rating 1-5",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Chat Message"
        verbose_name_plural = "Chat Messages"
        ordering = ["created_at"]

    def __str__(self):
        return (
            f"Q: {self.question[:50]}... - {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


class MessageSource(models.Model):
    """Model linking chat messages to their source fragments"""

    message = models.ForeignKey(
        ChatMessage, on_delete=models.CASCADE, related_name="sources"
    )

    # Link to content
    program_fragment = models.ForeignKey(
        "content.ProgramFragment",
        on_delete=models.CASCADE,
        help_text="Het programma fragment dat als bron is gebruikt",
    )

    # Relevance scoring
    relevance_score = models.FloatField(
        default=0.0, help_text="Relevantie score van 0.0 tot 1.0"
    )

    # Position in response
    order = models.PositiveIntegerField(
        default=0, help_text="Volgorde van bronnen in antwoord"
    )

    class Meta:
        verbose_name = "Message Source"
        verbose_name_plural = "Message Sources"
        ordering = ["message", "order"]
        unique_together = [("message", "program_fragment")]

    def __str__(self):
        return f"Source for {self.message.id}: {self.program_fragment.content[:30]}..."
