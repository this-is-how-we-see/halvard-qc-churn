# Halvard QC failures and HaloCloud churn

Did QC failures drive HaloCloud churn at the last renewal, and would a Plus-tier QC alert have kept those sites? The short answer is in `FINDINGS.md`, the recommendation is in `PROPOSAL.md`, and the analysis walkthrough is in `notebooks/walkthrough.md`. The runnable copy of the walkthrough is `notebooks/walkthrough.ipynb`.

## Setup

Python 3.14. From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The data pack isn't in the repo, because the brief doesn't ask for it in a public repository. Unzip `halvard_data_pack.zip` from the brief into `data/raw/halvard_data_pack/`, so that `data/raw/halvard_data_pack/runs.csv` exists.

## Reproduce

```bash
python src/build.py       # loads the CSVs into output/halvard.duckdb, builds the views, writes output/checks.md
python src/analysis.py    # tests and tables: output/tables/, output/stats.json, most figures
python src/figures.py     # the remaining figures
```

Every run starts from the raw CSVs and gives the same outputs. The DuckDB session runs in UTC, because the pack's timestamps are UTC and date casts depend on the session time zone. To rerun the notebook, run `jupyter nbconvert --to notebook --execute --inplace notebooks/walkthrough.ipynb`. `notebooks/walkthrough.md` is a Markdown export of the executed notebook, because GitHub's notebook viewer doesn't load in every browser setup. nbviewer is another way to read the notebook: https://nbviewer.org/github/this-is-how-we-see/halvard-qc-churn/blob/analysis/notebooks/walkthrough.ipynb

## What's where

| Path | What it holds |
|---|---|
| `_docs/KICKOFF.md`, `_docs/CHECKIN.md` | The plan before any code, and the midpoint status |
| `sql/staging/` | One view per CSV, cleaning only |
| `sql/marts/site_renewal.sql` | One row per site, with its decision date and the 90 days before it |
| `sql/checks/checks.sql` | 34 data checks, each with its rule and the rule's source |
| `src/analysis.py` | Part A lot test, Part B churn comparison, Part C customer story, Part D follow-up checks |
| `notebooks/` | The walkthrough: `walkthrough.md` to read on GitHub, `walkthrough.ipynb` to run |
| `output/` | `checks.md`, `stats.json`, tables and figures |

## How the data was handled

No row was deleted and no value was changed without a stated reason.

| Issue | Count | What was done |
|---|---|---|
| Duplicate run IDs, identical in every column | 1,561 | Staging keeps one copy of each |
| Runs dated before their instrument's install | 3 | Kept, too few to move any rate |
| Tickets resolved before they opened | 12 | Kept, with resolution hours left blank |
| Active sites whose next renewal had already passed | 4 | Flagged and left out of the churn comparison |
| `notice` sites | 9 | Not counted as lost, because their decision is still ahead, and reported separately |
| Sites with fewer than 90 days of data before their decision | 65 | Kept out of the main cohort of 431 |
| Main-cohort sites with no instrument installed before the decision | 10 | Left out of the QC comparison only |
| Main-cohort sites with only pre-4.0.0 runs | 17 | Left out of the QC comparison, because older firmware records a skipped QC step as a fail |
| `user_email` in app events | all | Dropped at staging, because it's personal data the analysis never uses |

## Limits

- The pack covers one renewal cycle, so normal churn of about 11% is an estimate, likely between 8% and 15%.
- QC is pass or fail only. The pack has no control values and no lot numbers, so the lot test uses timing instead.
- App events are a 1-in-10 sample, scaled by 10.
- The pack has no territory field and no HaloCloud version history.
- KICKOFF assumed European tickets were undercounted because a distributor takes first-line support. They aren't: European sites log 6.0 tickets a site, against 5.8 for direct sites.
- The 9 `notice` sites' last renewal fell between 2025-09-13 and 2025-11-18, before the defect reached the fleet, so a 90-day window before it measures nothing. They count as exposed if they ever ran the affected firmware.
- The primary test is the exposure comparison in Part B. The Part D checks came after seeing the data and are exploratory.
- p-values below 0.05 are called significant, 0.05 to 0.25 a possible trend, and above 0.25 a place where we need more data.

## Time log

The clock started at the data pack download. Times are elapsed.

| Elapsed | Work |
|---|---|
| 0:00 to 0:10 | Read the brief and the data dictionary, wrote and committed KICKOFF |
| 0:10 to 0:20 | Loaded the data, staging views and data checks |
| 0:20 to 1:00 | Site table, decision dates, cohorts, QC comparison rules |
| 1:00 to 1:15 | Lot test, adoption, churn comparison and regressions |
| 1:15 to 2:10 | Customer story, and two independent reviews of the work so far |
| 2:10 to 2:45 | Follow-up checks from the reviews, the check-in |
| 2:45 to 3:05 | FINDINGS, the walkthrough notebook, the smallest group worth reporting |
| 3:05 to 3:35 | PROPOSAL, BACKLOG_001 with its backtest, CLIENT_REPLY, ACCOUNT_NOTE |
| 3:35 onward | README, pull request and self-review, walkthrough video |

## How AI was used

I used Claude Code throughout. It wrote the SQL, the Python and the first draft of every document, and I made the calls: what counts as a lost site, which data to leave out and why, which tests to trust, what to tell Dana and what to hold for the account lead. I reviewed every number, and I approved every document in its final form. At the midpoint, two separate AI sessions reviewed the work without seeing my reasoning. Both reproduced every number, and their findings changed the check-in's lead and added the Part D checks.
