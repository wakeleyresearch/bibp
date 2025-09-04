#!/usr/bin/env python3
"""
BibP v2.0 Setup and Installation Script
Automated setup with environment validation and GROBID integration.
"""

import sys
import os
import subprocess
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Color output for terminals
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def colored(text: str, color: str) -> str:
    """Add color to text if terminal supports it."""
    if os.getenv('NO_COLOR') or not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.END}"

def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{colored('=' * 60, Colors.CYAN)}")
    print(f"{colored(title, Colors.BOLD + Colors.WHITE)}")
    print(f"{colored('=' * 60, Colors.CYAN)}")

def print_step(step: str, status: str = ""):
    """Print a setup step with status."""
    if status == "OK":
        status_colored = colored("✅ OK", Colors.GREEN)
    elif status == "SKIP":
        status_colored = colored("⏭️  SKIP", Colors.YELLOW)
    elif status == "FAIL":
        status_colored = colored("❌ FAIL", Colors.RED)
    else:
        status_colored = colored("🔄 RUNNING", Colors.BLUE)
    
    print(f"{colored('•', Colors.CYAN)} {step} {status_colored}")

def check_python_version() -> bool:
    """Check if Python version is compatible."""
    version = sys.version_info
    min_version = (3, 8)
    
    if version >= min_version:
        print_step(f"Python {version.major}.{version.minor}.{version.micro}", "OK")
        return True
    else:
        print_step(f"Python {version.major}.{version.minor}.{version.micro} (need 3.8+)", "FAIL")
        return False

def check_pip() -> bool:
    """Check if pip is available and up to date."""
    try:
        import pip
        result = subprocess.run([sys.executable, '-m', 'pip', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print_step("pip available", "OK")
            return True
        else:
            print_step("pip check failed", "FAIL")
            return False
    except ImportError:
        print_step("pip not found", "FAIL")
        return False

def install_requirements(requirements_file: str = "requirements.txt") -> bool:
    """Install Python requirements."""
    if not Path(requirements_file).exists():
        print_step(f"{requirements_file} not found", "FAIL")
        return False
    
    try:
        print_step("Installing Python packages...", "")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', requirements_file, '--upgrade'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print_step("Python packages installed", "OK")
            return True
        else:
            print_step("Package installation failed", "FAIL")
            print(f"Error: {result.stderr}")
            return False
    except Exception as e:
        print_step(f"Installation error: {e}", "FAIL")
        return False

def check_docker() -> bool:
    """Check if Docker is available."""
    try:
        result = subprocess.run(['docker', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print_step("Docker available", "OK")
            return True
        else:
            print_step("Docker not found", "FAIL")
            return False
    except FileNotFoundError:
        print_step("Docker not installed", "FAIL")
        return False

def check_grobid_running() -> Tuple[bool, str]:
    """Check if GROBID is running."""
    try:
        import requests
        response = requests.get("http://localhost:8070/api/isalive", timeout=5)
        if response.status_code == 200:
            return True, "GROBID service responding"
        else:
            return False, f"GROBID returned status {response.status_code}"
    except Exception as e:
        return False, f"Cannot connect to GROBID: {e}"

def start_grobid_docker() -> bool:
    """Start GROBID using Docker."""
    try:
        print_step("Starting GROBID Docker container...", "")
        
        # Check if container already exists
        result = subprocess.run([
            'docker', 'ps', '-a', '--filter', 'name=grobid_bibp', '--format', '{{.Names}}'
        ], capture_output=True, text=True)
        
        if 'grobid_bibp' in result.stdout:
            print_step("Stopping existing GROBID container...", "")
            subprocess.run(['docker', 'stop', 'grobid_bibp'], capture_output=True)
            subprocess.run(['docker', 'rm', 'grobid_bibp'], capture_output=True)
        
        # Start new container
        cmd = [
            'docker', 'run', '-d', '--name', 'grobid_bibp', '--rm', 
            '--init', '-p', '8070:8070', 'grobid/grobid:0.8.1'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print_step("GROBID container started", "OK")
            
            # Wait for service to be ready
            print_step("Waiting for GROBID to initialize...", "")
            for i in range(30):  # Wait up to 30 seconds
                is_running, msg = check_grobid_running()
                if is_running:
                    print_step("GROBID service ready", "OK")
                    return True
                time.sleep(1)
            
            print_step("GROBID startup timeout", "FAIL")
            return False
        else:
            print_step("Failed to start GROBID container", "FAIL")
            print(f"Error: {result.stderr}")
            return False
            
    except Exception as e:
        print_step(f"Docker error: {e}", "FAIL")
        return False

def create_config_file() -> bool:
    """Create or update configuration file."""
    try:
        config_content = """# BibP v2.0 Configuration
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
"""
        
        config_file = Path("bibp_config.sh")
        with open(config_file, 'w') as f:
            f.write(config_content)
        
        print_step(f"Configuration template created: {config_file}", "OK")
        return True
        
    except Exception as e:
        print_step(f"Config creation failed: {e}", "FAIL")
        return False

def test_installation() -> Dict[str, bool]:
    """Test the installation by importing all modules."""
    results = {}
    
    test_modules = {
        'config': 'Configuration management',
        'extractor': 'Reference extraction', 
        'downloader': 'Multi-API downloader',
        'grobid_client': 'GROBID integration',
        'gui': 'GUI interface'
    }
    
    for module_name, description in test_modules.items():
        try:
            __import__(module_name)
            print_step(f"{description} module", "OK")
            results[module_name] = True
        except ImportError as e:
            print_step(f"{description} module: {e}", "FAIL")
            results[module_name] = False
        except Exception as e:
            print_step(f"{description} module error: {e}", "FAIL")
            results[module_name] = False
    
    return results

def create_desktop_shortcut() -> bool:
    """Create desktop shortcut for BibP (Windows/Linux)."""
    try:
        current_dir = Path.cwd()
        
        if sys.platform == "win32":
            # Windows shortcut (.bat file)
            shortcut_content = f"""@echo off
cd /d "{current_dir}"
python main.py
pause
"""
            shortcut_path = Path.home() / "Desktop" / "BibP.bat"
            
        else:
            # Linux desktop entry
            shortcut_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=BibP Reference Retriever
Comment=Automatically download academic PDFs from references
Exec=python3 {current_dir / 'main.py'}
Icon={current_dir / 'icon.png'}
Path={current_dir}
Terminal=false
Categories=Office;Education;Science;
"""
            shortcut_path = Path.home() / "Desktop" / "BibP.desktop"
        
        with open(shortcut_path, 'w') as f:
            f.write(shortcut_content)
        
        if sys.platform != "win32":
            # Make executable on Linux
            os.chmod(shortcut_path, 0o755)
        
        print_step(f"Desktop shortcut created: {shortcut_path.name}", "OK")
        return True
        
    except Exception as e:
        print_step(f"Desktop shortcut failed: {e}", "FAIL")
        return False

def print_usage_guide():
    """Print usage instructions."""
    print_header("🚀 BibP v2.0 Usage Guide")
    
    usage_text = f"""
{colored('Basic Usage:', Colors.BOLD)}
• GUI Mode: {colored('python main.py', Colors.GREEN)}
• CLI Mode: {colored('python main.py --cli paper.pdf', Colors.GREEN)}
• Test Setup: {colored('python main.py --test', Colors.GREEN)}

{colored('Configuration:', Colors.BOLD)}
• Edit bibp_config.sh with your email and API keys
• Run: {colored('source bibp_config.sh', Colors.GREEN)} (Linux/Mac)
• Or set environment variables manually

{colored('GROBID (Recommended):', Colors.BOLD)}
• Provides superior reference extraction
• Already started if Docker setup succeeded
• Access at: {colored('http://localhost:8070', Colors.CYAN)}

{colored('API Keys (Optional but Recommended):', Colors.BOLD)}
• Semantic Scholar: https://www.semanticscholar.org/product/api
• Improves rate limits and access to premium features

{colored('Troubleshooting:', Colors.BOLD)}
• Check logs in the GUI or run with --verbose
• Test individual components with python main.py --test
• Analyze PDFs with python main.py --diagnose paper.pdf

{colored('Support:', Colors.BOLD)}
• GitHub: https://github.com/your-repo/bibp
• Documentation: See README.md
"""
    
    print(usage_text)

def main():
    """Main setup function."""
    parser = argparse.ArgumentParser(description="BibP v2.0 Setup Script")
    parser.add_argument('--skip-packages', action='store_true',
                       help='Skip Python package installation')
    parser.add_argument('--skip-grobid', action='store_true', 
                       help='Skip GROBID Docker setup')
    parser.add_argument('--skip-test', action='store_true',
                       help='Skip installation testing')
    parser.add_argument('--no-shortcut', action='store_true',
                       help='Skip desktop shortcut creation')
    
    args = parser.parse_args()
    
    print_header("🔧 BibP v2.0 Setup & Installation")
    
    setup_success = True
    
    # Check prerequisites
    print_header("📋 Checking Prerequisites")
    
    if not check_python_version():
        print(f"\n{colored('❌ Python 3.8+ is required. Please upgrade Python.', Colors.RED)}")
        return 1
    
    if not check_pip():
        print(f"\n{colored('❌ pip is required. Please install pip.', Colors.RED)}")
        return 1
    
    # Install Python packages
    if not args.skip_packages:
        print_header("📦 Installing Python Packages")
        if not install_requirements():
            setup_success = False
            print(f"\n{colored('⚠️ Package installation failed. Try manually: pip install -r requirements.txt', Colors.YELLOW)}")
    else:
        print_header("📦 Skipping Package Installation")
    
    # Setup GROBID
    if not args.skip_grobid:
        print_header("🔬 Setting up GROBID")
        
        if check_docker():
            is_running, msg = check_grobid_running()
            
            if is_running:
                print_step("GROBID already running", "OK")
            else:
                if not start_grobid_docker():
                    setup_success = False
                    print(f"\n{colored('⚠️ GROBID setup failed. You can start it manually:', Colors.YELLOW)}")
                    print(f"{colored('docker run --rm --init -p 8070:8070 grobid/grobid:0.8.1', Colors.CYAN)}")
        else:
            print(f"\n{colored('⚠️ Docker not found. GROBID requires Docker.', Colors.YELLOW)}")
            print(f"Install Docker and run: {colored('docker run --rm --init -p 8070:8070 grobid/grobid:0.8.1', Colors.CYAN)}")
            setup_success = False
    else:
        print_header("🔬 Skipping GROBID Setup")
    
    # Create configuration
    print_header("⚙️ Creating Configuration")
    create_config_file()
    
    # Test installation
    if not args.skip_test:
        print_header("🧪 Testing Installation")
        test_results = test_installation()
        
        failed_tests = [name for name, success in test_results.items() if not success]
        if failed_tests:
            print(f"\n{colored('⚠️ Some components failed to load:', Colors.YELLOW)} {', '.join(failed_tests)}")
            setup_success = False
        else:
            print_step("All components loaded successfully", "OK")
    
    # Create desktop shortcut
    if not args.no_shortcut:
        print_header("🖥️ Creating Desktop Shortcut")
        create_desktop_shortcut()
    
    # Final status and usage guide
    if setup_success:
        print(f"\n{colored('🎉 BibP v2.0 Setup Complete!', Colors.BOLD + Colors.GREEN)}")
        print_usage_guide()
        
        print(f"\n{colored('Quick Start:', Colors.BOLD)}")
        print(f"1. {colored('python main.py', Colors.GREEN)} - Launch BibP")
        print(f"2. Drag & drop a PDF file")
        print(f"3. Click 'Start Processing'")
        
        return 0
    else:
        print(f"\n{colored('⚠️ Setup completed with some issues.', Colors.YELLOW)}")
        print(f"BibP should still work, but some features may be limited.")
        print(f"Run {colored('python main.py --test', Colors.CYAN)} to diagnose issues.")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())