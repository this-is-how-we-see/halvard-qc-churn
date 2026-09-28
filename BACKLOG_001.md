# BACKLOG_001 — Fleet QC view

**For:** Quarry lead engineer · **Level:** Epic, to split into stories at planning · **From:** PROPOSAL.md, item 1 · **Estimate:** 80 hours · **Client contact:** Dana Whitfield

## 1. Problem

HaloCloud gives Halvard's product and quality teams no fleet-wide view of QC failure rates by firmware version.

Every HX-200 reports each run's QC result, and HaloCloud's fleet dashboard already uses instrument telemetry, but no view compares QC results across all customers by firmware, model and assay. When 4.1.0 raised IA-Panel-3 failures on the HX-200 from about 3% to about 40%, the signal was in the telemetry within 19 days of release, and it stayed there for 116 days until 4.1.2 fixed it. In that time, labs filed QC rejection tickets, and 35 sites that ran the affected firmware did not renew.

**User need:** as a Halvard user responsible for firmware quality, I need a rolling HaloCloud view of QC failure rates for each firmware version, by model and assay, compared with the previous validated version, so that I can see a failing release within days of rollout and decide whether to hold it.

## 2. What to build

A chart in HaloCloud's fleet information, for Halvard staff only, updated daily, with one line or bar per firmware, model and assay combination.

- **Data:** `runs` (`instrument_id`, `run_date`, `assay_type`, `firmware_version`, `qc_status`) joined to `instruments` (`model`).
- **Time range:** the trailing 7 days by default, recalculated each day. The user can change the range, and the limit follows whatever range is selected.
- **QC failure rate:** `fail / (pass + fail)`. Leave `skipped` out. Use firmware 4.0.0 and later only, because older firmware records a skipped QC step as `fail`.
- **Baseline:** the model and assay failure rate on the previous validated firmware. For HX-200 with IA-Panel-3 on 4.0.x, that rate is 3.0%.
- **Limit:** the baseline plus 3 standard deviations for the window's run count, `baseline + 3 × √(baseline × (1 − baseline) / runs)`. This is a p-chart, the control chart a QC lab uses for a failure rate. The limit is wider when a window has few runs, so a small window needs a higher failure rate to flag. At about 200 runs a week, the HX-200 IA-Panel-3 limit is 6.6%, which agrees with the observed weekly range on validated firmware, whose upper limit is 6.2% (D13).
- **Setting the baseline:** recalculated from the fleet's QC results each time Halvard validates a firmware version. A new model or assay uses the fleet rate for that assay on other models until 8 weeks of its own data exist.
- **Override:** a Halvard quality lead can set the limit for one model and assay, for example from that assay's own acceptance criteria. The override records who set it, when and why, and the chart shows it beside the calculated limit. Each override is reviewed at the next firmware validation.

The same rule already runs as a backtest in `src/analysis.py` (Part D, D10), with every flagged day in `output/tables/monitor_backtest_flags.csv`.

## 3. Acceptance criteria

**AC1. Show QC failure rates by firmware, with flags**

Given a user is in HaloCloud and viewing fleet information  
When the user selects QC data  
Then a chart shows the QC failure rate for each firmware, model and assay combination over the last 7 days, against its baseline

- Each combination shows its runs, failures, failure rate, baseline and limit, updated daily.
- A combination whose failure rate in the last 7 days is above its limit for that window's run count shows as flagged.
- `skipped` runs and pre-4.0.0 firmware never enter a rate.
- The user can change the time range, and the flags follow the selected range.
- The user can set the chart to an earlier date.
- With the 2025-09-01 to 2026-08-31 telemetry and the date set to 2025-11-16, the chart flags HX-200, IA-Panel-3, 4.1.0. Across that year, it flags HX-200 IA-Panel-3 on 4.1.0 or 4.1.1 on 387 of the 399 days either ran, matching the backtest.
- The implementation pull request lists the other 79 flag episodes in the year, counted by combination, and `output/tables/monitor_backtest_flags.csv` already holds them by day. An episode is a run of consecutive flagged days for one combination.

**AC2. Override a limit**

Given a Halvard quality lead is viewing the QC chart  
When the lead sets a limit for one model and assay and enters a reason  
Then the chart flags that combination against the override limit

- The chart shows the override limit beside the calculated limit, marked as an override.
- The override records who set it, when and the reason, and any user of the chart can see them.
- Only users on the override list can set or remove an override.
- At the next firmware validation, the chart lists every override for review.

## 4. Scope

The immediate scope is the chart and its flags. Notifications, summaries, a lab-facing version, the hold and rollback path (PROPOSAL item 2), the instrument simulators (item 3) and control values (item 5) are out of scope. Notifications wait until users have used the chart and said what they need.

## 5. Questions to settle before starting

- **Telemetry source:** does HaloCloud receive telemetry from every instrument, or only from subscribing sites? Churned sites keep reporting runs, so the data exists either way.
- **Flag load:** the backtest raises about 1.5 flag episodes a week across 60 combinations. The quality team confirms that load before release.
- **Who can override a limit:** the working answer is Halvard's quality leads, with Dana agreeing the list.
- **Access:** the working answer is Halvard's quality and product leads, agreed with Dana.
