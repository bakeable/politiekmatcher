# Data Sources and Content Processing

## Overview

PolitiekMatcher processes diverse political content to provide comprehensive analysis and matching. This document explains how we collect, process, and validate political data while maintaining transparency about our sources and methodologies.

## Content Sources

### 1. Election Programs (Verkiezingsprogramma's)

**Source Type**: Official party election programs in PDF format

**Processing Pipeline:**
```python
# Located in: backend/scraped_content/
files = [
    "d66_program_2023.pdf",
    "vvd_program_2023.pdf", 
    "gl-pvda_program_2023.pdf",
    # ... all major Dutch political parties
]
```

**Extraction Process:**
1. **PDF Parsing**: Using `pdfplumber` for accurate text extraction
2. **Content Segmentation**: Breaking programs into meaningful fragments
3. **Metadata Enrichment**: Adding page numbers, sections, and context
4. **Quality Validation**: Manual review of extracted content

**Data Structure:**
```python
class ProgramFragment(models.Model):
    content = models.TextField()           # Extracted text content
    raw_content = models.TextField()       # Original unprocessed text
    fragment_type = models.CharField()     # Type of content (policy, intro, etc.)
    source_page_start = models.IntegerField()  # PDF page reference
    source_page_end = models.IntegerField()
    word_count = models.IntegerField()
    char_count = models.IntegerField()
    relevance_score = models.FloatField()  # Quality/relevance rating
```

### 2. Political Statements Database

**Purpose**: Structured statements on key political issues for user engagement

**Statement Categories:**
- Economic policy (belastingen, economie, werk)
- Social issues (onderwijs, zorg, sociale zekerheid)
- Environmental policy (klimaat, energie, natuur)
- Immigration and integration (migratie, integratie)
- European Union (EU, europa, buitenland)
- Authority and governance (bestuur, veiligheid, rechtsstaat)

**Statement Structure:**
```python
class Statement(models.Model):
    text = models.TextField()              # The political statement
    explanation = models.TextField()       # Context and background
    source = models.CharField()            # Where statement originates
    theme = models.ForeignKey(Theme)       # Broad category
    slug = models.SlugField()              # URL-friendly identifier
    embedding = models.JSONField()         # Vector embedding for similarity
```

### 3. Party Position Data

**Collection Method**: Systematic analysis of party responses to political statements

**Position Recording:**
```python
class StatementPosition(models.Model):
    statement = models.ForeignKey(Statement)
    party = models.ForeignKey(PoliticalParty)
    stance = models.CharField(choices=[
        ('strongly_agree', 'Strongly Agree'),
        ('agree', 'Agree'),
        ('neutral', 'Neutral'),
        ('disagree', 'Disagree'),
        ('strongly_disagree', 'Strongly Disagree'),
    ])
    explanation = models.TextField()       # Party's reasoning
    source = models.CharField()            # Reference to source material
    dimensions = models.OneToOneField(PoliticalDimensions)  # Multi-dimensional analysis
```

**Quality Assurance:**
- Cross-reference with official party materials
- Regular updates when party positions change
- Expert validation of contentious positions
- Source attribution for all claims

## Content Processing Pipeline

### 1. Document Ingestion

**PDF Processing:**
```python
def extract_pdf_content(pdf_path: str) -> List[ProgramFragment]:
    """Extract structured content from party program PDFs"""
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            text = page.extract_text()
            # Process and structure content
            fragments = segment_content(text, page_num)
```

**Text Segmentation:**
- **Paragraph-level**: Maintain semantic coherence
- **Section-aware**: Respect document structure
- **Context preservation**: Include surrounding context for clarity
- **Length optimization**: Balance detail with usability

### 2. Content Classification

**Automatic Categorization:**
```python
def classify_content_type(fragment: str) -> str:
    """Classify program fragment by content type"""
    # Policy statements, introductions, promises, etc.
```

**Topic Assignment:**
- Economic, social, environmental, etc.
- Machine learning-based classification
- Expert validation for accuracy
- Hierarchical topic structure

### 3. Quality Scoring

**Relevance Assessment:**
```python
class ContentQualityScorer:
    def score_fragment(self, fragment: ProgramFragment) -> float:
        """Score content relevance and quality (0.0 - 1.0)"""
        # Factors: length, specificity, political relevance, clarity
```

**Quality Factors:**
- **Political Relevance**: How directly the content relates to political positions
- **Specificity**: Concrete policy proposals vs. vague statements
- **Clarity**: Understandable language and clear meaning
- **Completeness**: Sufficient context for understanding

## Data Validation and Quality Control

### 1. Automated Validation

**Content Integrity Checks:**
```python
def validate_content_integrity():
    """Automated validation of processed content"""
    # Check for: truncated text, encoding issues, missing metadata
```

**Consistency Verification:**
- Ensure all fragments have required metadata
- Validate document structure preservation
- Check for processing artifacts or errors

### 2. Expert Review Process

**Manual Validation:**
- Political science experts review sensitive content
- Fact-checking of party position claims
- Validation of dimensional scoring accuracy
- Review of AI-generated classifications

**Review Workflow:**
1. **Initial Processing**: Automated extraction and classification
2. **Expert Review**: Domain experts validate accuracy
3. **Quality Rating**: Content receives quality scores
4. **Publication**: Approved content becomes available to users

### 3. Source Attribution

**Transparency Requirements:**
```python
class SourceMetadata(models.Model):
    original_document = models.CharField()    # Source document name
    document_url = models.URLField()          # Official source URL
    extraction_date = models.DateTimeField()  # When content was processed
    last_verified = models.DateTimeField()    # Last validation check
    processing_version = models.CharField()   # Processing pipeline version
```

**Citation Standards:**
- Every fragment linked to original source
- Page numbers and section references maintained
- Processing timestamps for accountability
- Version control for content updates

## Content Update and Maintenance

### 1. Regular Updates

**Update Schedule:**
- **Monthly**: Check for new party publications
- **Quarterly**: Comprehensive review of existing content
- **Election Cycles**: Major update and validation campaigns
- **Ad-hoc**: Immediate updates for significant political developments

**Change Detection:**
```python
def detect_position_changes():
    """Monitor for changes in party positions"""
    # Compare current positions with historical data
    # Flag significant changes for expert review
```

### 2. Version Control

**Content Versioning:**
- Track all changes to party positions
- Maintain historical record of political evolution
- Enable temporal analysis of political trends
- Support research into political consistency

**Data Lineage:**
```python
class ContentVersion(models.Model):
    content_object = models.ForeignKey()     # The content being versioned
    version_number = models.IntegerField()
    changes_summary = models.TextField()     # What changed
    change_reason = models.CharField()       # Why it changed
    validated_by = models.CharField()        # Who approved the change
    created_at = models.DateTimeField()
```

## Research and Analytics Support

### 1. Academic Collaboration

**Research Features:**
- Structured data export for academic research
- Historical trend analysis capabilities
- Anonymized user interaction data (with consent)
- Political science methodology validation

**Data Access:**
- API endpoints for researchers
- Bulk data export with proper attribution
- Documentation for research applications
- Ethics review for research proposals

### 2. Political Trend Analysis

**Trend Detection:**
```python
def analyze_political_trends():
    """Identify shifts in political landscape"""
    # Track party position changes over time
    # Identify emerging political themes
    # Measure public opinion alignment
```

**Analytics Capabilities:**
- Party position evolution over time
- Public opinion trend analysis
- Coalition compatibility assessment
- Political polarization measurement

## Privacy and Ethical Considerations

### 1. Data Protection

**User Privacy:**
- Anonymous content processing
- No personal identifiers in content analysis
- Secure data handling and storage
- Regular privacy audits

**Source Protection:**
- Respect for copyright and intellectual property
- Fair use principles for political content
- Proper attribution for all sources
- Transparent content usage policies

### 2. Political Neutrality

**Bias Prevention:**
- Balanced representation across political spectrum
- Objective content categorization
- Non-partisan language in descriptions
- Regular bias audits by external experts

**Editorial Standards:**
- No editorial commentary in source material
- Factual accuracy over opinion
- Transparent methodology documentation
- Regular review by political science experts

This comprehensive approach to data sources and content processing ensures that PolitiekMatcher provides accurate, up-to-date, and trustworthy political information while maintaining transparency about our methods and sources.
