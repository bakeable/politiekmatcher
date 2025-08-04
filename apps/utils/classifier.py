import os
import re
from functools import lru_cache
from politiekmatcher.settings import BASE_DIR
from transformers import pipeline
import torch

# Path to your fine-tuned model directory
MODEL_DIR = os.path.join(BASE_DIR, "models/opinion_classifier")
LABEL_MAP = {0: "disagree", 1: "neutral", 2: "agree"}


def _apply_rule_based_fallback(reaction: str) -> str | None:
    """
    Apply rule-based classification for clear Dutch expressions.
    Returns the stance if detected, None otherwise.
    """
    reaction_lower = reaction.lower().strip()

    # Strong disagreement patterns
    disagree_patterns = [
        r"\b(ik\s+ben\s+het\s+niet\s+eens|niet\s+eens)\b",
        r"\b(oneens|on\s*eens)\b",
        r"\b(helemaal\s+niet|absoluut\s+niet)\b",
        r"\b(nee,?\s*(dit|dat)?)\b",
        r"\btegen\s+deze?\s+stelling\b",
    ]

    # Strong agreement patterns
    agree_patterns = [
        r"\b(ik\s+ben\s+het\s+(helemaal\s+)?eens|eens)\b",
        r"\b(ja,?\s*(dit|dat)?)\b",
        r"\b(helemaal\s+mee\s+eens|volledig\s+eens)\b",
        r"\bvoor\s+deze?\s+stelling\b",
    ]

    # Check disagreement patterns
    for pattern in disagree_patterns:
        if re.search(pattern, reaction_lower):
            return "disagree"

    # Check agreement patterns (but be more conservative)
    for pattern in agree_patterns:
        if re.search(pattern, reaction_lower):
            return "agree"

    return None


def get_pipeline():

    # Detect if CUDA (GPU) is available
    device = 0 if torch.cuda.is_available() else -1

    return pipeline(
        "text-classification",
        model=MODEL_DIR,
        tokenizer=MODEL_DIR,
        return_all_scores=True,
        device=device,
    )


def classify_opinion(
    statement: str, reaction: str, neutral_threshold: float = 0.4
) -> tuple[str, float]:
    """
    Classify a user's reaction to a political statement.

    First applies rule-based fallback for clear Dutch expressions,
    then falls back to the ML model for ambiguous cases.
    """
    # Try rule-based classification first
    rule_based_result = _apply_rule_based_fallback(reaction)
    if rule_based_result:
        # Return high confidence for rule-based results
        return rule_based_result, 0.95

    # Fall back to ML model
    text = f"Stelling: {statement}\nReactie: {reaction}"
    pipeline = get_pipeline()
    all_scores = pipeline(text, truncation=True, max_length=512)
    # all_scores is a list of lists; take first element
    scores_list = all_scores[0]
    # Map label IDs to human labels
    prob = {}
    for item in scores_list:
        label = item["label"]
        if isinstance(label, str) and label.startswith("LABEL_"):
            label_id = int(label.replace("LABEL_", ""))
        else:
            label_id = int(label)
        prob[LABEL_MAP[label_id]] = item["score"]

    # Apply neutral threshold
    if prob.get("neutral", 0.0) >= neutral_threshold:
        label = "neutral"
    else:
        # Otherwise pick the higher of agree/disagree
        label = max(("agree", "disagree"), key=lambda lab: prob.get(lab, 0.0))

    return label, prob.get(label, 0.0)
