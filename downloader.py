"""
Production Multi-API Downloader
Comprehensive reference resolution using multiple APIs with intelligent fallbacks.
"""

import requests
import json
import time
import threading
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from urllib.parse import urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
import xml.etree.ElementTree as ET
import logging

# Import API clients
try:
    from semanticscholar import SemanticScholar
except ImportError:
    SemanticScholar = None

try:
    from habanero import Crossref
except ImportError:
    Crossref = None

from config import config

logger = logging.getLogger(__name__)

@dataclass
class SourceResult:
    """Result from a single API source."""
    source_name: str
    success: bool
    url: Optional[str] = None
    metadata: Optional[Dict] = None
    error: Optional[str] = None
    response_time: float = 0.0

@dataclass
class ReferenceResult:
    """Complete result for a reference download attempt."""
    filename: str
    status: str  # 'success', 'exists', 'failed', 'error'
    source: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None
    sources_tried: List[SourceResult] = field(default_factory=list)
    reference_info: Optional[Dict] = None
    
    def add_source_attempt(self, result: SourceResult):
        """Add a source attempt to the history."""
        self.sources_tried.append(result)

class RateLimiter:
    """Thread-safe rate limiter with burst handling."""
    
    def __init__(self, calls_per_second: float, burst_size: int = 5):
        self.rate = calls_per_second
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_refill = time.time()
        self.lock = threading.Lock()
    
    def acquire(self, api_name: str = ""):
        """Acquire permission to make an API call."""
        with self.lock:
            now = time.time()
            
            # Refill tokens based on time passed
            time_passed = now - self.last_refill
            self.tokens = min(self.burst_size, self.tokens + time_passed * self.rate)
            self.last_refill = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            
            # Need to wait
            sleep_time = (1.0 - self.tokens) / self.rate
            if config.log_api_calls:
                logger.debug(f"Rate limiting {api_name}: sleeping {sleep_time:.2f}s")
            
            time.sleep(sleep_time)
            self.tokens = 0

class APIManager:
    """Manages API clients and rate limiters."""
    
    def __init__(self):
        self.rate_limiters = {}
        self.clients = {}
        
        # Initialize rate limiters
        for api_name, api_config in config.get_enabled_apis().items():
            self.rate_limiters[api_name] = RateLimiter(
                calls_per_second=api_config.rate_limit,
                burst_size=max(2, int(api_config.rate_limit * 2))
            )
        
        # Initialize API clients
        self._init_clients()
    
    def _init_clients(self):
        """Initialize API clients."""
        try:
            if config.apis['semantic_scholar'].enabled and SemanticScholar:
                self.clients['semantic_scholar'] = SemanticScholar(
                    api_key=config.semantic_scholar_api_key,
                    timeout=config.apis['semantic_scholar'].timeout
                )
                logger.info("Initialized Semantic Scholar client")
        except Exception as e:
            logger.warning(f"Failed to initialize Semantic Scholar: {e}")
        
        try:
            if config.apis['crossref'].enabled and Crossref:
                self.clients['crossref'] = Crossref(
                    mailto=config.contact_email,
                    ua_string=f"BibP/2.0 (mailto:{config.contact_email})"
                )
                logger.info("Initialized Crossref client")
        except Exception as e:
            logger.warning(f"Failed to initialize Crossref: {e}")
        
        # HTTP session for other APIs
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': f'BibP/2.0 Research Tool (mailto:{config.contact_email})'
        })
    
    def rate_limit(self, api_name: str):
        """Apply rate limiting for an API."""
        if api_name in self.rate_limiters:
            self.rate_limiters[api_name].acquire(api_name)

# Global API manager
api_manager = APIManager()

class ReferenceProcessor:
    """Processes individual references through the API pipeline."""
    
    def __init__(self):
        self.source_handlers = {
            'arxiv': self._handle_arxiv,
            'unpaywall': self._handle_unpaywall,
            'openalex': self._handle_openalex,
            'semantic_scholar': self._handle_semantic_scholar,
            'crossref': self._handle_crossref,
            'pubmed': self._handle_pubmed,
            'core': self._handle_core,
        }
    
    def process_reference(self, ref: Dict, output_dir: Path, index: int) -> ReferenceResult:
        """Process a single reference through all available sources."""
        ref_info = self._extract_reference_info(ref)
        filename = self._generate_filename(ref_info, index)
        save_path = output_dir / filename
        
        result = ReferenceResult(
            filename=filename,
            status='failed',
            reference_info=ref_info
        )
        
        logger.info(f"Processing ref {index}: {ref_info['title'][:60]}...")
        
        # Check if file already exists
        if save_path.exists():
            result.status = 'exists'
            logger.info(f"File already exists: {filename}")
            return result
        
        # Try each enabled source in priority order
        enabled_apis = config.get_enabled_apis()
        
        for api_name in enabled_apis:
            if api_name in self.source_handlers:
                source_result = self.source_handlers[api_name](ref_info)
                result.add_source_attempt(source_result)
                
                if source_result.success and source_result.url:
                    try:
                        self._download_pdf(source_result.url, save_path)
                        result.status = 'success'
                        result.source = api_name
                        result.url = source_result.url
                        logger.info(f"Downloaded {filename} from {api_name}")
                        return result
                    except Exception as e:
                        logger.warning(f"Download failed from {api_name}: {e}")
                        source_result.success = False
                        source_result.error = str(e)
        
        # No sources succeeded
        result.error = "No open access source found"
        logger.warning(f"No source found for {filename}")
        return result
    
    def _extract_reference_info(self, ref: Dict) -> Dict[str, str]:
        """Extract and normalize reference information."""
        info = {}
        
        # Standard fields
        for field in ['title', 'author', 'journal', 'year', 'doi', 'volume', 'page', 'raw_reference']:
            value = ref.get(field, '')
            if isinstance(value, list):
                info[field] = ' '.join(str(item) for item in value if item)
            else:
                info[field] = str(value).strip() if value else ''
        
        # Extract arXiv ID from misc or raw_reference
        misc_text = ' '.join([
            str(ref.get('misc', '')),
            str(ref.get('raw_reference', ''))
        ])
        
        arxiv_match = re.search(r'arXiv:?(\d{4}\.\d{4,5}(?:v\d+)?)', misc_text, re.IGNORECASE)
        info['arxiv_id'] = arxiv_match.group(1) if arxiv_match else ''
        
        # Clean DOI
        info['doi'] = self._clean_doi(info['doi'])
        
        return info
    
    def _clean_doi(self, doi: str) -> str:
        """Clean and validate DOI."""
        if not doi:
            return ''
        
        # Remove URL prefix
        doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
        doi = doi.strip().rstrip('.')
        
        # Validate format
        if re.match(r'^10\.\d+/', doi):
            return doi
        
        return ''
    
    def _generate_filename(self, ref_info: Dict, index: int) -> str:
        """Generate safe, descriptive filename."""
        # Use title, fallback to raw_reference
        title = ref_info['title'] or ref_info['raw_reference']
        
        if title:
            # Clean title for filename
            clean_title = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', title)
            clean_title = re.sub(r'\s+', '_', clean_title.strip())
            clean_title = clean_title[:60]  # Reasonable length limit
        else:
            clean_title = f"reference_{index}"
        
        # Create hash for uniqueness
        hash_content = f"{ref_info['title']}|{ref_info['doi']}|{ref_info['arxiv_id']}|{index}"
        file_hash = hashlib.sha256(hash_content.encode()).hexdigest()[:8]
        
        filename = f"ref_{index:03d}_{clean_title}_{file_hash}.pdf"
        
        # Ensure filename isn't too long
        if len(filename) > config.max_filename_length:
            # Truncate title part
            max_title_len = config.max_filename_length - len(f"ref_{index:03d}___{file_hash}.pdf")
            clean_title = clean_title[:max(10, max_title_len)]
            filename = f"ref_{index:03d}_{clean_title}_{file_hash}.pdf"
        
        return filename
    
    def _download_pdf(self, url: str, save_path: Path) -> None:
        """Download PDF from URL with validation."""
        response = api_manager.session.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        # Basic content validation
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
            logger.warning(f"Unexpected content type: {content_type}")
        
        # Download in chunks
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Validate file size
        if save_path.stat().st_size < config.min_pdf_size:
            save_path.unlink()  # Delete invalid file
            raise ValueError(f"Downloaded file too small: {save_path.stat().st_size} bytes")
    
    def _handle_arxiv(self, ref_info: Dict) -> SourceResult:
        """Handle arXiv preprints."""
        start_time = time.time()
        result = SourceResult('arxiv', False)
        
        try:
            arxiv_id = ref_info['arxiv_id']
            if not arxiv_id:
                # Try to extract from other fields
                text_sources = [ref_info['title'], ref_info['raw_reference']]
                combined_text = ' '.join(filter(None, text_sources))
                
                arxiv_match = re.search(r'arXiv:?(\d{4}\.\d{4,5}(?:v\d+)?)', combined_text, re.IGNORECASE)
                if arxiv_match:
                    arxiv_id = arxiv_match.group(1)
            
            if arxiv_id:
                result.url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                result.success = True
                result.metadata = {'arxiv_id': arxiv_id}
            
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _handle_unpaywall(self, ref_info: Dict, doi: str = None) -> SourceResult:
        """Handle Unpaywall API."""
        start_time = time.time()
        result = SourceResult('unpaywall', False)
        
        doi = doi or ref_info['doi']
        if not doi:
            return result
        
        try:
            api_manager.rate_limit('unpaywall')
            
            url = f"https://api.unpaywall.org/v2/{doi}"
            params = {'email': config.contact_email}
            
            response = api_manager.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('is_oa'):
                # Find best PDF URL
                best_url = None
                best_priority = -1
                
                for location in data.get('oa_locations', []):
                    pdf_url = location.get('url_for_pdf')
                    if not pdf_url:
                        continue
                    
                    # Priority scoring
                    priority = 0
                    host_type = location.get('host_type', '')
                    
                    if 'repository' in host_type:
                        priority += 2
                    if 'arxiv' in pdf_url.lower():
                        priority += 3
                    if pdf_url.endswith('.pdf'):
                        priority += 1
                    
                    if priority > best_priority:
                        best_priority = priority
                        best_url = pdf_url
                
                if best_url:
                    result.url = best_url
                    result.success = True
                    result.metadata = {'is_oa': True, 'host_type': host_type}
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _handle_openalex(self, ref_info: Dict) -> SourceResult:
        """Handle OpenAlex API."""
        start_time = time.time()
        result = SourceResult('openalex', False)
        
        try:
            api_manager.rate_limit('openalex')
            
            base_url = "https://api.openalex.org/works"
            
            # Try DOI first
            if ref_info['doi']:
                url = f"{base_url}/doi:{ref_info['doi']}"
                response = api_manager.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    work_data = response.json()
                    pdf_url = self._extract_openalex_pdf(work_data)
                    if pdf_url:
                        result.url = pdf_url
                        result.success = True
                        result.metadata = {'method': 'doi', 'openalex_id': work_data.get('id')}
                        return result
            
            # Try title search
            if ref_info['title'] and len(ref_info['title']) > 10:
                params = {
                    'search': ref_info['title'][:200],
                    'per-page': 1
                }
                
                response = api_manager.session.get(base_url, params=params, timeout=10)
                response.raise_for_status()
                
                data = response.json()
                if data.get('results'):
                    work_data = data['results'][0]
                    pdf_url = self._extract_openalex_pdf(work_data)
                    if pdf_url:
                        result.url = pdf_url
                        result.success = True
                        result.metadata = {'method': 'title', 'openalex_id': work_data.get('id')}
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _extract_openalex_pdf(self, work_data: Dict) -> Optional[str]:
        """Extract PDF URL from OpenAlex work data."""
        # Check open access info
        open_access = work_data.get('open_access', {})
        if open_access.get('is_oa') and open_access.get('oa_url'):
            return open_access['oa_url']
        
        # Check locations
        for location in work_data.get('locations', []):
            if location.get('is_oa') and location.get('pdf_url'):
                return location['pdf_url']
        
        return None
    
    def _handle_semantic_scholar(self, ref_info: Dict) -> SourceResult:
        """Handle Semantic Scholar API."""
        start_time = time.time()
        result = SourceResult('semantic_scholar', False)
        
        if not api_manager.clients.get('semantic_scholar'):
            result.error = "Semantic Scholar client not available"
            return result
        
        try:
            api_manager.rate_limit('semantic_scholar')
            
            sch = api_manager.clients['semantic_scholar']
            paper = None
            
            # Try DOI first
            if ref_info['doi']:
                try:
                    paper = sch.get_paper(ref_info['doi'], fields=['openAccessPdf', 'externalIds'])
                except Exception:
                    pass
            
            # Try title search
            if not paper and ref_info['title'] and len(ref_info['title']) > 5:
                try:
                    results = sch.search_paper(ref_info['title'][:200], limit=1, fields=['openAccessPdf', 'externalIds'])
                    if results and len(results) > 0:
                        paper = results[0]
                except Exception:
                    pass
            
            if paper:
                # Extract PDF URL
                pdf_url = self._extract_s2_pdf_url(paper)
                if pdf_url:
                    result.url = pdf_url
                    result.success = True
                    result.metadata = {'paper_id': getattr(paper, 'paperId', None)}
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _extract_s2_pdf_url(self, paper) -> Optional[str]:
        """Extract PDF URL from Semantic Scholar paper."""
        try:
            open_access_pdf = None
            if hasattr(paper, 'openAccessPdf'):
                open_access_pdf = paper.openAccessPdf
            elif isinstance(paper, dict) and 'openAccessPdf' in paper:
                open_access_pdf = paper['openAccessPdf']
            
            if open_access_pdf:
                if isinstance(open_access_pdf, dict):
                    return open_access_pdf.get('url')
                elif hasattr(open_access_pdf, 'url'):
                    return open_access_pdf.url
        except Exception:
            pass
        
        return None
    
    def _handle_crossref(self, ref_info: Dict) -> SourceResult:
        """Handle Crossref API (for DOI resolution, then use Unpaywall)."""
        start_time = time.time()
        result = SourceResult('crossref', False)
        
        if not api_manager.clients.get('crossref'):
            result.error = "Crossref client not available"
            return result
        
        try:
            api_manager.rate_limit('crossref')
            
            cr = api_manager.clients['crossref']
            
            # Search for DOI if not already present
            if ref_info['doi']:
                # Use existing DOI with Unpaywall
                unpaywall_result = self._handle_unpaywall(ref_info, ref_info['doi'])
                if unpaywall_result.success:
                    result.url = unpaywall_result.url
                    result.success = True
                    result.metadata = {'existing_doi': ref_info['doi']}
            
            elif ref_info['title'] and len(ref_info['title']) > 5:
                # Search for DOI
                search_params = {
                    'query_bibliographic': ref_info['title'][:200],
                    'rows': 3,
                    'select': 'DOI,title,published'
                }
                
                if ref_info['author']:
                    search_params['query_author'] = ref_info['author'][:100]
                
                works = cr.works(**search_params)
                items = works.get('message', {}).get('items', [])
                
                if items:
                    # Find best match
                    for item in items:
                        doi = item.get('DOI')
                        if doi:
                            # Try Unpaywall with this DOI
                            unpaywall_result = self._handle_unpaywall(ref_info, doi)
                            if unpaywall_result.success:
                                result.url = unpaywall_result.url
                                result.success = True
                                result.metadata = {'crossref_doi': doi}
                                break
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _handle_pubmed(self, ref_info: Dict) -> SourceResult:
        """Handle PubMed/PMC API."""
        start_time = time.time()
        result = SourceResult('pubmed', False)
        
        try:
            api_manager.rate_limit('pubmed')
            
            base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
            
            # Search PubMed
            search_term = ref_info['doi'] if ref_info['doi'] else f'"{ref_info["title"]}"[Title]'
            if not search_term or search_term == '""[Title]':
                return result
            
            search_params = {
                'db': 'pubmed',
                'term': search_term,
                'retmax': 1,
                'retmode': 'json'
            }
            
            search_response = api_manager.session.get(
                f"{base_url}/esearch.fcgi", 
                params=search_params, 
                timeout=10
            )
            search_response.raise_for_status()
            search_data = search_response.json()
            
            pmid_list = search_data.get('esearchresult', {}).get('idlist', [])
            if pmid_list:
                pmid = pmid_list[0]
                
                # Check PMC availability
                link_params = {
                    'dbfrom': 'pubmed',
                    'db': 'pmc',
                    'id': pmid
                }
                
                link_response = api_manager.session.get(
                    f"{base_url}/elink.fcgi", 
                    params=link_params, 
                    timeout=10
                )
                
                if 'PMC' in link_response.text:
                    pmc_match = re.search(r'PMC(\d+)', link_response.text)
                    if pmc_match:
                        pmcid = pmc_match.group(1)
                        result.url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/pdf/"
                        result.success = True
                        result.metadata = {'pmid': pmid, 'pmcid': pmcid}
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result
    
    def _handle_core(self, ref_info: Dict) -> SourceResult:
        """Handle CORE API (UK research repository)."""
        start_time = time.time()
        result = SourceResult('core', False)
        
        try:
            api_manager.rate_limit('core')
            
            if not ref_info['title'] or len(ref_info['title']) < 10:
                return result
            
            # CORE API search
            url = "https://api.core.ac.uk/v3/search/works"
            params = {
                'q': ref_info['title'][:200],
                'limit': 1
            }
            
            response = api_manager.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            if results:
                work = results[0]
                # Look for fulltext URL
                if work.get('fulltextUrls'):
                    pdf_url = work['fulltextUrls'][0]
                    if pdf_url.endswith('.pdf'):
                        result.url = pdf_url
                        result.success = True
                        result.metadata = {'core_id': work.get('id')}
        
        except Exception as e:
            result.error = str(e)
        
        result.response_time = time.time() - start_time
        return result

def download_references_parallel(references: List[Dict], input_pdf: str) -> List[str]:
    """
    Main function to download references using the comprehensive pipeline.
    """
    if not references:
        logger.warning("No references to process")
        return ["No references found in PDF"]
    
    # Create output directory
    input_path = Path(input_pdf)
    output_dir = input_path.parent / f"{input_path.stem}{config.output_dir_suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Processing {len(references)} references into {output_dir}")
    logger.info(f"Enabled APIs: {list(config.get_enabled_apis().keys())}")
    
    # Process references in parallel
    processor = ReferenceProcessor()
    results = []
    successful_downloads = 0
    sources_used = {}
    total_response_time = 0.0
    
    with ThreadPoolExecutor(max_workers=config.max_threads) as executor:
        future_to_index = {
            executor.submit(processor.process_reference, ref, output_dir, i): i
            for i, ref in enumerate(references, 1)
        }
        
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                result = future.result()
                
                # Collect timing statistics
                for source_result in result.sources_tried:
                    total_response_time += source_result.response_time
                
                # Generate status message
                if result.status == "success":
                    successful_downloads += 1
                    source = result.source or "unknown"
                    sources_used[source] = sources_used.get(source, 0) + 1
                    status_msg = f"✅ {result.filename} (from {source})"
                elif result.status == "exists":
                    status_msg = f"📄 {result.filename} (already exists)"
                elif result.status == "error":
                    status_msg = f"❌ {result.filename} (error: {result.error})"
                else:
                    status_msg = f"❌ {result.filename} ({result.error or 'no source found'})"
                
                results.append(status_msg)
                logger.info(f"Completed {index}/{len(references)}: {status_msg}")
                
                # Log source attempts if debugging
                if config.log_api_calls and result.sources_tried:
                    for src in result.sources_tried:
                        logger.debug(f"  {src.source_name}: {src.success} ({src.response_time:.2f}s)")
                
            except Exception as e:
                error_msg = f"❌ ref_{index:03d} (processing error: {e})"
                results.append(error_msg)
                logger.error(f"Processing error for reference {index}: {e}")
    
    # Generate comprehensive summary
    summary_lines = _generate_summary(
        successful_downloads, 
        len(references), 
        sources_used, 
        total_response_time
    )
    
    results.extend(summary_lines)
    
    for line in summary_lines:
        logger.info(line)
    
    return results

def _generate_summary(successful: int, total: int, sources_used: Dict, total_time: float) -> List[str]:
    """Generate comprehensive download summary."""
    success_rate = (successful / total) * 100 if total > 0 else 0
    
    summary = [
        "",
        f"📊 Download Summary: {successful}/{total} PDFs ({success_rate:.1f}% success rate)"
    ]
    
    if sources_used:
        summary.append("📈 Sources breakdown:")
        for source, count in sorted(sources_used.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / successful) * 100 if successful > 0 else 0
            summary.append(f"   • {source}: {count} ({percentage:.1f}%)")
    
    # Performance stats
    if total_time > 0:
        avg_response_time = total_time / max(1, total)
        summary.append(f"⚡ Average API response time: {avg_response_time:.2f}s")
    
    # Recommendations based on results
    if success_rate == 0:
        summary.extend([
            "",
            "🔍 Troubleshooting suggestions:",
            "   • Check if PDF contains academic references",
            "   • Verify GROBID is running for better extraction",
            "   • Try papers from major publishers or arXiv",
            "   • Check network connectivity to APIs"
        ])
    elif success_rate < 30:
        summary.extend([
            "",
            "💡 To improve success rate:",
            "   • Enable GROBID for better reference extraction",
            "   • Check if references have DOIs or clear titles",
            "   • Try more recent papers (better OA coverage)"
        ])
    elif success_rate > 70:
        summary.append("🎉 Excellent success rate! The multi-API approach is working well.")
    
    return summary

# Backwards compatibility
def download_reference(*args, **kwargs):
    """Legacy function for backwards compatibility."""
    logger.warning("Using deprecated download_reference function")
    return None

if __name__ == "__main__":
    # Test the downloader
    print("BibP Production Downloader Test")
    print(f"Configuration: {len(config.get_enabled_apis())} APIs enabled")
    
    # Show enabled APIs
    for api_name, api_config in config.get_enabled_apis().items():
        print(f"  • {api_name}: {api_config.rate_limit}/s")
    
    print("\nReady for reference processing!")