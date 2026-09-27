-- One row per assay run from instrument telemetry. Timestamps stay in UTC.
-- Blank error codes become null. The firmware string is split into numbers
-- so later steps can compare versions (for example, before or after 4.0.0).
--
-- Approved 2026-09-27: 1,561 run_ids appear twice in runs.csv, and every pair
-- is identical in all nine columns (check raw_runs_duplicates_identical).
-- run_id is the primary key and the file holds one row per run, so each pair
-- is one run recorded twice. The view keeps one copy. The cause is unknown and
-- is a question for Halvard's data team.
create or replace view stg_runs as
select
    trim(run_id)                                      as run_id,
    trim(instrument_id)                               as instrument_id,
    run_ts                                            as run_ts,
    cast(run_ts as date)                              as run_date,
    trim(assay_type)                                  as assay_type,
    sample_count                                      as sample_count,
    lower(trim(qc_status))                            as qc_status,
    nullif(trim(error_code), '')                      as error_code,
    trim(firmware_version)                            as firmware_version,
    cast(split_part(firmware_version, '.', 1) as int) as fw_major,
    cast(split_part(firmware_version, '.', 2) as int) as fw_minor,
    cast(split_part(firmware_version, '.', 3) as int) as fw_patch,
    duration_min                                      as duration_min
from (select distinct * from raw_runs);
