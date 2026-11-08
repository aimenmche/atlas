## Summary

<!-- What changed, and why. Link the issue this closes. -->

Closes #

## Test plan

<!-- Check what you actually ran. Add the command or the manual step. -->

- [ ] `python -m pytest`
- [ ] `python benchmarks/run.py`
- [ ] `node --check atlas/static/app.js` (and the other bundles)
- [ ] `npm test`
- [ ] `ATLAS_E2E=1 python -m pytest tests/e2e` (UI changes)

## Screenshots

<!-- Before/after for visual changes. Remove personal data. -->

## Checklist

- [ ] The change works offline with no new runtime dependency.
- [ ] New behaviour has a test, including the rejection path where relevant.
- [ ] No secrets, customer data, or personal data are included.
- [ ] Documentation or changelog updated when behaviour is user-visible.
- [ ] Destructive operations are explicit and reversible where possible.
