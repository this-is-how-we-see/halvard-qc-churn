# Data checks

Zero failing rows means the check passes.

| Check | What it tests | Source of the rule | Failing rows | Result | Action |
|---|---|---|---|---|---|
| `sites_pk_unique` | Every site_id appears once in sites | Dictionary: site_id is the primary key | 0 | pass |  |
| `instruments_pk_unique` | Every instrument_id appears once | Dictionary: instrument_id is the primary key | 0 | pass |  |
| `raw_runs_duplicate_ids` | Every run_id appears once in the file as delivered | Dictionary: run_id is the primary key | 1561 | **FAIL** | Approved: stg_runs keeps one copy of each identical pair |
| `raw_runs_duplicates_identical` | Where a run_id repeats in the file, every copy is identical in every column | Diagnostic: tests the duplicate proposal | 0 | pass |  |
| `runs_pk_unique` | Every run_id appears once after staging | Dictionary: run_id is the primary key | 0 | pass |  |
| `events_pk_unique` | Every event_id appears once | Dictionary: event_id is the primary key | 0 | pass |  |
| `tickets_pk_unique` | Every ticket_id appears once | Dictionary: ticket_id is the primary key | 0 | pass |  |
| `subscriptions_one_per_site` | Each site has at most one subscription row | Dictionary: one row per site | 0 | pass |  |
| `every_site_has_subscription` | Every site has a subscription row | Dictionary: one row per site | 0 | pass |  |
| `instruments_site_fk` | Every instrument belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `runs_instrument_fk` | Every run belongs to a known instrument | Dictionary: instrument_id is a foreign key to instruments | 0 | pass |  |
| `events_site_fk` | Every app event belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `tickets_site_fk` | Every ticket belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `runs_firmware_known` | Every run's firmware is a published release | Inference: firmware_releases lists the published releases | 0 | pass |  |
| `region_values` | Region is one of the four documented values | Dictionary: listed values | 0 | pass |  |
| `segment_values` | Segment is one of the three documented values | Dictionary: listed values | 0 | pass |  |
| `model_values` | Model is HX-200 or HX-200 Plus | Dictionary: listed values | 0 | pass |  |
| `qc_status_values` | QC status is pass, fail or skipped | Dictionary: listed values | 0 | pass |  |
| `skipped_before_400` | No run on firmware before 4.0.0 records skipped | Dictionary: skipped arrived in firmware 4.0.0 | 0 | pass |  |
| `status_values` | Subscription status is active, notice or churned | Dictionary: listed values | 0 | pass |  |
| `tier_values` | Tier is Basic or Plus | Dictionary: listed values | 0 | pass |  |
| `runs_in_window` | Every run falls inside 2025-09-01 to 2026-08-31 UTC | Dictionary: extract window | 0 | pass |  |
| `events_in_window` | Every app event falls inside the window | Dictionary: extract window | 0 | pass |  |
| `tickets_in_window` | Every ticket opened inside the window | Dictionary: extract window | 0 | pass |  |
| `runs_after_install` | No run happens before its instrument was installed | Dictionary: install_date is the date the instrument was commissioned | 3 | **FAIL** | Approved: keep the runs, too few to move any rate |
| `tickets_resolve_after_open` | A resolved ticket closes after it opens | Logic | 12 | **FAIL** | Approved: keep the tickets, resolution_hours is blank for them |
| `runs_positive_values` | Sample count and duration are positive | Logic | 0 | pass |  |
| `churned_date_in_window` | A churned site's missed renewal falls inside the window | Inference: churn is observed at a renewal inside the window | 0 | pass |  |
| `active_date_after_extract` | An active or notice site's next renewal is after the extract date | Dictionary: renewal_date is the next renewal for active sites | 4 | **FAIL** | Approved: flag the sites (status_conflict) and leave them out of the churn comparison |
| `renewal_on_anniversary` | Renewal date falls on the start date's anniversary | Inference: HaloCloud is an annual subscription | 0 | pass |  |
| `mart_one_row_per_site` | site_renewal holds exactly one row for every site | Logic: the table is defined as one row per site | 0 | pass |  |
| `mart_rates_in_range` | Every rate and share falls between 0 and 1 | Logic | 0 | pass |  |
| `mart_runs_add_up` | QC pass, fail and skipped on 4.0.0 and later plus pre-4.0.0 runs equal all runs | Logic | 0 | pass |  |
| `mart_qc_rules_applied` | Main-cohort sites without a clean QC rate are exactly the ones the two approved rules leave out | Logic: approved QC comparison rules 1 and 2 | 0 | pass |  |
