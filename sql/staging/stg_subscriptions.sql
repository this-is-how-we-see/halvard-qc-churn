-- One row per site's HaloCloud subscription, current tier only.
-- renewal_date means the next renewal for active and notice sites, and the
-- missed renewal for churned sites. That difference is handled downstream.
--
-- Approved 2026-09-27: 4 active sites carry a "next" renewal date that passed
-- before the 2026-08-31 extract. Their status and date contradict each other,
-- so their churn outcome is effectively missing. status_conflict flags them;
-- the churn comparison leaves them out and lists them separately.
create or replace view stg_subscriptions as
select
    trim(site_id)              as site_id,
    trim(tier)                 as tier,
    cast(start_date as date)   as start_date,
    cast(renewal_date as date) as renewal_date,
    lower(trim(status))        as status,
    arr_usd                    as arr_usd,
    (lower(trim(status)) in ('active', 'notice')
     and cast(renewal_date as date) <= date '2026-08-31') as status_conflict
from raw_subscriptions;
