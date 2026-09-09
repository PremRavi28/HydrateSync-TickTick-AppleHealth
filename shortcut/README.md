# The HydrateSync Shortcut

The one step that has to run on your phone — Apple only allows Health writes
from an on-device app you've approved, so no part of this can move to the
cloud, here or in any comparable project.

Build a Shortcut named **"HydrateSync"**:

1. **Get Contents of URL**
   `https://api.github.com/gists/<GIST_ID>`
   Headers: `Authorization: Bearer <a read-only PAT, separate from the one in GitHub Actions>`

2. **Get Dictionary from Input**

3. **Get Value for** `files` → `hydrate_sync.json` → `content`
   (the Gist API wraps your JSON as a string inside this structure)

4. **Get Dictionary from Input** again — this parses the actual payload

5. **Get Value for** `days` → a dictionary like `{"20260908": 3150, ...}`

6. **Repeat with Each** key in that dictionary:
   - **Get Value for** `[key]` → the ml amount for that day
   - **Date** action: parse `[key]` with format `yyyyMMdd`, so the entry
     lands on the correct historical day rather than "now"
   - **Log Health Sample** — Category: Water, Amount: `[value]` mL, Date: the parsed date

7. **Show Notification**: "HydrateSync: synced N day(s) to Apple Health" (optional)

## Running it

Tap it whenever — there's no schedule requirement on this side. It always
reflects whatever the last HydrateSync GitHub Actions run wrote to the Gist.

## Avoiding duplicates

Apple Health doesn't dedupe manual entries for you. Before step 6's
`Log Health Sample`, add a **Find Health Samples** lookup for that date and
skip the write if one already exists — otherwise re-running the Shortcut
for an already-synced day will double-count it.
