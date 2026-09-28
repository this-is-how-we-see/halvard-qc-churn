-- One row per installed analyzer.
create or replace view stg_instruments as
select
    trim(instrument_id)            as instrument_id,
    trim(site_id)                  as site_id,
    trim(model)                    as model,
    cast(install_date as date)     as install_date,
    trim(firmware_version_current) as firmware_version_current
from raw_instruments;
