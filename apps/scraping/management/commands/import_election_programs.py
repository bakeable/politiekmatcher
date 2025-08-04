"""
Django management command to scrape and process election programs
"""

import requests
import time
from pathlib import Path
import hashlib

from django.core.management.base import BaseCommand
from django.conf import settings

# Third-party imports for content extraction
import pdfplumber
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from apps.content.models import PoliticalParty, ElectionProgram
from apps.scraping.selenium_utils import get_driver


class ContentExtractor:
    """Handles extraction of text content from various sources"""

    def __init__(self):
        self.storage_dir = Path(settings.BASE_DIR) / "scraped_content"
        self.storage_dir.mkdir(exist_ok=True)

    def extract_pdf_content(self, pdf_path: str) -> str:
        """Extract structured text content from PDF file with annotations"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                structured_content = []
                
                for page_num, page in enumerate(pdf.pages, 1):
                    structured_content.append(f"[PAGE {page_num}]")
                    
                    # Extract text with layout information
                    page_content = self._extract_structured_page_content(page, page_num)
                    if page_content:
                        structured_content.append(page_content)
                    
                    structured_content.append(f"[/PAGE {page_num}]")
                    structured_content.append("")  # Empty line between pages
                
                return "\n".join(structured_content)
        except Exception as e:
            raise Exception(f"Failed to extract PDF content: {e}")
    
    def _extract_structured_page_content(self, page, page_num: int) -> str:
        """Extract structured content from a single PDF page"""
        content_lines = []
        
        try:
            # Get all text elements with their bounding boxes
            chars = page.chars
            if not chars:
                return ""
            
            # Group characters into lines and analyze structure
            lines = self._group_chars_into_lines(chars)
            
            for line_info in lines:
                text = line_info['text'].strip()
                if not text:
                    continue
                
                # Classify the line type based on formatting
                line_type = self._classify_line_type(line_info, page)
                
                # Format the line with appropriate annotation
                formatted_line = self._format_line_with_annotation(text, line_type, line_info)
                content_lines.append(formatted_line)
            
            # Post-process to identify lists and group related content
            processed_lines = self._post_process_lines(content_lines)
            
            return "\n".join(processed_lines)
            
        except Exception as e:
            # Fallback to basic text extraction
            page_text = page.extract_text()
            return f"[TEXT]\n{page_text}\n[/TEXT]" if page_text else ""
    
    def _group_chars_into_lines(self, chars) -> list:
        """Group characters into lines with formatting information"""
        lines = []
        current_line = {
            'chars': [],
            'y_positions': [],
            'font_sizes': [],
            'fonts': [],
            'x_positions': []
        }
        
        # Sort characters by y-position (top to bottom), then x-position (left to right)
        sorted_chars = sorted(chars, key=lambda c: (-c['top'], c['x0']))
        
        current_y = None
        y_tolerance = 3  # Tolerance for considering characters on the same line
        
        for char in sorted_chars:
            char_y = char['top']
            
            # If this is a new line (significant y difference)
            if current_y is None or abs(char_y - current_y) > y_tolerance:
                # Save the previous line if it exists
                if current_line['chars']:
                    line_text = ''.join(c['text'] for c in current_line['chars'])
                    lines.append({
                        'text': line_text,
                        'y_pos': current_y,
                        'avg_font_size': sum(current_line['font_sizes']) / len(current_line['font_sizes']) if current_line['font_sizes'] else 12,
                        'dominant_font': max(set(current_line['fonts']), key=current_line['fonts'].count) if current_line['fonts'] else 'unknown',
                        'x_start': min(current_line['x_positions']) if current_line['x_positions'] else 0,
                        'x_end': max(current_line['x_positions']) if current_line['x_positions'] else 0
                    })
                
                # Start new line
                current_line = {
                    'chars': [char],
                    'y_positions': [char_y],
                    'font_sizes': [char.get('size', 12)],
                    'fonts': [char.get('fontname', 'unknown')],
                    'x_positions': [char['x0']]
                }
                current_y = char_y
            else:
                # Add to current line
                current_line['chars'].append(char)
                current_line['y_positions'].append(char_y)
                current_line['font_sizes'].append(char.get('size', 12))
                current_line['fonts'].append(char.get('fontname', 'unknown'))
                current_line['x_positions'].append(char['x0'])
        
        # Don't forget the last line
        if current_line['chars']:
            line_text = ''.join(c['text'] for c in current_line['chars'])
            lines.append({
                'text': line_text,
                'y_pos': current_y,
                'avg_font_size': sum(current_line['font_sizes']) / len(current_line['font_sizes']) if current_line['font_sizes'] else 12,
                'dominant_font': max(set(current_line['fonts']), key=current_line['fonts'].count) if current_line['fonts'] else 'unknown',
                'x_start': min(current_line['x_positions']) if current_line['x_positions'] else 0,
                'x_end': max(current_line['x_positions']) if current_line['x_positions'] else 0
            })
        
        return lines
    
    def _classify_line_type(self, line_info: dict, page) -> str:
        """Classify the type of line based on formatting and content"""
        text = line_info['text'].strip()
        font_size = line_info['avg_font_size']
        font_name = line_info['dominant_font'].lower()
        x_start = line_info['x_start']
        
        # Get page dimensions for relative positioning
        page_width = page.width
        page_height = page.height
        
        # Determine average font size for the page (for comparison)
        avg_page_font_size = 12  # Default assumption
        
        # Classification logic
        if not text:
            return "empty"
        
        # Check for page numbers (usually small, at edges)
        if (len(text) <= 3 and text.isdigit() and 
            (x_start < page_width * 0.1 or x_start > page_width * 0.9)):
            return "page_number"
        
        # Check for headers/footers (usually at top/bottom 10% of page)
        y_pos = line_info['y_pos']
        if y_pos < page_height * 0.1 or y_pos > page_height * 0.9:
            if len(text) < 100:  # Short text at top/bottom
                return "header_footer"
        
        # Check for titles (large font, often bold, usually centered or left-aligned)
        if font_size > avg_page_font_size * 1.3:
            if 'bold' in font_name or 'black' in font_name:
                return "title"
            else:
                return "subtitle"
        
        # Check for numbered/bulleted lists
        import re
        if re.match(r'^\s*[•·▪▫‣⁃*-]\s+', text):
            return "bullet_list"
        elif re.match(r'^\s*\d+[\.\)]\s+', text):
            return "numbered_list"
        elif re.match(r'^\s*[a-zA-Z][\.\)]\s+', text):
            return "lettered_list"
        
        # Check for chapter/section headings (all caps, or numbered sections)
        if (text.isupper() and len(text.split()) <= 8) or re.match(r'^\d+\.?\s+[A-Z]', text):
            return "section_heading"
        
        # Check for table of contents entries
        if '.' * 3 in text or '\t' in text:  # Dots or tabs suggesting TOC
            return "toc_entry"
        
        # Check for indented text (quotes, sub-points)
        if x_start > page_width * 0.15:  # Significantly indented
            return "indented_text"
        
        # Default to regular text
        return "text"
    
    def _format_line_with_annotation(self, text: str, line_type: str, line_info: dict) -> str:
        """Format a line with appropriate structural annotation"""
        if line_type == "title":
            return f"[TITLE]{text}[/TITLE]"
        elif line_type == "subtitle":
            return f"[SUBTITLE]{text}[/SUBTITLE]"
        elif line_type == "section_heading":
            return f"[HEADING]{text}[/HEADING]"
        elif line_type == "bullet_list":
            return f"[LIST_ITEM]{text}[/LIST_ITEM]"
        elif line_type == "numbered_list":
            return f"[NUMBERED_ITEM]{text}[/NUMBERED_ITEM]"
        elif line_type == "lettered_list":
            return f"[LETTERED_ITEM]{text}[/LETTERED_ITEM]"
        elif line_type == "toc_entry":
            return f"[TOC_ENTRY]{text}[/TOC_ENTRY]"
        elif line_type == "indented_text":
            return f"[QUOTE]{text}[/QUOTE]"
        elif line_type == "page_number":
            return f"[PAGE_NUM]{text}[/PAGE_NUM]"
        elif line_type == "header_footer":
            return f"[HEADER_FOOTER]{text}[/HEADER_FOOTER]"
        elif line_type == "empty":
            return ""
        else:  # "text"
            return f"[TEXT]{text}[/TEXT]"
    
    def _post_process_lines(self, lines: list) -> list:
        """Post-process lines to group related content and improve structure"""
        processed_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Group consecutive list items
            if "[LIST_ITEM]" in line or "[NUMBERED_ITEM]" in line or "[LETTERED_ITEM]" in line:
                list_items = []
                list_type = "LIST"
                
                if "[NUMBERED_ITEM]" in line:
                    list_type = "NUMBERED_LIST"
                elif "[LETTERED_ITEM]" in line:
                    list_type = "LETTERED_LIST"
                
                # Collect all consecutive list items
                while i < len(lines) and ("[LIST_ITEM]" in lines[i] or "[NUMBERED_ITEM]" in lines[i] or "[LETTERED_ITEM]" in lines[i]):
                    list_items.append(lines[i])
                    i += 1
                
                # Wrap in list structure
                processed_lines.append(f"[{list_type}]")
                processed_lines.extend(list_items)
                processed_lines.append(f"[/{list_type}]")
                continue
            
            # Group table of contents entries
            elif "[TOC_ENTRY]" in line:
                toc_items = []
                
                # Collect all consecutive TOC entries
                while i < len(lines) and "[TOC_ENTRY]" in lines[i]:
                    toc_items.append(lines[i])
                    i += 1
                
                # Wrap in TOC structure
                processed_lines.append("[TABLE_OF_CONTENTS]")
                processed_lines.extend(toc_items)
                processed_lines.append("[/TABLE_OF_CONTENTS]")
                continue
            
            # Regular line
            processed_lines.append(line)
            i += 1
        
        return processed_lines

    def extract_word_content(self, doc_path: str) -> str:
        """Extract text content from Word document"""
        try:
            # Try to use python-docx for .docx files
            if doc_path.lower().endswith('.docx'):
                try:
                    from docx import Document
                    doc = Document(doc_path)
                    paragraphs = []
                    for paragraph in doc.paragraphs:
                        if paragraph.text.strip():
                            paragraphs.append(paragraph.text)
                    return "\n\n".join(paragraphs)
                except ImportError:
                    raise Exception("python-docx package not installed. Install with: pip install python-docx")
            else:
                # For .doc files, we might need other tools like antiword or conversion
                raise Exception("Legacy .doc format not supported. Please convert to .docx or PDF")
        except Exception as e:
            raise Exception(f"Failed to extract Word document content: {e}")

    def extract_webpage_content(self, url: str, use_selenium: bool = False) -> str:
        """Extract text content from web page"""
        if use_selenium:
            return self._extract_with_selenium(url)
        else:
            return self._extract_with_requests(url)

    def _extract_with_requests(self, url: str) -> str:
        """Extract content using requests + BeautifulSoup"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.decompose()

            # Extract text from main content areas
            content_selectors = [
                "main",
                "article",
                ".content",
                "#content",
                ".post-content",
                ".entry-content",
                ".page-content",
            ]

            text_content = []
            for selector in content_selectors:
                elements = soup.select(selector)
                if elements:
                    for element in elements:
                        text_content.append(
                            element.get_text(strip=True, separator="\n")
                        )
                    break

            # Fallback: extract from body if no specific content found
            if not text_content:
                body = soup.find("body")
                if body:
                    text_content.append(body.get_text(strip=True, separator="\n"))

            return "\n\n".join(text_content)

        except Exception as e:
            raise Exception(f"Failed to extract webpage content with requests: {e}")

    def _extract_with_selenium(self, url: str) -> str:
        """Extract content using Selenium (for dynamic pages)"""
        driver = None
        try:
            driver = get_driver()
            driver.get(url)

            # Wait for page to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Try to find main content
            content_selectors = [
                "main",
                "article",
                '[class*="content"]',
                '[id*="content"]',
            ]

            text_content = []
            for selector in content_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        for element in elements:
                            text_content.append(element.text)
                        break
                except:
                    continue

            # Fallback: get body text
            if not text_content:
                body = driver.find_element(By.TAG_NAME, "body")
                text_content.append(body.text)

            return "\n\n".join(text_content)

        except Exception as e:
            raise Exception(f"Failed to extract webpage content with Selenium: {e}")
        finally:
            if driver:
                driver.quit()

    def download_file(self, url: str, filename: str) -> str:
        """Download file from URL and save locally"""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            }
            response = requests.get(url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()

            file_path = self.storage_dir / filename
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return str(file_path)

        except Exception as e:
            raise Exception(f"Failed to download file: {e}")

    def save_text_content(self, content: str, party_name: str, source_url: str, content_type: str = "webpage") -> str:
        """Save extracted text content to local file with metadata"""
        # Create filename based on party name and URL hash
        url_hash = hashlib.md5(source_url.encode()).hexdigest()[:8]
        filename = f"{party_name.lower().replace(' ', '_')}_{url_hash}.txt"
        file_path = self.storage_dir / filename

        with open(file_path, "w", encoding="utf-8") as f:
            # Write metadata header
            f.write(f"Source: {source_url}\n")
            f.write(f"Party: {party_name}\n")
            f.write(f"Content Type: {content_type}\n")
            f.write(f"Extracted at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            # Write structured content
            if content_type.lower() == "pdf":
                f.write("# STRUCTURED PDF CONTENT\n")
                f.write("# This content includes structural annotations:\n")
                f.write("# [PAGE n] / [/PAGE n] - Page boundaries\n")
                f.write("# [TITLE] / [/TITLE] - Main titles\n") 
                f.write("# [SUBTITLE] / [/SUBTITLE] - Subtitles\n")
                f.write("# [HEADING] / [/HEADING] - Section headings\n")
                f.write("# [TEXT] / [/TEXT] - Regular text\n")
                f.write("# [LIST] / [/LIST] - Lists with items\n")
                f.write("# [LIST_ITEM] / [/LIST_ITEM] - Individual list items\n")
                f.write("# [NUMBERED_LIST] / [/NUMBERED_LIST] - Numbered lists\n")
                f.write("# [TABLE_OF_CONTENTS] / [/TABLE_OF_CONTENTS] - Table of contents\n")
                f.write("# [QUOTE] / [/QUOTE] - Indented/quoted text\n\n")
            
            f.write(content)

        return str(file_path)


class Command(BaseCommand):
    help = "Import and process election programs from URLs"

    def add_arguments(self, parser):
        parser.add_argument(
            "--use-selenium",
            action="store_true",
            help="Use Selenium for web scraping (for dynamic content)",
        )
        
    def handle(self, *args, **options):
        # Get all unimported election programs from database
        unimported_programs = ElectionProgram.objects.filter(
            is_imported=False, is_active=True
        ).select_related("party")

        if not unimported_programs.exists():
            self.stdout.write(
                self.style.SUCCESS(
                    "✅ No unimported election programs found in database"
                )
            )
            return

        extractor = ContentExtractor()
        processed_count = 0

        self.stdout.write(
            f"🚀 Starting to process {unimported_programs.count()} unimported election programs..."
        )

        for program in unimported_programs:
            party_name = program.party.name
            url = program.source_url or program.pdf_url

            # Check if URL is available
            if not url:
                self.stdout.write(
                    self.style.ERROR("   ❌ No source URL or PDF URL found")
                )
                continue

            # Use the url_type field to determine how to process
            url_type = getattr(program, 'url_type', 'webpage')  # Fallback for existing records
            
            # Map url_type to processing method
            if url_type == 'pdf':
                content_type_display = "PDF"
                # Use PDF URL if available, otherwise try source URL
                if program.pdf_url:
                    url = program.pdf_url
            elif url_type in ['doc', 'docx']:
                content_type_display = f"Word Document ({url_type.upper()})"
            elif url_type == 'html':
                content_type_display = "HTML Document"
            else:
                content_type_display = "Webpage"

            self.stdout.write(f"\n📋 Processing: {party_name} ({content_type_display})")
            self.stdout.write(f"   URL: {url}")
            self.stdout.write(f"   Program: {program.title}")
            self.stdout.write(f"   Type: {url_type}")

            try:
                if url_type == 'pdf':
                    # Download PDF and extract content
                    pdf_filename = f"{party_name.lower().replace(' ', '_')}_program_{program.year}.pdf"
                    pdf_path = extractor.download_file(url, pdf_filename)
                    self.stdout.write(f"   📥 Downloaded PDF to: {pdf_path}")

                    content = extractor.extract_pdf_content(pdf_path)

                elif url_type in ['webpage', 'html']:
                    # Extract from webpage/HTML
                    content = extractor.extract_webpage_content(
                        url, use_selenium=options.get("use_selenium", False)
                    )
                elif url_type in ['doc', 'docx']:
                    # Download and extract Word document content
                    doc_filename = f"{party_name.lower().replace(' ', '_')}_program_{program.year}.{url_type}"
                    doc_path = extractor.download_file(url, doc_filename)
                    self.stdout.write(f"   � Downloaded {url_type.upper()} to: {doc_path}")

                    content = extractor.extract_word_content(doc_path)
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            f"   ❌ Unsupported URL type: {url_type}"
                        )
                    )
                    continue

                # Clean and validate content
                if not content or len(content.strip()) < 100:
                    self.stdout.write(
                        self.style.WARNING(
                            f"   ⚠️ Content too short or empty (length: {len(content)})"
                        )
                    )
                    continue

                # Save text content locally with structure information
                text_file_path = extractor.save_text_content(content, party_name, url, content_type_display)
                self.stdout.write(f"   💾 Saved structured text to: {text_file_path}")
                self.stdout.write(f"   📏 Content length: {len(content)} characters")

                # Count structural elements if it's a PDF
                if url_type == 'pdf':
                    structure_stats = self._analyze_structure(content)
                    self.stdout.write(f"   📊 Structure: {structure_stats}")

                # Mark program as imported
                program.is_imported = True
                program.save()
                self.stdout.write(f"   ✅ Marked program as imported in database")

                processed_count += 1
                self.stdout.write(f"   ✅ Successfully processed {party_name}")

                # Add delay between requests
                time.sleep(2)

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Failed to process {party_name}: {e}")
                )
                continue

        self.stdout.write(
            self.style.SUCCESS(
                f"\n🎉 Processing complete! Successfully processed {processed_count}/{unimported_programs.count()} programs"
            )
        )
        self.stdout.write(f"📁 Files saved to: {extractor.storage_dir}")

    def _analyze_structure(self, content: str) -> str:
        """Analyze the structural elements in the extracted content"""
        import re
        
        stats = {}
        stats['pages'] = len(re.findall(r'\[PAGE \d+\]', content))
        stats['titles'] = len(re.findall(r'\[TITLE\]', content))
        stats['subtitles'] = len(re.findall(r'\[SUBTITLE\]', content))
        stats['headings'] = len(re.findall(r'\[HEADING\]', content))
        stats['lists'] = len(re.findall(r'\[(?:NUMBERED_)?LIST\]', content))
        stats['list_items'] = len(re.findall(r'\[(?:LIST_ITEM|NUMBERED_ITEM|LETTERED_ITEM)\]', content))
        stats['toc_entries'] = len(re.findall(r'\[TOC_ENTRY\]', content))
        stats['text_blocks'] = len(re.findall(r'\[TEXT\]', content))
        
        # Format nicely
        return f"{stats['pages']} pages, {stats['titles']} titles, {stats['headings']} headings, {stats['lists']} lists ({stats['list_items']} items), {stats['text_blocks']} text blocks"