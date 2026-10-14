# Pre-commit checks

The installed Git hook runs on `git commit`. Checks use staged filenames; the
Python and auth test suites run on every commit. Lint, formatting, type, and
security findings block the commit. Whitespace/newline fixers can update files;
review and re-stage those edits before committing again.

## Setup on another checkout

```sh
uv sync --locked
npm ci
uv run --locked pre-commit install
```

Python 3.12+ and Node.js 22+ are required, along with uv and npm. Tool versions are
pinned in `pyproject.toml`/`uv.lock` and `package.json`/`package-lock.json`; local
hooks use those installed versions. Production Python installs still exclude dev
tools with `uv sync --frozen --no-dev`.

## Coverage

| Category               | Checks                                                                                                                         |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Linting and formatting | Ruff (E4/E7/E9/F), Black targeting Python 3.12, Prettier for CSS/JS/JSON/YAML/Markdown                                         |
| Type checking          | mypy on application/scripts, including untyped function bodies; test mocks excluded                                            |
| Security and secrets   | Bandit medium/high severity and confidence, detect-secrets, credential-file guard, locked dependency audit                     |
| Syntax and files       | Python AST, JavaScript syntax without execution, YAML/JSON/TOML syntax, conflict markers, oversized files, whitespace/newlines |
| Tests                  | Full offline Python unittest suite and Node auth frontend tests                                                                |

mypy skips imports and tolerates missing third-party stubs because the existing
Dash/data stack is only partly typed. It checks the submitted Python files and
untyped bodies rather than claiming full typed coverage of third-party libraries.
Bandit excludes test fixtures; secrets scanning includes them.

The dependency hook runs when `pyproject.toml` or `uv.lock` changes. It exports
locked runtime **and dev** dependencies into a temporary file and audits with
`pip-audit --strict`. Advisory access requires the network. A stale lockfile,
scanner error, or vulnerability fails the check. Existing CI separately audits
locked production dependencies.

The test wrapper overrides rate-limit environment settings to use memory storage,
including clearing the Redis URL and proxy settings. Existing tests mock external
services. It never runs ELT, dbt commands, bootstrap scripts, governance database
scripts, or creates accounts. Tests that require live services must not be added
to this offline suite.

## Generated files and secret baseline

Environment directories, agent worktrees, and generated dbt outputs are excluded.
Generated `assets/auth.js`, geographic JSON assets, and npm's lockfile are excluded
from formatting; they remain eligible for secrets and relevant syntax checks.
Intentional geographic assets and the auth bundle are exempt from the file-size
limit. `.env` variants and `gcp-key.json` are forbidden, including if force-added;
`.env.example` is permitted but still scanned for secrets.

`.secrets.baseline` contains seven reviewed false-positive fingerprints: the dbt
package digest, a recovery password fixture, two bundled library findings, a SQL
password fixture, and two synthetic credential URLs used in security tests. No
real credentials are approved. Do not regenerate or expand this baseline blindly;
review each finding first. New private-key findings still fail the hook.

## Running checks

```sh
# Normal staged-file run; both test suites also run.
uv run --locked pre-commit run

# Check a specific file, without staging it.
uv run --locked pre-commit run --files scripts/pre_commit_checks.py

# Check every tracked file (can fix existing whitespace/newline issues).
uv run --locked pre-commit run --all-files

# Format deliberately, then inspect and re-stage the changes.
uv run --locked black path/to/file.py
npm run format -- path/to/file.css
```

## Repository baseline

The initial scan findings have been resolved with formatting, explicit types,
intentional Dash registration imports, and security boundary validation. Full
repository checks and offline tests pass. SQL scanner exceptions are limited to
B608 at reviewed templates: project, analytics dataset, and staging dataset
identifiers are validated before builders/loaders execute; filter values remain
bound parameters and demographic expressions come from a fixed allowlist.
The ELT extraction query uses only the fixed table list. No global Bandit rule
has been disabled. The subprocess exceptions cover fixed CLI checks with
argument lists and no shell invocation. See [security check notes](security-checks.md).

Reference: [pre-commit's installation and staged-file behavior](https://pre-commit.com/).
