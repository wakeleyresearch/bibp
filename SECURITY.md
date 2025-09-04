# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | ✅ Yes            |
| < 2.0   | ❌ No             |

## Reporting a Vulnerability

### How to Report

**For security vulnerabilities, please do NOT create a public issue.**

Instead, please report security issues by:
1. Using GitHub's private vulnerability reporting feature
2. Emailing the maintainers directly
3. Opening a discussion marked as security-related

### What to Include

Please provide:
- Clear description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Any suggested fixes or mitigations
- Your contact information for follow-up

### Response Process

- **Acknowledgment**: Within 72 hours
- **Initial assessment**: Within 1 week  
- **Status updates**: Weekly until resolved
- **Fix deployment**: Based on severity assessment
- **Public disclosure**: After fix is available

## Security Scope

### In Scope
- BibP application code
- Configuration handling
- API key management
- File system operations
- Network communications

### Out of Scope
- Third-party APIs (Semantic Scholar, OpenAlex, etc.)
- GROBID Docker container
- User's local system security
- PDF content from downloaded papers

## Known Security Considerations

### API Key Protection
- API keys are stored in local config files only
- No transmission of API keys to unauthorized services
- Keys should be rotated if potentially compromised

### Downloaded Content
- PDFs are validated for type and size before saving
- No execution of downloaded content
- Files saved to user-specified directories only

### Network Security
- All API communications use HTTPS
- No sensitive user data transmitted
- Rate limiting prevents service abuse

### Data Privacy
- No personal data collected or transmitted
- Local processing only
- No telemetry or usage tracking

## Best Practices for Users

1. **Protect your API keys**: Never share or commit API keys
2. **Use trusted networks**: Avoid public WiFi for API-intensive operations
3. **Keep software updated**: Use the latest version of BibP
4. **Verify downloads**: Check downloaded PDFs before opening
5. **Monitor usage**: Be aware of your API rate limits

## Disclosure Timeline

For critical vulnerabilities:
- **Day 0**: Report received
- **Day 1-3**: Acknowledgment and initial triage
- **Day 7**: Assessment complete, timeline established
- **Day 30**: Target fix completion (may vary by complexity)
- **Post-fix**: Public disclosure after users can update

## Contact

For security concerns that don't require private reporting, you can also create a discussion in the repository.
