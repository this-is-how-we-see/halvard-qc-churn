"""Statistical tests and comparison tables.

Usage:  python src/analysis.py   (run src/build.py first)
Writes: output/tables/*.csv, output/stats.json,
        output/figures/lot_test_by_firmware.png, output/figures/lot_test_event_time.png,
        output/figures/adoption_and_failures.png, output/figures/visible_before_fixed.png,
        output/figures/churn_by_segment_region.png, output/figures/what_goes_with_churn.png,
        output/figures/eu_support_churn.png, output/figures/lost_by_region_and_lab.png

Part A asks whether a bad QC control lot, rather than the firmware, can explain
the HX-200 IA-Panel-3 failures. The pack has no lot data, so the test uses the
one thing a lot problem must follow: calendar time. A bad lot reaches every lab
that uses it over the same weeks. A firmware defect follows each instrument's
own firmware version.

Part B is the comparison across sites: does QC failure still go with churn
among similar sites?

Part C is the customer story: tickets, response times and the renewal cost.

Part D holds follow-up checks on Parts B and C: the European channel, app use,
decisions made after the fix, a QC failure threshold, a baseline for normal churn,
the smallest group worth reporting, a backtest of the fleet QC monitor, instruments
still on the affected firmware, and a range for the ARR estimate. These are
exploratory. The primary test is the exposure comparison in Part B.
"""
from pathlib import Path
import json
import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.stats.proportion import proportion_confint, proportions_ztest
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUT, TAB, FIG = ROOT / "output", ROOT / "output" / "tables", ROOT / "output" / "figures"
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
AFFECTED = ["4.1.0", "4.1.1"]


def wilson(k, n):
    lo, hi = proportion_confint(k, n, method="wilson") if n else (np.nan, np.nan)
    return lo, hi


def rate_table(df, by, outcome):
    # Count, events, rate and a 95% Wilson interval for each group.
    g = df.groupby(by, observed=True)[outcome].agg(["size", "sum"]).reset_index()
    g.columns = list(g.columns[:-2]) + ["n", "events"]
    g["rate"] = g["events"] / g["n"]
    ci = [wilson(k, n) for k, n in zip(g["events"], g["n"])]
    g["ci_low"], g["ci_high"] = [c[0] for c in ci], [c[1] for c in ci]
    return g


def odds_ratios(model, keep):
    ci = model.conf_int()
    rows = []
    for term in model.params.index:
        if any(term.startswith(k) for k in keep):
            rows.append({"term": term, "odds_ratio": np.exp(model.params[term]),
                         "ci_low": np.exp(ci.loc[term, 0]), "ci_high": np.exp(ci.loc[term, 1]),
                         "p_value": model.pvalues[term]})
    return pd.DataFrame(rows)


def style(ax):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)



# Presentation figures share one format: 16:9, a takeaway title, a one-line subtitle,
# a legend row, and a source line. Orange always means the affected firmware or the
# problem; grey means the comparison; blue is a neutral trend over time.
GREY = "#a8a6a0"


def slide(title, subtitle, source, nrows=1, ncols=1, **kw):
    fig, axes = plt.subplots(nrows, ncols, figsize=(12, 6.75), dpi=150, facecolor=SURFACE, **kw)
    fig.text(0.04, 0.945, title, color=INK, fontsize=17, fontweight="bold", va="top")
    fig.text(0.04, 0.885, subtitle, color=INK_2, fontsize=12, va="top")
    fig.text(0.04, 0.025, source, color=INK_2, fontsize=9.5, va="bottom")
    for ax in np.atleast_1d(axes).ravel():
        style(ax)
        ax.tick_params(labelsize=10.5)
    return fig, axes


def legend_row(fig, items, y=0.835):
    # Coloured squares with labels, in a row under the subtitle, clear of the plots.
    x = 0.04
    for color, label in items:
        fig.patches.append(matplotlib.patches.Rectangle((x, y - 0.012), 0.012, 0.022, color=color,
                                                        transform=fig.transFigure, figure=fig))
        fig.text(x + 0.018, y, label, color=INK, fontsize=10.5, va="center")
        x += 0.018 + 0.0072 * len(label) + 0.03


# ---------------------------------------------------------------- Part A

def lot_test(con, results):
    runs = con.execute("""
        select r.instrument_id, i.model, r.assay_type, r.run_date, r.firmware_version,
               (r.qc_status = 'fail')::int as fail
        from stg_runs r join stg_instruments i using (instrument_id)
        where r.fw_major >= 4 and r.qc_status in ('pass', 'fail')
    """).df()
    runs["run_date"] = pd.to_datetime(runs["run_date"])
    hx = runs[(runs.model == "HX-200") & (runs.assay_type == "IA-Panel-3")].copy()
    hx["affected"] = hx.firmware_version.isin(AFFECTED).astype(int)
    hx["month"] = hx.run_date.dt.strftime("%Y-%m")

    # Test 1: calendar month against firmware, in one model.
    # If a lot problem drove the failures, month would matter after firmware.
    m_month = smf.logit("fail ~ C(month)", data=hx).fit(disp=0)
    m_fw = smf.logit("fail ~ affected", data=hx).fit(disp=0)
    m_both = smf.logit("fail ~ affected + C(month)", data=hx).fit(disp=0)
    lr_month = 2 * (m_both.llf - m_fw.llf)
    df_month = int(m_both.df_model - m_fw.df_model)
    lr_fw = 2 * (m_both.llf - m_month.llf)
    ci = m_both.conf_int().loc["affected"]
    results["lot_model"] = {
        "runs": int(len(hx)),
        "firmware_odds_ratio": float(np.exp(m_both.params["affected"])),
        "firmware_or_ci": [float(np.exp(ci[0])), float(np.exp(ci[1]))],
        "firmware_lr_chi2": float(lr_fw), "firmware_p": float(stats.chi2.sf(lr_fw, 1)),
        "month_lr_chi2": float(lr_month), "month_df": df_month,
        "month_p": float(stats.chi2.sf(lr_month, df_month)),
    }

    # Test 2: the same calendar window, split by firmware.
    win = hx[(hx.run_date >= "2025-12-01") & (hx.run_date <= "2026-03-31")]
    plus = runs[(runs.model == "HX-200 Plus") & (runs.assay_type == "IA-Panel-3")
                & (runs.run_date >= "2025-12-01") & (runs.run_date <= "2026-03-31")]
    rows = []
    for fw in ["4.0.0", "4.0.2", "4.1.0", "4.1.1"]:
        s = win[win.firmware_version == fw]
        rows.append(("HX-200 · IA-Panel-3", fw, len(s), int(s.fail.sum())))
    s = plus[plus.firmware_version.isin(AFFECTED)]
    rows.append(("HX-200 Plus · IA-Panel-3", "4.1.0 or 4.1.1", len(s), int(s.fail.sum())))
    t = pd.DataFrame(rows, columns=["group", "firmware", "n", "events"])
    t["rate"] = t.events / t.n
    t["ci_low"], t["ci_high"] = zip(*[wilson(k, n) for k, n in zip(t.events, t.n)])
    t.to_csv(TAB / "lot_same_window.csv", index=False)
    a = win[win.affected == 1]
    b = win[win.firmware_version.isin(["4.0.0", "4.0.2"])]
    z, p = proportions_ztest([a.fail.sum(), b.fail.sum()], [len(a), len(b)])
    results["lot_same_window"] = {"affected": [int(a.fail.sum()), int(len(a))],
                                  "unaffected": [int(b.fail.sum()), int(len(b))], "z": float(z), "p": float(p)}

    # Test 3: each instrument's own move to 4.1.2, 60 days either side.
    up = runs[runs.firmware_version == "4.1.2"].groupby("instrument_id").run_date.min().rename("up")
    e = hx.join(up, on="instrument_id", how="inner")
    e["t"] = (e.run_date - e.up).dt.days
    e = e[e.t.abs() <= 60].copy()
    e["post"] = e.t >= 0
    per = e.groupby(["instrument_id", "post"]).fail.mean().unstack().dropna()
    w = stats.wilcoxon(per[False], per[True])
    results["lot_event_time"] = {
        "instruments": int(e.instrument_id.nunique()),
        "before": [int(e[~e.post].fail.sum()), int((~e.post).sum())],
        "after": [int(e[e.post].fail.sum()), int(e.post.sum())],
        "upgrade_first": str(up[up.index.isin(e.instrument_id)].min().date()),
        "upgrade_last": str(up[up.index.isin(e.instrument_id)].max().date()),
        "paired_instruments": int(len(per)),
        "lower_after": int((per[True] < per[False]).sum()),
        "same": int((per[True] == per[False]).sum()),
        "higher_after": int((per[True] > per[False]).sum()),
        "wilcoxon_p": float(w.pvalue),
    }
    e["week"] = np.floor(e.t / 7).astype(int)
    wk = rate_table(e[(e.week >= -8) & (e.week <= 7)], "week", "fail")
    wk.to_csv(TAB / "lot_event_time.csv", index=False)

    # Figure: same window by firmware.
    fig, ax = plt.subplots(figsize=(8.5, 3.6), dpi=160, facecolor=SURFACE)
    style(ax)
    labels = [f"{g.replace(' · IA-Panel-3', '')}\n{f}" for g, f in zip(t.group, t.firmware)]
    colors = [BLUE, BLUE, ORANGE, ORANGE, AQUA]
    x = np.arange(len(t))
    ax.errorbar(x, t.rate, yerr=[t.rate - t.ci_low, t.ci_high - t.rate], fmt="none",
                ecolor=INK_2, elinewidth=1.2, capsize=4, zorder=2)
    ax.scatter(x, t.rate, s=70, color=colors, zorder=3)
    for xi, r, n in zip(x, t.rate, t.n):
        ax.text(xi + 0.12, r, f"{r:.1%}\n{n:,} runs", color=INK, fontsize=8.5, va="center")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5, color=INK)
    ax.set_xlim(-0.5, len(t) - 0.2)
    ax.set_ylim(0, 0.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("IA-Panel-3 QC failure rate, December 2025 to March 2026, by firmware",
                 loc="left", color=INK, fontsize=11, fontweight="bold")
    fig.text(0.01, 0.01, "Same four months for every group, so the same control lots were on the market. "
             "Bars: 95% Wilson intervals.", color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.24, top=0.88, left=0.07, right=0.97)
    fig.savefig(FIG / "lot_test_by_firmware.png", facecolor=SURFACE)
    plt.close(fig)

    # Figure: event time around each instrument's own upgrade.
    r = results["lot_event_time"]
    b, a = r["before"][0] / r["before"][1], r["after"][0] / r["after"][1]
    fig, ax = slide("QC failures dropped the week each instrument installed 4.1.2",
                    f"HX-200 IA-Panel-3 QC failure rate, by week before and after each instrument's own upgrade, "
                    f"{r['instruments']} instruments",
                    f"Source: Halvard instrument telemetry. Upgrades ran from {r['upgrade_first']} to {r['upgrade_last']}, "
                    "so week 0 is a different date for each instrument. Shaded band: likely range.")
    fig.subplots_adjust(top=0.8, bottom=0.2, left=0.07, right=0.96)
    ax.fill_between(wk.week, wk.ci_low, wk.ci_high, color=BLUE, alpha=0.15, linewidth=0)
    ax.plot(wk.week, wk.rate, color=BLUE, linewidth=2.4, marker="o", markersize=5)
    ax.axvline(-0.5, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    box = dict(facecolor=SURFACE, edgecolor="none", pad=1.5)
    ax.text(-0.35, 0.47, "Each instrument moves to 4.1.2", color=INK, fontsize=10.5, va="center", bbox=box)
    ax.text(-5.2, 0.475, f"{b:.0%} of runs failed before", color=INK, fontsize=11, fontweight="bold", ha="center", bbox=box)
    ax.text(3.5, 0.17, f"{a:.0%} after", color=INK, fontsize=11, fontweight="bold", ha="center", bbox=box)
    ax.set_xticks(range(-8, 8))
    ax.set_xticklabels([f"{w:+d}" if w else "0" for w in range(-8, 8)])
    ax.set_xlabel("Weeks from that instrument's own upgrade", color=INK_2, fontsize=10.5)
    ax.set_ylim(0, 0.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    fig.savefig(FIG / "lot_test_event_time.png", facecolor=SURFACE)
    plt.close(fig)


def adoption(con, results):
    # Weekly: share of HX-200 IA-Panel-3 runs on 4.1.0 or 4.1.1, and the QC failure rate.
    w = con.execute("""
        select date_trunc('week', r.run_date)::date as week,
               avg((r.firmware_version in ('4.1.0', '4.1.1'))::int) as affected_share,
               count(*) filter (where r.qc_status = 'fail') * 1.0
                 / nullif(count(*) filter (where r.qc_status in ('pass', 'fail')), 0) as fail_rate,
               count(*) as n
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.fw_major >= 4
          and date_trunc('week', r.run_date) >= date '2025-09-01'
          and date_trunc('week', r.run_date) <  date '2026-08-31'
        group by 1 order by 1
    """).df()
    w.to_csv(TAB / "adoption_weekly.csv", index=False)
    f = smf.wls("fail_rate ~ affected_share", data=w, weights=w.n).fit()
    results["adoption"] = {"weeks": int(len(w)), "intercept": float(f.params["Intercept"]),
                           "slope": float(f.params["affected_share"]), "r2": float(f.rsquared),
                           "slope_p": float(f.pvalues["affected_share"])}
    rel = con.execute("""select version, release_date from stg_firmware_releases
                         where release_date between date '2025-09-01' and date '2026-08-31'""").fetchall()
    fig, axes = slide("QC failures rose and fell with the share of runs on the affected firmware",
                      "HX-200 IA-Panel-3, weekly",
                      "Source: Halvard instrument telemetry, September 2025 to August 2026. Dashed lines: firmware releases.",
                      nrows=2, sharex=True)
    fig.subplots_adjust(top=0.8, bottom=0.14, left=0.07, right=0.96, hspace=0.5)
    box = dict(facecolor=SURFACE, edgecolor="none", pad=1.2)
    for ax, col, color, title, top in [
        (axes[0], "affected_share", ORANGE, "A.  Share of runs on firmware 4.1.0 or 4.1.1", 0.6),
        (axes[1], "fail_rate", BLUE, "B.  QC failure rate", 0.3)]:
        ax.plot(pd.to_datetime(w.week), w[col], color=color, linewidth=2.4)
        for v, d in rel:
            ax.axvline(pd.Timestamp(d), color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
            ax.text(pd.Timestamp(d) + pd.Timedelta(days=3), top * 0.93, v, color=INK, fontsize=10,
                    va="center", ha="left", bbox=box)
        ax.set_ylim(0, top)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_title(title, loc="left", color=INK, fontsize=11.5, fontweight="bold")
    axes[1].xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    axes[1].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    fig.savefig(FIG / "adoption_and_failures.png", facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------- Part B

def comparison(con, results):
    sites = con.execute("select * from site_renewal where cohort = 'main'").df()
    # Did the site run HX-200 IA-Panel-3 on the affected firmware in its 90 days?
    exp = con.execute(f"""
        select m.site_id, count(*) as affected_runs
        from site_renewal m
        join stg_instruments i on i.site_id = m.site_id and i.model = 'HX-200'
        join stg_runs r on r.instrument_id = i.instrument_id
         and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1')
         and r.run_date >= m.decision_date - interval 90 day and r.run_date < m.decision_date
        where m.cohort = 'main' group by 1
    """).df()
    sites = sites.merge(exp, on="site_id", how="left").fillna({"affected_runs": 0})
    sites["affected_exposure"] = np.where(sites.affected_runs > 0, "yes", "no")
    sites["churn"] = sites.churned.astype(int)
    sites["qc_band"] = pd.cut(sites.qc_fail_rate, [-0.001, 0.0, 0.05, 0.10, 0.20, 1.0],
                              labels=["0%", "over 0 to 5%", "over 5 to 10%", "over 10 to 20%", "over 20%"])
    sites["region_group"] = np.where(sites.region == "EU", "EU (distributor)", "Direct (NA, APAC)")
    sites["tickets_band"] = pd.cut(sites.tickets_90d, [-1, 0, 2, 100], labels=["0", "1 to 2", "3 or more"])
    sites["app_band"] = pd.qcut(sites.app_events_90d_est, 3, labels=["low", "middle", "high"])
    sites["runs_band"] = pd.qcut(sites.runs_90d.rank(method="first"), 3, labels=["low", "middle", "high"])
    sites.to_csv(TAB / "sites_main.csv", index=False)

    qc = sites[sites.in_qc_comparison]
    tables = {
        "churn_by_qc_band": rate_table(qc, "qc_band", "churn"),
        "churn_by_qc_band_check": rate_table(qc[~qc.partial_run_coverage], "qc_band", "churn"),
        "churn_by_region": rate_table(sites, "region", "churn"),
        "churn_by_segment": rate_table(sites, "segment", "churn"),
        "churn_by_tier": rate_table(sites, "tier", "churn"),
        "churn_by_affected_exposure": rate_table(sites, "affected_exposure", "churn"),
        "churn_by_tickets": rate_table(sites, "tickets_band", "churn"),
        "churn_by_app_use": rate_table(sites, "app_band", "churn"),
        "churn_by_run_volume": rate_table(sites, "runs_band", "churn"),
        "churn_by_qc_band_and_region": rate_table(qc, ["region_group", "qc_band"], "churn"),
        "churn_by_exposure_and_region": rate_table(sites, ["region_group", "affected_exposure"], "churn"),
    }
    for name, t in tables.items():
        t.to_csv(TAB / f"{name}.csv", index=False)

    # Median of each factor for churned against renewed sites.
    cols = ["qc_fail_rate", "runs_90d", "app_events_90d_est", "qc_review_90d_est", "tickets_90d",
            "median_first_response_hrs", "ia3_share", "fw_410_411_share", "n_instruments", "arr_usd"]
    med = sites.groupby("churned")[cols].median().T.reset_index()
    med.columns = ["factor", "renewed_median", "churned_median"]
    med.to_csv(TAB / "factor_medians.csv", index=False)

    keep = ["C(affected", "C(region", "C(segment", "C(tier", "log_runs"]

    # Models without app use and tickets. Both can sit on the path from QC
    # failures to churn (a lab with failures files tickets and uses the app
    # less), so holding them equal can hide a real effect of QC.
    def prep(df):
        d = df.copy()
        d["log_runs"] = np.log1p(d.runs_90d)
        return d
    base = " + C(region, Treatment('NA-East')) + C(segment) + C(tier) + log_runs"
    m_exp = smf.logit("churn ~ C(affected_exposure)" + base, data=prep(sites)).fit(disp=0)
    odds_ratios(m_exp, keep).to_csv(TAB / "regression_exposure_no_mediators.csv", index=False)
    path = sites.groupby("affected_exposure").agg(
        sites=("site_id", "size"), median_tickets=("tickets_90d", "median"),
        qc_rejection_tickets_per_site=("qc_rejection_tickets_90d", "mean"),
        median_app_events=("app_events_90d_est", "median")).reset_index()
    path.to_csv(TAB / "path_by_exposure.csv", index=False)
    reg = sites.groupby("region_group").agg(
        sites=("site_id", "size"), median_tickets=("tickets_90d", "median"),
        median_first_response_hrs=("median_first_response_hrs", "median"),
        median_app_events=("app_events_90d_est", "median")).reset_index()
    reg.to_csv(TAB / "support_by_region.csv", index=False)
    results["regression"] = {"sites": int(m_exp.nobs), "churned": int(sites.churn.sum()),
                             "pseudo_r2": float(m_exp.prsquared)}


# ---------------------------------------------------------------- Part C

def customer_story(con, results):
    """What users did after the failures began, how fast Halvard responded,
    and what it cost in renewals."""
    # QC rejection tickets and first response, by month.
    t = con.execute("""
        select strftime(cast(opened_ts as date), '%Y-%m') as month,
               count(*) as tickets,
               count(*) filter (where category = 'qc_rejection') as qc_rejection_tickets,
               median(first_response_hours) filter (where category = 'qc_rejection') as qc_rejection_median_response_hrs
        from stg_support_tickets group by 1 order by 1
    """).df()
    t.to_csv(TAB / "tickets_by_month.csv", index=False)

    # Every QC rejection ticket, split by whether its site ever ran the defect.
    q = con.execute("""
        with aff as (select distinct i.site_id from stg_runs r join stg_instruments i using (instrument_id)
                     where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3'
                       and r.firmware_version in ('4.1.0', '4.1.1'))
        select case when s.region = 'EU' then 'EU (distributor)' else 'Direct (NA, APAC)' end as region_group,
               t.site_id in (select site_id from aff) as site_ran_defect,
               count(*) as qc_rejection_tickets,
               median(t.first_response_hours) as median_first_response_hrs,
               min(cast(t.opened_ts as date)) as first_ticket
        from stg_support_tickets t join stg_sites s using (site_id)
        where t.category = 'qc_rejection' group by 1, 2 order by 1, 2
    """).df()
    q.to_csv(TAB / "qc_rejection_tickets_by_region.csv", index=False)

    # Detection: weekly HX-200 IA-Panel-3 runs on 4.1.0, tested against the 4.0.x baseline.
    base = con.execute("""
        select count(*) filter (where r.qc_status = 'fail') * 1.0
               / count(*) filter (where r.qc_status in ('pass', 'fail'))
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.0.0', '4.0.2')
    """).fetchone()[0]
    d = con.execute("""
        select date_trunc('week', r.run_date)::date as week,
               count(*) filter (where r.qc_status in ('pass', 'fail')) as n,
               count(*) filter (where r.qc_status = 'fail') as fails
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version = '4.1.0'
          and r.run_date < date '2025-12-15'
        group by 1 order by 1
    """).df()
    d["rate"] = d.fails / d.n
    d["p_vs_baseline"] = [stats.binomtest(int(f), int(n), base, alternative="greater").pvalue if n else np.nan
                          for f, n in zip(d.fails, d.n)]
    d.to_csv(TAB / "detection_weekly.csv", index=False)
    clear = d[(d.p_vs_baseline < 0.001) & (d.n >= 20)].week.min()
    first = con.execute("""select min(r.run_date) from stg_runs r join stg_instruments i using (instrument_id)
                           where i.model = 'HX-200' and r.firmware_version = '4.1.0'""").fetchone()[0]
    e117 = con.execute("select min(run_date) from stg_runs where error_code = 'E-117'").fetchone()[0]
    fix = con.execute("select release_date from stg_firmware_releases where version = '4.1.2'").fetchone()[0]
    rel = con.execute("select release_date from stg_firmware_releases where version = '4.1.0'").fetchone()[0]
    first_ticket = q[q.site_ran_defect].first_ticket.min()

    # Renewal cost: exposed main-cohort sites against the unexposed baseline.
    s = pd.read_csv(TAB / "sites_main.csv", parse_dates=["decision_date"])
    exp, unexp = s[s.affected_exposure == "yes"], s[s.affected_exposure == "no"]
    base_churn = unexp.churn.mean()
    excess = exp.churn.sum() - base_churn * len(exp)
    # Notice sites count as exposed if they EVER ran the defect, not in a 90-day
    # window. All 9 are short_history: their decision dates (last renewal) fall
    # 2025-09-13 to 2025-11-18, before or as the defect reached the fleet, so a
    # window before the decision measures nothing. This is an at-risk signal,
    # not a figure to add to the main-cohort excess.
    notice = con.execute("""
        with aff as (select distinct i.site_id from stg_runs r join stg_instruments i using (instrument_id)
                     where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3'
                       and r.firmware_version in ('4.1.0', '4.1.1'))
        select count(*), sum(arr_usd), count(*) filter (where site_id in (select site_id from aff)),
               sum(arr_usd) filter (where site_id in (select site_id from aff))
        from stg_subscriptions where status = 'notice'
    """).fetchone()
    ex_ch = exp[exp.churn == 1]
    results["customer_story"] = {
        "release_410": str(rel), "first_hx200_run_410": str(first), "first_e117": str(e117),
        "signal_clear_week": str(clear), "first_qc_rejection_ticket": str(first_ticket), "fix_412": str(fix),
        "days_signal_to_fix": int((pd.Timestamp(fix) - pd.Timestamp(clear)).days),
        "days_first_ticket_to_fix": int((pd.Timestamp(fix) - pd.Timestamp(first_ticket)).days),
        "baseline_fail_rate": float(base),
        "qc_rejection_tickets_total": int(q.qc_rejection_tickets.sum()),
        "qc_rejection_tickets_from_defect_sites": int(q[q.site_ran_defect].qc_rejection_tickets.sum()),
        "exposed_sites": int(len(exp)), "exposed_churned": int(exp.churn.sum()),
        "exposed_churned_before_fix": int((ex_ch.decision_date < pd.Timestamp(fix)).sum()),
        "baseline_churn": float(base_churn), "excess_churned_sites": float(excess),
        "exposed_churned_arr": int(ex_ch.arr_usd.sum()),
        "excess_arr": float(excess * ex_ch.arr_usd.mean()),
        "notice_sites": int(notice[0]), "notice_arr": int(notice[1]),
        "notice_sites_exposed": int(notice[2]), "notice_arr_exposed": int(notice[3]),
        "notice_exposure_rule": "ever ran the defect; all notice sites are short_history",
    }

    # Filing a QC rejection ticket, among exposed sites.
    ft = pd.crosstab(np.where(exp.qc_rejection_tickets_90d > 0, "filed", "none"), exp.churn)
    fisher = stats.fisher_exact(ft.values)
    results["ticket_filed_vs_churn"] = {
        "filed": [int(ft.loc["filed", 1]), int(ft.loc["filed"].sum())],
        "none": [int(ft.loc["none", 1]), int(ft.loc["none"].sum())], "fisher_p": float(fisher.pvalue)}

    # The leadership chart: the defect was visible long before it was fixed.
    w = con.execute("""
        select date_trunc('week', r.run_date)::date as week,
               count(*) filter (where r.qc_status = 'fail') * 1.0
                 / nullif(count(*) filter (where r.qc_status in ('pass', 'fail')), 0) as rate
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.fw_major >= 4
          and r.run_date >= date '2025-09-01' and date_trunc('week', r.run_date) < date '2026-08-31'
        group by 1 order by 1
    """).df()
    tk = con.execute("""
        select date_trunc('week', cast(opened_ts as date))::date as week, count(*) as n
        from stg_support_tickets where category = 'qc_rejection' group by 1 order by 1
    """).df()
    cs = results["customer_story"]
    lo, hi, r410 = pd.Timestamp(clear), pd.Timestamp(fix), pd.Timestamp(rel)
    fig, axes = slide(f"The defect was visible for {cs['days_signal_to_fix']} days before the fix shipped",
                      "HX-200 IA-Panel-3 QC failures, QC rejection tickets and lost renewals, by week",
                      "Source: Halvard instrument telemetry, support tickets and subscriptions, September 2025 to "
                      "August 2026. Shading starts the week the rise was statistically clear.",
                      nrows=3, sharex=True, gridspec_kw={"height_ratios": [3, 1.5, 1]})
    fig.subplots_adjust(top=0.78, bottom=0.14, left=0.07, right=0.96, hspace=0.55)
    for ax in axes:
        ax.axvspan(lo, hi, color=ORANGE, alpha=0.10, linewidth=0, zorder=0)
        for day in (r410, hi):
            ax.axvline(day, color=INK_2, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
    box = dict(facecolor=SURFACE, edgecolor="none", pad=1.5)
    ax = axes[0]
    ax.plot(pd.to_datetime(w.week), w.rate, color=BLUE, linewidth=2.4, zorder=3)
    ax.set_ylim(0, 0.34)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("A.  QC failure rate", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    ax.text(r410 - pd.Timedelta(days=3), 0.31, "4.1.0 released", color=INK, fontsize=10, ha="right",
            va="center", bbox=box, zorder=4)
    ax.text(hi + pd.Timedelta(days=3), 0.31, "4.1.2 fix released", color=INK, fontsize=10, ha="left",
            va="center", bbox=box, zorder=4)
    ax.text(lo + (hi - lo) / 2, 0.035, f"Clear in telemetry to fix: {cs['days_signal_to_fix']} days",
            color=ORANGE, fontsize=11, fontweight="bold", ha="center", bbox=box, zorder=4)
    ax = axes[1]
    ax.bar(pd.to_datetime(tk.week), tk.n, width=5, color=GREY, zorder=3)
    ax.set_title("B.  QC rejection tickets", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    ax.set_ylim(0, tk.n.max() + 1.5)
    ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(2))
    ft = pd.Timestamp(first_ticket)
    ax.annotate(f"First ticket, {(ft - r410).days} days after release", xy=(ft, 1), xytext=(ft - pd.Timedelta(days=62), 5.2),
                color=INK, fontsize=10, va="center", arrowprops=dict(arrowstyle="-", color=INK_2, lw=0.8),
                bbox=box, zorder=4)
    ax = axes[2]
    before = [d for d in ex_ch.decision_date if d < hi]
    after = [d for d in ex_ch.decision_date if d >= hi]
    ax.scatter(before, [0.5] * len(before), s=42, color=ORANGE, zorder=3, linewidths=0)
    ax.scatter(after, [0.5] * len(after), s=42, color=GREY, zorder=3, linewidths=0)
    ax.set_yticks([])
    ax.set_ylim(0, 1)
    ax.set_title(f"C.  Lost renewals at sites that ran the affected firmware: {len(before)} before the fix, "
                 f"{len(after)} after", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    axes[2].xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    axes[2].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    fig.savefig(FIG / "visible_before_fixed.png", facecolor=SURFACE)
    plt.close(fig)


def churn_figures(con, results):
    """Two figures that explain the comparison inside the figure itself."""
    s = pd.read_csv(TAB / "sites_main.csv")
    # Figure 1: churn by segment and by region, split by whether the site ran the affected firmware.
    fig, axes = slide("Sites that ran the affected firmware lost more renewals, most of all in Europe",
                      "Share of sites that did not renew at the last cycle",
                      "Source: Halvard subscriptions and telemetry, 431 sites with 90 days of data before renewal.\n"
                      "Site counts under each group: did not run it / ran it. Smaller groups vary more by chance.",
                      ncols=2, sharey=True, gridspec_kw={"width_ratios": [3, 4]})
    fig.subplots_adjust(top=0.75, bottom=0.21, left=0.06, right=0.97, wspace=0.08)
    legend_row(fig, [(GREY, "Did not run the affected firmware"), (ORANGE, "Ran the affected firmware")])
    names = {"hospital_lab": "Hospital labs", "reference_lab": "Reference labs", "research": "Research labs",
             "EU": "Europe"}
    for ax, col, order, title in [
            (axes[0], "segment", ["hospital_lab", "reference_lab", "research"], "By segment"),
            (axes[1], "region", ["NA-East", "NA-West", "APAC", "EU"], "By region")]:
        counts = []
        for j2, (exp, color) in enumerate([("no", GREY), ("yes", ORANGE)]):
            t = rate_table(s[s.affected_exposure == exp], col, "churn").set_index(col).reindex(order)
            x = np.arange(len(order)) + (j2 - 0.5) * 0.36
            ax.bar(x, t.rate, width=0.34, color=color, zorder=3)
            for xi, r in zip(x, t.rate):
                ax.text(xi, r + 0.012, f"{r:.0%}", color=INK, fontsize=11, ha="center", va="bottom",
                        fontweight="bold" if exp == "yes" else "normal")
            counts.append(t.n.astype(int).tolist())
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([f"{names.get(o, o)}\n{a} / {b} sites" for o, a, b in zip(order, *counts)],
                           fontsize=10.5, color=INK)
        ax.set_title(title, loc="left", color=INK, fontsize=12, fontweight="bold")
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    axes[0].set_ylim(0, 0.5)
    fig.savefig(FIG / "churn_by_segment_region.png", facecolor=SURFACE)
    plt.close(fig)

    # Figure 2: the affected-firmware model as a forest plot, explained in the figure.
    t = pd.read_csv(TAB / "regression_exposure_no_mediators.csv")
    names = {"C(affected_exposure)[T.yes]": "Ran the affected firmware (vs did not)",
             "C(segment)[T.research]": "Research lab (vs hospital lab)",
             "C(region, Treatment('NA-East'))[T.EU]": "EU (vs NA-East)",
             "C(region, Treatment('NA-East'))[T.APAC]": "APAC (vs NA-East)",
             "log_runs": "Run volume (per step on a log scale)",
             "C(tier)[T.Plus]": "Plus tier (vs Basic)",
             "C(region, Treatment('NA-East'))[T.NA-West]": "NA-West (vs NA-East)",
             "C(segment)[T.reference_lab]": "Reference lab (vs hospital lab)"}
    t = t[t.term.isin(names)].copy()
    t["label"] = t.term.map(names)
    t = t.sort_values("odds_ratio")
    t["label"] = t.label.str.replace("EU (vs NA-East)", "Europe (vs NA-East)", regex=False)
    t["label"] = t.label.str.replace("Run volume (per step on a log scale)", "Higher run volume", regex=False)
    fig, ax = slide("The affected firmware raised the odds of losing a site, with other factors held equal",
                    "How each factor changes the odds of not renewing, against the group in brackets",
                    "Source: 431 sites, one model with all eight factors. Lines show the likely range; "
                    "a line that crosses \u00d71 could be chance.")
    fig.subplots_adjust(top=0.76, bottom=0.14, left=0.28, right=0.95)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    legend_row(fig, [(ORANGE, "The affected firmware"), (INK_2, "Clear difference"), (GREY, "Could be chance")])
    y = np.arange(len(t))
    cols = [ORANGE if term == "C(affected_exposure)[T.yes]" else (INK_2 if p < 0.05 else GREY)
            for term, p in zip(t.term, t.p_value)]
    ax.hlines(y, t.ci_low, t.ci_high, color=cols, linewidth=2.2)
    ax.scatter(t.odds_ratio, y, s=70, color=cols, zorder=3)
    for yi, (o, hi) in enumerate(zip(t.odds_ratio, t.ci_high)):
        ax.text(hi * 1.07, yi, f"\u00d7{o:.1f}", color=INK, fontsize=11, va="center")
    ax.axvline(1, color=INK, linewidth=1)
    ax.set_xscale("log")
    ax.set_xlim(0.15, 12)
    ax.set_xticks([0.25, 0.5, 1, 2, 4, 8])
    ax.set_xticklabels(["\u00d70.25", "\u00d70.5", "\u00d71", "\u00d72", "\u00d74", "\u00d78"])
    ax.xaxis.set_minor_locator(matplotlib.ticker.NullLocator())
    ax.set_yticks(y)
    ax.set_yticklabels(t.label, color=INK)
    ax.text(0.93, len(t) - 0.2, "less likely to leave", ha="right", color=INK_2, fontsize=10.5)
    ax.text(1.07, len(t) - 0.2, "more likely to leave", ha="left", color=INK_2, fontsize=10.5)
    ax.set_ylim(-0.6, len(t) + 0.3)
    fig.savefig(FIG / "what_goes_with_churn.png", facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------- Part D

def follow_ups(con, results):
    """Exploratory checks on Parts B and C."""
    s = pd.read_csv(TAB / "sites_main.csv", parse_dates=["decision_date"])
    s["region_group"] = np.where(s.region == "EU", "EU (distributor)", "Direct (NA, APAC)")
    exp, unexp = s[s.affected_exposure == "yes"], s[s.affected_exposure == "no"]
    fix = pd.Timestamp(con.execute("select release_date from stg_firmware_releases where version = '4.1.2'").fetchone()[0])
    out = {}

    def fisher(a, b):
        # Churn in group a against group b, as [churned, n] pairs.
        t = [[a[0], a[1] - a[0]], [b[0], b[1] - b[0]]]
        r = stats.fisher_exact(t)
        return {"a": a, "b": b, "odds_ratio": float(r.statistic), "p": float(r.pvalue)}
    kn = lambda d: [int(d.churn.sum()), int(len(d))]

    # D1. App use. App events sit in the same 90 days as the decision, so low use
    # can be a cause, a result of the defect, or a lab that already plans to leave.
    # It stays out of the causal model; this asks only whether the exposure gap
    # holds inside each app-use third.
    rate_table(s, ["app_band", "affected_exposure"], "churn").to_csv(TAB / "churn_by_exposure_and_app_use.csv", index=False)
    from statsmodels.stats.contingency_tables import StratifiedTable
    tables = [pd.crosstab(g.affected_exposure, g.churn).reindex(index=["yes", "no"], columns=[1, 0]).values
              for _, g in s.groupby("app_band", observed=True)]
    st = StratifiedTable(tables)
    out["exposure_within_app_use"] = {
        "pooled_odds_ratio": float(st.oddsratio_pooled), "cmh_p": float(st.test_null_odds().pvalue),
        "equal_odds_p": float(st.test_equal_odds().pvalue)}

    # D2. Small cells behind the region and segment gaps.
    rate_table(s, ["region_group", "segment", "affected_exposure"], "churn").to_csv(
        TAB / "churn_by_exposure_region_segment.csv", index=False)

    # D3. Sites that decided after 4.1.2 shipped. Their 90-day window can reach
    # back before the fix, and the fleet took weeks to install it.
    post = exp[exp.decision_date >= fix]
    late = con.execute(f"""
        select count(distinct m.site_id)
        from site_renewal m
        join stg_instruments i on i.site_id = m.site_id and i.model = 'HX-200'
        join stg_runs r on r.instrument_id = i.instrument_id
         and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1')
         and r.run_date >= date '{fix.date()}'
         and r.run_date >= m.decision_date - interval 90 day and r.run_date < m.decision_date
        where m.cohort = 'main' and m.decision_date >= date '{fix.date()}'
    """).fetchone()[0]
    out["decided_after_fix"] = {**fisher(kn(post), kn(unexp[unexp.decision_date >= fix])),
                                "sites_running_defect_after_fix": int(late)}
    # When did those sites last run the affected firmware, and did the ones still
    # running it after the fix churn more than the ones that had upgraded?
    last = con.execute(f"""
        select m.site_id, max(r.run_date) as last_affected_run
        from site_renewal m
        join stg_instruments i on i.site_id = m.site_id and i.model = 'HX-200'
        join stg_runs r on r.instrument_id = i.instrument_id
         and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1')
         and r.run_date < m.decision_date
        where m.cohort = 'main' and m.decision_date >= date '{fix.date()}'
        group by 1
    """).df()
    pl = post.merge(last, on="site_id", how="left")
    pl["last_affected_run"] = pd.to_datetime(pl.last_affected_run)
    still = pl[pl.last_affected_run >= fix]
    upgraded = pl[~(pl.last_affected_run >= fix)]
    out["decided_after_fix"]["still_running_vs_upgraded"] = {
        **fisher(kn(still), kn(upgraded)),
        "median_days_run_after_fix": float((still.last_affected_run - fix).dt.days.median()),
        "max_days_run_after_fix": int((still.last_affected_run - fix).dt.days.max()),
        "ran_it_within_30_days_of_renewal": int(((still.decision_date - still.last_affected_run).dt.days <= 30).sum())}

    # D13. The normal weekly range for HX-200 IA-Panel-3. A QC lab reads a control
    # failure rate against its normal range, not against an average or a slope. The
    # fleet runs about 200 QC runs of this combination a week, enough to set the range.
    # A site runs a median of about 5 per assay in its 90 days, too few for its own.
    wk = con.execute("""
        select date_trunc('week', r.run_date) as week,
               r.firmware_version in ('4.1.0', '4.1.1') as affected,
               count(*) filter (where r.qc_status = 'fail') as fails,
               count(*) filter (where r.qc_status in ('pass', 'fail')) as qc_runs
        from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version >= '4.0.0'
        group by 1, 2 having count(*) filter (where r.qc_status in ('pass', 'fail')) >= 20
        order by 1, 2
    """).df()
    wk["rate"] = wk.fails / wk.qc_runs
    wk.to_csv(TAB / "ia3_weekly_range.csv", index=False)
    nrm, aff = wk[~wk.affected], wk[wk.affected]
    limit = float(nrm.rate.mean() + 3 * nrm.rate.std())
    site_assay = con.execute("""
        select count(*) filter (where r.qc_status in ('pass', 'fail')) as qc_runs
        from site_renewal m join stg_instruments i on i.site_id = m.site_id
        join stg_runs r on r.instrument_id = i.instrument_id
         and r.run_date >= m.decision_date - interval 90 day and r.run_date < m.decision_date
        where m.cohort = 'main' and m.in_qc_comparison and r.firmware_version >= '4.0.0'
        group by m.site_id, r.assay_type
    """).df()
    out["ia3_weekly_range"] = {
        "min_qc_runs_per_week": 20,
        "normal_weeks": int(len(nrm)), "normal_mean": float(nrm.rate.mean()),
        "normal_sd": float(nrm.rate.std()), "normal_max": float(nrm.rate.max()),
        "upper_limit_3sd": limit,
        "affected_weeks": int(len(aff)), "affected_mean": float(aff.rate.mean()),
        "affected_min": float(aff.rate.min()), "affected_max": float(aff.rate.max()),
        "affected_weeks_above_limit": int((aff.rate > limit).sum()),
        "median_qc_runs_per_site_assay_90d": float(site_assay.qc_runs.median())}

    # D14. Set aside: a straight-line model and a site-level cut. KICKOFF planned a
    # logistic regression on each site's QC failure rate. It assumes churn rises steadily
    # with the rate, which is not how a QC lab acts on failures: an assay above its normal
    # range is a problem whatever the rate. A site's counts are also small (D13). The 5% cut
    # came after seeing the band table, so it is tested against nearby cuts. Kept for the
    # record; the finding rests on D13 and on exposure.
    q = s[s.in_qc_comparison].copy()
    q["qc_per_10pts"] = q.qc_fail_rate * 10
    q["log_runs"] = np.log1p(q.runs_90d)
    q["log_app"] = np.log1p(q.app_events_90d_est)
    ctrl = " + C(region, Treatment('NA-East')) + C(segment) + C(tier) + log_runs"
    line = smf.logit("churn ~ qc_per_10pts" + ctrl, data=q).fit(disp=0)
    line_all = smf.logit("churn ~ qc_per_10pts" + ctrl + " + log_app + tickets_90d", data=q).fit(disp=0)
    keep_sa = ["qc_per_10pts", "C(region", "C(segment", "C(tier", "log_runs", "log_app", "tickets_90d"]
    odds_ratios(line, keep_sa).to_csv(TAB / "set_aside_qc_straight_line.csv", index=False)
    odds_ratios(line_all, keep_sa).to_csv(TAB / "set_aside_qc_straight_line_all_factors.csv", index=False)
    p0 = float(con.execute("""
        select count(*) filter (where r.qc_status = 'fail') * 1.0
             / count(*) filter (where r.qc_status in ('pass', 'fail'))
        from stg_runs r join stg_instruments i using (instrument_id)
        where r.firmware_version >= '4.0.0'
          and not (i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1'))
    """).fetchone()[0])
    cut = lambda c, d: fisher(kn(d[d.qc_fail_rate > c]), kn(d[d.qc_fail_rate <= c]))
    out["set_aside"] = {
        "straight_line_p": float(line.pvalues["qc_per_10pts"]),
        "straight_line_all_factors_p": float(line_all.pvalues["qc_per_10pts"]),
        "normal_rate": p0,
        "cuts": {"normal_rate": cut(p0, q), "5pct": cut(0.05, q), "double_normal": cut(2 * p0, q)},
        "5pct_did_not_run_defect": cut(0.05, q[q.affected_exposure == "no"]),
        "median_qc_runs_per_site_90d": float((q.qc_pass + q.qc_fail).median())}

    # D15. Two rules the main comparison depends on, changed to see whether the answer moves.
    # (a) The nine notice sites are left out, because their last renewal fell before the defect
    # reached the fleet. Here they are counted as renewed, then as lost, exposed if they ever
    # ran the affected combination. (b) The 90-day window. Each window keeps only the sites
    # with that much data before their decision, and "all" uses everything before it.
    def compare(d):
        a, b = d[d.affected_exposure == "yes"], d[d.affected_exposure == "no"]
        d = d.assign(log_runs=np.log1p(d.runs_90d))
        m = smf.logit("churn ~ C(affected_exposure) + C(region, Treatment('NA-East')) + C(segment)"
                      " + C(tier) + log_runs", data=d).fit(disp=0)
        k = "C(affected_exposure)[T.yes]"
        return {**fisher(kn(a), kn(b)), "adjusted_odds_ratio": float(np.exp(m.params[k])),
                "adjusted_p": float(m.pvalues[k])}
    cols = ["site_id", "region", "segment", "tier", "runs_90d", "affected_exposure", "churn"]
    ever = set(con.execute("""
        select distinct i.site_id from stg_instruments i join stg_runs r using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1')
    """).df().site_id)
    nt = con.execute("select site_id, region, segment, tier, coalesce(runs_90d, 0) as runs_90d "
                     "from site_renewal where status = 'notice'").df()
    nt["affected_exposure"] = np.where(nt.site_id.isin(ever), "yes", "no")
    out["robustness_notice"] = {
        "left_out": compare(s[cols]),
        "as_renewed": compare(pd.concat([s[cols], nt.assign(churn=0)[cols]])),
        "as_lost": compare(pd.concat([s[cols], nt.assign(churn=1)[cols]]))}
    allsites = con.execute("""
        select site_id, churned::int as churn, decision_date from site_renewal
        where status <> 'notice' and cohort <> 'status_conflict'
    """).df()
    allsites["decision_date"] = pd.to_datetime(allsites.decision_date)
    aff = con.execute("""
        select i.site_id, r.run_date from stg_runs r join stg_instruments i using (instrument_id)
        where i.model = 'HX-200' and r.assay_type = 'IA-Panel-3' and r.firmware_version in ('4.1.0', '4.1.1')
    """).df()
    aff["run_date"] = pd.to_datetime(aff.run_date)
    aff = aff.merge(allsites[["site_id", "decision_date"]], on="site_id")
    aff = aff[aff.run_date < aff.decision_date]
    start = pd.Timestamp("2025-09-01")
    windows = []
    for days in [30, 60, 90, 120, 180, None]:
        if days is None:
            coh, ran = allsites, set(aff.site_id)
        else:
            coh = allsites[allsites.decision_date >= start + pd.Timedelta(days=days)]
            ran = set(aff[aff.run_date >= aff.decision_date - pd.Timedelta(days=days)].site_id)
        yes = coh.site_id.isin(ran)
        windows.append({"days": days if days else "all", "sites": int(len(coh)),
                        **fisher(kn(coh[yes]), kn(coh[~yes]))})
    out["robustness_window"] = windows

    # D7. European research labs, by exposure.
    er = s[(s.region == "EU") & (s.segment == "research")]
    out["eu_research_labs"] = fisher(kn(er[er.affected_exposure == "yes"]), kn(er[er.affected_exposure == "no"]))

    # D4. Range for the excess ARR. Excess sites = exposed churned minus what the
    # unexposed churn rate predicts. Three ways to price them.
    base = unexp.churn.mean()
    excess = exp.churn.sum() - base * len(exp)
    ch = exp[exp.churn == 1]
    out["excess_arr_range"] = {
        "excess_sites": float(excess),
        "at_mean_arr_of_exposed_churned": float(excess * ch.arr_usd.mean()),
        "at_mean_arr_of_all_exposed": float(excess * exp.arr_usd.mean()),
        "churned_arr_minus_expected": float(ch.arr_usd.sum() - base * exp.arr_usd.sum())}

    # D5. The European channel. First response by channel and ticket type.
    tk = con.execute("""
        select case when s.region = 'EU' then 'EU (distributor)' else 'Direct (NA, APAC)' end as region_group,
               case when t.category = 'qc_rejection' then 'QC rejection' else 'All other' end as ticket_type,
               t.first_response_hours as hrs
        from stg_support_tickets t join stg_sites s using (site_id)
    """).df()
    resp = tk.groupby(["ticket_type", "region_group"]).hrs.agg(
        n="size", median="median", q25=lambda v: v.quantile(0.25), q75=lambda v: v.quantile(0.75)).reset_index()
    resp.to_csv(TAB / "first_response_by_channel.csv", index=False)
    mw = {t: float(stats.mannwhitneyu(g[g.region_group == "EU (distributor)"].hrs,
                                      g[g.region_group != "EU (distributor)"].hrs).pvalue)
          for t, g in tk.groupby("ticket_type")}
    per_site = con.execute("""
        select case when s.region = 'EU' then 'EU (distributor)' else 'Direct (NA, APAC)' end as g,
               count(t.ticket_id) * 1.0 / count(distinct s.site_id)
        from stg_sites s left join stg_support_tickets t using (site_id) group by 1 order by 1
    """).fetchall()
    # Each exposed site's QC rejection tickets before its decision, any time in the window.
    qt = con.execute("""
        select t.site_id, count(*) as n_qc, median(t.first_response_hours) as median_response_hrs
        from stg_support_tickets t join site_renewal m using (site_id)
        where t.category = 'qc_rejection' and m.cohort = 'main' and cast(t.opened_ts as date) < m.decision_date
        group by 1
    """).df()
    e = exp.merge(qt, on="site_id", how="left")
    e["filed"] = e.n_qc.notna()
    w = e[e.filed]
    w[["site_id", "region", "churn", "n_qc", "median_response_hrs"]].sort_values("median_response_hrs").to_csv(
        TAB / "exposed_sites_qc_ticket_response.csv", index=False)
    eu, di = e[e.region_group == "EU (distributor)"], e[e.region_group != "EU (distributor)"]
    out["eu_channel"] = {
        "first_response_mannwhitney_p": mw, "tickets_per_site": {g: round(v, 1) for g, v in per_site},
        "exposed_churn_eu_vs_direct": fisher(kn(eu), kn(di)),
        "unexposed_churn_eu_vs_direct": fisher(kn(unexp[unexp.region == "EU"]), kn(unexp[unexp.region != "EU"])),
        "response_churned_vs_renewed": {
            "sites": int(len(w)), "churned": int(w.churn.sum()),
            "median_churned": float(w[w.churn == 1].median_response_hrs.median()),
            "median_renewed": float(w[w.churn == 0].median_response_hrs.median()),
            "mannwhitney_p": float(stats.mannwhitneyu(w[w.churn == 1].median_response_hrs,
                                                      w[w.churn == 0].median_response_hrs).pvalue)},
        "eu_churned_with_no_qc_ticket": [int(eu[~eu.filed].churn.sum()), int(eu.churn.sum())],
        "eu_filed_vs_none": fisher(kn(eu[eu.filed]), kn(eu[~eu.filed])),
        "filed_share": {"eu": [int(eu.filed.sum()), int(len(eu))], "direct": [int(di.filed.sum()), int(len(di))]}}
    # D8. A baseline for normal churn, and limits that show when a group breaches it.
    # The pack holds one renewal per site, so this is one cycle. Normal = sites that
    # did not run the defect. A second check uses renewals decided before the defect
    # reached the fleet (short_history; notice sites have not decided, so they drop).
    base_k, base_n = kn(unexp)
    lo, hi = wilson(base_k, base_n)
    pre = con.execute("""select count(*) filter (where churned), count(*)
                         from site_renewal where cohort = 'short_history' and status <> 'notice'""").fetchone()
    p0 = base_k / base_n
    def limit(n):
        # Approximate 95% upper limit for a group of n sites: center line plus 1.96 standard errors.
        return p0 + 1.96 * np.sqrt(p0 * (1 - p0) / n)
    seg = rate_table(unexp, "segment", "churn")
    seg.to_csv(TAB / "churn_baseline_by_segment.csv", index=False)
    groups = [("Ran the affected firmware", exp), ("EU, ran the affected firmware", exp[exp.region == "EU"])]
    s["quarter"] = s.decision_date.dt.to_period("Q").astype(str)
    groups += [(f"All main-cohort renewals, {q}", g) for q, g in s.groupby("quarter")]
    groups += [(f"Did not run the defect, {q}", g) for q, g in unexp.assign(
        quarter=unexp.decision_date.dt.to_period("Q").astype(str)).groupby("quarter")]
    lim = pd.DataFrame([{"group": name, "n": len(g), "churned": int(g.churn.sum()), "rate": g.churn.mean(),
                         "upper_limit": limit(len(g)), "breach": bool(g.churn.mean() > limit(len(g)))}
                        for name, g in groups])
    lim.to_csv(TAB / "churn_vs_baseline_limits.csv", index=False)
    out["churn_baseline"] = {
        "normal": [base_k, base_n], "rate": float(p0), "ci_low": float(lo), "ci_high": float(hi),
        "before_defect": [int(pre[0]), int(pre[1])],
        "upper_limit_by_size": {str(n): float(limit(n)) for n in (50, 136, 300)}}

    # D9. The smallest group a churn rate is worth reporting for. An exact one-sided
    # binomial test against normal churn, with a 5% false-alarm rate and an 80% chance
    # of catching a real change. The one judgment is the size of change to catch.
    # Power jumps up and down as n grows, so the answer is the first n after which
    # power stays at 80% or more for the next 50 values.
    def min_sites(p1, alpha=0.05, power=0.8, nmax=1500):
        pw = []
        for n in range(5, nmax):
            k = int(stats.binom.isf(alpha, n, p0)) + 1
            while stats.binom.sf(k - 1, n, p0) > alpha:
                k += 1
            pw.append((n, stats.binom.sf(k - 1, n, p1)))
        for i, (n, _) in enumerate(pw):
            if all(q >= power for _, q in pw[i:i + 50]):
                return n
    sizes = pd.DataFrame([{"change": name, "churn_to_catch": p1, "sites_needed": min_sites(p1)}
                          for name, p1 in [("1.5 times normal", 1.5 * p0), ("double normal", 2 * p0),
                                           ("the defect effect", exp.churn.mean()), ("triple normal", 3 * p0)]])
    sizes.to_csv(TAB / "min_group_size.csv", index=False)
    need = int(sizes.loc[sizes.change == "double normal", "sites_needed"].iloc[0])
    reg = s.groupby("region").size().rename("sites").reset_index()
    reg["meets_minimum"] = reg.sites >= need
    reg.to_csv(TAB / "regions_vs_min_group_size.csv", index=False)
    out["min_group_size"] = {"to_catch_double_normal": need,
                             "table": sizes.assign(churn_to_catch=sizes.churn_to_catch.round(3)).to_dict("records"),
                             "regions_meeting_it": reg[reg.meets_minimum].region.tolist()}

    # D10. Backtest of the fleet QC monitor in BACKLOG_001. Each day, for every firmware,
    # model and assay combination, count QC results over the trailing 7 days. Flag when the
    # failure rate is above the control limit: the baseline (the model and assay rate on
    # 4.0.0 and 4.0.2) plus 3 standard deviations for the window's run count, as on a
    # p-chart. The limit widens for a small window, so one failure in a few runs doesn't flag.
    LIMIT_SD = 3
    daily = con.execute("""
        select i.model, r.assay_type as assay, r.firmware_version as fw, r.run_date as day,
               count(*) filter (where r.qc_status in ('pass', 'fail')) as n,
               count(*) filter (where r.qc_status = 'fail') as f
        from stg_runs r join stg_instruments i using (instrument_id)
        where r.fw_major >= 4 group by all
    """).df()
    mbase = con.execute("""
        select i.model, r.assay_type as assay,
               count(*) filter (where r.qc_status = 'fail') * 1.0
                 / count(*) filter (where r.qc_status in ('pass', 'fail')) as baseline
        from stg_runs r join stg_instruments i using (instrument_id)
        where r.firmware_version in ('4.0.0', '4.0.2') group by all
    """).df()
    daily["day"] = pd.to_datetime(daily.day)
    days = pd.date_range("2025-09-01", "2026-08-31", freq="D")
    rows = []
    for key, g in daily.groupby(["model", "assay", "fw"]):
        g = g.set_index("day")[["n", "f"]].reindex(days, fill_value=0).rolling(7, min_periods=1).sum()
        g["model"], g["assay"], g["fw"] = key
        rows.append(g.rename_axis("day").reset_index())
    roll = pd.concat(rows).merge(mbase, on=["model", "assay"])
    roll = roll[roll.n > 0]
    roll["rate"] = roll.f / roll.n
    roll["limit"] = roll.baseline + LIMIT_SD * np.sqrt(roll.baseline * (1 - roll.baseline) / roll.n)
    roll["flag"] = roll.rate > roll.limit
    defect = (roll.model == "HX-200") & (roll.assay == "IA-Panel-3") & roll.fw.isin(AFFECTED)
    flags = roll[roll.flag].copy()
    flags["defect"] = defect[roll.flag]
    flags.to_csv(TAB / "monitor_backtest_flags.csv", index=False)
    # An episode is a run of consecutive flagged days for one combination: one thing to review.
    other = flags[~flags.defect].sort_values(["model", "assay", "fw", "day"])
    new_episode = other.groupby(["model", "assay", "fw"]).day.diff().dt.days.ne(1)
    first = roll[defect & roll.flag & (roll.fw == "4.1.0")].day.min()
    rel = pd.Timestamp(con.execute("select release_date from stg_firmware_releases where version = '4.1.0'").fetchone()[0])
    out["monitor_backtest"] = {
        "window_days": 7, "limit_sd": LIMIT_SD,
        "first_flag_410": str(first.date()), "days_after_release": int((first - rel).days),
        "defect_days_flagged": [int((defect & roll.flag).sum()), int(defect.sum())],
        "other_flag_episodes": int(new_episode.sum()),
        "other_flag_episodes_per_week": round(float(new_episode.sum()) / 52, 1),
        "combinations": int(roll[["model", "assay", "fw"]].drop_duplicates().shape[0])}

    # D11. Instruments still on the affected firmware at the extract date, from
    # instruments.firmware_version_current (the dictionary: firmware at extract).
    still = con.execute("""
        select model, firmware_version_current as fw, count(*) as n from stg_instruments
        where firmware_version_current in ('4.1.0', '4.1.1') group by all order by all
    """).df()
    out["still_on_affected_at_extract"] = {f"{r.model} {r.fw}": int(r.n) for r in still.itertuples()}

    # D12. Lost sites that ran the affected firmware and filed a QC rejection ticket.
    # Part B counts tickets in the 90-day window only; FINDINGS says "before deciding",
    # so this counts any ticket before the decision date, and any ticket at all.
    con.register("lost_exposed", exp[exp.churn == 1][["site_id", "decision_date"]])
    lt = con.execute("""
        select l.site_id,
               count(t.site_id) filter (where t.opened_ts < l.decision_date) as before_decision,
               count(t.site_id) as ever
        from lost_exposed l
        left join stg_support_tickets t on t.site_id = l.site_id and t.category = 'qc_rejection'
        group by 1 order by 1
    """).df()
    con.unregister("lost_exposed")
    out["lost_exposed_qc_ticket"] = {
        "lost_sites": int(len(lt)), "filed_in_90d_window": results["ticket_filed_vs_churn"]["filed"][0],
        "filed_before_decision": int((lt.before_decision > 0).sum()), "filed_ever": int((lt.ever > 0).sum())}

    results["follow_ups"] = out

    # Figure: three panels side by side. Blue is Europe, grey is the direct channel; orange
    # stays reserved for the affected firmware.
    G = ["Direct (NA, APAC)", "EU (distributor)"]
    COL = {G[0]: GREY, G[1]: BLUE}
    fig, axes = slide("European support is slower, but the sites that left didn't wait longer",
                      "First-response times and churn, by sales channel",
                      "Source: Halvard support tickets and subscriptions. Panel C: sites that ran the affected firmware "
                      f"and filed a QC rejection ticket before renewal, {len(w)} sites.",
                      ncols=3, gridspec_kw={"width_ratios": [1, 1, 1.1], "wspace": 0.35})
    fig.subplots_adjust(top=0.72, bottom=0.2, left=0.06, right=0.97)
    legend_row(fig, [(GREY, "Direct (North America and APAC)"), (BLUE, "Europe, through the distributor")])
    r = resp.set_index(["ticket_type", "region_group"])
    ax = axes[0]
    for j2, g in enumerate(G):
        x = np.arange(2) + (j2 - 0.5) * 0.38
        vals = [r.loc[(tt, g), "median"] for tt in ["QC rejection", "All other"]]
        ax.bar(x, vals, width=0.36, color=COL[g], zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + 0.5, f"{v:.1f} h", ha="center", va="bottom", fontsize=10.5, color=INK)
    ax.set_xticks([0, 1], ["QC rejection\ntickets", "All other\ntickets"], color=INK)
    ax.set_ylim(0, 28)
    ax.set_title("A.  Median hours to first response", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    ax = axes[1]
    counts = []
    for j2, g in enumerate(G):
        x = np.arange(2) + (j2 - 0.5) * 0.38
        vals, ns = [], []
        for e in ["yes", "no"]:
            d = s[(s.affected_exposure == e) & (s.region_group == g)]
            vals.append(d.churn.mean()); ns.append(len(d))
        counts.append(ns)
        ax.bar(x, vals, width=0.36, color=COL[g], zorder=3)
        for xi, v in zip(x, vals):
            ax.text(xi, v + 0.01, f"{v:.0%}", ha="center", va="bottom", fontsize=10.5, color=INK)
    ax.set_xticks([0, 1], [f"Ran the affected\nfirmware\n{counts[0][0]} / {counts[1][0]} sites",
                           f"Did not\n\n{counts[0][1]} / {counts[1][1]} sites"], color=INK)
    ax.set_ylim(0, 0.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("B.  Share of sites that left", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    ax = axes[2]
    rng = np.random.default_rng(7)
    for i2, o in enumerate([0, 1]):
        d = w[w.churn == o]
        for g in G:
            dd = d[d.region.eq("EU") == (g == G[1])]
            ax.scatter(i2 + rng.uniform(-0.15, 0.15, len(dd)), dd.median_response_hrs, s=55, color=COL[g],
                       edgecolor=SURFACE, linewidth=1.2, zorder=3)
        m = d.median_response_hrs.median()
        ax.plot([i2 - 0.3, i2 + 0.3], [m, m], color=INK, linewidth=2, zorder=4)
        ax.text(i2 + 0.33, m, f"median\n{m:.0f} h", va="center", fontsize=10, color=INK)
    ax.set_xticks([0, 1], [f"Renewed\n{(w.churn == 0).sum()} sites", f"Left\n{(w.churn == 1).sum()} sites"], color=INK)
    ax.set_xlim(-0.5, 1.9)
    ax.set_title("C.  Hours to first response, QC tickets", loc="left", color=INK, fontsize=11.5, fontweight="bold")
    fig.savefig(FIG / "eu_support_churn.png", facecolor=SURFACE)
    plt.close(fig)


def lost_by_region_and_lab():
    """Schematic map: lost renewals by region and lab type.

    Each region gets its own panel, west to east, and each lab type its own slot,
    so no bubble can sit on another. Bubble area is the count of lost sites; the
    orange wedge is the part that ran the affected firmware. Every cell is under
    the 80-site minimum, so only the European research-lab rate is printed: it is
    the one cell with a test behind it (D7).
    """
    s = pd.read_csv(TAB / "sites_main.csv")
    t = (s.assign(exposed_lost=(s.affected_exposure == "yes") & (s.churn == 1))
          .groupby(["region", "segment"])
          .agg(sites=("site_id", "size"), lost=("churn", "sum"), exposed_lost=("exposed_lost", "sum"))
          .reset_index())
    t.to_csv(TAB / "lost_by_region_and_lab.csv", index=False)

    REGIONS = [("NA-West", "NA-West"), ("NA-East", "NA-East"), ("EU", "Europe"), ("APAC", "APAC")]
    LABS = [("hospital_lab", "Hospital", GREY), ("reference_lab", "Reference", "#d3d1cb"), ("research", "Research", BLUE)]
    fig, ax = slide("European research labs had the highest churn",
                    "Lost renewals at the last cycle, by region and lab type. Bubble area is the number of lost sites.",
                    "Source: Halvard subscriptions and telemetry, 431 sites with 90 days of data before renewal. Regions are arranged "
                    "west to east, not to scale.\nEvery group here is under 80 sites, so only the European research-lab rate is "
                    "shown: 14 of 19 that ran the affected firmware were lost, against 4 of 18 that didn't.")
    legend_row(fig, [(c, f"{name} labs") for _, name, c in LABS] + [(ORANGE, "Lost sites that ran the affected firmware")])
    ax.set_position([0.04, 0.15, 0.92, 0.64])
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.set_xticks([]), ax.set_yticks([])
    ax.set_xlim(0, 4), ax.set_ylim(0, 1.3)
    ax.set_aspect("equal")
    rmax, slot = 0.14, 0.3
    top = t.lost.max()
    for i, (code, label) in enumerate(REGIONS):
        cx = i + 0.5
        ax.add_patch(matplotlib.patches.FancyBboxPatch((i + 0.04, 0.06), 0.92, 1.18, boxstyle="round,pad=0,rounding_size=0.04",
                                                       facecolor="#f3f2ee", edgecolor="none", zorder=0))
        n_sites = int(t[t.region == code].sites.sum())
        ax.text(cx, 1.12, label, ha="center", va="center", fontsize=13, fontweight="bold", color=INK)
        ax.text(cx, 1.02, f"{n_sites} sites", ha="center", va="center", fontsize=10.5, color=INK_2)
        for j, (seg, name, color) in enumerate(LABS):
            row = t[(t.region == code) & (t.segment == seg)].iloc[0]
            x, y = cx + (j - 1) * slot, 0.68
            lost, exp_lost = int(row.lost), int(row.exposed_lost)
            if lost == 0:
                ax.add_patch(matplotlib.patches.Circle((x, y), 0.02, facecolor="none", edgecolor=INK_2, linewidth=1, zorder=2))
            else:
                r = rmax * np.sqrt(lost / top)
                share = exp_lost / lost
                ax.add_patch(matplotlib.patches.Wedge((x, y), r, 90, 90 + 360 * (1 - share), facecolor=color,
                                                      edgecolor=SURFACE, linewidth=1.5, zorder=2))
                if exp_lost:
                    ax.add_patch(matplotlib.patches.Wedge((x, y), r, 90 - 360 * share, 90, facecolor=ORANGE,
                                                          edgecolor=SURFACE, linewidth=1.5, zorder=3))
            highlight = code == "EU" and seg == "research"
            ax.text(x, 0.43, name, ha="center", va="center", fontsize=9.5, color=INK)
            ax.text(x, 0.33, f"{lost} of {int(row.sites)}", ha="center", va="center", fontsize=10.5,
                    color=INK, fontweight="bold" if highlight else "normal")
            if highlight:
                ax.text(x, 0.2, f"{lost / row.sites:.0%} lost", ha="center", va="center", fontsize=10.5,
                        color=INK, fontweight="bold")
    fig.savefig(FIG / "lost_by_region_and_lab.png", facecolor=SURFACE)
    plt.close(fig)


if __name__ == "__main__":
    for d in (TAB, FIG):
        d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(OUT / "halvard.duckdb"), read_only=True)
    con.execute("set TimeZone = 'UTC'")
    results = {}
    lot_test(con, results)
    adoption(con, results)
    comparison(con, results)
    customer_story(con, results)
    churn_figures(con, results)
    follow_ups(con, results)
    lost_by_region_and_lab()
    (OUT / "stats.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
