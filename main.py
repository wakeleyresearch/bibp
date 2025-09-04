#!/usr/bin/env python3
"""
BibP - Reference PDF Retriever v2.0
Production entry point with enhanced error handling and diagnostics.
"""

import sys
import os
import logging
import argparse
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt
except ImportError:
    print("❌ Error: PyQt6 not installed. Please run: pip install PyQt6")
    sys.exit(1)

from config import config
from gui import MainWindow

logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if all required dependencies are available."""
    missing_deps = []
    optional_deps = []
    
    # Required dependencies
    required = {
        'requests': 'HTTP requests',
        'pathlib': 'Path handling (built-in)',
        'threading': 'Threading support (built-in)',
        'concurrent.futures': 'Parallel processing (built-in)'
    }
    
    for module, description in required.items():
        try:
            __import__(module)
        except ImportError:
            if 'built-in' not in description:
                missing_deps.append(f"{module} ({description})")
    
    # Optional but recommended
    optional = {
        'refextract': 'Reference extraction fallback',
        'semanticscholar': 'Semantic Scholar API',
        'habanero': 'Crossref API',
        'tenacity': 'Retry logic'
    }
    
    for module, description in optional.items():
        try:
            __import__(module)
        except ImportError:
            optional_deps.append(f"{module} ({description})")
    
    return missing_deps, optional_deps

def check_grobid_connection():
    """Check if GROBID service is accessible."""
    if not config.grobid_enabled:
        return False, "GROBID disabled in configuration"
    
    try:
        import requests
        response = requests.get(f"{config.grobid_url}/api/isalive", timeout=5)
        if response.status_code == 200:
            return True, "GROBID service is accessible"
        else:
            return False, f"GROBID returned status {response.status_code}"
    except Exception as e:
        return False, f"Cannot connect to GROBID: {e}"

def show_startup_diagnostics():
    """Show startup diagnostics and configuration."""
    print("🔍 BibP v2.0 Startup Diagnostics")
    print("=" * 50)
    
    # Check dependencies
    missing, optional_missing = check_dependencies()
    
    if missing:
        print("❌ Missing required dependencies:")
        for dep in missing:
            print(f"   • {dep}")
        print("\nPlease install missing dependencies and try again.")
        return False
    else:
        print("✅ All required dependencies found")
    
    if optional_missing:
        print("⚠️  Missing optional dependencies:")
        for dep in optional_missing:
            print(f"   • {dep}")
        print("   (BibP will work with reduced functionality)")
    
    # Check GROBID
    grobid_ok, grobid_msg = check_grobid_connection()
    status_icon = "✅" if grobid_ok else "⚠️ "
    print(f"{status_icon} GROBID: {grobid_msg}")
    
    # Show API configuration
    enabled_apis = config.get_enabled_apis()
    print(f"🔧 {len(enabled_apis)} APIs enabled: {', '.join(enabled_apis.keys())}")
    
    # Configuration validation
    is_valid, warnings = config.validate()
    if warnings:
        print("⚠️  Configuration warnings:")
        for warning in warnings:
            print(f"   • {warning}")
    else:
        print("✅ Configuration is valid")
    
    print("=" * 50)
    return True

def create_cli_parser():
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="BibP - Reference PDF Retriever v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Launch GUI
  %(prog)s --cli paper.pdf           # CLI mode for single PDF
  %(prog)s --test                    # Test configuration
  %(prog)s --diagnose paper.pdf      # Analyze reference extraction
        """
    )
    
    parser.add_argument('--cli', metavar='PDF', 
                       help='Run in CLI mode for single PDF')
    parser.add_argument('--test', action='store_true',
                       help='Test API connectivity and configuration')
    parser.add_argument('--diagnose', metavar='PDF',
                       help='Analyze reference extraction quality')
    parser.add_argument('--method', choices=['auto', 'grobid', 'refextract'],
                       default='auto', help='Reference extraction method')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Enable verbose logging')
    parser.add_argument('--no-gui-check', action='store_true',
                       help='Skip GUI availability check')
    
    return parser

def run_cli_mode(pdf_path: str, extraction_method: str = 'auto'):
    """Run BibP in CLI mode for a single PDF."""
    print(f"📖 Processing {pdf_path} in CLI mode...")
    
    try:
        from extractor import extract_references
        from downloader import download_references_parallel
        
        # Extract references
        method = None if extraction_method == 'auto' else extraction_method
        references = extract_references(pdf_path, force_method=method)
        
        if not references:
            print("❌ No references found in PDF")
            return 1
        
        print(f"📚 Found {len(references)} references")
        
        # Download PDFs
        results = download_references_parallel(references, pdf_path)
        
        # Print results
        success_count = 0
        for result in results:
            print(result)
            if result.startswith("✅"):
                success_count += 1
        
        print(f"\n🎉 CLI processing complete: {success_count} PDFs downloaded")
        return 0
        
    except Exception as e:
        print(f"❌ CLI processing failed: {e}")
        logger.error(f"CLI error: {e}")
        return 1

def run_test_mode():
    """Test API connectivity and configuration."""
    print("🧪 Testing BibP Configuration and APIs...")
    
    try:
        # Test imports
        print("\n📦 Testing imports...")
        test_modules = [
            ('extractor', 'Reference extraction'),
            ('downloader', 'Multi-API downloader'), 
            ('grobid_client', 'GROBID integration'),
            ('config', 'Configuration management')
        ]
        
        for module_name, description in test_modules:
            try:
                __import__(module_name)
                print(f"   ✅ {description}")
            except Exception as e:
                print(f"   ❌ {description}: {e}")
        
        # Test configuration
        print(f"\n⚙️  Testing configuration...")
        is_valid, warnings = config.validate()
        if is_valid:
            print("   ✅ Configuration is valid")
        else:
            print("   ❌ Configuration has errors")
        
        for warning in warnings:
            print(f"   ⚠️  {warning}")
        
        # Test GROBID
        print(f"\n🔬 Testing GROBID...")
        grobid_ok, grobid_msg = check_grobid_connection()
        print(f"   {'✅' if grobid_ok else '❌'} {grobid_msg}")
        
        # Test API connectivity (basic)
        print(f"\n🌐 Testing API connectivity...")
        import requests
        
        test_urls = [
            ('OpenAlex', 'https://api.openalex.org/works?per-page=1'),
            ('Unpaywall', f'https://api.unpaywall.org/v2/10.1038/nature12373?email={config.contact_email}'),
            ('arXiv', 'https://arxiv.org/api/query?search_query=cat:cs.AI&max_results=1'),
        ]
        
        for api_name, test_url in test_urls:
            try:
                response = requests.get(test_url, timeout=10)
                if response.status_code == 200:
                    print(f"   ✅ {api_name} API responding")
                else:
                    print(f"   ⚠️  {api_name} API returned {response.status_code}")
            except Exception as e:
                print(f"   ❌ {api_name} API failed: {e}")
        
        print(f"\n✅ Test complete! Check results above.")
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return 1

def run_diagnose_mode(pdf_path: str):
    """Analyze reference extraction for a PDF."""
    print(f"🔍 Diagnosing reference extraction for {pdf_path}...")
    
    try:
        from extractor import extract_references, analyze_extraction_quality
        
        # Test both extraction methods
        methods = ['auto']
        if config.grobid_enabled:
            methods.extend(['grobid', 'refextract'])
        
        for method in methods:
            print(f"\n📖 Testing {method} extraction...")
            
            extraction_method = None if method == 'auto' else method
            references = extract_references(pdf_path, force_method=extraction_method)
            
            if not references:
                print(f"   ❌ No references found with {method}")
                continue
            
            analysis = analyze_extraction_quality(references)
            
            print(f"   📊 Found {len(references)} references")
            print(f"   🎯 Quality score: {analysis['quality_score']:.2f}")
            print(f"   📝 Titles: {analysis['percentages']['has_title']:.1f}%")
            print(f"   🏷️  DOIs: {analysis['percentages']['has_doi']:.1f}%")
            print(f"   👥 Authors: {analysis['percentages']['has_authors']:.1f}%")
            
            if analysis['issues']:
                print(f"   ⚠️  Issues: {', '.join(analysis['issues'])}")
            
            print(f"   💡 {analysis['recommendation']}")
            
            # Show sample references
            print(f"   📄 Sample references:")
            for i, ref in enumerate(references[:3], 1):
                title = ref.get('title', '')[:60] + '...' if len(ref.get('title', '')) > 60 else ref.get('title', 'No title')
                doi = f" (DOI: {ref.get('doi', '')})" if ref.get('doi', '') else ""
                print(f"      {i}. {title}{doi}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Diagnosis failed: {e}")
        logger.error(f"Diagnosis error: {e}")
        return 1

def main():
    """Main entry point."""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    # Set up logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
        config.log_api_calls = True
    else:
        logging.basicConfig(level=logging.WARNING)
    
    # Show startup diagnostics
    if not args.no_gui_check:
        if not show_startup_diagnostics():
            return 1
    
    # Handle different modes
    if args.test:
        return run_test_mode()
    
    if args.diagnose:
        if not Path(args.diagnose).exists():
            print(f"❌ File not found: {args.diagnose}")
            return 1
        return run_diagnose_mode(args.diagnose)
    
    if args.cli:
        if not Path(args.cli).exists():
            print(f"❌ File not found: {args.cli}")
            return 1
        return run_cli_mode(args.cli, args.method)
    
    # Default: GUI mode
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("BibP")
        app.setApplicationVersion("2.0")
        
        # Set application properties
        app.setStyle("Fusion")
        app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
        
        # Show startup message
        startup_msg = QMessageBox()
        startup_msg.setWindowTitle("BibP v2.0")
        startup_msg.setIcon(QMessageBox.Icon.Information)
        
        enabled_apis = len(config.get_enabled_apis())
        grobid_status = "✅ Connected" if config.grobid_enabled else "❌ Disabled"
        
        startup_text = f"""
BibP v2.0 is ready!

Configuration:
• {enabled_apis} APIs enabled
• GROBID: {grobid_status}
• Max threads: {config.max_threads}

Ready to process academic PDFs and find open access versions of references.
        """
        
        startup_msg.setText(startup_text.strip())
        startup_msg.exec()
        
        # Create and show main window
        window = MainWindow()
        window.show()
        
        return app.exec()
        
    except ImportError as e:
        print(f"❌ GUI not available: {e}")
        print("💡 Try CLI mode: python main.py --cli your_paper.pdf")
        return 1
    except Exception as e:
        print(f"❌ Failed to start GUI: {e}")
        logger.error(f"GUI startup error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())