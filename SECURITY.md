# Security notes

This project logs into a personal TickTick account from a GitHub Actions
runner, so it's worth being explicit about the trust boundaries.

**Secrets used:** `TICKTICK_USERNAME`, `TICKTICK_PASSWORD`, `GIST_ID`,
`GIST_TOKEN`. All four are stored as encrypted GitHub Actions secrets
(Settings → Secrets and variables → Actions) — never committed, never
printed in logs, and not visible to anyone without write access to the
repo settings.

**Gist token scope:** the token behind `GIST_TOKEN` should be scoped to
`gist` only — not full repo access. If it ever leaks, the blast radius
is "someone can read/write one Gist," not "someone owns your GitHub
account."

**Why TickTick credentials at all:** TickTick's official public API
doesn't expose habit data, only tasks/projects, so there's no OAuth
app / scoped-token option here — the unofficial client authenticates
like a normal login. If TickTick ships an official habits API in the
future, swapping this for a scoped OAuth token in `hydrate_sync.py`
would remove the need to store a raw password at all, and is the
recommended upgrade path.

**Workflow permissions:** the sync workflow's `GITHUB_TOKEN` is scoped
to `contents: write`, and only for one reason — committing the updated
`badge.json` back to the repo after a successful run, so the "last
synced" badge in the README stays current. It never touches anything
else in the repo. The separate test workflow, which doesn't need to
write anywhere, stays at `contents: read`.

**If you fork this:** rotate your own tokens rather than reusing any
example values, and keep the Gist holding your actual water data
*secret*, not public — the code in this repo is meant to be public,
your health data isn't.
