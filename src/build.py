"""Build the DuckDB database from the data pack and run the data checks.

Usage:  python src/build.py
Reads:  data/raw/halvard_data_pack/*.csv
Writes: output/halvard.duckdb, output/checks.md
"""
from pathlib import Path
import re
import duckdb

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw" / "halvard_data_pack"
OUT = ROOT / "output"
TABLES = ["sites", "instruments", "runs", "app_events",
          "support_tickets", "subscriptions", "firmware_releases"]


def connect():
    OUT.mkdir(exist_ok=True)
    con = duckdb.connect(str(OUT / "halvard.duckdb"))
    con.execute("set TimeZone = 'UTC'")  # the dictionary says every timestamp is UTC
    return con


def load_raw(con):
    # Each CSV becomes a raw_ table exactly as delivered. No cleaning here.
    for t in TABLES:
        con.execute(f"create or replace table raw_{t} as "
                    f"select * from read_csv_auto('{DATA / (t + '.csv')}')")


def run_sql_dir(con, folder):
    # Run every .sql file in a folder, in name order.
    for f in sorted((ROOT / "sql" / folder).glob("*.sql")):
        con.execute(f.read_text())


def run_checks(con):
    # Split checks.sql on its "-- check: name | description" headers.
    text = (ROOT / "sql" / "checks" / "checks.sql").read_text()
    blocks = re.split(r"^-- check: ", text, flags=re.M)[1:]
    results = []
    for b in blocks:
        header, sql = b.split("\n", 1)
        name, desc, source, action = [p.strip() for p in header.split("|", 3)]
        failing = con.execute(f"select count(*) from ({sql.strip().rstrip(';')})").fetchone()[0]
        results.append((name, desc, source, action, failing))
    return results


def write_checks(results):
    lines = ["# Data checks", "", "Zero failing rows means the check passes.", "",
             "| Check | What it tests | Source of the rule | Failing rows | Result | Action |", "|---|---|---|---|---|---|"]
    for name, desc, source, action, n in results:
        lines.append(f"| `{name}` | {desc} | {source} | {n} | {'pass' if n == 0 else '**FAIL**'} | {action if n else ''} |")
    (OUT / "checks.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    con = connect()
    load_raw(con)
    run_sql_dir(con, "staging")
    results = run_checks(con)
    write_checks(results)
    for name, desc, source, action, n in results:
        print(f"{'PASS' if n == 0 else 'FAIL'}  {n:>6}  {name}" + (f"  -> {action}" if n else ""))
