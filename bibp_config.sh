# BibP v2.0 Configuration
# Environment variables for BibP configuration

# Core settings
export BIBP_MAX_THREADS=4
export BIBP_EMAIL="your-email@domain.com"

# API credentials (optional but recommended)
export SEMANTIC_SCHOLAR_API_KEY="your-s2-api-key"

# GROBID settings
export GROBID_URL="http://localhost:8070"
export GROBID_ENABLED="true"

# API rate limits (requests per second)
export BIBP_SEMANTIC_SCHOLAR_RATE=0.8
export BIBP_CROSSREF_RATE=2.0
export BIBP_UNPAYWALL_RATE=5.0
export BIBP_OPENALEX_RATE=10.0

# Logging
export BIBP_LOG_LEVEL="INFO"
export BIBP_LOG_API_CALLS="false"

# To use this configuration, run: source bibp_config.sh
