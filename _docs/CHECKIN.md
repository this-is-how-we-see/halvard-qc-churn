# Check-in

As suspected, QC failures went with the lost renewals at the last cycle. The failures came from the IA-Panel-3 curve-fit problem that Halvard corrected in 4.1.2, and the data confirms it. IA-Panel-3 on the HX-200 failed QC 38% of the time on 4.1.0 and 42% on 4.1.1, against about 3% on other firmware. Sites that ran IA-Panel-3 on the affected firmware churned at 25.7%, against 10.8% for the rest.

## Significant findings (p below 0.05)

- Sites that ran the affected firmware had 2.3 times the odds of churning, with region, segment, tier and run volume held equal (p = 0.005).
- The failures follow each instrument's own upgrade, not the calendar, so a bad control lot doesn't explain them. Across 361 instruments, the failure rate fell from 27% before the upgrade to 4% after it (p < 0.001).
- Telemetry showed the defect clearly 19 days after 4.1.0 shipped (p < 0.001 against the 3% baseline). 4.1.2 shipped 116 days after that, and 49 HX-200s were still on 4.1.0 at the end of August.
- Sites with a QC failure rate above 5% churned at 23%, against 12% for sites at or below 5% (p = 0.005). Most of the sites above 5% ran the affected firmware.
- European sites that ran the affected firmware churned at 41%, against 16% for direct sites (p = 0.002). European research labs account for much of it: 14 of 19 churned, against 4 of 18 European research labs that didn't run it (p = 0.003).
- European support tickets wait about three times longer for a first response: 22.8 hours against 6.2 for QC rejection tickets, and 17.8 against 6.2 for everything else (p < 0.001 for both).

## Trending findings (p from 0.05 to 0.25)

- Among sites that didn't run the affected firmware, a QC failure rate above 5% still went with more churn, 17% against 10% (p = 0.16). A failure threshold may matter beyond this defect.
- Sites that ran the affected firmware and came up for renewal after 4.1.2 shipped still churned more than other sites renewing in the same months, 23% against 14% (p = 0.18). Upgrades were slow: 36 of those 52 sites kept running the affected firmware after the fix shipped, for a median of 30 more days. Those 36 churned no more than the 16 that had already upgraded, so the slow upgrade alone doesn't explain the gap.
- Reference labs churned less than hospital labs, at about half the odds with the other factors held equal (p = 0.14).

## Where we need more data (p above 0.25)

- We need more data to say whether the slower European response caused the European churn. Among sites that filed a QC ticket, the ones that churned didn't wait longer (p = 0.94).

## What comes next

A Plus-tier QC alert would have missed most of these sites. Labs already saw the failures on the instrument, 4.1.2 removed the cause, and 28 of the 35 churned sites that ran the affected firmware were on Basic. I'll propose aiming QC alerting at Halvard's own fleet, so the next defect gets caught in weeks instead of months, and I'll raise the European distributor channel as a question.

We're about 2.5 hours in, with about 2 hours of work left. Next are FINDINGS, PROPOSAL and BACKLOG_001, then the client reply, the account note, the README, the pull request and the walkthrough. One risk goes to the account lead, not the client documents.
