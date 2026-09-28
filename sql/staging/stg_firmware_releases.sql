-- Published firmware releases, with the version split into numbers.
create or replace view stg_firmware_releases as
select
    trim(version)                            as version,
    cast(split_part(version, '.', 1) as int) as fw_major,
    cast(split_part(version, '.', 2) as int) as fw_minor,
    cast(split_part(version, '.', 3) as int) as fw_patch,
    cast(release_date as date)               as release_date,
    trim(release_notes)                      as release_notes
from raw_firmware_releases;
