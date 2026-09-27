# BACKLOG_001 — Fleet QC view

**For:** Quarry lead engineer · **Level:** Epic, to split into stories at planning · **From:** PROPOSAL.md, item 1 · **Estimate:** 80 hours · **Client contact:** Dana Whitfield

## 1. Problem

HaloCloud gives Halvard's product and quality teams no fleet-wide view of QC failure rates by firmware version.

Every HX-200 reports each run's QC result, and HaloCloud's fleet dashboard already uses instrument telemetry, but no view compares QC results across all customers by firmware, model and assay. When 4.1.0 raised IA-Panel-3 failures on the HX-200 from about 3% to about 40%, the signal was in the telemetry within 2 weeks of release, and it stayed there for 116 days until 4.1.2 fixed it. In that time, labs filed QC rejection tickets, and 35 sites that ran the affected firmware did not renew.

**User need:** as a Halvard user responsible for firmware quality, I need a rolling HaloCloud view of QC failure rates for each firmware version, by model and assay, compared with the previous validated version, so that I can see a failing release within days of rollout and decide whether to hold it.

## 2. What to build

A chart in HaloCloud's fleet information, for Halvard staff only, updated daily, with one line or bar per firmware, model and assay combination.

- **Data:** `runs` (`instrument_id`, `run_date`, `assay_type`, `firmware_version`, `qc_status`) joined to `instruments` (`model`).
- **Time range:** the trailing 7 days by default, recalculated each day. The user can change the range, and the flag rules apply to whatever range is selected.
- **QC failure rate:** `fail / (pass + fail)`. Leave `skipped` out. Use firmware 4.0.0 and later only, because older firmware records a skipped QC step as `fail`.
- **Baseline:** the model and assay failure rate on the previous validated firmware. For HX-200 with IA-Panel-3 on 4.0.x, that rate is 3.0%.
- **Flags:** a window with fewer than 10 runs flags on any QC failure. A window with 10 or more runs flags when its failure rate is above 3 times the baseline. The rules are sensitive on purpose, because missing a defect cost far more last cycle than reviewing a false alarm.

The same rules already run as a backtest in `src/analysis.py` (Part D, D10), with every flagged day in `output/tables/monitor_backtest_flags.csv`.

## 3. Acceptance criteria

**AC1. Show QC failure rates by firmware, with flags**

Given a user is in HaloCloud and viewing fleet information  
When the user selects QC data  
Then a chart shows the QC failure rate for each firmware, model and assay combination over the last 7 days, against its baseline

- Each combination shows its runs, failures, failure rate and baseline, updated daily.
- A combination with fewer than 10 runs and at least one QC failure in the last 7 days shows as flagged.
- A combination with 10 or more runs and a failure rate above 3 times its baseline in the last 7 days shows as flagged.
- `skipped` runs and pre-4.0.0 firmware never enter a rate.
- The user can change the time range, and the flags follow the selected range.
- The user can set the chart to an earlier date.
- With the 2025-09-01 to 2026-08-31 telemetry and the date set to 2025-11-15, the chart flags HX-200, IA-Panel-3, 4.1.0. Across that year, it flags HX-200 IA-Panel-3 on 4.1.0 or 4.1.1 on 390 of the 399 days either ran, matching the backtest.
- The implementation pull request lists the other 230 flag episodes in the year, counted by combination, and `output/tables/monitor_backtest_flags.csv` already holds them by day. An episode is a run of consecutive flagged days for one combination.

## 4. Scope

The immediate scope is the chart and its flags. Notifications, summaries, a lab-facing version, the hold and rollback path (PROPOSAL item 2), the instrument simulators (item 3) and control values (item 5) are out of scope. Notifications wait until users have used the chart and said what they need.

## 5. Questions to settle before starting

- **Telemetry source:** does HaloCloud receive telemetry from every instrument, or only from subscribing sites? Churned sites keep reporting runs, so the data exists either way.
- **Flag load:** the backtest raises about 4 flag episodes a week across 60 combinations. The quality team confirms that load before release.
- **Baseline for something new:** a new model or assay has no previous firmware. The working answer is the fleet rate for that assay on other models until 8 weeks of its own data exist.
- **Access:** the working answer is Halvard's quality and product leads, agreed with Dana.
