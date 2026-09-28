-- One row per support ticket. resolved_ts is null while a ticket is open.
--
-- Approved 2026-09-27: 12 tickets close before they open, which is impossible.
-- The tickets stay, and both timestamps stay as delivered. Only
-- resolution_hours is left blank for them, because a negative duration would
-- pull any average down.
create or replace view stg_support_tickets as
select
    trim(ticket_id)       as ticket_id,
    trim(site_id)         as site_id,
    opened_ts             as opened_ts,
    trim(category)        as category,
    trim(severity)        as severity,
    first_response_hours  as first_response_hours,
    resolved_ts           as resolved_ts,
    case when resolved_ts >= opened_ts
         then date_diff('minute', opened_ts, resolved_ts) / 60.0
    end                   as resolution_hours
from raw_support_tickets;
