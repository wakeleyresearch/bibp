"""
BibP Configuration Template
Copy this file to config.py and fill in your actual values before running.

SETUP REQUIRED:
1. Replace 'YOUR_EMAIL_HERE' with your actual email address
2. Get a Semantic Scholar API key from: https://www.semanticscholar.org/product/api
3. Replace 'YOUR_SEMANTIC_SCHOLAR_API_KEY_HERE' with your actual key
"""

import os
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class APIConfig:
    """Configuration for individual APIs."""
    enabled: bool = True
    rate_limit: float = 1.0  # requests per second
    timeout: int = 15
    retries: int = 3
    priority: int = 5  # lower = higher priority

@dataclass
class BibPConfig:
    """Main BibP configuration with validation."""
    
    # Core Settings
    max_threads: int = 4
    output_dir_suffix: str = "_refs"
    min_pdf_size: int = 1000  # bytes
    
    # SETUP REQUIRED: Replace with your email address
    contact_email: str = "YOUR_EMAIL_HERE"
    
    # API Credentials - will be set from environment variable
    semantic_scholar_api_key: Optional[str] = None
    
    # GROBID Settings
    grobid_url: str = "http://localhost:8070"
    grobid_enabled: bool = True
    
    # API Configurations
    apis: Dict[str, APIConfig] = field(default_factory=lambda: {
        'arxiv': APIConfig(enabled=True, rate_limit=10.0, priority=1),
        'unpaywall': APIConfig(enabled=True, rate_limit=5.0, priority=2),  
        'openalex': APIConfig(enabled=True, rate_limit=10.0, priority=3),
        'semantic_scholar': APIConfig(enabled=True, rate_limit=0.8, priority=4),
        'crossref': APIConfig(enabled=True, rate_limit=2.0, priority=5),
        'pubmed': APIConfig(enabled=True, rate_limit=3.0, priority=6),
        'core': APIConfig(enabled=False, rate_limit=1.0, priority=7),  # Optional
    })
    
    # Quality Thresholds
    min_title_length: int = 10
    min_reference_quality_score: float = 0.3
    max_filename_length: int = 150
    
    # Logging
    log_level: str = "INFO"
    log_api_calls: bool = False
    log_to_file: bool = True
    
    @classmethod
    def from_environment(cls) -> 'BibPConfig':
        """Create configuration from environment variables with fallbacks."""
        config = cls()
        
        # Core settings
        config.max_threads = int(os.getenv('BIBP_MAX_THREADS', config.max_threads))
        config.contact_email = os.getenv('BIBP_EMAIL', config.contact_email)
        config.output_dir_suffix = os.getenv('BIBP_OUTPUT_SUFFIX', config.output_dir_suffix)
        
        # SETUP REQUIRED: Set your API key here or via environment variable
        config.semantic_scholar_api_key = os.getenv('SEMANTIC_SCHOLAR_API_KEY', 'YOUR_SEMANTIC_SCHOLAR_API_KEY_HERE')
        
        # GROBID settings
        config.grobid_url = os.getenv('GROBID_URL', config.grobid_url)
        config.grobid_enabled = os.getenv('GROBID_ENABLED', 'true').lower() == 'true'
        
        # Logging
        config.log_level = os.getenv('BIBP_LOG_LEVEL', config.log_level)
        config.log_api_calls = os.getenv('BIBP_LOG_API_CALLS', 'false').lower() == 'true'
        
        # API-specific rate limits
        for api_name in config.apis:
            env_var = f'BIBP_{api_name.upper()}_RATE'
            if env_var in os.environ:
                config.apis[api_name].rate_limit = float(os.environ[env_var])
            
            env_var = f'BIBP_{api_name.upper()}_ENABLED'
            if env_var in os.environ:
                config.apis[api_name].enabled = os.environ[env_var].lower() == 'true'
        
        return config
    
    def validate(self) -> tuple[bool, list[str]]:
        """Validate configuration and return (is_valid, warnings)."""
        warnings = []
        is_valid = True
        
        # Required settings
        if not self.contact_email or '@' not in self.contact_email or self.contact_email == "YOUR_EMAIL_HERE":
            warnings.append("❌ Invalid contact email - required for API access")
            is_valid = False
        
        # API key check
        if not self.semantic_scholar_api_key or self.semantic_scholar_api_key == "YOUR_SEMANTIC_SCHOLAR_API_KEY_HERE":
            warnings.append("⚠️ No Semantic Scholar API key configured")
        
        # Thread limits
        if self.max_threads < 1 or self.max_threads > 100:
            warnings.append(f"⚠️ max_threads should be 1-100, got {self.max_threads}")
            self.max_threads = max(1, min(100, self.max_threads))
        
        # GROBID connectivity
        if self.grobid_enabled:
            try:
                import requests
                response = requests.get(f"{self.grobid_url}/api/isalive", timeout=5)
                if response.status_code != 200:
                    warnings.append(f"⚠️ GROBID not responding at {self.grobid_url}")
            except Exception:
                warnings.append(f"⚠️ Cannot connect to GROBID at {self.grobid_url}")
        
        enabled_apis = [name for name, api in self.apis.items() if api.enabled]
        if len(enabled_apis) < 3:
            warnings.append(f"⚠️ Only {len(enabled_apis)} APIs enabled - may reduce success rate")
        
        return is_valid, warnings
    
    def setup_logging(self) -> None:
        """Configure logging based on settings."""
        log_level = getattr(logging, self.log_level.upper(), logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        
        # File handler if enabled
        handlers = [console_handler]
        if self.log_to_file:
            log_file = Path.home() / '.bibp' / 'bibp.log'
            log_file.parent.mkdir(exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(log_level)
            handlers.append(file_handler)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        for handler in handlers:
            handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.handlers = handlers
    
    def get_enabled_apis(self) -> Dict[str, APIConfig]:
        """Get enabled APIs sorted by priority."""
        enabled = {name: api for name, api in self.apis.items() if api.enabled}
        return dict(sorted(enabled.items(), key=lambda x: x[1].priority))
    
    def print_summary(self) -> None:
        """Print configuration summary."""
        print("🔧 BibP Configuration Summary")
        print("=" * 50)
        print(f"Max threads: {self.max_threads}")
        print(f"Contact email: {self.contact_email}")
        print(f"GROBID: {'✅ Enabled' if self.grobid_enabled else '❌ Disabled'} ({self.grobid_url})")
        print(f"S2 API key: {'✅ Present' if self.semantic_scholar_api_key and self.semantic_scholar_api_key != 'YOUR_SEMANTIC_SCHOLAR_API_KEY_HERE' else '❌ Missing'}")
        
        print(f"\nEnabled APIs ({len(self.get_enabled_apis())}):")
        for name, api in self.get_enabled_apis().items():
            print(f"  • {name}: {api.rate_limit}/s (priority {api.priority})")
        
        print()

# Global configuration instance
config = BibPConfig.from_environment()

# Legacy compatibility for existing code
SEMANTIC_SCHOLAR_API_KEY = config.semantic_scholar_api_key
UNPAYWALL_EMAIL = config.contact_email  
CROSSREF_EMAIL = config.contact_email
MAX_THREADS = config.max_threads
RETRY_ATTEMPTS = 3
OUTPUT_DIR_SUFFIX = config.output_dir_suffix

# Initialize logging
config.setup_logging()

if __name__ == "__main__":
    # Validate and show config when run directly
    is_valid, warnings = config.validate()
    
    config.print_summary()
    
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  {warning}")
    
    if is_valid:
        print("✅ Configuration is valid")
    else:
        print("❌ Configuration has errors")