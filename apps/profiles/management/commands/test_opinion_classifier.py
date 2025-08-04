from django.core.management.base import BaseCommand
from apps.content.models import Statement, StatementPosition
from apps.utils.classifier import classify_opinion
import torch


class Command(BaseCommand):
    help = "Interactive prediction of opinions using a fine-tuned model."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interactive", action="store_true", help="Run in interactive mode"
        )
        return super().add_arguments(parser)

    def handle(self, *args, **options):

        if options["interactive"]:
            while True:
                # Grab a random statement
                random_statement = Statement.objects.order_by("?").first()

                self.stdout.write(f"\nStatement: {random_statement.text}\n")
                text = input(
                    "\nGive reaction to statement (or 'exit' to quit): "
                ).strip()
                if text.lower() == "exit":
                    break
                if not text:
                    continue

                label, prob = classify_opinion(
                    statement=random_statement.text, reaction=text
                )

                if label == "neutral":
                    print(
                        f"⚠️ Neutral opinion detected for response:\n{text}\nwith probability {prob:.2f}."
                    )
                elif label == "disagree":
                    print(
                        f"❌ Disagree opinion detected for response:\n{text}\nwith probability {prob:.2f}."
                    )
                else:
                    print(
                        f"✅ Agree opinion detected for response:\n{text}\nwith probability {prob:.2f}."
                    )

        else:
            # Get all statements
            statements = Statement.objects.all()

            # Get all statement positions
            tp, fp, tn, fn = 0, 0, 0, 0
            for statement in statements:
                self.stdout.write(f"🔍 Classifying statement {statement.id}...")
                positions = StatementPosition.objects.filter(statement=statement)
                for pos in positions:
                    # Classify the statement
                    label, prob = classify_opinion(
                        statement=statement.text, reaction=pos.explanation
                    )

                    real_label = pos.stance
                    if real_label == "strongly_agree":
                        real_label = "agree"
                    if real_label == "strongly_disagree":
                        real_label = "disagree"

                    if label == real_label:
                        tp += 1
                    else:
                        fp += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Classification complete: {tp} true positives, {fp} false positives, accuracy: {tp / (tp + fp) if (tp + fp) > 0 else 0:.2f}"
                )
            )
