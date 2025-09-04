"""
GROBID Client for Enhanced Reference Extraction
Provides high-quality structured reference extraction from PDFs using GROBID service.
"""

import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
import time
import re
from dataclasses import dataclass
from config import config

logger = logging.getLogger(__name__)

@dataclass
class Reference:
    """Structured reference data extracted from GROBID."""
    title: str = ""
    authors: List[str] = None
    journal: str = ""
    venue: str = ""
    year: str = ""
    volume: str = ""
    issue: str = ""
    pages: str = ""
    doi: str = ""
    arxiv_id: str = ""
    pmid: str = ""
    raw_reference: str = ""
    quality_score: float = 0.0
    
    def __post_init__(self):
        if self.authors is None:
            self.authors = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format compatible with existing code."""
        return {
            'title': self.title,
            'author': self.authors,
            'journal': self.journal or self.venue,
            'year': self.year,
            'volume': self.volume,
            'page': self.pages,
            'doi': self.doi,
            'misc': f"arxiv:{self.arxiv_id}" if self.arxiv_id else "",
            'raw_reference': self.raw_reference
        }
    
    def calculate_quality_score(self) -> float:
        """Calculate quality score based on available fields."""
        score = 0.0
        
        # Title quality (most important)
        if self.title:
            if len(self.title) > 10:
                score += 0.4
            if len(self.title) > 20:
                score += 0.1
        
        # Author information
        if self.authors:
            score += 0.2
        
        # Publication info
        if self.journal or self.venue:
            score += 0.1
        
        # Year
        if self.year and self.year.isdigit():
            score += 0.1
        
        # DOI (very valuable)
        if self.doi:
            score += 0.2
        
        # arXiv ID (valuable for preprints)
        if self.arxiv_id:
            score += 0.15
        
        self.quality_score = min(1.0, score)
        return self.quality_score

class GROBIDClient:
    """Client for GROBID reference extraction service."""
    
    def __init__(self, grobid_url: str = None):
        self.base_url = grobid_url or config.grobid_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'BibP/2.0 GROBID Client (mailto:{config.contact_email})'
        })
        
        # Verify GROBID is accessible
        self.is_alive = self._check_service()
    
    def _check_service(self) -> bool:
        """Check if GROBID service is accessible."""
        try:
            response = self.session.get(f"{self.base_url}/api/isalive", timeout=10)
            if response.status_code == 200:
                logger.info(f"GROBID service is alive at {self.base_url}")
                return True
            else:
                logger.warning(f"GROBID service returned status {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Cannot connect to GROBID at {self.base_url}: {e}")
            return False
    
    def extract_references(self, pdf_path: str) -> List[Reference]:
        """
        Extract references from PDF using GROBID.
        Returns structured Reference objects with quality scoring.
        """
        if not self.is_alive:
            logger.error("GROBID service is not accessible")
            return []
        
        pdf_file = Path(pdf_path)
        if not pdf_file.exists() or pdf_file.suffix.lower() != '.pdf':
            raise ValueError(f"Invalid PDF file: {pdf_path}")
        
        logger.info(f"Extracting references from {pdf_file.name} using GROBID")
        
        try:
            # Upload PDF to GROBID for reference extraction
            with open(pdf_file, 'rb') as f:
                files = {'input': (pdf_file.name, f, 'application/pdf')}
                data = {
                    'consolidateHeader': '1',
                    'consolidateCitations': '1',
                    'includeRawCitations': '1'
                }
                
                response = self.session.post(
                    f"{self.base_url}/api/processReferences",
                    files=files,
                    data=data,
                    timeout=120  # References can take a while
                )
                
                response.raise_for_status()
        
            # Parse XML response
            references = self._parse_grobid_xml(response.text)
            
            # Calculate quality scores and filter
            quality_references = []
            for ref in references:
                score = ref.calculate_quality_score()
                if score >= config.min_reference_quality_score:
                    quality_references.append(ref)
                else:
                    logger.debug(f"Filtered low-quality reference: {ref.title[:50]}... (score: {score:.2f})")
            
            logger.info(f"Extracted {len(quality_references)} high-quality references from {len(references)} total")
            return quality_references
            
        except requests.exceptions.Timeout:
            logger.error(f"GROBID request timed out for {pdf_file.name}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"GROBID request failed for {pdf_file.name}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error processing {pdf_file.name}: {e}")
            return []
    
    def _parse_grobid_xml(self, xml_content: str) -> List[Reference]:
        """Parse GROBID XML response into Reference objects."""
        references = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Handle namespaces
            ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
            
            # Find all biblStruct elements (structured references)
            for biblio in root.findall('.//tei:biblStruct', ns):
                ref = Reference()
                
                # Title
                title_elem = biblio.find('.//tei:title[@level="a"]', ns)
                if title_elem is None:
                    title_elem = biblio.find('.//tei:title[@level="m"]', ns)
                if title_elem is not None and title_elem.text:
                    ref.title = self._clean_text(title_elem.text)
                
                # Authors
                authors = []
                for author in biblio.findall('.//tei:author', ns):
                    author_parts = []
                    
                    # First name
                    first_name = author.find('.//tei:forename[@type="first"]', ns)
                    if first_name is not None and first_name.text:
                        author_parts.append(first_name.text)
                    
                    # Middle name
                    middle_name = author.find('.//tei:forename[@type="middle"]', ns)
                    if middle_name is not None and middle_name.text:
                        author_parts.append(middle_name.text)
                    
                    # Last name
                    last_name = author.find('.//tei:surname', ns)
                    if last_name is not None and last_name.text:
                        author_parts.append(last_name.text)
                    
                    if author_parts:
                        authors.append(' '.join(author_parts))
                
                ref.authors = authors
                
                # Journal/Venue
                journal_elem = biblio.find('.//tei:title[@level="j"]', ns)
                if journal_elem is not None and journal_elem.text:
                    ref.journal = self._clean_text(journal_elem.text)
                
                # Conference/Meeting
                meeting_elem = biblio.find('.//tei:title[@level="m"]', ns)
                if meeting_elem is not None and meeting_elem.text and not ref.journal:
                    ref.venue = self._clean_text(meeting_elem.text)
                
                # Publication date
                date_elem = biblio.find('.//tei:date[@type="published"]', ns)
                if date_elem is not None:
                    when = date_elem.get('when')
                    if when:
                        # Extract year from ISO date
                        year_match = re.search(r'(\d{4})', when)
                        if year_match:
                            ref.year = year_match.group(1)
                
                # Volume, issue, pages
                vol_elem = biblio.find('.//tei:biblScope[@unit="volume"]', ns)
                if vol_elem is not None and vol_elem.text:
                    ref.volume = vol_elem.text
                
                issue_elem = biblio.find('.//tei:biblScope[@unit="issue"]', ns)
                if issue_elem is not None and issue_elem.text:
                    ref.issue = issue_elem.text
                
                page_elem = biblio.find('.//tei:biblScope[@unit="page"]', ns)
                if page_elem is not None:
                    from_page = page_elem.get('from')
                    to_page = page_elem.get('to')
                    if from_page and to_page:
                        ref.pages = f"{from_page}-{to_page}"
                    elif from_page:
                        ref.pages = from_page
                
                # DOI
                doi_elem = biblio.find('.//tei:idno[@type="DOI"]', ns)
                if doi_elem is not None and doi_elem.text:
                    ref.doi = self._clean_doi(doi_elem.text)
                
                # arXiv ID
                arxiv_elem = biblio.find('.//tei:idno[@type="arXiv"]', ns)
                if arxiv_elem is not None and arxiv_elem.text:
                    ref.arxiv_id = arxiv_elem.text
                
                # PMID
                pmid_elem = biblio.find('.//tei:idno[@type="PMID"]', ns)
                if pmid_elem is not None and pmid_elem.text:
                    ref.pmid = pmid_elem.text
                
                # Skip empty references
                if ref.title or ref.authors or ref.doi:
                    references.append(ref)
            
            # Also parse raw references if structured ones are insufficient
            raw_references = self._parse_raw_references(xml_content, ns)
            if len(references) < len(raw_references) * 0.7:  # If structured extraction missed many
                logger.info("Supplementing with raw reference parsing")
                references.extend(raw_references[len(references):])
            
        except ET.ParseError as e:
            logger.error(f"XML parsing error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing GROBID XML: {e}")
            return []
        
        return references
    
    def _parse_raw_references(self, xml_content: str, ns: dict) -> List[Reference]:
        """Parse raw reference strings as fallback."""
        references = []
        
        try:
            root = ET.fromstring(xml_content)
            
            # Find raw reference elements
            for raw_ref in root.findall('.//tei:bibl', ns):
                if raw_ref.text and len(raw_ref.text.strip()) > 20:
                    ref = Reference()
                    ref.raw_reference = self._clean_text(raw_ref.text)
                    
                    # Try to extract basic info from raw text
                    ref = self._extract_from_raw_text(ref)
                    
                    if ref.title or len(ref.raw_reference) > 30:
                        references.append(ref)
        
        except Exception as e:
            logger.debug(f"Error parsing raw references: {e}")
        
        return references
    
    def _extract_from_raw_text(self, ref: Reference) -> Reference:
        """Extract basic information from raw reference text."""
        text = ref.raw_reference
        
        # Try to extract DOI
        doi_match = re.search(r'(?:doi:?\s*|DOI:?\s*)(10\.\d+/[^\s,]+)', text, re.IGNORECASE)
        if doi_match:
            ref.doi = doi_match.group(1)
        
        # Try to extract arXiv ID
        arxiv_match = re.search(r'arXiv:(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.IGNORECASE)
        if arxiv_match:
            ref.arxiv_id = arxiv_match.group(1)
        
        # Try to extract year
        year_match = re.search(r'\b(19|20)\d{2}\b', text)
        if year_match:
            ref.year = year_match.group()
        
        # Try to extract title (very basic heuristic)
        # Remove leading citation markers
        clean_text = re.sub(r'^\s*\[\d+\]\s*', '', text)
        clean_text = re.sub(r'^\s*\d+\.\s*', '', clean_text)
        
        # Look for title-like text (before venue indicators)
        title_match = re.search(r'^([^.]+(?:\.[^.]+)*?)\.\s*(?:In\s|Proc|Conference|Journal)', clean_text, re.IGNORECASE)
        if title_match:
            potential_title = title_match.group(1).strip()
            if len(potential_title) > 10 and not re.match(r'^[A-Z][a-z]+,\s*[A-Z]', potential_title):  # Not author name
                ref.title = potential_title
        
        return ref
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common artifacts
        text = re.sub(r'^\d+\.\s*', '', text)  # Leading numbers
        text = re.sub(r'^\[\d+\]\s*', '', text)  # Citation markers
        
        return text
    
    def _clean_doi(self, doi: str) -> str:
        """Clean and validate DOI."""
        if not doi:
            return ""
        
        # Remove URL prefix if present
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
        
        # Validate DOI format
        if re.match(r'^10\.\d+/', doi):
            return doi
        
        return ""

# Global GROBID client instance
grobid_client = GROBIDClient() if config.grobid_enabled else None

def extract_references_grobid(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Main function to extract references using GROBID.
    Returns list of dictionaries compatible with existing downloader code.
    """
    if not grobid_client or not grobid_client.is_alive:
        logger.warning("GROBID not available, falling back to refextract")
        from extractor import extract_references
        return extract_references(pdf_path)
    
    try:
        references = grobid_client.extract_references(pdf_path)
        return [ref.to_dict() for ref in references]
    except Exception as e:
        logger.error(f"GROBID extraction failed: {e}, falling back to refextract")
        from extractor import extract_references
        return extract_references(pdf_path)

if __name__ == "__main__":
    # Test GROBID client
    if len(sys.argv) != 2:
        print("Usage: python grobid_client.py <pdf_path>")
        sys.exit(1)
    
    import sys
    pdf_path = sys.argv[1]
    
    client = GROBIDClient()
    if client.is_alive:
        refs = client.extract_references(pdf_path)
        
        print(f"Extracted {len(refs)} references:")
        for i, ref in enumerate(refs[:5], 1):  # Show first 5
            print(f"\nRef {i} (quality: {ref.quality_score:.2f}):")
            print(f"  Title: {ref.title}")
            print(f"  Authors: {', '.join(ref.authors[:3])}")
            print(f"  Journal: {ref.journal}")
            print(f"  Year: {ref.year}")
            print(f"  DOI: {ref.doi}")
    else:
        print("GROBID service not available")