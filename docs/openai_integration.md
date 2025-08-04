# OpenAI GPT Integration Guide

## Overview

PolitiekMatcher leverages OpenAI's GPT models for three critical functions: comparing political opinions, explaining party matches to users, and providing contextual analysis of political statements. This document explains how each system works and ensures transparency in AI decision-making.

## 1. Opinion Comparison System

### Purpose
Help users understand how their political opinions relate to different party positions on specific issues.

### How It Works

#### Input Processing
```python
def compare_political_opinions(statement_data, user_opinion, party_statements):
    """
    Compare political party opinions using OpenAI API with caching
    """
```

**Required Data:**
- **Statement**: Original political statement with context
- **User Opinion**: User's free-text response to the statement
- **Party Statements**: Each party's official position and explanation

#### Caching Strategy
Before making API calls, the system checks for cached results:

```python
cached_comparison, created = OpinionComparison.get_or_create_comparison(
    statement_id=statement_id, 
    user_opinion=user_opinion, 
    party_ids=party_ids
)
```

**Cache Key Components:**
- Statement ID
- User opinion text (exact match)
- List of party IDs involved in comparison
- Timestamp (for cache invalidation)

#### Prompt Engineering

The system builds structured prompts for consistent, objective analysis:

```markdown
**POLITIEKE MENINGSVERGELIJKING**

**Stelling:** "{statement_text}"
**Context:** {theme} - {topic}
**Stellinguitleg:** {explanation}

**Gebruikersmening:** "{user_opinion}"

**Partijstandpunten:**
1. **{Party Name} ({Abbreviation})**
   - Standpunt: {stance_translation}
   - Uitleg: {explanation}
```

#### Analysis Structure

The AI is instructed to provide:

1. **📊 Partijstandpunten Samenvatting**: Objective summary of each party's position
2. **🔍 Belangrijkste Verschillen**: Core differences between party positions
3. **⚖️ Jouw Mening**: Analysis of how user opinion relates to each party
4. **🎯 Conclusie**: Objective assessment of best matches

#### AI Configuration

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
            "role": "system",
            "content": "Je bent een objectieve politieke analist die partijstandpunten vergelijkt. Geef altijd een neutrale, informatieve analyse in het Nederlands."
        },
        {"role": "user", "content": prompt}
    ],
    max_tokens=1500,
    temperature=0.3  # Lower temperature for consistent, factual responses
)
```

## 2. Party Match Explanation System

### Purpose
Provide users with detailed, personalized explanations of why they match with specific political parties.

### Service Architecture

```python
class PartyExplanationService:
    """Service for generating AI-powered explanations of party matches with caching"""
```

#### Data Aggregation

Before generating explanations, the system gathers:

**Overall Match Data:**
```python
party_match = PartyMatch.objects.get(profile=profile, party=party)
# Contains: match_percentage, confidence_weighted_score, importance_weighted_score
```

**Individual Statement Matches:**
```python
statement_matches = PartyStatementMatch.objects.filter(
    profile=profile, party=party
).select_related("statement__theme__topic", "user_response")
```

#### Topic Organization

Statements are grouped by topic and ranked by match quality:

```python
# Organize statements by topic for better structure
topic_groups = defaultdict(list)
for stmt_match in statement_matches:
    topic = stmt_match.statement.theme.topic
    topic_groups[topic.name].append(stmt_match)

# Sort topics by average match score (highest first)
sorted_topics = sorted(topic_groups.items(), 
    key=lambda x: (sum(m.match_score for m in x[1]) / len(x[1])), 
    reverse=True
)
```

#### Prompt Construction

The AI receives structured data about the user's political profile:

```markdown
**MATCH UITLEG VOOR {party_name}**

Je hebt {match_percentage}% overeenkomst met {party_name}.

**BELANGRIJKSTE OVEREENKOMSTEN:**

{topic_name}: {average_score}%
- Stelling: "{statement_text}"
- Jouw mening: "{user_opinion}" 
- Partij standpunt: {party_stance} - "{party_explanation}"
- Match score: {match_score}%

**GROOTSTE VERSCHILLEN:**
[Similar structure for low-scoring topics]

**SCHRIJFINSTRUCTIES:**
- Gebruik markdown headers (##)
- Maximaal 600 woorden
- Schrijf neutraal en objectief
- Gebruik concrete voorbeelden
- Richt je op de kiezer (tweede persoon: "jij")
- Vermijd jargon en opsommingen
```

#### AI Configuration for Explanations

```python
response = client.chat.completions.create(
    model="gpt-4o-mini",  # More cost-effective for explanations
    messages=[
        {
            "role": "system",
            "content": "Je bent een neutrale politieke analist die heldere, gestructureerde uitleg geeft over partij-matches."
        },
        {"role": "user", "content": prompt}
    ],
    max_tokens=1200,
    temperature=0.2  # Very low temperature for consistent explanations
)
```

#### Caching and Performance

```python
# Check if explanation is already cached
if party_match.explanation:
    return party_match.explanation

# Generate new explanation and cache it
explanation = PartyExplanationService._generate_ai_explanation(...)
party_match.explanation = explanation
party_match.save(update_fields=["explanation"])
```

## 3. Statement Context System

### Purpose
Provide users with additional context about political statements, including background information and implications.

### Context Sources

**Statement Metadata:**
- Original source (party program, statement)
- Theme and topic classification
- Related statements from other parties
- Historical context when available

**Dynamic Context Generation:**
The system can generate contextual explanations using GPT for complex statements:

```python
def generate_statement_context(statement, user_profile=None):
    """Generate contextual information about a political statement"""
```

## 4. Quality Assurance and Transparency

### Response Validation

**Content Filtering:**
- Check for inappropriate content
- Ensure factual accuracy where possible
- Validate response structure and format

**Consistency Checks:**
- Compare similar requests for consistent responses
- Monitor for bias or unfair characterizations
- Ensure neutral tone is maintained

### Error Handling and Fallbacks

```python
try:
    # AI-generated explanation
    explanation = generate_ai_explanation(...)
except Exception as e:
    # Fallback to template-based explanation
    explanation = generate_fallback_explanation(party_match)
    logger.error(f"AI explanation failed: {e}")
```

**Fallback Strategies:**
1. **Template-based explanations**: Pre-written explanations using match data
2. **Simplified summaries**: Basic statistical overview of matches
3. **Error messages**: Transparent communication when systems fail

### Cost Management

**API Usage Optimization:**
- Caching to prevent duplicate API calls
- Efficient prompt design to minimize token usage
- Batch processing where possible

**Usage Tracking:**
```python
# Track premium feature usage for cost control
PremiumService.track_feature_usage(
    profile, "opinion_comparison", Decimal("0.005")
)
```

## 5. Ethical Guidelines and Limitations

### Objectivity Measures

**Neutral Language Requirements:**
- No political preferences or recommendations
- Balanced presentation of all party positions
- Factual rather than persuasive language

**Bias Prevention:**
- Regular prompt auditing for neutral language
- Diverse test cases across political spectrum
- User feedback integration for bias detection

### User Transparency

**Clear AI Disclosure:**
All AI-generated content includes disclaimers:
```markdown
*Deze uitleg is automatisch gegenereerd op basis van uw antwoorden en de verkiezingsprogramma's. 
Voor de meest actuele standpunten raadpleegt u de partijwebsites.*
```

**Explanation Limitations:**
- AI explanations are based on available data only
- Updates to party positions may not be immediately reflected
- Personal political decisions should consider additional factors

### Data Privacy

**Anonymization:**
- User data is anonymized before AI processing
- No personal identifiers in prompts or responses
- Cached responses use hashed identifiers

**Data Retention:**
- Generated explanations are cached for performance
- Users can request deletion of their AI-generated content
- Regular cleanup of outdated cached responses

## 6. Monitoring and Improvement

### Quality Metrics

**Response Quality:**
- User satisfaction ratings
- Manual review of generated content
- Comparison with expert political analysis

**Performance Tracking:**
- API response times and success rates
- Cache hit rates and efficiency
- Cost per interaction and user engagement

### Continuous Improvement

**Prompt Optimization:**
- A/B testing of different prompt structures
- Regular updates based on user feedback
- Integration of domain expert recommendations

**Model Updates:**
- Monitoring OpenAI model improvements
- Testing new models and configurations
- Gradual rollout of optimizations

This comprehensive integration of OpenAI's GPT models ensures that users receive high-quality, objective, and helpful political analysis while maintaining transparency about how AI-generated insights are created.
