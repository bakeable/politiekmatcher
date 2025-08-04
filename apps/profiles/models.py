import uuid
from django.db import models
from django.utils import timezone
from apps.content.models import PoliticalParty, Statement


class UserProfile(models.Model):
    """Anonymous user profile for political matching"""

    # Unique identifier for anonymous users
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Optional email for profile retrieval
    email = models.EmailField(
        blank=True, null=True, help_text="Email for profile retrieval"
    )

    # Profile status
    is_completed = models.BooleanField(
        default=False, help_text="Has user completed all statements"
    )

    # Session management
    session_key = models.CharField(max_length=40, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_active = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
        ordering = ["-created_at"]

    def __str__(self):
        if self.email:
            return f"Profile {self.uuid} ({self.email})"
        return f"Anonymous Profile {self.uuid}"


class UserResponse(models.Model):
    """User's response to a political statement"""

    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="responses"
    )
    statement = models.ForeignKey(Statement, on_delete=models.CASCADE)

    # User's opinion (free text)
    user_opinion = models.TextField(help_text="User's opinion on the statement")

    # Confidence level (1-5)
    confidence = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        default=3,
        help_text="How confident is the user in their opinion (1-5)",
    )

    # Importance level (1-5)
    importance = models.IntegerField(
        choices=[(i, i) for i in range(1, 6)],
        default=3,
        help_text="How important is this topic to the user (1-5)",
    )

    label = models.CharField(
        max_length=20,
        choices=[
            ("agree", "Agree"),
            ("neutral", "Neutral"),
            ("disagree", "Disagree"),
        ],
        null=True,
        blank=True,
        help_text="Label for the user's opinion (optional)",
    )

    # Confidence score for the label (0.0 - 1.0)
    confidence_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Confidence score for the classified label (0.0 - 1.0)",
    )

    # Original label set by the classifier
    # This is used to track the original label before any user edits
    # or changes are made to the response.
    classified_label = models.CharField(
        max_length=20,
        choices=[
            ("agree", "Agree"),
            ("neutral", "Neutral"),
            ("disagree", "Disagree"),
        ],
        null=True,
        blank=True,
        help_text="Original label set by the classifier",
    )
    label_set_by = models.CharField(
        max_length=50,
        choices=[
            ("user", "User"),
            ("AI", "AI Classified"),
        ],
        null=True,
        blank=True,
        help_text="Who set the label (e.g. 'user', 'AI')",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "statement")
        verbose_name = "User Response"
        verbose_name_plural = "User Responses"

    def __str__(self):
        return f"{self.profile} - {self.statement.text[:50]}..."


class EmailVerification(models.Model):
    """Email verification for profile access"""

    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    email = models.EmailField()
    token = models.UUIDField(default=uuid.uuid4, unique=True)

    # Verification status
    is_verified = models.BooleanField(default=False)

    # Expiration
    expires_at = models.DateTimeField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Email Verification"
        verbose_name_plural = "Email Verifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Verification for {self.email}"

    def is_expired(self):
        return timezone.now() > self.expires_at


class PartyMatch(models.Model):
    """Calculated match between user and political party"""

    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="party_matches"
    )
    party = models.ForeignKey(PoliticalParty, on_delete=models.CASCADE)

    # Match percentage (0-100)
    match_percentage = models.FloatField(help_text="Match percentage (0-100)")

    # Detailed scoring
    agreement_score = models.FloatField(default=0.0, help_text="Agreement score")
    confidence_weighted_score = models.FloatField(
        default=0.0, help_text="Confidence weighted score"
    )
    importance_weighted_score = models.FloatField(
        default=0.0, help_text="Importance weighted score"
    )

    # Match details
    total_statements = models.IntegerField(default=0)
    matching_statements = models.IntegerField(default=0)

    # AI-generated explanation (cached)
    explanation = models.TextField(
        blank=True,
        null=True,
        help_text="AI-generated explanation of the match (cached)",
    )

    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "party")
        verbose_name = "Party Match"
        verbose_name_plural = "Party Matches"
        ordering = ["-match_percentage"]

    def __str__(self):
        return f"{self.profile} - {self.party.name}: {self.match_percentage:.1f}%"


class PartyStatementMatch(models.Model):
    """Individual statement match between user response and party position"""

    profile = models.ForeignKey(
        UserProfile, on_delete=models.CASCADE, related_name="statement_matches"
    )
    statement = models.ForeignKey(Statement, on_delete=models.CASCADE)
    party = models.ForeignKey(PoliticalParty, on_delete=models.CASCADE)

    # User response details
    user_response = models.ForeignKey(
        UserResponse, on_delete=models.CASCADE, related_name="party_matches"
    )

    # Party stance from StatementPosition
    party_stance = models.CharField(
        max_length=20,
        choices=[
            ("strongly_agree", "Strongly Agree"),
            ("agree", "Agree"),
            ("neutral", "Neutral"),
            ("disagree", "Disagree"),
            ("strongly_disagree", "Strongly Disagree"),
        ],
        help_text="Party's stance on this statement",
    )
    party_explanation = models.TextField(
        help_text="Party's explanation of their position"
    )

    # Match scores (0-100)
    match_score = models.FloatField(
        help_text="Base agreement score between user and party on this statement"
    )
    confidence_weighted_score = models.FloatField(
        help_text="Match score weighted by user's confidence"
    )
    importance_weighted_score = models.FloatField(
        help_text="Match score weighted by user's importance rating"
    )
    final_score = models.FloatField(
        help_text="Final weighted score (confidence + importance)"
    )

    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("profile", "statement", "party")
        verbose_name = "Party Statement Match"
        verbose_name_plural = "Party Statement Matches"
        ordering = ["-final_score"]

    def __str__(self):
        return f"{self.profile} - {self.party.name} on '{self.statement.text[:50]}...': {self.match_score:.1f}%"
