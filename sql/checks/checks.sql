-- Data quality checks. Each block returns the rows that FAIL the check.
-- Zero rows means the check passes. build.py runs every block and writes
-- the results to output/checks.md. Nothing is fixed silently.
--
-- Header format:
--   -- check: name | what it tests | source of the rule | action if it fails
-- Sources: "Dictionary" = data_dictionary.md from Quarry; "Inference" = drawn
-- from a stated fact; "Logic" = no document needed; "Diagnostic" = added to
-- test a proposal. Actions marked "Approved" were approved by Howie 2026-09-27.

-- check: sites_pk_unique | Every site_id appears once in sites | Dictionary: site_id is the primary key | Stop and investigate
select site_id from stg_sites group by 1 having count(*) > 1;

-- check: instruments_pk_unique | Every instrument_id appears once | Dictionary: instrument_id is the primary key | Stop and investigate
select instrument_id from stg_instruments group by 1 having count(*) > 1;

-- check: raw_runs_duplicate_ids | Every run_id appears once in the file as delivered | Dictionary: run_id is the primary key | Approved: stg_runs keeps one copy of each identical pair
select run_id from raw_runs group by 1 having count(*) > 1;

-- check: raw_runs_duplicates_identical | Where a run_id repeats in the file, every copy is identical in every column | Diagnostic: tests the duplicate proposal | Stop and investigate
select run_id from raw_runs group by 1
having count(*) > 1
   and count(distinct (instrument_id, run_ts, assay_type, sample_count, qc_status,
                       coalesce(error_code, ''), firmware_version, duration_min)) > 1;

-- check: runs_pk_unique | Every run_id appears once after staging | Dictionary: run_id is the primary key | Stop and investigate
select run_id from stg_runs group by 1 having count(*) > 1;

-- check: events_pk_unique | Every event_id appears once | Dictionary: event_id is the primary key | Stop and investigate
select event_id from stg_app_events group by 1 having count(*) > 1;

-- check: tickets_pk_unique | Every ticket_id appears once | Dictionary: ticket_id is the primary key | Stop and investigate
select ticket_id from stg_support_tickets group by 1 having count(*) > 1;

-- check: subscriptions_one_per_site | Each site has at most one subscription row | Dictionary: one row per site | Stop and investigate
select site_id from stg_subscriptions group by 1 having count(*) > 1;

-- check: every_site_has_subscription | Every site has a subscription row | Dictionary: one row per site | Stop and investigate
select s.site_id from stg_sites s
left join stg_subscriptions b using (site_id) where b.site_id is null;

-- check: instruments_site_fk | Every instrument belongs to a known site | Dictionary: site_id is a foreign key to sites | Stop and investigate
select i.instrument_id from stg_instruments i
left join stg_sites s using (site_id) where s.site_id is null;

-- check: runs_instrument_fk | Every run belongs to a known instrument | Dictionary: instrument_id is a foreign key to instruments | Stop and investigate
select r.run_id from stg_runs r
left join stg_instruments i using (instrument_id) where i.instrument_id is null;

-- check: events_site_fk | Every app event belongs to a known site | Dictionary: site_id is a foreign key to sites | Stop and investigate
select e.event_id from stg_app_events e
left join stg_sites s using (site_id) where s.site_id is null;

-- check: tickets_site_fk | Every ticket belongs to a known site | Dictionary: site_id is a foreign key to sites | Stop and investigate
select t.ticket_id from stg_support_tickets t
left join stg_sites s using (site_id) where s.site_id is null;

-- check: runs_firmware_known | Every run's firmware is a published release | Inference: firmware_releases lists the published releases | Stop and investigate
select r.run_id, r.firmware_version from stg_runs r
left join stg_firmware_releases f on f.version = r.firmware_version where f.version is null;

-- check: region_values | Region is one of the four documented values | Dictionary: listed values | Stop and investigate
select site_id, region from stg_sites where region not in ('NA-East','NA-West','EU','APAC');

-- check: segment_values | Segment is one of the three documented values | Dictionary: listed values | Stop and investigate
select site_id, segment from stg_sites where segment not in ('hospital_lab','reference_lab','research');

-- check: model_values | Model is HX-200 or HX-200 Plus | Dictionary: listed values | Stop and investigate
select instrument_id, model from stg_instruments where model not in ('HX-200','HX-200 Plus');

-- check: qc_status_values | QC status is pass, fail or skipped | Dictionary: listed values | Stop and investigate
select run_id, qc_status from stg_runs where qc_status not in ('pass','fail','skipped') or qc_status is null;

-- check: skipped_before_400 | No run on firmware before 4.0.0 records skipped | Dictionary: skipped arrived in firmware 4.0.0 | Stop and investigate
select run_id, firmware_version from stg_runs where qc_status = 'skipped' and fw_major < 4;

-- check: status_values | Subscription status is active, notice or churned | Dictionary: listed values | Stop and investigate
select site_id, status from stg_subscriptions where status not in ('active','notice','churned');

-- check: tier_values | Tier is Basic or Plus | Dictionary: listed values | Stop and investigate
select site_id, tier from stg_subscriptions where tier not in ('Basic','Plus');

-- check: runs_in_window | Every run falls inside 2025-09-01 to 2026-08-31 UTC | Dictionary: extract window | Stop and investigate
select run_id, run_ts from stg_runs where run_ts < timestamptz '2025-09-01 00:00:00+00' or run_ts >= timestamptz '2026-09-01 00:00:00+00';

-- check: events_in_window | Every app event falls inside the window | Dictionary: extract window | Stop and investigate
select event_id, event_ts from stg_app_events where event_ts < timestamptz '2025-09-01 00:00:00+00' or event_ts >= timestamptz '2026-09-01 00:00:00+00';

-- check: tickets_in_window | Every ticket opened inside the window | Dictionary: extract window | Stop and investigate
select ticket_id, opened_ts from stg_support_tickets where opened_ts < timestamptz '2025-09-01 00:00:00+00' or opened_ts >= timestamptz '2026-09-01 00:00:00+00';

-- check: runs_after_install | No run happens before its instrument was installed | Dictionary: install_date is the date the instrument was commissioned | Approved: keep the runs, too few to move any rate
select r.run_id, r.run_date, i.install_date from stg_runs r
join stg_instruments i using (instrument_id) where r.run_date < i.install_date;

-- check: tickets_resolve_after_open | A resolved ticket closes after it opens | Logic | Approved: keep the tickets, resolution_hours is blank for them
select ticket_id from stg_support_tickets where resolved_ts is not null and resolved_ts < opened_ts;

-- check: runs_positive_values | Sample count and duration are positive | Logic | Stop and investigate
select run_id from stg_runs where sample_count <= 0 or duration_min <= 0 or sample_count is null or duration_min is null;

-- check: churned_date_in_window | A churned site's missed renewal falls inside the window | Inference: churn is observed at a renewal inside the window | Stop and investigate
select site_id, renewal_date from stg_subscriptions where status = 'churned' and (renewal_date < date '2025-09-01' or renewal_date > date '2026-08-31');

-- check: active_date_after_extract | An active or notice site's next renewal is after the extract date | Dictionary: renewal_date is the next renewal for active sites | Approved: flag the sites (status_conflict) and leave them out of the churn comparison
select site_id, status, renewal_date from stg_subscriptions where status in ('active','notice') and renewal_date <= date '2026-08-31';

-- check: renewal_on_anniversary | Renewal date falls on the start date's anniversary | Inference: HaloCloud is an annual subscription | Stop and investigate
select site_id, start_date, renewal_date from stg_subscriptions
where month(start_date) <> month(renewal_date) or day(start_date) <> day(renewal_date);
