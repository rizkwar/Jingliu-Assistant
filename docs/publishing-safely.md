# Publishing without local data

`.env`, local conversations/preferences, recordings, voice samples, artwork
projects, caches, databases, private keys and backups are excluded from Git.
`.env.example` contains blank credential settings, never your real keys.

Before pushing, run:

```powershell
.\.venv\Scripts\python.exe scripts/check_publish_safety.py --history --compare-local-env
```

The optional local comparison reads configured credential values in memory and
compares them against indexed files and reachable history. It does not print them.
The check also detects common credential formats, private file paths, absolute
user-home paths, contact emails and personal commit metadata. Test/example-domain
emails and GitHub no-reply addresses are allowed.

Use your GitHub handle for the author name and the no-reply address shown in
**GitHub Settings → Emails** for the author email. Configure them for this
repository, rather than changing your global Git identity.

Enable the included local push hook with:

```powershell
git config --local core.hooksPath .githooks
```

The hook checks reachable history before a push and also runs Gitleaks if it is
available in the project's audit cache or PATH. The GitHub Actions workflow
independently runs the checks and a checksum-pinned Gitleaks scan. It prints
finding categories/locations with sensitive values redacted, and does not upload
scan reports. The workflow checks a push after it arrives; local hooks and
GitHub's secret push protection provide checks before publication.

Review `git diff --cached` and `git diff --cached --name-only` too: automated
patterns cannot identify every kind of private information in arbitrary prose.
Do not force-add ignored local files or put real conversations in examples.
Character profiles in this repository are editable examples, not user-memory
exports; custom profiles and conversations live under ignored `data/`.

The privacy cleanup preserves the application history with anonymized author
metadata. A local pre-cleanup bundle remains under ignored `.cache/privacy-audit/`;
it is for recovery and must not be published. Old commit IDs change when metadata
is rewritten. Avoid merging an old clone's history back into the cleaned branch.

GitHub may retain old commit URLs and cached views after a history rewrite.
Full server-side removal can require GitHub Support; see
[GitHub's removal guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository#fully-removing-the-data-from-github).
