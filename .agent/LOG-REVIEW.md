# AzurPilot daily log review

Canonical **scan → triage TODO → fix** loop for AzurPilot farm failures.

Triggers: the user mentions AzurPilot logs, overnight errors, GameStuck, RequestHumanTakeover, restarts, or a nightly/daily log scan. Cursor skill: `azurpilot-log-review`. Workspace pointer: `E:/Azur/AzurLaneAutoScript/docs/azurpilot-log-review.md`.

Chat with the user in English. New AzurPilot Python comments stay 简体中文.

## Preconditions

- Must run against the local tree `E:/Azur/AzurPilot` (logs are gitignored).
- If `log/` is missing, **stop**. Report that the run was not local / cloud-only. Do not guess from git history.

## Loop

1. **Index, do not slurp.** From AzurPilot root:

   ```bash
   uv run python dev_tools/scan_error_logs.py
   uv run python dev_tools/scan_error_logs.py --date YYYY-MM-DD
   ```

   **Overnight / morning scan:** log files roll at local midnight (`log/YYYY-MM-DD_{1-6,gui}.txt`). Scan **yesterday and today** so evening farm plus pre-dawn hours are both counted. Do not only scan `today` at 06:00.

   Reads day logs (complete counts) and remaining `log/error/<account>/<ms>/` snapshots (stack samples). Writes `docs/log-review/YYYY-MM-DD.digest.json` (gitignored with `docs/`).

2. **Read the digest + 1–2 sample `log.txt` files per top cluster.** Never open every snapshot or a full day log. Account suffixes: `1` 6ix7even, `2` brad, `3` asami, `4` nyan, `5` booty, `6` margaret.

3. **Update the living TODO** [`docs/log-review/TODO.md`](../docs/log-review/TODO.md). Merge by `cluster_id`; do not duplicate. Refresh counts and `Last scan`. Keep daily narrative in `docs/log-review/YYYY-MM-DD.md`.

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
