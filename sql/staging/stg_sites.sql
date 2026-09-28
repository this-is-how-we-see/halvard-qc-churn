-- One row per customer site. Clean only: trim text, no business logic.
create or replace view stg_sites as
select
    trim(site_id)  as site_id,
    trim(region)   as region,
    trim(segment)  as segment
from raw_sites;
