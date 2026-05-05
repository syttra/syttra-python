# PyPI publish runbook

Releases are automated by `.github/workflows/release.yml` — pushing a tag
like `v0.2.0` builds the dists, publishes them to PyPI via Trusted
Publishing (OIDC, no long-lived tokens), and creates a matching GitHub
release with the CHANGELOG section as release notes.

## One-time setup (PyPI Trusted Publishing)

You only need to do this once per project. After it's configured the
GitHub workflow can publish without secrets.

1. Sign in to <https://pypi.org/manage/account/publishing/> with a 2FA-
   enabled account that owns the `syttra` project.
2. Click **Add a new pending publisher** (or **Add publisher** if the
   project already exists). Fill in:

   | Field | Value |
   |---|---|
   | PyPI Project Name | `syttra` |
   | Owner | `syttra` |
   | Repository name | `syttra-python` |
   | Workflow filename | `release.yml` |
   | Environment name | `pypi` |

3. Save. PyPI now trusts our specific workflow + environment to mint
   tokens via OIDC at release time.

4. In GitHub: open <https://github.com/syttra/syttra-python/settings/environments>
   and create an environment named `pypi`. (Optional: add a manual
   approval gate or restrict it to the `main` branch / tag pattern
   `v*` — both are good defenses against an accidental push triggering
   a release.)

That's it. No `~/.pypirc`, no API tokens to rotate.

## Releasing a new version

Pre-flight on a feature/release branch:

```bash
cd syttra-python
source .venv-sdk/bin/activate
pytest                          # all green
ruff check src/ tests/          # clean
ruff format --check src/ tests/ # clean
mypy src/syttra                 # clean
```

Bump the version in `pyproject.toml` *and* `src/syttra/__init__.py`,
add a `## [X.Y.Z] — YYYY-MM-DD` section to `CHANGELOG.md`, open a PR,
get it merged.

After merge, on `main`:

```bash
git checkout main && git pull
git tag v0.2.0          # match the pyproject version exactly
git push origin v0.2.0
```

Pushing the tag triggers `release.yml`. It will:

1. Verify the tag matches the version in `pyproject.toml` (fail-fast if
   they disagree — saves you from publishing a mismatched wheel that
   you can never re-publish since PyPI is append-only).
2. Build sdist + wheel, run `twine check`.
3. Publish to PyPI via Trusted Publishing (OIDC).
4. Create a GitHub release at the tag with the CHANGELOG section as the
   body and the dists attached.

Watch the run at <https://github.com/syttra/syttra-python/actions>.
The publish job pauses for environment approval if you set that up.

## Verify the release

```bash
pip install --upgrade syttra
python -c "import syttra; print(syttra.__version__)"
# Should print the new version.
```

The PyPI page <https://pypi.org/project/syttra/> updates within ~30s of
upload.

## Manual fallback (emergencies only)

If the workflow is broken and you need to ship now, you can publish by
hand. Requires a PyPI API token scoped to the `syttra` project (create
one at <https://pypi.org/manage/account/token/>):

```bash
python -m pip install --upgrade build twine
python -m build
twine check dist/*
twine upload dist/* \
  --username __token__ --password 'pypi-…(token)…'
```

Don't do this if the workflow can do it for you — Trusted Publishing
removes a whole class of leaked-token incidents.

## Troubleshooting

- **Workflow fails at "Verify tag matches pyproject version"**: the tag
  and `pyproject.toml`'s `version` disagree. Don't try to fix it by
  re-tagging — bump the version in code, merge, then tag.
- **Workflow fails at the publish step with `permission denied`**: the
  PyPI Trusted Publishing config doesn't match (wrong owner, repo,
  workflow filename, or environment). Re-check the values in step 2 of
  the one-time setup.
- **`HTTPError 400 — File already exists`**: PyPI is append-only — you
  can't reupload the same version. Bump to a new version.
- **GitHub release notes are empty**: the CHANGELOG section header
  didn't match `## [X.Y.Z]`. Check the heading format in `CHANGELOG.md`.
