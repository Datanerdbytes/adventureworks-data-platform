# Opening pull requests without bot approval timeouts

On branch pushes other than `main`/`master`, the **Pull Request Link** workflow
publishes a **Create or view a pull request into main** link in its Actions run
summary. Open that link while signed in to GitHub, review the comparison, and
submit the PR as your account. If a PR already exists, the compare page links to
it; do not create a duplicate. You can also use GitHub's normal **Compare & pull
request** button directly after pushing.

The workflow keeps the historical filename `.github/workflows/auto-pr.yml`, but
it no longer creates PRs. It runs a local summary-writing step with
`permissions: {}`, no checkout, no API calls, and no token or new secret. Branch
names pass through an environment variable and URL encoding, not shell source.

## Why the old workflow expired

The previous workflow opened PRs with `secrets.GITHUB_TOKEN`, making
`github-actions[bot]` the author. GitHub requires approval for workflows triggered
by those automated PRs, including same-repository PRs. PR #14's audit run expired
before approval; this was not a vulnerability finding or application test failure.
The push audit and the subsequent `main` audit passed independently.

[GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token)
describes the mandatory approval behavior and token alternatives. The
[June 11, 2026 announcement](https://github.blog/changelog/2026-06-11-bot-created-pull-requests-can-run-workflows-if-approved/)
explains why bot-created PR workflows now enter this state.

Opening the PR as the repository owner avoids this bot-specific approval cause.
It does not exempt outside contributors, forks, protected environments, or other
workflows from their own approval requirements. The repository's existing fork
approval settings are retained; reducing them would not fix the token-created PR
policy.

## Checks retained

`dependency-audit.yml` remains unchanged: independent pinned Bandit and strict
locked production `pip-audit` jobs run on PRs targeting `integration`/`main`, on
pushes to those branches, and on the existing weekly schedule. PRs continue to
use ordinary `pull_request`, with `contents: read`; there is no privileged
`pull_request_target`, auto-approval workflow, or skipped scan.

The workflow change takes effect for future pushes once present on the pushed
branch. It does not erase historical failed runs. The fix itself should be opened
through the signed-in GitHub UI; no bot should open it first.
