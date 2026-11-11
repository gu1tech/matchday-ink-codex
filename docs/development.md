# Development and verification

Use Python 3.11+ and install `.[dev,ai,device]` in a virtual environment.

```sh
python -m ruff check src tests scripts
python -m pytest -q
python -m build
```

Install the resulting wheel in a separate virtual environment and run the demo outside the source directory. This checks packaged fonts/icons instead of accidentally relying on the source tree. Firmware compilation uses Arduino CLI and esp32 core 3.3.12; see getting started.

Tests exercise fixture validation, providers, standings identity, lifecycle/restart/buffer policy, prediction, AI caching/errors, USB configuration validation, status icons and framebuffer encoding. Native C++ helper tests need a C++ compiler; inspect skips rather than treating skipped tests as hardware verification.

## Before tagging a release

- Review the candidate diff and third-party notices.
- Scan both repository files and Git history for secrets before publishing existing history.
- Run Python tests, lint, package installation and firmware compilation.
- Complete a fresh setup with no previous settings.
- Verify power reconnection, unavailable-server behaviour and physical display updates.
- Test logout/login startup on macOS.
- Add a real finished-device photograph; current images are labelled previews.
- Run GitHub CI and link actual results before adding a passing badge.

Existing physical acceptance came from the assembled prototype. It does not imply that the renamed startup installer has been exercised or that this candidate has been flashed. See `verification.md` for checks performed on this copy.
