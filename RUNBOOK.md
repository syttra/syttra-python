# PyPI publish runbook

## Pre-requisites (one-time)

- PyPI account with **2FA enabled** at <https://pypi.org/account/register/>.
- Optional: TestPyPI account for dry-runs at <https://test.pypi.org/account/register/>.
- API tokens generated at <https://pypi.org/manage/account/token/>. After the first upload claims the project name, scope the token to *project: syttra* for follow-up releases.

## Build + upload (every release)

```bash
cd syttra-python
python -m venv .venv && source .venv/bin/activate
pip install --upgrade build twine

# Build
python -m build
twine check dist/*    # both files must say PASSED

# Optional: dry-run on TestPyPI
twine upload --repository testpypi dist/* \
  --username __token__ --password 'pypi-…(testpypi token)…'

# Real upload to PyPI
twine upload dist/* \
  --username __token__ --password 'pypi-…(pypi token)…'
```

## Verify

```bash
pip install --upgrade syttra
python -c "import syttra; print(syttra.__version__)"
# 0.0.1 — emits FutureWarning while we're still on the placeholder
```

## Releasing a new version

PyPI is **append-only** — never re-upload an old filename, never delete-and-replace. Bump the `version` in `pyproject.toml`, rebuild from a clean `dist/`, upload.

When the real SDK lands (0.1.0), drop the `_placeholder_warning()` call from `src/syttra/__init__.py` along with the version bump.

## Troubleshooting

- **`HTTPError 403 — invalid or non-existent authentication`**: token is for the wrong repository (TestPyPI vs PyPI). Tokens are environment-scoped.
- **`HTTPError 400 — name 'syttra' is not allowed`**: name is taken by another account, or your account doesn't have permission. Contact PyPI support if you hit this on a name that should be yours.
- **`twine check` warns about long_description**: `pyproject.toml` declares `readme = "README.md"`, so `twine` reads it as Markdown automatically — no extra config needed.
