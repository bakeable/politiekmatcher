# Political Dimensions Fine-Tuning System

## Overview

PolitiekMatcher employs a sophisticated fine-tuning approach to assess political dimensions in text. This system trains specialized transformer models to measure political positions across seven key dimensions, enabling nuanced understanding of political content beyond simple left-right classifications.

## Political Dimensions Framework

### The Seven Dimensions

Our system measures political content across these dimensions, each scaled from -1 to +1:

1. **Economic** (-1: left → +1: right)
   - Left: High government intervention, wealth redistribution, social programs
   - Right: Free market, low taxes, minimal government intervention

2. **Social** (-1: progressive → +1: conservative)
   - Progressive: Liberal social values, LGBTQ+ rights, modern family structures
   - Conservative: Traditional values, religious influence, family structures

3. **Environmental** (-1: green → +1: brown)
   - Green: Climate action, environmental protection, sustainability
   - Brown: Economic priorities over environment, climate skepticism

4. **Immigration** (-1: open → +1: closed)
   - Open: Welcoming immigration policies, multiculturalism, integration support
   - Closed: Strict immigration controls, border security, cultural assimilation

5. **Europe** (-1: pro-EU → +1: anti-EU)
   - Pro-EU: European integration, shared sovereignty, EU cooperation
   - Anti-EU: National sovereignty, EU skepticism, reduced integration

6. **Authority** (-1: libertarian → +1: authoritarian)
   - Libertarian: Individual freedom, limited government power, civil liberties
   - Authoritarian: Strong government control, law and order, security focus

7. **Institutionality** (-1: institutional → +1: anti-elite/populist)
   - Institutional: Trust in established institutions, expert knowledge, system stability
   - Populist: Anti-establishment, direct democracy, elite criticism

## Why Fine-Tuning for Political Dimensions?

### Limitations of General Models

**Generic Language Models:**
- Trained on broad internet data without political expertise
- May reflect biases from training data
- Lack nuanced understanding of Dutch political context
- Cannot reliably distinguish between different political dimensions

**Need for Specialized Models:**
- Political text requires domain-specific understanding
- Multiple dimensions need separate, focused training
- Dutch political context differs from international training data
- Consistent, objective scoring requires specialized training

### Benefits of Per-Dimension Models

**Specialized Focus:**
```python
# Separate model for each dimension
DIM_FIELDS = [
    "economic", "social", "environmental", "immigration", 
    "europe", "authority", "institutionality"
]

# Each model trained specifically for one dimension
for dim in DIM_FIELDS:
    model_path = f"models/political_dimensions_{dim}"
```

**Improved Accuracy:**
- Each model specializes in one political aspect
- Reduces interference between different political concepts
- Enables fine-grained control over each dimension
- Better calibration for specific political axes

## Training Data Generation

### Source Data Collection

**Content Sources:**
```python
# Training data comes from multiple sources
objs = (
    list(StatementPosition.objects.filter(dimensions__isnull=False)) +
    list(ProgramFragment.objects.filter(dimensions__isnull=False)) +
    list(ExampleOpinion.objects.filter(dimensions__isnull=False))
)
```

**Data Types:**
1. **StatementPosition**: Party responses to political statements
2. **ProgramFragment**: Excerpts from party election programs  
3. **ExampleOpinion**: Generated example opinions on statements

### Expert Annotation Process

**Human Labeling:**
- Political scientists and domain experts provide ground truth labels
- Each text fragment labeled on all relevant dimensions
- Confidence scores provided for each annotation
- Evidence quotes explaining the dimensional scores

**Training Data Format:**
```jsonl
{
  "messages": [
    {
      "role": "system", 
      "content": "Label the statement on political dimensions [-1,1]..."
    },
    {
      "role": "user", 
      "content": "Stelling: ... Reactie: ..."
    },
    {
      "role": "assistant", 
      "content": "{\"economic\": 0.5, \"social\": -0.5, \"environmental\": -1, ...}"
    }
  ]
}
```

### Data Quality Assurance

**Validation Steps:**
1. **Inter-annotator Agreement**: Multiple experts label same content
2. **Consistency Checks**: Regular review of annotation patterns
3. **Bias Detection**: Monitor for systematic labeling biases
4. **Expert Review**: Political scientists validate controversial cases

## Model Architecture and Training

### Base Model Selection

**Transformer Architecture:**
- **Base Model**: DistilBERT or similar efficient transformer
- **Language**: Dutch-optimized models when available
- **Size**: Balanced between performance and computational efficiency

**Per-Dimension Customization:**
```python
# Each dimension gets its own model
for dim in DIM_FIELDS:
    model = AutoModelForSequenceClassification.from_pretrained(
        base_model_name,
        num_labels=regression_targets  # Continuous values [-1, 1]
    )
```

### Training Configuration

**Hyperparameters:**
```python
training_args = TrainingArguments(
    output_dir=f"models/political_dimensions_{dim}",
    num_train_epochs=100,
    per_device_train_batch_size=16,
    learning_rate=2e-5,
    warmup_steps=500,
    weight_decay=0.01,
    evaluation_strategy="epoch",
    save_total_limit=3,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
)
```

**Loss Function:**
- **Regression Loss**: Mean Squared Error for continuous dimension values
- **Regularization**: Weight decay to prevent overfitting
- **Early Stopping**: Prevent overtraining on small datasets

### Training Process

**Data Preparation:**
```python
# Convert text to training format
for obj in training_objects:
    if isinstance(obj, StatementPosition):
        text = f"Stelling: {obj.statement.text}\nReactie: {obj.explanation}"
    elif isinstance(obj, ProgramFragment):
        text = obj.content
    # Extract dimension values as targets
    dims = obj.dimensions
    y = [getattr(dims, field) for field in DIM_FIELDS]
```

**Cross-Validation:**
- **Train/Validation Split**: 80/20 split for model evaluation
- **Stratified Sampling**: Ensure balanced representation across dimensions
- **Temporal Validation**: Test on newer data than training data

## Model Application and Inference

### Scoring Political Content

**Multi-Model Inference:**
```python
def score_political_dimensions(text: str, model_dir="models") -> Dict[str, float]:
    """Score text across all political dimensions"""
    results = {}
    for dim in DIM_FIELDS:
        tokenizer = AutoTokenizer.from_pretrained(f"{model_dir}/political_dimensions_{dim}")
        model = AutoModelForSequenceClassification.from_pretrained(f"{model_dir}/political_dimensions_{dim}")
        
        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        outputs = model(**inputs)
        score = outputs.logits.item()  # Regression output
        results[dim] = score
    
    return results
```

**Confidence Estimation:**
- **Model Uncertainty**: Measure prediction confidence
- **Ensemble Methods**: Compare multiple model predictions
- **Domain Detection**: Identify when text is outside training domain

### Integration with Matching System

**User Opinion Scoring:**
```python
# Score user opinion on political dimensions
user_dimensions = score_political_dimensions(user_opinion)

# Compare with party positions
for party_item in party_positions:
    party_dimensions = extract_dimensions_vector(party_item.dimensions)
    dimension_similarity = calculate_dimension_similarity(user_dimensions, party_dimensions)
```

**Match Score Calculation:**
```python
def calculate_dimension_modifier(user_vec: List[float], party_vec: List[float]) -> float:
    """Calculate political dimension modifier score (-20 to +20)"""
    # Cosine similarity between dimension vectors
    similarity = cosine_similarity([user_vec], [party_vec])[0][0]
    # Convert to modifier score
    return float(similarity * 20)  # Scale to ±20 points
```

## Quality Assurance and Validation

### Model Evaluation

**Performance Metrics:**
```python
# Evaluation metrics for each dimension
metrics = {
    "mae": mean_absolute_error,      # Average prediction error
    "mse": mean_squared_error,       # Squared error for outliers
    "r2": r2_score,                  # Explained variance
    "correlation": pearson_correlation  # Linear relationship
}
```

**Validation Strategies:**
1. **Cross-Validation**: K-fold validation across training data
2. **Hold-Out Testing**: Reserved test set for final evaluation
3. **Expert Validation**: Human experts review model predictions
4. **Real-World Testing**: Performance on actual user data

### Bias Detection and Mitigation

**Systematic Bias Checks:**
- **Political Spectrum Coverage**: Ensure balanced training across political views
- **Source Diversity**: Include content from all major political parties
- **Temporal Stability**: Test consistency across different time periods

**Mitigation Strategies:**
- **Balanced Sampling**: Equal representation of different political positions
- **Adversarial Training**: Train models to be robust to political biases
- **Regular Auditing**: Ongoing review of model predictions for systematic errors

## Use Cases and Applications

### Primary Applications

**1. User-Party Matching:**
- Score user opinions on political dimensions
- Compare with party dimension profiles
- Calculate compatibility scores beyond simple agreement/disagreement

**2. Content Analysis:**
- Classify political statements and program fragments
- Understand political positioning of parties and candidates
- Track political evolution over time

**3. Research and Analytics:**
- Generate insights about political landscape
- Identify political trends and shifts
- Support academic research on Dutch politics

### Advanced Features

**Dynamic Scoring:**
```python
# Real-time dimension scoring for new content
def analyze_new_content(text: str) -> PoliticalDimensions:
    """Analyze new political content and create dimensions object"""
    scores = score_political_dimensions(text)
    return PoliticalDimensions.objects.create(
        economic=scores["economic"],
        social=scores["social"],
        environmental=scores["environmental"],
        # ... other dimensions
        confidence=calculate_confidence(scores),
        evidence=extract_key_phrases(text)
    )
```

**Comparative Analysis:**
- Compare political evolution of parties over time
- Identify ideological shifts in political discourse
- Analyze coalition compatibility based on dimensions

## Technical Implementation

### Model Management

**Model Versioning:**
```python
# Version control for model updates
MODEL_VERSION = "v2.1"
MODEL_DIR = f"models/political_dimensions_{MODEL_VERSION}"
```

**Performance Optimization:**
- **Model Caching**: Keep models in memory for fast inference
- **Batch Processing**: Process multiple texts efficiently
- **GPU Acceleration**: Use CUDA when available for large-scale processing

### Continuous Improvement

**Model Updates:**
1. **Regular Retraining**: Update models with new training data
2. **Performance Monitoring**: Track model accuracy over time
3. **A/B Testing**: Compare different model versions
4. **Feedback Integration**: Incorporate user and expert feedback

**Data Pipeline:**
```python
# Automated training pipeline
def update_dimension_models():
    """Retrain all dimension models with latest data"""
    for dim in DIM_FIELDS:
        train_dimension_model(dim)
        validate_model_performance(dim)
        deploy_if_improved(dim)
```

This sophisticated fine-tuning system enables PolitiekMatcher to provide nuanced, accurate assessments of political content across multiple dimensions, supporting more meaningful political matching and analysis than simple left-right classifications.
