"""Figures from the built database.

Usage:  python src/figures.py   (run src/build.py first)
Writes: output/figures/qc_rate_over_time.png
        output/figures/affected_firmware_share.png
        output/figures/site_timelines.png
"""
from pathlib import Path
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "output" / "figures"

# Colors from the validated three-slot palette (light surface).
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
Q1_BAND = "#f1f0ec"

# Firmware releases inside the extract window (2025-09-01 to 2026-08-31).
# 3.9.4, 4.0.0 and 4.0.2 were released before the window starts.
RELEASES_SQL = """
select version, release_date from stg_firmware_releases
where release_date between date '2025-09-01' and date '2026-08-31' order by release_date
"""


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))


def mark_releases(ax, releases, ymax):
    # A thin vertical rule and a version label at each release date.
    for version, day in releases:
        ax.axvline(day, color=INK_2, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
        ax.text(day, ymax, f" {version}", color=INK_2, fontsize=8.5, va="top", ha="left")


def shade_q1(ax):
    # Most HaloCloud renewals fall in Q1.
    import datetime as dt
    ax.axvspan(dt.date(2026, 1, 1), dt.date(2026, 3, 31), color=Q1_BAND, zorder=0)


def qc_rate_over_time(con):
    # Weekly clean QC failure rate: failures / (passes + failures), firmware 4.0.0
    # and later only. Split three ways, because the 4.1.2 release notes name
    # IA-Panel-3 on the HX-200.
    rows = con.execute("""
        select date_trunc('week', r.run_date)::date as week,
               case when i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' then 'HX-200 · IA-Panel-3'
                    when i.model = 'HX-200' then 'HX-200 · other assays'
                    else 'HX-200 Plus · all assays' end as grp,
               count(*) filter (where r.qc_status = 'fail') * 1.0
                 / nullif(count(*) filter (where r.qc_status in ('pass', 'fail')), 0) as rate
        from stg_runs r join stg_instruments i using (instrument_id)
        where r.fw_major >= 4
          and date_trunc('week', r.run_date) >= date '2025-09-01'
          and date_trunc('week', r.run_date) <  date '2026-08-31'
        group by 1, 2 order by 1
    """).fetchall()
    releases = con.execute(RELEASES_SQL).fetchall()
    groups = ["HX-200 · IA-Panel-3", "HX-200 · other assays", "HX-200 Plus · all assays"]

    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=160, facecolor=SURFACE)
    style(ax)
    shade_q1(ax)
    ymax = 0.3
    for g, color in zip(groups, SERIES):
        pts = [(w, r) for w, grp, r in rows if grp == g and r is not None]
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=color,
                linewidth=2.4 if g == groups[0] else 1.8, label=g, zorder=3)
        if g == groups[0]:
            # Direct label on the series the figure is about. The legend names all three.
            ax.text(pts[-1][0], pts[-1][1], f"  {g}", color=INK, fontsize=8.5, va="center", ha="left")
    mark_releases(ax, releases, ymax)
    import datetime as dt
    ax.text(dt.date(2026, 1, 3), ymax * 0.9, "Q1 2026:\nmost renewals", color=INK_2,
            fontsize=8.5, va="top", ha="left")
    ax.set_ylim(0, ymax)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("Weekly QC failure rate, firmware 4.0.0 and later", loc="left",
                 color=INK, fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -0.14), ncol=3, frameon=False,
              fontsize=8.5, labelcolor=INK)
    ax.margins(x=0)
    fig.text(0.01, 0.01, "Failures ÷ (passes + failures). Skipped QC excluded. Dashed lines: firmware releases. "
             "Duplicate runs removed.", color=INK_2, fontsize=7.5)
    fig.subplots_adjust(right=0.86, bottom=0.24, top=0.9, left=0.06)
    fig.savefig(FIG / "qc_rate_over_time.png", facecolor=SURFACE)
    plt.close(fig)


def affected_firmware_share(con):
    # Share of HX-200 runs on 4.1.0 or 4.1.1 each week: how fast the fleet
    # moved onto those versions, and how slowly it left them after 4.1.2.
    rows = con.execute("""
        select date_trunc('week', r.run_date)::date as week,
               avg((r.firmware_version in ('4.1.0', '4.1.1'))::int) as share
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200'
          and date_trunc('week', r.run_date) >= date '2025-09-01'
          and date_trunc('week', r.run_date) <  date '2026-08-31'
        group by 1 order by 1
    """).fetchall()
    releases = con.execute(RELEASES_SQL).fetchall()
    fig, ax = plt.subplots(figsize=(10, 3.0), dpi=160, facecolor=SURFACE)
    style(ax)
    shade_q1(ax)
    ax.plot([r[0] for r in rows], [r[1] for r in rows], color=SERIES[0], linewidth=2.2, zorder=3)
    mark_releases(ax, releases, 0.5)
    ax.set_ylim(0, 0.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("Share of HX-200 runs on firmware 4.1.0 or 4.1.1", loc="left",
                 color=INK, fontsize=12, fontweight="bold")
    ax.margins(x=0)
    fig.subplots_adjust(right=0.86, bottom=0.2, top=0.86, left=0.06)
    fig.savefig(FIG / "affected_firmware_share.png", facecolor=SURFACE)
    plt.close(fig)



# Three sites chosen to show the story, one row each:
#   S0457  EU, one HX-200, took firmware 4.1.0, churned in Q1 2026
#   S0480  NA-East, two HX-200s, same firmware exposure, renewed in Q1 2026
#   S0362  one of the 10 sites whose only listed instrument arrived after its decision
TIMELINE_SITES = ["S0457", "S0480", "S0362"]
PASS_GRAY, FAIL, TICKET_GRAY, APP = "#b9b8b2", "#eb6834", "#8a8984", "#9fb7d8"
CHURN, RENEW = "#e34948", "#2a78d6"


def site_timelines(con, sites=TIMELINE_SITES):
    import datetime as dt
    import matplotlib.lines as mlines
    releases = con.execute(RELEASES_SQL).fetchall()
    start, end = dt.date(2025, 9, 1), dt.date(2026, 9, 1)

    # Lanes per site: one per instrument, then tickets, then app use.
    plans = []
    for s in sites:
        info = con.execute("""select m.site_id, m.region, m.segment, m.tier, m.churned, m.decision_date
                              from site_renewal m where site_id = ?""", [s]).fetchone()
        insts = con.execute("""select instrument_id, model, install_date from stg_instruments
                               where site_id = ? order by install_date""", [s]).fetchall()
        plans.append((info, insts))
    heights = [len(p[1]) + 2 for p in plans]

    fig, axes = plt.subplots(len(sites), 1, figsize=(11, 1.15 * sum(heights) + 1.4), dpi=160,
                             facecolor=SURFACE, sharex=True, gridspec_kw={"height_ratios": heights})
    for ax, (info, insts) in zip(axes, plans):
        site, region, segment, tier, churned, decision = info
        n = len(insts)
        ax.set_facecolor(SURFACE)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=INK_2, labelsize=8.5, length=0)
        lanes = [f"{iid} · {model}" for iid, model, _ in insts] + ["Support tickets", "App use (weekly)"]
        ax.set_yticks(range(len(lanes)))
        ax.set_yticklabels(lanes, fontsize=8.5, color=INK)
        ax.set_ylim(len(lanes) - 0.4, -0.8)

        # The 90 days before the decision, and the decision itself.
        ax.axvspan(decision - dt.timedelta(days=90), decision, color=Q1_BAND, zorder=0)
        color = CHURN if churned else RENEW
        ax.axvline(decision, color=color, linewidth=2, zorder=2)
        ax.text(decision, -0.75, f" {'Churned' if churned else 'Renewed'} {decision:%Y-%m-%d}",
                color=color, fontsize=8.5, fontweight="bold", va="top", ha="left")
        for version, day in releases:
            ax.axvline(day, color=GRID, linewidth=1, linestyle=(0, (2, 3)), zorder=1)

        for lane, (iid, model, install) in enumerate(insts):
            runs = con.execute("""select run_date, qc_status, assay_type, firmware_version
                                  from stg_runs where instrument_id = ? order by run_ts""", [iid]).fetchall()
            ax.axhline(lane, color=GRID, linewidth=0.8, zorder=1)
            for d, status, assay, fw in runs:
                if status == "fail":
                    ax.scatter(d, lane, s=34, color=FAIL, marker="D" if assay == "IA-Panel-3" else "o",
                               zorder=4, linewidths=0)
                elif status == "skipped":
                    ax.scatter(d, lane, s=14, facecolors="none", edgecolors=PASS_GRAY, zorder=3)
                else:
                    ax.scatter(d, lane, s=10, color=PASS_GRAY, zorder=3, linewidths=0)
            # Label the firmware each time it changes on this instrument.
            last = None
            for d, _, _, fw in runs:
                if fw != last:
                    ax.text(d, lane - 0.28, fw, color=INK_2, fontsize=7.5, ha="left", va="bottom")
                    last = fw
            if start <= install < end:
                ax.scatter(install, lane, s=60, marker="^", color=INK, zorder=5)
                ax.text(install, lane + 0.3, " installed", color=INK, fontsize=7.5, va="top", ha="left")

        # Support tickets: QC rejection tickets stand out.
        t_lane = n
        ax.axhline(t_lane, color=GRID, linewidth=0.8, zorder=1)
        last_label = None
        for d, cat in con.execute("""select cast(opened_ts as date), category from stg_support_tickets
                                     where site_id = ? order by opened_ts""", [site]).fetchall():
            qc = cat == "qc_rejection"
            ax.scatter(d, t_lane, s=40 if qc else 26, marker="X", color=FAIL if qc else TICKET_GRAY, zorder=4,
                       linewidths=0)
            # Skip a label that would collide with the previous one.
            if last_label is None or (d - last_label).days > 25:
                ax.text(d, t_lane - 0.22, cat.replace("_", " "), color=INK_2, fontsize=6.5, ha="center", va="bottom")
                last_label = d

        # App use: weekly sampled events x 10, drawn as short bars inside the lane.
        a_lane = n + 1
        weeks = con.execute("""select date_trunc('week', cast(event_ts as date))::date, 10 * count(*)
                               from stg_app_events where site_id = ? group by 1 order by 1""", [site]).fetchall()
        peak = max([w[1] for w in weeks], default=1)
        for w, cnt in weeks:
            h = 0.7 * cnt / peak
            ax.bar(w, h, width=5, bottom=a_lane + 0.35 - h, color=APP, zorder=3, align="edge")

        ax.set_title(f"{site}  ·  {region}  ·  {segment.replace('_', ' ')}  ·  {tier}",
                     loc="left", color=INK, fontsize=10.5, fontweight="bold")
        ax.set_xlim(start, end)

    for version, day in releases:
        axes[0].text(day, -1.35, version, color=INK_2, fontsize=8, ha="center", va="bottom")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))

    legend = [
        mlines.Line2D([], [], color=PASS_GRAY, marker="o", linestyle="", markersize=4, label="QC pass"),
        mlines.Line2D([], [], color=FAIL, marker="D", linestyle="", markersize=5, label="QC fail, IA-Panel-3"),
        mlines.Line2D([], [], color=FAIL, marker="o", linestyle="", markersize=5, label="QC fail, other assay"),
        mlines.Line2D([], [], markeredgecolor=PASS_GRAY, markerfacecolor="none", marker="o", linestyle="",
                      markersize=5, label="QC skipped"),
        mlines.Line2D([], [], color=INK, marker="^", linestyle="", markersize=6, label="Instrument installed"),
        mlines.Line2D([], [], color=FAIL, marker="X", linestyle="", markersize=6, label="QC rejection ticket"),
        mlines.Line2D([], [], color=TICKET_GRAY, marker="X", linestyle="", markersize=6, label="Other ticket"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=7, frameon=False, fontsize=8, labelcolor=INK,
               bbox_to_anchor=(0.5, 0.005))
    fig.text(0.01, 0.985, "Site timelines: runs, firmware, installs, tickets and app use", color=INK,
             fontsize=12, fontweight="bold", va="top")
    fig.text(0.01, 0.958, "Shaded: the 90 days before each renewal decision. Dotted: firmware releases. "
             "Labels on each instrument lane: firmware at each change.", color=INK_2, fontsize=8, va="top")
    fig.subplots_adjust(left=0.16, right=0.98, top=0.9, bottom=0.09, hspace=0.45)
    fig.savefig(FIG / "site_timelines.png", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    FIG.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ROOT / "output" / "halvard.duckdb"), read_only=True)
    con.execute("set TimeZone = 'UTC'")
    qc_rate_over_time(con)
    affected_firmware_share(con)
    site_timelines(con)
    print("wrote", *sorted(p.name for p in FIG.glob("*.png")))
