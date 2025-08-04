"""
Celery tasks for profile operations
"""

from apps.utils.match_opinions import rank_parties
from celery import shared_task
from django.utils import timezone
from apps.utils.classifier import classify_opinion
from apps.profiles.models import UserResponse


@shared_task(bind=True, max_retries=3)
def classify_user_response_async(self, response_id: int):
    """
    Asynchronously classify a user response using the opinion classifier.

    Args:
        response_id: The ID of the UserResponse to classify

    Returns:
        dict: Classification results with label and confidence score
    """
    try:
        # Get the response
        try:
            response = UserResponse.objects.get(id=response_id)
        except UserResponse.DoesNotExist:
            return {
                "success": False,
                "error": f"UserResponse with id {response_id} not found",
            }

        # Skip if already classified
        if response.label and response.confidence_score is not None:
            return {
                "success": True,
                "message": "Response already classified",
                "label": response.label,
                "confidence_score": response.confidence_score,
            }

        # Classify the response
        statement_text = response.statement.text
        user_opinion = response.user_opinion

        label, confidence_score = classify_opinion(
            statement=statement_text,
            reaction=user_opinion,
        )

        # Update the response with classification results
        response.label = label
        response.confidence_score = float(
            confidence_score
        )  # Ensure it's a regular Python float
        response.classified_label = label  # Store original AI classification
        response.label_set_by = "AI"  # Mark as AI-classified
        response.updated_at = timezone.now()
        response.save(
            update_fields=[
                "label",
                "confidence_score",
                "classified_label",
                "label_set_by",
                "updated_at",
            ]
        )

        # Match parties for the response
        match_parties_async.delay(response_id)

        return {
            "success": True,
            "label": label,
            "confidence_score": float(confidence_score),  # Ensure JSON serializable
            "message": f"Successfully classified response {response_id}",
        }

    except Exception as exc:
        # Retry the task with exponential backoff
        countdown = 2**self.request.retries
        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=3)
def match_parties_async(self, response_id: int):
    """
    Match parties for a user response asynchronously.

    Args:
        response_id: The ID of the UserResponse to match parties for

    Returns:
        dict: Results of the party matching operation
    """
    import gc
    import torch

    try:
        # Get the response
        response = UserResponse.objects.get(id=response_id)

        # Create party matches with error handling
        positions = response.statement.positions.all()

        if not positions.exists():
            return {
                "success": False,
                "error": f"No party positions found for statement {response.statement.id}",
            }

        try:
            scores = rank_parties(
                response.user_opinion,
                response.label or "",  # Handle case where label is None
                positions,
                statement_text=response.statement.text,
            )
        except Exception as e:
            print(f"Error in rank_parties for response {response_id}: {e}")
            # Return a fallback result
            return {"success": False, "error": f"Party ranking failed: {str(e)}"}

        from apps.profiles.models import PartyStatementMatch
        from apps.content.models import PoliticalParty

        # Bulk fetch parties to avoid N+1 queries
        party_ids = [int(pid) for pid in scores.keys()]
        parties = {p.id: p for p in PoliticalParty.objects.filter(id__in=party_ids)}

        matches_created = 0
        for party_id, score in scores.items():
            party_id_int = int(party_id)  # Convert string to int
            party = parties.get(party_id_int)
            if not party:
                print(f"Warning: Party {party_id} not found")
                continue

            position = positions.filter(party=party).first()

            if position:
                base_score = float(score)
                confidence_weight = response.confidence / 5.0
                importance_weight = response.importance / 5.0

                PartyStatementMatch.objects.update_or_create(
                    profile=response.profile,
                    statement=response.statement,
                    party=party,
                    user_response=response,
                    defaults={
                        "party_stance": position.stance,
                        "party_explanation": position.explanation or "",
                        "match_score": base_score,
                        "confidence_weighted_score": base_score * confidence_weight,
                        "importance_weighted_score": base_score * importance_weight,
                        "final_score": base_score
                        * confidence_weight
                        * importance_weight,
                    },
                )
                matches_created += 1

        # Force garbage collection to free memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

        # Convert scores to regular Python floats for JSON serialization
        serializable_scores = {str(k): float(v) for k, v in scores.items()}
        return {
            "success": True,
            "scores": serializable_scores,
            "matches_created": matches_created,
        }

    except UserResponse.DoesNotExist:
        return {
            "success": False,
            "error": f"UserResponse with id {response_id} not found",
        }
    except Exception as exc:
        print(
            f"Critical error in match_parties_async for response {response_id}: {exc}"
        )
        # Force cleanup before retry
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

        # Retry the task with exponential backoff
        countdown = 2**self.request.retries
        raise self.retry(
            exc=exc, countdown=countdown, max_retries=2
        )  # Reduce max retries
        raise self.retry(exc=exc, countdown=countdown)


@shared_task
def bulk_classify_responses():
    """
    Bulk classify all unclassified responses.
    This can be run periodically to ensure all responses are classified.
    """
    unclassified = UserResponse.objects.filter(label__isnull=True).select_related(
        "statement"
    )

    results = {"total_processed": 0, "successful": 0, "failed": 0, "errors": []}

    for response in unclassified:
        try:
            classify_user_response_async.delay(response.id)
            results["successful"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"Response {response.id}: {str(e)}")

        results["total_processed"] += 1

    return results
