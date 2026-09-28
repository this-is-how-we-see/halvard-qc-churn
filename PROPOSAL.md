# Proposal: next quarter

**For:** Dana Whitfield · **Period:** retainer months 8 to 10 · **Hours:** 240

The lost renewals came from a firmware defect that Halvard's telemetry showed within 19 days and took another 116 days to fix. This quarter points QC alerting at Halvard's fleet, so the next defect gets caught and fixed sooner.

## First, the renewals

106 sites that ran the affected firmware are still customers, five on notice. In week one, we'd give Customer Success that list with renewal dates and the 49 HX-200s still on 4.1.0, so Halvard can upgrade them and call each site before it renews. It takes about 8 hours of requests.

## What we'd build

| Work | Hours |
|---|---|
| 1. Fleet QC view | 80 |
| 2. Hold and rollback, HaloCloud side | 40 |
| 3. Instrument simulator pilot | 40 |
| 4. Renewal-churn check | 20 |
| 5. Telemetry spec | 10 |
| Requests | 48 |
| Total | 238 |

1. Fleet QC view. A HaloCloud chart of 7-day QC failure rates for every firmware, model and assay combination against its own baseline, for Halvard's quality teams. BACKLOG_001 is this item.
2. Hold and rollback. When the view flags a release, Halvard stops sending it and returns instruments to the last validated version. Halvard's firmware team builds the mechanism, and we'd build the HaloCloud version view and the notice to affected labs.
3. Instrument simulators. A tool that replays recorded QC control runs from each model through a new curve fit before release, piloted on IA-Panel-3 with Halvard's curve-fit code.
4. Renewal-churn check. Churn by segment against its normal range, monthly, so a rise shows before the cycle closes.
5. Telemetry spec. Control lot numbers and values in each run record, so the next QC problem can be traced in days. Spec only this quarter.

## What we wouldn't do

- QC alerting as a Plus-tier feature. A QC failure from Halvard's firmware is Halvard's defect to catch, so any customer alert goes to every tier.
- Territory cuts for renewal calls. The extracts have no territory field.
- Changes to European support yet. We'd need the distributor's ticket data first.

## Fit within the retainer

The plan uses 238 of 240 hours. We'd propose that any request over 2 hours gets your approval first, with small requests under 16 hours a month. **If the quarter runs short, the view comes first and the simulator pilot moves.**

## How we'd know it worked

- On last year's data, the view flags 4.1.0 10 days after release.
- The 49 HX-200s run 4.1.2 before their sites renew.
- A flagged release comes off most affected instruments within 14 days, against a median of 30 days for 4.1.2.
- The simulator pilot flags the 4.1.0 curve fit on the HX-200 before release.
- At the Q1 2027 renewals, churn among sites that ran a flagged release stays inside its normal range.
