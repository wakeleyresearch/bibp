# Pull Request Template

## Create this file as .github/pull_request_template.md


## Description

**What does this PR do?**
Provide a clear and concise description of the changes.

**Why is this change needed?**
Explain the problem this PR solves or the feature it adds.

## Type of Change

Please check the relevant option:

- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] ✨ New feature (non-breaking change that adds functionality)  
- [ ] 💥 Breaking change (fix or feature that causes existing functionality to change)
- [ ] 📚 Documentation update
- [ ] 🔧 Code refactoring (no functional changes)
- [ ] ⚡ Performance improvement
- [ ] 🧪 Test coverage improvement

## Changes Made

**Core Changes:**
- [ ] Modified extractor logic
- [ ] Updated downloader functionality
- [ ] Changed GUI components
- [ ] Added new API integration
- [ ] Updated configuration options
- [ ] Modified CLI interface

**Files Changed:**
- `filename.py`: Brief description of changes
- `other_file.py`: Brief description of changes

## API Integration (if applicable)

- **New API added**: [API name]
- **Rate limiting**: [X requests/second]
- **Authentication**: [API key/none]
- **Priority level**: [1-7, where does it fit in the chain]
- **Expected coverage**: [what types of papers will this help with]

## Testing

**Testing completed:**
- [ ] `python main.py --test` passes
- [ ] Tested with sample PDFs (list domains tested)
- [ ] GUI functionality verified
- [ ] CLI mode tested
- [ ] Configuration changes tested
- [ ] New features work as expected
- [ ] No regression in existing functionality

**Test Results:**
- **PDFs tested**: [number and types]
- **Success rate impact**: [before/after if measurable]
- **Performance impact**: [faster/slower/no change]

**Test Environment:**
- **OS**: [Windows/macOS/Linux]
- **Python version**: [3.x]
- **GROBID status**: [running/tested without]

## Documentation

- [ ] Updated README.md (if user-facing changes)
- [ ] Updated config_template.py (if new config options)
- [ ] Added/updated function docstrings
- [ ] Updated API table in README (if new API)
- [ ] Updated troubleshooting section (if relevant)

## Code Quality

- [ ] Code follows existing style patterns
- [ ] Added appropriate error handling
- [ ] Added logging where appropriate
- [ ] No hardcoded values (use configuration)
- [ ] Type hints added for new functions
- [ ] Comments added for complex logic

## Security Checklist

- [ ] No API keys or sensitive data in code
- [ ] Input validation added where needed
- [ ] No security vulnerabilities introduced
- [ ] Rate limiting properly implemented (for API changes)
- [ ] Error messages don't expose sensitive information

## Breaking Changes

**Does this PR introduce breaking changes?**
- [ ] No breaking changes
- [ ] Yes, breaking changes (describe below)

**If yes, describe the breaking changes:**
- What will break?
- How can users migrate?
- What's the upgrade path?

## Performance Impact

- [ ] No performance impact
- [ ] Performance improvement
- [ ] Potential performance degradation (explain why necessary)

**If performance changes:**
- Benchmarks before/after
- Memory usage impact
- Network usage impact

## Related Issues

- Closes #[issue number]
- Related to #[issue number]
- Addresses part of #[issue number]

## Reviewer Notes

**Areas that need special attention:**
- Specific files or functions to review carefully
- Potential edge cases to consider
- Integration points to verify

**Questions for reviewers:**
- Any specific concerns about the implementation?
- Suggestions for alternative approaches?

## Deployment Notes

**Any special deployment considerations:**
- [ ] Requires GROBID restart
- [ ] Requires new dependencies
- [ ] Requires configuration changes
- [ ] Requires API key updates

## Screenshots (if UI changes)

Before:
[Screenshot or description]

After:
[Screenshot or description]

---

**Checklist before submitting:**
- [ ] I have tested this thoroughly
- [ ] I have updated relevant documentation  
- [ ] I have considered security implications
- [ ] I have followed the project's coding standards
- [ ] I understand this will be reviewed by maintainers
```
