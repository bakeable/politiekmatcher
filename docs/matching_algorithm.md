# Matching Algorithm Documentation

## Overview

PolitiekMatcher uses a sophisticated multi-layered algorithm to match users with political parties based on their opinions. This document provides complete transparency about how these matches are calculated, ensuring users understand the methodology behind their political compatibility scores.

## Algorithm Architecture

### Core Matching Components

The matching system consists of four main components:

1. **Opinion Classification**: Determining user stance (agree/neutral/disagree)
2. **Base Match Scoring**: Calculating fundamental compatibility
3. **Political Dimension Modifiers**: Adding nuanced political positioning
4. **Weighted Scoring**: Incorporating user confidence and importance ratings

```python
def rank_parties(
    user_opinion: str,
    party_items: List[StatementPosition],
    statement_text: str = "",
    model_dir: str = "models"
) -> Dict[str, float]:
    """
    Rank parties using improved matching algorithm:
    1. Classify user opinion stance (agree/neutral/disagree)
    2. Calculate base match score based on stance alignment  
    3. Add political dimension modifier (-20 to +20)
    4. Ensure final score is in range [0, 100]
    """
```

## Step 1: Opinion Classification

### Input Processing
```python
# User provides free-text opinion on political statement
user_opinion = "Ik denk dat we meer moeten investeren in duurzame energie..."
statement_text = "De regering moet meer investeren in hernieuwbare energie."
```

### Classification Methods

**Rule-Based Classification:**
```python
def _apply_rule_based_fallback(reaction: str) -> str | None:
    """Apply rule-based classification for clear Dutch expressions"""
    # Strong disagreement patterns
    disagree_patterns = [
        r"\b(ik\s+ben\s+het\s+niet\s+eens|niet\s+eens)\b",
        r"\b(oneens|on\s*eens)\b",
        # ... more patterns
    ]
```

**AI Classification:**
When rule-based patterns don't match, use fine-tuned transformer model:
```python
user_stance, confidence = classify_opinion(statement_text, user_opinion)
# Returns: ("agree", 0.85) or ("disagree", 0.92) or ("neutral", 0.45)
```

## Step 2: Base Match Scoring

### Stance Alignment Matrix

The base score depends on how user and party stances align:

```python
def _calculate_base_match_score(user_stance: str, party_stance: str) -> float:
    """Calculate base match score (0-100) based on stance alignment"""
    
    # Perfect alignment scores
    if user_stance == party_stance:
        return 100.0
    
    # Partial alignment with neutral positions
    if user_stance == "neutral" or party_stance == "neutral":
        return 60.0
    
    # Complete disagreement
    if (user_stance == "agree" and party_stance == "disagree") or \
       (user_stance == "disagree" and party_stance == "agree"):
        return 20.0
    
    # Default case
    return 50.0
```

### Alignment Scoring Table

| User Stance | Party Stance | Base Score | Reasoning |
|-------------|--------------|------------|-----------|
| Agree | Agree | 100 | Perfect alignment |
| Disagree | Disagree | 100 | Perfect alignment |
| Neutral | Any | 60 | Partial compatibility |
| Any | Neutral | 60 | Partial compatibility |
| Agree | Disagree | 20 | Direct opposition |
| Disagree | Agree | 20 | Direct opposition |

## Step 3: Political Dimension Modifiers

### Multi-Dimensional Analysis

Beyond simple agreement/disagreement, the system analyzes political dimensions:

```python
# Seven political dimensions (each scaled -1 to +1)
DIM_FIELDS = [
    "economic",        # left (-1) to right (+1)
    "social",          # progressive (-1) to conservative (+1)  
    "environmental",   # green (-1) to brown (+1)
    "immigration",     # open (-1) to closed (+1)
    "europe",          # pro-EU (-1) to anti-EU (+1)
    "authority",       # libertarian (-1) to authoritarian (+1)
    "institutionality" # institutional (-1) to populist (+1)
]
```

### Dimension Scoring Process

**User Opinion Scoring:**
```python
def score_political_dimensions(text: str) -> List[float]:
    """Score user opinion across all political dimensions using fine-tuned models"""
    scores = []
    for dim in DIM_FIELDS:
        # Use specialized model for each dimension
        tokenizer = load_tokenizer(f"models/political_dimensions_{dim}")
        model = load_model(f"models/political_dimensions_{dim}")
        score = predict_dimension_score(text, tokenizer, model)
        scores.append(score)
    return scores
```

**Party Position Scoring:**
```python
def extract_dimensions_vector(dimensions: PoliticalDimensions) -> List[float]:
    """Extract dimension scores from party's stored political dimensions"""
    return [
        dimensions.economic,
        dimensions.social, 
        dimensions.environmental,
        dimensions.immigration,
        dimensions.europe,
        dimensions.authority,
        dimensions.institutionality,
    ]
```

### Dimension Similarity Calculation

```python
def calculate_dimension_modifier(user_vec: List[float], party_vec: List[float]) -> float:
    """
    Calculate political dimension modifier score (-20 to +20)
    Uses cosine similarity between user and party dimension vectors
    """
    # Calculate cosine similarity
    dot_product = sum(u * p for u, p in zip(user_vec, party_vec))
    user_norm = math.sqrt(sum(u * u for u in user_vec))
    party_norm = math.sqrt(sum(p * p for p in party_vec))
    
    if user_norm == 0 or party_norm == 0:
        return 0.0
    
    similarity = dot_product / (user_norm * party_norm)
    
    # Convert similarity (-1 to +1) to modifier score (-20 to +20)
    return float(similarity * 20)
```

### Dimension Impact Examples

**High Dimensional Alignment:**
- User: [Economic: -0.8, Social: -0.6, Environmental: -0.9, ...]
- Party: [Economic: -0.7, Social: -0.5, Environmental: -0.8, ...]
- Similarity: 0.95 → Modifier: +19 points

**Dimensional Mismatch:**
- User: [Economic: -0.8, Social: -0.6, Environmental: -0.9, ...]  
- Party: [Economic: +0.7, Social: +0.5, Environmental: +0.8, ...]
- Similarity: -0.95 → Modifier: -19 points

## Step 4: Final Score Calculation

### Score Combination

```python
def calculate_final_score(base_score: float, dimension_modifier: float) -> float:
    """Combine base score with dimension modifier, ensuring result stays in [0, 100]"""
    final_score = base_score + dimension_modifier
    return max(0.0, min(100.0, final_score))
```

### Score Examples

**Example 1: Strong Agreement with Dimensional Alignment**
- Base Score: 100 (perfect stance agreement)
- Dimension Modifier: +15 (high dimensional similarity)
- Final Score: 100 (capped at maximum)

**Example 2: Agreement with Dimensional Mismatch**
- Base Score: 100 (perfect stance agreement)
- Dimension Modifier: -15 (dimensional differences)
- Final Score: 85

**Example 3: Neutral Stance with Good Dimensional Fit**
- Base Score: 60 (neutral compatibility)
- Dimension Modifier: +18 (strong dimensional alignment)
- Final Score: 78

**Example 4: Disagreement with Some Dimensional Overlap**
- Base Score: 20 (stance opposition)
- Dimension Modifier: +10 (partial dimensional alignment)
- Final Score: 30

## Advanced Scoring Features

### Confidence-Weighted Scoring

```python
class PartyStatementMatch(models.Model):
    match_score = models.FloatField()           # Base algorithm score
    confidence_weighted_score = models.FloatField()  # Adjusted for user confidence
    
    def calculate_confidence_weighted_score(self):
        """Adjust match score based on user confidence in their opinion"""
        confidence_factor = self.user_response.confidence / 5.0  # Scale 1-5 to 0.2-1.0
        return self.match_score * confidence_factor
```

### Importance-Weighted Scoring

```python
def calculate_importance_weighted_score(self):
    """Weight match score by topic importance to user"""
    importance_factor = self.user_response.importance / 5.0  # Scale 1-5 to 0.2-1.0
    return self.match_score * importance_factor
```

### Overall Party Match Calculation

```python
class PartyMatch(models.Model):
    def calculate_overall_scores(self):
        """Calculate comprehensive party match scores"""
        statement_matches = self.statement_matches.all()
        
        # Basic average
        self.match_percentage = sum(sm.match_score for sm in statement_matches) / len(statement_matches)
        
        # Confidence-weighted average
        confidence_scores = [sm.confidence_weighted_score for sm in statement_matches]
        self.confidence_weighted_score = sum(confidence_scores) / len(confidence_scores)
        
        # Importance-weighted average  
        importance_scores = [sm.importance_weighted_score for sm in statement_matches]
        self.importance_weighted_score = sum(importance_scores) / len(importance_scores)
```

## Transparency and Validation

### Score Breakdown for Users

Users can see detailed breakdowns of their matches:

```python
# Example match breakdown shown to users
{
    "party": "D66",
    "overall_match": 78.5,
    "statement_breakdown": [
        {
            "statement": "De regering moet meer investeren in hernieuwbare energie",
            "user_opinion": "Ik denk dat we meer moeten investeren in duurzame energie",
            "party_stance": "agree",
            "user_classified_stance": "agree", 
            "base_score": 100,
            "dimension_modifier": -15,
            "final_score": 85,
            "confidence": 4,
            "importance": 5
        }
    ],
    "dimensional_analysis": {
        "economic": {"user": -0.3, "party": -0.1, "similarity": 0.85},
        "environmental": {"user": -0.9, "party": -0.8, "similarity": 0.95}
    }
}
```

### Algorithm Validation

**Testing Methods:**
1. **Synthetic Data Testing**: Known input/output pairs for algorithm verification
2. **Expert Validation**: Political scientists review algorithm outputs
3. **User Feedback**: Integration of user corrections and feedback
4. **Cross-Validation**: Comparison with traditional political compass tools

**Quality Metrics:**
- **Consistency**: Same inputs produce same outputs
- **Sensitivity**: Appropriate responses to input variations  
- **Face Validity**: Results align with expert political knowledge
- **User Satisfaction**: Users find matches meaningful and accurate

### Limitations and Assumptions

**Algorithm Limitations:**
1. **Opinion Classification**: Dependent on quality of user text input
2. **Dimensional Modeling**: Limited to seven predefined dimensions
3. **Party Position Accuracy**: Based on available party materials
4. **Temporal Stability**: Party positions may change over time

**Key Assumptions:**
1. **Linear Scoring**: Political alignment can be measured numerically
2. **Dimensional Independence**: Political dimensions can be analyzed separately
3. **Text Reflects Beliefs**: User text accurately represents their political views
4. **Static Positions**: Party positions remain stable during analysis period

This comprehensive matching algorithm provides nuanced, multi-dimensional political compatibility assessment while maintaining full transparency about methodology and limitations.
