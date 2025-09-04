"""
Enhanced Reference Extraction
Combines GROBID (when available) with refextract fallback for robust reference extraction.
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import config

logger = logging.getLogger(__name__)

def extract_references(pdf_path: str, force_method: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract references from PDF using the best available method.
    
    Args:
        pdf_path: Path to PDF file
        force_method: Force specific extraction method ('grobid', 'refextract', or None for auto)
    
    Returns:
        List of reference dictionaries
    """
    path = Path(pdf_path)
    if not path.exists() or path.suffix.lower() != ".pdf":
        raise ValueError(f"Invalid PDF path: {pdf_path}")
    
    logger.info(f"Extracting references from {path.name}")
    
    # Determine extraction method
    use_grobid = (
        force_method == 'grobid' or 
        (force_method != 'refextract' and config.grobid_enabled)
    )
    
    references = []
    
    if use_grobid:
        try:
            references = _extract_with_grobid(pdf_path)
            if references:
                logger.info(f"GROBID extracted {len(references)} references")
            else:
                logger.warning("GROBID returned no references, trying refextract")
                references = _extract_with_refextract(pdf_path)
        except Exception as e:
            logger.warning(f"GROBID extraction failed ({e}), falling back to refextract")
            references = _extract_with_refextract(pdf_path)
    else:
        references = _extract_with_refextract(pdf_path)
    
    if not references:
        logger.warning(f"No references found in {path.name}")
        return []
    
    # Post-process and validate references
    processed_references = []
    for ref in references:
        processed_ref = _post_process_reference(ref)
        if _is_valid_reference(processed_ref):
            processed_references.append(processed_ref)
    
    logger.info(f"Final result: {len(processed_references)} valid references from {path.name}")
    return processed_references

def _extract_with_grobid(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract references using GROBID."""
    try:
        from grobid_client import extract_references_grobid
        return extract_references_grobid(pdf_path)
    except ImportError:
        logger.error("GROBID client not available")
        return []
    except Exception as e:
        logger.error(f"GROBID extraction error: {e}")
        raise

def _extract_with_refextract(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract references using refextract (fallback method)."""
    try:
        import refextract
        logger.info("Using refextract for reference extraction")
        references = refextract.extract_references_from_file(str(pdf_path))
        return references or []
    except ImportError:
        logger.error("refextract not available")
        return []
    except Exception as e:
        logger.error(f"refextract extraction error: {e}")
        raise

def _post_process_reference(ref: Dict[str, Any]) -> Dict[str, Any]:
    """Post-process and normalize reference data."""
    processed = ref.copy()
    
    # Normalize list fields to strings
    for field in ['title', 'author', 'journal', 'year', 'doi', 'misc', 'volume', 'page']:
        if field in processed:
            value = processed[field]
            if isinstance(value, list):
                # Join list elements with spaces
                processed[field] = ' '.join(str(item) for item in value if item)
            elif value is None:
                processed[field] = ""
            else:
                processed[field] = str(value).strip()
    
    # Clean and validate DOI
    if 'doi' in processed and processed['doi']:
        processed['doi'] = _clean_doi(processed['doi'])
    
    # Extract additional identifiers from misc field
    if 'misc' in processed and processed['misc']:
        misc_text = processed['misc']
        
        # Extract arXiv ID if not already present
        if not processed.get('arxiv_id'):
            import re
            arxiv_match = re.search(r'arXiv:?(\d{4}\.\d{4,5}(?:v\d+)?)', misc_text, re.IGNORECASE)
            if arxiv_match:
                processed['arxiv_id'] = arxiv_match.group(1)
    
    # Ensure raw_reference exists for fallback
    if not processed.get('raw_reference') and processed.get('title'):
        # Construct raw reference from available fields
        parts = []
        if processed.get('title'):
            parts.append(processed['title'])
        if processed.get('author'):
            parts.append(f"by {processed['author']}")
        if processed.get('journal'):
            parts.append(processed['journal'])
        if processed.get('year'):
            parts.append(f"({processed['year']})")
        
        processed['raw_reference'] = '. '.join(parts)
    
    return processed

def _clean_doi(doi: str) -> str:
    """Clean and validate DOI format."""
    import re
    
    if not doi:
        return ""
    
    # Remove URL prefix
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    
    # Remove extra whitespace and punctuation
    doi = doi.strip().rstrip('.')
    
    # Validate DOI format
    if re.match(r'^10\.\d+/', doi):
        return doi
    
    return ""

def _is_valid_reference(ref: Dict[str, Any]) -> bool:
    """Check if reference has sufficient quality for processing."""
    
    # Must have either title, raw_reference, or DOI
    has_content = (
        (ref.get('title', '').strip() and len(ref['title'].strip()) >= config.min_title_length) or
        (ref.get('raw_reference', '').strip() and len(ref['raw_reference'].strip()) >= 20) or
        ref.get('doi', '').strip()
    )
    
    if not has_content:
        logger.debug(f"Filtering reference with insufficient content: {ref}")
        return False
    
    # Additional quality checks
    title = ref.get('title', '').strip()
    if title:
        # Filter out common false positives
        false_positive_patterns = [
            r'^(acknowledgments?|references?|bibliography)$',  # Section headers
            r'^(table|figure|fig\.)\s*\d+',  # Captions
            r'^\d+$',  # Just numbers
            r'^[a-z]$',  # Single letters
        ]
        
        import re
        for pattern in false_positive_patterns:
            if re.match(pattern, title, re.IGNORECASE):
                logger.debug(f"Filtering false positive reference: {title}")
                return False
    
    return True

def analyze_extraction_quality(references: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze the quality of extracted references."""
    if not references:
        return {
            'total_references': 0,
            'quality_score': 0.0,
            'issues': ['No references found']
        }
    
    total = len(references)
    issues = []
    scores = {
        'has_title': 0,
        'has_authors': 0,
        'has_year': 0,
        'has_doi': 0,
        'has_journal': 0,
        'title_length_ok': 0,
        'has_structured_data': 0
    }
    
    for ref in references:
        title = ref.get('title', '').strip()
        if title:
            scores['has_title'] += 1
            if len(title) >= config.min_title_length:
                scores['title_length_ok'] += 1
        
        if ref.get('author', '').strip():
            scores['has_authors'] += 1
        
        if ref.get('year', '').strip():
            scores['has_year'] += 1
        
        if ref.get('doi', '').strip():
            scores['has_doi'] += 1
        
        if ref.get('journal', '').strip():
            scores['has_journal'] += 1
        
        # Check if reference has structured data beyond raw text
        has_structured = any(ref.get(field, '').strip() for field in ['title', 'author', 'doi', 'year'])
        if has_structured:
            scores['has_structured_data'] += 1
    
    # Calculate percentages
    percentages = {key: (value / total) * 100 for key, value in scores.items()}
    
    # Identify issues
    if percentages['has_title'] < 50:
        issues.append(f"Low title extraction rate: {percentages['has_title']:.1f}%")
    
    if percentages['has_doi'] < 10:
        issues.append(f"Very few DOIs found: {percentages['has_doi']:.1f}%")
    
    if percentages['has_structured_data'] < 70:
        issues.append(f"Limited structured data: {percentages['has_structured_data']:.1f}%")
    
    # Overall quality score
    quality_score = (
        percentages['has_title'] * 0.3 +
        percentages['title_length_ok'] * 0.2 +
        percentages['has_authors'] * 0.15 +
        percentages['has_doi'] * 0.15 +
        percentages['has_year'] * 0.1 +
        percentages['has_structured_data'] * 0.1
    ) / 100
    
    return {
        'total_references': total,
        'quality_score': quality_score,
        'percentages': percentages,
        'issues': issues,
        'recommendation': _get_extraction_recommendation(quality_score, percentages)
    }

def _get_extraction_recommendation(quality_score: float, percentages: Dict[str, float]) -> str:
    """Get recommendation based on extraction quality."""
    if quality_score > 0.8:
        return "Excellent reference quality - should have high success rate"
    elif quality_score > 0.6:
        return "Good reference quality - decent success rate expected"
    elif quality_score > 0.4:
        return "Moderate quality - consider using GROBID if not already enabled"
    elif quality_score > 0.2:
        return "Poor quality - PDF may have low-quality references or extraction issues"
    else:
        return "Very poor quality - PDF may not contain standard academic references"

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python extractor.py <pdf_path> [method]")
        print("Methods: auto (default), grobid, refextract")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    method = sys.argv[2] if len(sys.argv) > 2 else 'auto'
    
    try:
        references = extract_references(pdf_path, force_method=method if method != 'auto' else None)
        
        print(f"Extracted {len(references)} references using {method}")
        
        # Show analysis
        analysis = analyze_extraction_quality(references)
        print(f"\nQuality Score: {analysis['quality_score']:.2f}")
        print(f"Recommendation: {analysis['recommendation']}")
        
        if analysis['issues']:
            print(f"Issues: {', '.join(analysis['issues'])}")
        
        # Show first few references
        print(f"\nFirst 3 references:")
        for i, ref in enumerate(references[:3], 1):
            title = ref.get('title', '')[:60] + '...' if len(ref.get('title', '')) > 60 else ref.get('title', '')
            doi = ref.get('doi', '')
            print(f"{i}. {title}")
            if doi:
                print(f"   DOI: {doi}")
            print()
                
    except Exception as e:
        logger.error(f"Error extracting references: {e}")
        sys.exit(1)