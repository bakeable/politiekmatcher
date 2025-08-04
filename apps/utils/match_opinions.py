from typing import List, Tuple, Dict, Union
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
from apps.utils.classifier import classify_opinion

DIM_FIELDS = [
    "economic",
    "social",
    "environmental",
    "immigration",
    "europe",
    "authority",
    "institutionality",
]

# Global cache for models to prevent repeated loading across workers
_MODEL_CACHE = {"tokenizers": None, "models": None, "device": None, "loaded": False}


def _load_dimension_models(model_dir="models"):
    """
    Load per-dimension fine-tuned models and tokenizers with caching.
    """
    global _MODEL_CACHE

    # Return cached models if already loaded
    if _MODEL_CACHE["loaded"]:
        return (
            _MODEL_CACHE["tokenizers"],
            _MODEL_CACHE["models"],
            _MODEL_CACHE["device"],
        )

    try:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        models = {}
        tokenizers = {}

        print(f"Loading political dimension models to {device}...")

        for dim in DIM_FIELDS:
            model_path = f"{model_dir}/political_dimensions_{dim}"
            print(f"  Loading {dim} model...")

            # Load with error handling
            try:
                tokenizers[dim] = AutoTokenizer.from_pretrained(model_path)
                model = AutoModelForSequenceClassification.from_pretrained(model_path)
                model.eval().to(device)
                models[dim] = model
            except Exception as e:
                print(f"  Error loading {dim} model: {e}")
                # Continue with other models
                continue

        # Cache the loaded models
        _MODEL_CACHE["tokenizers"] = tokenizers
        _MODEL_CACHE["models"] = models
        _MODEL_CACHE["device"] = device
        _MODEL_CACHE["loaded"] = True

        print(f"Successfully loaded {len(models)} dimension models")
        return tokenizers, models, device

    except Exception as e:
        print(f"Critical error loading models: {e}")
        # Return empty models to prevent crashes
        return {}, {}, torch.device("cpu")
    return tokenizers, models, device


def _score_dimensions(text: str, tokenizers, models, device) -> np.ndarray:
    """
    Score a text across all political dimensions.
    Returns a numpy array of shape (len(DIM_FIELDS),)
    """
    scores = []
    for dim in DIM_FIELDS:
        tok = tokenizers[dim]
        model = models[dim]
        inputs = tok(
            text,
            return_tensors="pt",
            truncation=True,
            padding="longest",
            max_length=256,
        ).to(device)
        with torch.no_grad():
            output = model(**inputs)
            score = output.logits[0][0].item()
            score = max(-1.0, min(1.0, score))
            scores.append(score)
    return np.array(scores, dtype=np.float32)


def _normalize_party_stance(stance: str) -> str:
    """
    Normalize party stances to agree/neutral/disagree.
    Maps strongly_agree/agree -> agree, strongly_disagree/disagree -> disagree
    """
    if stance in ["strongly_agree", "agree"]:
        return "agree"
    elif stance in ["strongly_disagree", "disagree"]:
        return "disagree"
    else:
        return "neutral"


def _calculate_base_match_score(user_stance: str, party_stance: str) -> float:
    """
    Calculate base match score based on stance alignment.
    - Matching stances: 80%
    - User agree/disagree vs party neutral: 50%
    - Opposite stances: 20%
    """
    normalized_party_stance = _normalize_party_stance(party_stance)

    if user_stance == normalized_party_stance:
        return 80.0
    elif normalized_party_stance == "neutral" and user_stance in ["agree", "disagree"]:
        return 50.0
    elif user_stance == "neutral" and normalized_party_stance in ["agree", "disagree"]:
        return 50.0
    else:
        # Opposite stances
        return 20.0


def _get_dimensions_vector(dimensions_obj) -> np.ndarray:
    """
    Extract dimension vector from PoliticalDimensions object.
    Returns a numpy array of shape (len(DIM_FIELDS),)
    """
    if not dimensions_obj:
        return np.zeros(len(DIM_FIELDS), dtype=np.float32)

    scores = []
    for dim in DIM_FIELDS:
        score = getattr(dimensions_obj, dim, 0.0)
        scores.append(float(score))

    return np.array(scores, dtype=np.float32)


def _calculate_dimension_modifier(
    user_opinion: str, party_dimensions, tokenizers, models, device
) -> float:
    """
    Calculate political dimension modifier score (-20 to +20) using stored party dimensions.
    Only considers dimensions with significant scores (< -0.1 or > 0.1).
    """
    # Get stored party dimensions
    party_vec = _get_dimensions_vector(party_dimensions)

    return _calculate_dimension_modifier_from_vectors(
        user_opinion, party_vec, tokenizers, models, device
    )


def _calculate_dimension_modifier_from_vectors(
    user_opinion: str, party_vec: np.ndarray, tokenizers, models, device
) -> float:
    """
    Calculate political dimension modifier score (-20 to +20) using pre-calculated party vector.
    Only considers dimensions with significant scores (< -0.1 or > 0.1).
    """
    # Score user opinion dimensions
    user_vec = _score_dimensions(user_opinion, tokenizers, models, device)

    # Filter significant dimensions
    significant_mask = (np.abs(user_vec) > 0.1) | (np.abs(party_vec) > 0.1)

    if not np.any(significant_mask):
        return 0.0

    # Calculate similarity only for significant dimensions
    user_sig = user_vec[significant_mask]
    party_sig = party_vec[significant_mask]

    # Cosine similarity
    norm_user = np.linalg.norm(user_sig)
    norm_party = np.linalg.norm(party_sig)

    if norm_user == 0 or norm_party == 0:
        return 0.0

    similarity = np.dot(user_sig, party_sig) / (norm_user * norm_party)

    # Map similarity [-1, 1] to modifier [-20, 20]
    modifier = similarity * 20.0

    # Make sure modifier is within bounds
    modifier = max(-20.0, min(20.0, modifier))

    # Convert to Python float to ensure JSON serialization compatibility
    return float(modifier)


def _create_and_save_dimensions(statement_position, party_vec: np.ndarray):
    """
    Create and save PoliticalDimensions object for a StatementPosition.
    Returns the created PoliticalDimensions object.
    """
    try:
        from apps.content.models import PoliticalDimensions

        # Create dimensions object with calculated values
        dimensions_data = {}
        for i, dim in enumerate(DIM_FIELDS):
            dimensions_data[dim] = float(party_vec[i])

        # Add confidence and evidence (required fields)
        dimensions_data["confidence"] = (
            0.8  # Default confidence for calculated dimensions
        )
        dimensions_data["evidence"] = "Calculated from statement explanation"

        # Create the dimensions object
        dimensions = PoliticalDimensions.objects.create(**dimensions_data)

        # Link it to the statement position
        statement_position.dimensions = dimensions
        statement_position.save()

        print(
            f"Created and saved dimensions for party {statement_position.party.abbreviation} on statement {statement_position.statement.id}"
        )

        return dimensions

    except Exception as e:
        print(f"Warning: Could not save dimensions for statement position: {e}")
        return None


def rank_parties(
    user_opinion: str,
    user_stance: str = "",
    party_items: Union[List[Tuple[str, str, str]], List] = [],
    statement_text: str = "",
    model_dir="models",
) -> Dict[str, float]:
    """
    Rank parties using improved matching algorithm:
    1. Classify user opinion stance (agree/neutral/disagree)
    2. Calculate base match score based on stance alignment
    3. Add political dimension modifier (-20 to +20) using stored dimensions when available
    4. Ensure final score is in range [0, 100]

    Args:
        user_opinion: User's opinion text
        party_items: List of StatementPosition objects OR (party_id, stance, explanation) tuples
        statement_text: Statement text for opinion classification
        model_dir: Directory containing the models

    Returns:
        Dict of party_id -> final_score (0-100)
    """
    if not user_opinion.strip():
        raise ValueError("user_opinion must be non-empty")
    if not party_items:
        return {}

    # Classify user opinion stance
    if not user_stance:
        try:
            if statement_text.strip():
                user_stance, confidence = classify_opinion(statement_text, user_opinion)
            else:
                # If no statement provided, try to infer stance from user opinion text
                # Use a generic statement to help classification
                generic_statement = "Dit onderwerp is belangrijk"
                user_stance, confidence = classify_opinion(
                    generic_statement, user_opinion
                )
        except Exception as e:
            print(f"Warning: Could not classify opinion, defaulting to neutral: {e}")
            user_stance = "neutral"

    # Load dimension models (only needed for user opinion scoring)
    try:
        tokenizers, models, device = _load_dimension_models(model_dir)
        if not models or not tokenizers:
            print("Warning: No models loaded, using simplified scoring")
            # Fallback to simple stance-based scoring without dimensions
            scores = {}
            for item in party_items:
                if hasattr(item, "party"):
                    party_id = str(item.party.id)
                    party_stance = item.stance
                else:
                    party_id, party_stance, party_explanation = item

                base_score = _calculate_base_match_score(user_stance, party_stance)
                scores[party_id] = float(round(base_score, 1))
            return scores
    except Exception as e:
        print(f"Error loading models: {e}")
        # Fallback to simple scoring
        scores = {}
        for item in party_items:
            if hasattr(item, "party"):
                party_id = str(item.party.id)
                party_stance = item.stance
            else:
                party_id, party_stance, party_explanation = item

            base_score = _calculate_base_match_score(user_stance, party_stance)
            scores[party_id] = float(round(base_score, 1))
        return scores

    scores = {}

    # Handle both StatementPosition objects and tuples
    for item in party_items:
        if hasattr(item, "party"):
            # StatementPosition object
            party_id = str(item.party.id)
            party_stance = item.stance
            party_explanation = item.explanation
            party_dimensions = item.dimensions
        else:
            # Tuple format (party_id, stance, explanation) - for backward compatibility
            party_id, party_stance, party_explanation = item
            party_dimensions = None

        # Calculate base match score
        base_score = _calculate_base_match_score(user_stance, party_stance)

        # Calculate dimension modifier with error handling
        dimension_modifier = 0.0  # Default to no modifier
        try:
            if party_dimensions:
                # Use stored dimensions (preferred method)
                dimension_modifier = _calculate_dimension_modifier(
                    user_opinion, party_dimensions, tokenizers, models, device
                )
            else:
                # Calculate dimensions from explanation text and save to database
                party_vec = _score_dimensions(
                    party_explanation, tokenizers, models, device
                )

                # If we have a StatementPosition object, create and save dimensions
                if hasattr(item, "party") and hasattr(item, "save"):
                    party_dimensions = _create_and_save_dimensions(item, party_vec)

                # If dimensions were created, calculate modifier
                dimension_modifier = _calculate_dimension_modifier_from_vectors(
                    user_opinion, party_vec, tokenizers, models, device
                )
        except Exception as e:
            print(f"Warning: Error calculating dimensions for party {party_id}: {e}")
            # Continue with base score only
            dimension_modifier = 0.0

        # Calculate final score
        final_score = base_score + dimension_modifier

        # Ensure score is within bounds [0, 100]
        final_score = max(0.0, min(100.0, final_score))

        # Convert to Python float to ensure JSON serialization compatibility
        scores[party_id] = float(round(final_score, 1))

    return scores
