# Contributing to BibP

Thank you for your interest in contributing to BibP! This document provides guidelines for contributing to the project.

## Ways to Contribute

### 🐛 Bug Reports
- Use the bug report template
- Include steps to reproduce
- Provide system information (OS, Python version, etc.)
- Include log files if available

### 💡 Feature Requests
- Use the feature request template
- Explain the use case clearly
- Consider if it fits the project scope

### 🔧 Code Contributions
- Fork the repository
- Create a feature branch: `git checkout -b feature-name`
- Make your changes
- Test thoroughly
- Submit a pull request

## Development Setup

```bash
# Clone your fork
git clone https://github.com/yourusername/bibp.git
cd bibp

# Install dependencies
pip install -r requirements.txt

# Copy configuration template
cp config_template.py config.py
# Edit config.py with your credentials

# Start GROBID
docker run --rm --init -p 8070:8070 grobid/grobid:0.8.1

# Test your setup
python main.py --test
