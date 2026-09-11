# AzurPilot daily log review

Scan today's local AzurPilot logs, cluster similar failures, update the living TODO, then start fixing the highest-count **code** issues.

Chat with the user in English. New AzurPilot Python comments stay 简体中文.

## Preconditions

- Must run against the local tree `E:/Azur/AzurPilot` (logs are gitignored).
- If `log/` is missing, **stop**. Report that the run was not local / cloud-only. Do not guess from git history.

## Steps

1. **Index, do not slurp.** From AzurPilot root:

   ```bash
   uv run python dev_tools/scan_error_logs.py
   uv run python dev_tools/scan_error_logs.py --date YYYY-MM-DD
   ```

   Reads `log/YYYY-MM-DD_{1-6,gui}.txt` (complete counts) and remaining `log/error/<account>/<ms>/` snapshots (stack samples). Writes `docs/log-review/YYYY-MM-DD.digest.json` (gitignored with `docs/`).

2. **Read the digest + 1–2 sample `log.txt` files per top cluster.** Never open every snapshot or a full day log.

3. **Update the living TODO** [`docs/log-review/TODO.md`](../docs/log-review/TODO.md). Merge by `cluster_id`; do not duplicate. Refresh counts. Keep daily narrative in `docs/log-review/YYYY-MM-DD.md`.

4. **Rank** by digest `rank` (`count × accounts`). Prefer `likely: code`. Skip emulator-offline, ADB blips, and one-off GameStuck unless they hit every account.

5. **Fix cap.** Take the top 1–2 code/UI clusters. One focused change per cluster. Stop after two. Leave work **uncommitted** unless the user asked to commit. Do not push. Write the outcome back into the TODO (`investigating` / `fixed` / `wontfix`).

## Cluster status values

`open` · `investigating` · `fixed` · `wontfix`

## Likely buckets (from the indexer)

| likely | Treat as |
|---|---|
| `code` | Investigate and fix if top-ranked |
| `ui_stuck` | Investigate if repeated on the same buttons/pages across accounts |
| `emulator` / `game_client` | Note only unless it dominates every account |
| `expected` | Ignore |

## Output files (gitignored)

| Path | Role |
|---|---|
| `docs/log-review/YYYY-MM-DD.digest.json` | Machine digest |
| `docs/log-review/YYYY-MM-DD.md` | Human summary for that day |
| `docs/log-review/TODO.md` | Rolling investigation list |
