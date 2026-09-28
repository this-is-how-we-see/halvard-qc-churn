# Kickoff

Written before any analysis code, from the brief and `data_dictionary.md` only.

## The question

Dana's team believes QC failures are driving HaloCloud churn: labs that see more QC failures lose trust in the instrument and don't renew. If that holds, they want to ship QC failure alerting as a Plus-tier feature this quarter and lead renewal conversations with it. I'm treating that as a hypothesis to test. The job is to find out whether QC failures explain which sites left, and only then to size what alerting could save.

## Planned approach

1. **Load and stage.** Load the seven extracts into DuckDB. One SQL staging view per file that fixes types and names and adds no business logic. `user_email` is dropped at staging and never used.
2. **Check the data.** Primary keys are unique, every foreign key resolves, dates fall inside the window, and nothing is duplicated. Anything that fails is written down, not silently fixed.
3. **Build one table per site.** The churn outcome, plus the QC failure rate, run volume, region, segment, tier, instrument model, instrument age, firmware, HaloCloud use and support history, all measured in the period before that site's renewal decision.
4. **Test the link.** Compare churn across groups of similar sites first, because that is the version Dana can check by eye. Then fit a logistic regression that holds the other factors constant, as a check on the tables.
5. **Look for a single cause behind the failures.** If QC failures cluster by firmware version or date, `firmware_releases.csv` should show it.
6. **Size it only if it holds.** If the link survives, the opportunity is the ARR of churned sites that alerting could plausibly have kept. If it does not survive, the honest number is close to zero, and the findings say what does explain churn.

## Assumptions

- **A lost site is a site with `status = churned`.** Dana asks why sites were lost at the last renewal cycle. The dictionary defines `notice` as a site that has told Customer Success it does not intend to renew at the upcoming renewal, so a `notice` site has not been lost yet. I report those sites separately, as an early signal for Q1 planning.
- **Downgrades and partial losses can't be measured.** `subscriptions.csv` has one row per site with the current tier only, so a move from Plus to Basic leaves no record, and the subscription is per site, not per instrument.
- **The last renewal date for an active site is its next renewal date minus 12 months.** HaloCloud is annual. This gives active and churned sites the same reference point, so both are measured over the same period before the decision.
- **QC failures are measured before the renewal decision, not after.** Otherwise a lab that had already decided to leave and stopped maintaining the instrument would look like a lab that left because of QC.
- **On firmware before 4.0.0, `fail` includes skipped QC.** The dictionary says so. The clean failure rate comes from runs on 4.0.0 and later, and older runs are reported separately rather than mixed in.
- **QC is measured per run, not as a count.** A busy lab fails more QC runs only because it runs more.
- **App event counts are multiplied by 10.** The extract is a uniform 1-in-10 sample. A small site can show no events by chance, so zero is read as low use, with that caveat.
- **European support tickets are undercounted.** The distributor takes first-line support in Europe, so most European problems never reach Halvard's ticket system.
- **`arr_usd` is the site's last contracted value**, including for churned sites.
- **Quarry's retainer is 80 hours a month across the team, and unused hours don't roll over.** No request rules appear in the brief, so I assume new requests go through Dana, who approves the hours.

## Questions I would ask

| For | Question | Working answer |
|---|---|---|
| Dana | Does a site on `notice` count as lost? | No. You asked about the last cycle, and their date is still ahead. Reported separately. |
| Dana | Which renewal cycle is "the last" one? | Renewals that fall inside the window, which is mostly Q1 2026. |
| Dana | Does a Plus-to-Basic downgrade count as a loss? | It can't be seen in this data, so it's out of scope. |
| Dana | What does alerting tell a lab that the instrument screen doesn't already show? | I assume it reaches people who aren't at the instrument, such as a lab manager watching the fleet. That value is unproven. |
| Dana | What form does the exec summary need to take? | A written summary she can present next week. |
| Data team | On pre-4.0.0 firmware, what share of `fail` is really a skipped step? | Unknown. I estimate it from 4.0.0 runs, where the two are recorded separately. |
| Data team | Is a site with no app events a non-user, or a gap in the sample? | Treated as low use, with the sampling caveat. |
| Data team | Are European support tickets complete? | No. Assumed undercounted because of the distributor. |
| Data team | Is `arr_usd` the value at the missed renewal for churned sites? | Yes. |
| Data team | Does every instrument in `instruments.csv` fall under its site's subscription? | Yes, one subscription per site. |
