# Findings: QC failures and churn

**For:** Dana Whitfield · **Data:** 2025-09-01 to 2026-08-31 · **Sites:** 431

As your team suspected, QC failures went with the lost renewals at the last cycle, and they came from the IA-Panel-3 curve-fit problem that Halvard corrected in 4.1.2. On the HX-200, IA-Panel-3 failed QC 38% of the time on firmware 4.1.0 and 42% on 4.1.1, against about 3% on other firmware. Each instrument's failures started when it installed 4.1.0 and stopped when it installed 4.1.2, whatever the date, so a bad control lot doesn't explain them. Across 361 instruments, the failure rate went from 27% before the upgrade to 4% after it.

## What it cost

Sites that ran IA-Panel-3 on the affected firmware churned at 25.7%, more than twice the normal rate of about 11% a year. The difference holds with region, segment, tier and run volume held equal, at 2.3 times the odds (p = 0.005). That's about 20 more lost sites than a normal year, worth $125,000 to $135,000 in ARR. Five of the nine sites now on notice ran the affected firmware too.

A high QC failure rate may matter beyond this defect. Sites with a failure rate above 5% churned at 23%, against 12% at or below 5% (p = 0.005), though most ran the affected firmware. Among sites that never ran it, the split was 17% against 10% (p = 0.16), a possible trend.

## Visible early, fixed late

![Failure rate, QC tickets and renewal decisions by week](output/figures/visible_before_fixed.png)

Users filed the first QC rejection ticket 14 days after 4.1.0 shipped, and all 71 QC rejection tickets came from sites that ran the affected firmware. Halvard's telemetry showed the problem clearly 19 days after release. 4.1.2 shipped 116 days after that, and 49 HX-200s were still on 4.1.0 at the end of August. Of the 35 churned sites that ran the affected firmware, 23 made their renewal decision before the fix existed.

## Europe

![Churn by segment and region](output/figures/churn_by_segment_region.png)

*Research labs that ran the affected firmware churned at 38%, against 19% for research labs that didn't. The whole difference is in Europe. European research labs that ran it churned at 74% (14 of 19), against 22% (4 of 18) for those that didn't, and direct research labs churned at 18% either way.*

European sites that ran the affected firmware churned at 41%, against 16% for direct sites (p = 0.002). European tickets of every kind also wait about three times longer for a first response, 22.8 hours against 6.2 for QC rejection tickets. We need more data to say whether the slower response caused the churn, because among sites that filed a QC ticket, the ones that left didn't wait longer.

## Would a Plus-tier alert have helped?

A Plus-tier alert would have reached few of the lost sites, because 28 of the 35 churned sites that ran the affected firmware were on Basic. Labs saw the failures on the instrument, and 4.1.2 has removed the cause. **The gap was between a clear signal in Halvard's telemetry and a fix in the field.**

Release testing is the other gap. A curve-fit change is normally verified with controls on real instruments, but the defect appeared only on the HX-200, and the HX-200 Plus ran IA-Panel-3 at about 4% on the same firmware. Testing most likely missed that combination. PROPOSAL.md covers instrument simulators that test every model and assay before release, a fleet QC monitor and a rollback path.

The analysis covers one renewal cycle, so the normal rate of 11% is an estimate, likely between 8% and 15%.
