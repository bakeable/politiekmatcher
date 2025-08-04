import os
import json
import time
import numpy as np
from django.core.management.base import BaseCommand
from apps.profiles.models import UserResponse


class Command(BaseCommand):
    help = (
        "Use a fine-tuned Transformer to classify user reactions "
        "(agree, neutral, disagree)."
    )

    def handle(self, *args, **options):
        responses = UserResponse.objects.all()

        for response in responses:
            self.stdout.write(f"🔍 Classifying user response {response.id}...")

            # Load the fine-tuned model and tokenizer
            from apps.utils.classifier import classify_opinion

            # Classify the user's opinion
            label, prob = classify_opinion(
                statement=response.statement.text,
                reaction=response.user_opinion,
            )

            if label == "neutral":
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠️ Neutral (prob: {prob:.2f}) opinion detected for response:\n{response.user_opinion}."
                    )
                )
            elif label == "disagree":
                self.stdout.write(
                    self.style.ERROR(
                        f"❌ Disagree (prob: {prob:.2f}) opinion detected for response:\n{response.user_opinion}."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ Agree (prob: {prob:.2f}) opinion detected for response:\n{response.user_opinion}."
                    )
                )

            response.label = label
            response.confidence_score = prob
            response.save()
