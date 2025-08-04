# Opinion Classification System

## Overview

PolitiekMatcher uses a sophisticated AI-based opinion classification system to automatically analyze user responses to political statements. This system determines whether a user agrees, disagrees, or is neutral about political statements based on their free-text responses.

## How It Works

### 1. User Input Processing

When a user provides a text response to a political statement, the system:

1. **Receives the input**: User's free-text opinion and the original political statement
2. **Preprocesses the text**: Cleans and normalizes the input text
3. **Applies classification**: Uses both rule-based and AI-based methods

### 2. Classification Methods

#### Rule-Based Fallback

Before using AI models, the system applies rule-based classification for clear Dutch expressions:

**Strong Disagreement Patterns:**
- "ik ben het niet eens" / "niet eens"
- "oneens" / "on eens"
- "helemaal niet" / "absoluut niet"
- "nee, dit/dat"
- "tegen deze stelling"

**Strong Agreement Patterns:**
- "ik ben het eens" / "helemaal eens"
- "dat klopt" / "dat is waar"
- "ja, dat" / "volledig akkoord"
- "daar ben ik het mee eens"

**Neutral Patterns:**
- "dat hangt ervan af"
- "ik weet het niet"
- "misschien" / "deels"

#### AI-Based Classification

If rule-based patterns don't match, the system uses a fine-tuned transformer model:

**Model Details:**
- **Base Model**: DistilBERT (Dutch-optimized)
- **Architecture**: Sequence classification with 3 labels
- **Training Data**: `example_opinions.jsonl` with 3,461 labeled examples
- **Labels**: `agree`, `neutral`, `disagree`
- **Location**: `models/opinion_classifier/`

### 3. Training Data Generation

The training data is generated using a sophisticated process:

1. **Source Statements**: Real political statements from party programs
2. **Orientation Variants**: Generated opinions for different political orientations:
   - Links (left-wing)
   - Rechts (right-wing)
   - Conservatief (conservative)
   - Progressief (progressive)

3. **AI Generation**: Uses GPT-4.1-mini to generate realistic user opinions:
   ```python
   prompt = f"Genereer een {orientation} mening over: {statement}"
   ```

4. **Quality Control**: Each generated opinion is validated and labeled with the appropriate stance

### 4. Classification Process

```python
def classify_opinion(statement: str, reaction: str) -> Tuple[str, float]:
    """
    Classify user opinion as agree/neutral/disagree
    
    Returns:
        - label: 'agree', 'neutral', or 'disagree'
        - confidence: probability score (0.0 - 1.0)
    """
```

**Steps:**
1. **Input Validation**: Check for empty or invalid input
2. **Rule-Based Check**: Apply pattern matching for obvious cases
3. **AI Classification**: Use fine-tuned model if patterns don't match
4. **Confidence Scoring**: Return probability score for the prediction
5. **Fallback**: Default to 'neutral' with low confidence if classification fails

### 5. Data Storage

Classification results are stored in the `UserResponse` model:

```python
class UserResponse(models.Model):
    # User's original opinion
    user_opinion = models.TextField()
    
    # Classification results
    label = models.CharField(max_length=20)  # agree/neutral/disagree
    confidence_score = models.FloatField()   # 0.0 - 1.0
    classified_label = models.CharField()    # Original AI classification
    label_set_by = models.CharField()        # 'AI' or 'user'
```

### 6. User Override Capability

Users can manually correct AI classifications:

- **Review Interface**: Users can see and modify their classified responses
- **Audit Trail**: System tracks who set each label (AI vs user)
- **Learning Data**: User corrections can be used to improve the model

## Quality Assurance

### Model Training

**Training Configuration:**
- **Epochs**: 100 (with early stopping)
- **Learning Rate**: 2e-5
- **Batch Size**: 16
- **Validation Split**: 20%
- **Class Balancing**: Weighted loss function to handle imbalanced data

**Evaluation Metrics:**
- **Accuracy**: Overall classification accuracy
- **F1-Score**: Per-class F1 scores
- **Confusion Matrix**: Detailed error analysis

### Continuous Improvement

1. **Error Analysis**: Regular review of misclassified examples
2. **User Feedback**: Integration of user corrections
3. **Model Updates**: Periodic retraining with new data
4. **A/B Testing**: Comparison of different model versions

## Transparency Features

### User Information

Users can see:
- **Classification Confidence**: How certain the AI is about their classification
- **Manual Override**: Ability to correct misclassifications
- **Explanation**: Why their response was classified in a certain way

### Debugging Tools

For developers and researchers:
- **Interactive Testing**: Command-line tool to test classifications
- **Performance Metrics**: Detailed accuracy and confidence statistics
- **Training Logs**: Complete training history and model versions

## Use Cases

### Primary Classification
- **Political Matching**: Determine agreement levels for party-user matching
- **Opinion Analysis**: Understand user political preferences
- **Response Validation**: Ensure consistent interpretation of user input

### Secondary Applications
- **Content Moderation**: Filter inappropriate or off-topic responses
- **Engagement Analysis**: Understand how users interact with different topics
- **Research Data**: Aggregate opinion trends across user base

## Technical Implementation

### Model Architecture

```python
# Fine-tuned transformer with custom loss function
class CustomLossTrainer(Trainer):
    def compute_loss(self, model, inputs, return_outputs=False):
        # Weighted loss to handle class imbalance
        loss_fct = torch.nn.CrossEntropyLoss(
            weight=self.label_weights.to(logits.device)
        )
```

### Asynchronous Processing

Classification happens asynchronously to ensure responsive user experience:

```python
@shared_task(bind=True, max_retries=3)
def classify_user_response_async(self, response_id: int):
    """Asynchronously classify user response"""
```

### Caching and Performance

- **Model Caching**: Models are loaded once and cached in memory
- **Batch Processing**: Multiple responses can be classified together
- **Fallback Handling**: Graceful degradation when models are unavailable

## Privacy and Ethics

### Data Protection
- **Anonymous Processing**: No personal data in classification models
- **Minimal Storage**: Only necessary data is retained
- **User Control**: Users can request deletion of their responses

### Bias Mitigation
- **Diverse Training Data**: Balanced representation across political spectrum
- **Regular Auditing**: Monitoring for systematic biases
- **Transparent Limitations**: Clear communication about system capabilities and limitations

This classification system ensures that user political opinions are accurately and fairly categorized while maintaining transparency about how the AI makes these determinations.
