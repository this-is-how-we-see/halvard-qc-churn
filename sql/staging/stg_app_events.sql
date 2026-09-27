-- HaloCloud product events, a uniform 1-in-10 sample of the full stream.
-- user_email is personal data and the analysis never needs it, so it is
-- dropped here and never reaches any later table.
create or replace view stg_app_events as
select
    trim(event_id)   as event_id,
    trim(site_id)    as site_id,
    trim(user_id)    as user_id,
    event_ts         as event_ts,
    trim(event_name) as event_name,
    trim(platform)   as platform
from raw_app_events;
