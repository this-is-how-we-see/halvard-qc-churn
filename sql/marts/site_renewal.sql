-- One row per site: the outcome of its last renewal decision, and the facts
-- about the site in the 90 days before that decision. Approved 2026-09-27.
--
-- Decision date:  churned sites -> the renewal date they did not renew.
--                 active and notice sites -> next renewal minus 12 months,
--                 because HaloCloud is annual (check renewal_on_anniversary).
-- Lookback:       the 90 days before the decision date, decision day excluded.
-- Cohort:         main            full 90 days of data before the decision
--                 short_history   decision before 2025-11-30, so the extract
--                                 (from 2025-09-01) holds fewer than 90 days
--                 status_conflict active site whose next renewal already passed
-- QC rate:        failures / (passes + failures) on firmware 4.0.0 and later.
--                 Skipped runs stay out. Older firmware records a skipped step
--                 as fail, so its runs get their own rate.
--
-- QC comparison rules, approved 2026-09-27 (main cohort only; no row deleted,
-- no value changed):
--   1. No instrument installed on or before the decision date -> no runs, so no
--      QC measure. in_qc_comparison = false. HaloCloud use before the listed
--      install shows an earlier instrument existed; its runs are not in the
--      extract.
--   2. Every run in the 90 days on firmware before 4.0.0 -> no clean QC rate.
--      in_qc_comparison = false. The mixed rate stays in qc_fail_rate_pre400.
--   3. An instrument installed inside the 90-day window -> runs may cover only
--      part of it. partial_run_coverage = true. Kept in the comparison; the
--      comparison is also run without these sites as a check.

create or replace table site_renewal as
with sub as (
    select
        site_id, tier, status, arr_usd, start_date, renewal_date, status_conflict,
        status = 'churned' as churned,
        case when status = 'churned' then renewal_date
             else cast(renewal_date - interval 12 month as date)
        end as decision_date
    from stg_subscriptions
),
win as (
    -- The lookback window for each site. It cannot start before the extract.
    select *,
        cast(decision_date - interval 90 day as date)                         as lookback_start,
        greatest(cast(decision_date - interval 90 day as date), date '2025-09-01') as data_start
    from sub
),
inst as (
    -- Instruments already installed on the decision date.
    select w.site_id,
        count(*)                                              as n_instruments,
        count(*) filter (where i.model = 'HX-200')            as n_hx200,
        avg(date_diff('day', i.install_date, w.decision_date)) / 365.25 as avg_instrument_age_yrs
    from win w
    join stg_instruments i on i.site_id = w.site_id and i.install_date <= w.decision_date
    group by 1
),
runs as (
    -- Runs in the lookback window, before the decision day.
    select w.site_id,
        count(*)                                                        as runs_90d,
        sum(r.sample_count)                                             as samples_90d,
        count(*) filter (where r.fw_major >= 4 and r.qc_status = 'pass')    as qc_pass,
        count(*) filter (where r.fw_major >= 4 and r.qc_status = 'fail')    as qc_fail,
        count(*) filter (where r.fw_major >= 4 and r.qc_status = 'skipped') as qc_skipped,
        count(*) filter (where r.fw_major < 4)                          as runs_pre400,
        count(*) filter (where r.fw_major < 4 and r.qc_status = 'fail') as qc_fail_pre400,
        count(*) filter (where r.assay_type = 'IA-Panel-3')             as runs_ia3,
        count(*) filter (where r.firmware_version in ('4.1.0', '4.1.1')) as runs_fw_410_411
    from win w
    join stg_instruments i on i.site_id = w.site_id
    join stg_runs r on r.instrument_id = i.instrument_id
     and r.run_date >= w.lookback_start and r.run_date < w.decision_date
    group by 1
),
events as (
    -- App events in the lookback window. The extract is a 1-in-10 sample,
    -- so counts are multiplied by 10 to estimate the full stream.
    select w.site_id,
        10 * count(*)                                        as app_events_90d_est,
        10 * count(*) filter (where e.event_name = 'qc_review') as qc_review_90d_est
    from win w
    join stg_app_events e on e.site_id = w.site_id
     and cast(e.event_ts as date) >= w.lookback_start and cast(e.event_ts as date) < w.decision_date
    group by 1
),
tickets as (
    -- Support tickets opened in the lookback window.
    select w.site_id,
        count(*)                                             as tickets_90d,
        count(*) filter (where t.category = 'qc_rejection')  as qc_rejection_tickets_90d,
        median(t.first_response_hours)                       as median_first_response_hrs
    from win w
    join stg_support_tickets t on t.site_id = w.site_id
     and cast(t.opened_ts as date) >= w.lookback_start and cast(t.opened_ts as date) < w.decision_date
    group by 1
)
select
    w.site_id,
    case when w.status_conflict                      then 'status_conflict'
         when w.decision_date < date '2025-11-30'    then 'short_history'
         else 'main' end                             as cohort,
    w.churned,
    w.status,
    w.decision_date,
    date_diff('day', w.data_start, w.decision_date)  as days_of_data,
    s.region,
    s.segment,
    w.tier,
    w.arr_usd,
    coalesce(inst.n_instruments, 0)                  as n_instruments,
    coalesce(inst.n_hx200, 0)                        as n_hx200,
    inst.avg_instrument_age_yrs,
    coalesce(runs.runs_90d, 0)                       as runs_90d,
    coalesce(runs.samples_90d, 0)                    as samples_90d,
    coalesce(runs.qc_pass, 0)                        as qc_pass,
    coalesce(runs.qc_fail, 0)                        as qc_fail,
    coalesce(runs.qc_skipped, 0)                     as qc_skipped,
    runs.qc_fail * 1.0 / nullif(runs.qc_pass + runs.qc_fail, 0)     as qc_fail_rate,
    coalesce(runs.runs_pre400, 0)                    as runs_pre400,
    runs.qc_fail_pre400 * 1.0 / nullif(runs.runs_pre400, 0)        as qc_fail_rate_pre400,
    runs.runs_ia3 * 1.0 / nullif(runs.runs_90d, 0)                 as ia3_share,
    runs.runs_fw_410_411 * 1.0 / nullif(runs.runs_90d, 0)          as fw_410_411_share,
    coalesce(events.app_events_90d_est, 0)           as app_events_90d_est,
    coalesce(events.qc_review_90d_est, 0)            as qc_review_90d_est,
    coalesce(tickets.tickets_90d, 0)                 as tickets_90d,
    coalesce(tickets.qc_rejection_tickets_90d, 0)    as qc_rejection_tickets_90d,
    tickets.median_first_response_hrs,
    case
        when coalesce(inst.n_instruments, 0) = 0
            then 'no runs before the decision: listed instrument installed after it'
        when coalesce(runs.runs_90d, 0) > 0 and runs.qc_pass + runs.qc_fail = 0
            then 'only firmware before 4.0.0: failures include skipped steps'
    end                                              as qc_exclusion_reason,
    coalesce(inst.n_instruments, 0) > 0
        and not (coalesce(runs.runs_90d, 0) > 0 and runs.qc_pass + runs.qc_fail = 0)
        and coalesce(runs.runs_90d, 0) > 0           as in_qc_comparison,
    coalesce(pc.partial, false)                      as partial_run_coverage
from win w
join stg_sites s using (site_id)
left join inst    using (site_id)
left join runs    using (site_id)
left join events  using (site_id)
left join tickets using (site_id)
left join (
    -- Sites with an instrument installed inside their 90-day window.
    select w.site_id, true as partial
    from win w
    join stg_instruments i on i.site_id = w.site_id
     and i.install_date >= w.lookback_start and i.install_date < w.decision_date
    group by 1
) pc using (site_id);
