"""Statistical tests and comparison tables.

Usage:  python src/analysis.py   (run src/build.py first)
Writes: output/tables/*.csv, output/stats.json,
        output/figures/lot_test_by_firmware.png, output/figures/lot_test_event_time.png,
        output/figures/adoption_and_failures.png, output/figures/visible_before_fixed.png,
        output/figures/churn_by_segment_region.png, output/figures/what_goes_with_churn.png,
        output/figures/eu_support_churn.png

Part A asks whether a bad QC control lot, rather than the firmware, can explain
the HX-200 IA-Panel-3 failures. The pack has no lot data, so the test uses the
one thing a lot problem must follow: calendar time. A bad lot reaches every lab
that uses it over the same weeks. A firmware defect follows each instrument's
own firmware version.

Part B is the comparison across sites: does QC failure still go with churn
among similar sites?

Part C is the customer story: tickets, response times and the renewal cost.

Part D holds follow-up checks on Parts B and C: the European channel, app use,
decisions made after the fix, and a range for the ARR estimate. These are
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
    fig, ax = plt.subplots(figsize=(8.5, 3.6), dpi=160, facecolor=SURFACE)
    style(ax)
    ax.fill_between(wk.week, wk.ci_low, wk.ci_high, color=BLUE, alpha=0.15, linewidth=0)
    ax.plot(wk.week, wk.rate, color=BLUE, linewidth=2.2, marker="o", markersize=4)
    ax.axvline(-0.5, color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
    ax.text(-0.4, 0.46, " each instrument moves to 4.1.2", color=INK_2, fontsize=8.5, va="top")
    ax.set_xticks(range(-8, 8))
    ax.set_xticklabels([f"{w:+d}" if w else "0" for w in range(-8, 8)], fontsize=8.5)
    ax.set_xlabel("Weeks from that instrument's own upgrade", color=INK_2, fontsize=9)
    ax.set_ylim(0, 0.5)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    r = results["lot_event_time"]
    ax.set_title(f"HX-200 IA-Panel-3 QC failure rate around each instrument's upgrade ({r['instruments']} instruments)",
                 loc="left", color=INK, fontsize=11, fontweight="bold")
    fig.text(0.01, 0.01, f"Upgrades spread from {r['upgrade_first']} to {r['upgrade_last']}, so week 0 falls on a "
             "different calendar date for each instrument. Band: 95% Wilson interval.", color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.25, top=0.88, left=0.07, right=0.97)
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
    fig, axes = plt.subplots(2, 1, figsize=(9.5, 5.6), dpi=160, facecolor=SURFACE, sharex=True)
    for ax, col, color, title, top in [
        (axes[0], "affected_share", BLUE, "Share of HX-200 IA-Panel-3 runs on firmware 4.1.0 or 4.1.1", 0.6),
        (axes[1], "fail_rate", ORANGE, "HX-200 IA-Panel-3 QC failure rate", 0.3)]:
        style(ax)
        ax.plot(pd.to_datetime(w.week), w[col], color=color, linewidth=2.2)
        for v, d in rel:
            ax.axvline(pd.Timestamp(d), color=INK_2, linewidth=1, linestyle=(0, (3, 3)))
            ax.text(pd.Timestamp(d), top, f" {v}", color=INK_2, fontsize=8, va="top")
        ax.set_ylim(0, top)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_title(title, loc="left", color=INK, fontsize=10.5, fontweight="bold")
    axes[1].xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    axes[1].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    a = results["adoption"]
    fig.text(0.01, 0.01, f"Weekly. The failure rate tracks adoption: rate = {a['intercept']:.1%} + "
             f"{a['slope']:.0%} x share on affected firmware (R² {a['r2']:.2f}, {a['weeks']} weeks). "
             "Dashed: release dates.", color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.13, top=0.93, left=0.07, right=0.97, hspace=0.35)
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

    # The regression check: every factor held equal at once.
    def fit(df):
        d = df.copy()
        d["qc_per_10pts"] = d.qc_fail_rate * 10
        d["log_runs"] = np.log1p(d.runs_90d)
        d["log_app"] = np.log1p(d.app_events_90d_est)
        return smf.logit("churn ~ qc_per_10pts + C(region, Treatment('NA-East')) + C(segment) + C(tier)"
                         " + log_runs + log_app + tickets_90d", data=d).fit(disp=0)
    keep = ["qc_per_10pts", "C(affected", "C(region", "C(segment", "C(tier", "log_runs", "log_app", "tickets_90d"]
    main = fit(qc)
    check = fit(qc[~qc.partial_run_coverage])
    odds_ratios(main, keep).to_csv(TAB / "regression_main.csv", index=False)
    odds_ratios(check, keep).to_csv(TAB / "regression_check.csv", index=False)

    # Models without app use and tickets. Both can sit on the path from QC
    # failures to churn (a lab with failures files tickets and uses the app
    # less), so holding them equal can hide a real effect of QC.
    def prep(df):
        d = df.copy()
        d["qc_per_10pts"] = d.qc_fail_rate * 10
        d["log_runs"] = np.log1p(d.runs_90d)
        return d
    base = " + C(region, Treatment('NA-East')) + C(segment) + C(tier) + log_runs"
    m_qc = smf.logit("churn ~ qc_per_10pts" + base, data=prep(qc)).fit(disp=0)
    m_exp = smf.logit("churn ~ C(affected_exposure)" + base, data=prep(sites)).fit(disp=0)
    odds_ratios(m_qc, keep).to_csv(TAB / "regression_qc_no_mediators.csv", index=False)
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
    results["regression"] = {"main_sites": int(main.nobs), "main_churned": int(qc.churn.sum()),
                             "check_sites": int(check.nobs),
                             "check_churned": int(qc[~qc.partial_run_coverage].churn.sum()),
                             "main_pseudo_r2": float(main.prsquared)}


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
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.4), dpi=160, facecolor=SURFACE, sharex=True,
                             gridspec_kw={"height_ratios": [3, 1.6, 1.1]})
    lo, hi = pd.Timestamp(clear), pd.Timestamp(fix)
    marks = [(pd.Timestamp(rel), "4.1.0 released"), (lo, "signal clear in telemetry"),
             (pd.Timestamp(first_ticket), "first QC rejection ticket"), (hi, "4.1.2 fix released")]
    for ax in axes:
        style(ax)
        ax.axvspan(lo, hi, color=ORANGE, alpha=0.10, linewidth=0, zorder=0)
        for day, _ in marks:
            ax.axvline(day, color=INK_2, linewidth=1, linestyle=(0, (3, 3)), zorder=1)
    ax = axes[0]
    ax.plot(pd.to_datetime(w.week), w.rate, color=BLUE, linewidth=2.2, zorder=3)
    ax.set_ylim(0, 0.32)
    ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    ax.set_title("HX-200 IA-Panel-3 QC failure rate, whole fleet, weekly", loc="left", color=INK,
                 fontsize=10.5, fontweight="bold")
    ypos = [0.315, 0.285, 0.255, 0.315]
    for (day, label), y in zip(marks, ypos):
        ax.text(day, y, f" {label}", color=INK, fontsize=8, va="top")
    cs = results["customer_story"]
    ax.text(lo + (hi - lo) / 2, 0.02, f"{cs['days_signal_to_fix']} days visible but unfixed",
            color=ORANGE, fontsize=9, fontweight="bold", ha="center")
    ax = axes[1]
    ax.bar(pd.to_datetime(tk.week), tk.n, width=5, color=ORANGE, zorder=3)
    ax.set_title("QC rejection tickets per week, all sites", loc="left", color=INK, fontsize=10.5,
                 fontweight="bold")
    ax = axes[2]
    for i, dday in enumerate(sorted(ex_ch.decision_date)):
        ax.scatter(dday, 0.5, s=36, color="#e34948" if dday < hi else INK_2, zorder=3, linewidths=0)
    ax.set_yticks([])
    ax.set_ylim(0, 1)
    ax.set_title(f"Renewal decisions of the {cs['exposed_churned']} churned sites that ran the affected firmware "
                 f"({cs['exposed_churned_before_fix']} before the fix)", loc="left", color=INK,
                 fontsize=10.5, fontweight="bold")
    axes[2].xaxis.set_major_locator(matplotlib.dates.MonthLocator())
    axes[2].xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b\n%Y"))
    fig.text(0.01, 0.01, "Shaded: from the week the failure spike was statistically clear in fleet telemetry "
             "(p < 0.001 against the 4.0.x baseline) to the 4.1.2 release. Red: decided before the fix.",
             color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.1, top=0.95, left=0.07, right=0.97, hspace=0.45)
    fig.savefig(FIG / "visible_before_fixed.png", facecolor=SURFACE)
    plt.close(fig)


def churn_figures(con, results):
    """Two figures that explain the comparison inside the figure itself."""
    s = pd.read_csv(TAB / "sites_main.csv")
    # Figure 1: churn by segment and by region, split by whether the site ran the affected firmware.
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.4), dpi=160, facecolor=SURFACE, sharey=True,
                             gridspec_kw={"width_ratios": [3, 4]})
    for ax, col, order, title in [
            (axes[0], "segment", ["hospital_lab", "reference_lab", "research"], "By segment"),
            (axes[1], "region", ["NA-East", "NA-West", "APAC", "EU"], "By region")]:
        style(ax)
        for j, (exp, color, label) in enumerate([("no", INK_2, "did not run the affected firmware"),
                                                 ("yes", ORANGE, "ran the affected firmware")]):
            t = rate_table(s[s.affected_exposure == exp], col, "churn").set_index(col).reindex(order)
            x = np.arange(len(order)) + (j - 0.5) * 0.28
            ax.errorbar(x, t.rate, yerr=[t.rate - t.ci_low, t.ci_high - t.rate], fmt="none",
                        ecolor=color, elinewidth=1.2, capsize=3, alpha=0.8)
            ax.scatter(x, t.rate, s=46, color=color, zorder=3, label=label)
            for xi, r, n in zip(x, t.rate, t.n):
                ax.text(xi + 0.05, r, f" {r:.0%}", color=INK, fontsize=8, va="center")
        ax.set_xticks(range(len(order)))
        ax.set_xticklabels([o.replace("_", " ") for o in order], fontsize=9, color=INK)
        ax.set_title(title, loc="left", color=INK, fontsize=10.5, fontweight="bold")
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    axes[0].set_ylim(0, 0.62)
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK)
    fig.suptitle("Churn rate at the last renewal: the affected firmware roughly doubles it in every segment",
                 x=0.01, ha="left", color=INK, fontsize=11.5, fontweight="bold")
    fig.text(0.01, 0.01, "Main cohort, 431 sites. Each dot is the share of sites in that group that did not renew. "
             "Bars: 95% Wilson intervals. NA-East is the one group where the firmware made no difference.",
             color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.16, top=0.86, left=0.06, right=0.98, wspace=0.08)
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
    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=160, facecolor=SURFACE)
    style(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    y = np.arange(len(t))
    sig = t.p_value < 0.05
    ax.hlines(y, t.ci_low, t.ci_high, color=[ORANGE if v else INK_2 for v in sig], linewidth=2)
    ax.scatter(t.odds_ratio, y, s=60, color=[ORANGE if v else INK_2 for v in sig], zorder=3)
    for yi, (o, lo, hi, p) in enumerate(zip(t.odds_ratio, t.ci_low, t.ci_high, t.p_value)):
        ax.text(max(hi, o) * 1.08, yi, f"{o:.1f}x  (p = {p:.3f})" if p >= 0.001 else f"{o:.1f}x  (p < 0.001)",
                color=INK, fontsize=8.5, va="center")
    ax.axvline(1, color=INK, linewidth=1)
    ax.set_xscale("log")
    ax.set_xlim(0.12, 14)
    ax.set_xticks([0.25, 0.5, 1, 2, 4, 8])
    ax.set_xticklabels(["0.25x", "0.5x", "1x", "2x", "4x", "8x"])
    ax.set_yticks(y)
    ax.set_yticklabels(t.label, fontsize=9, color=INK)
    ax.text(0.95, len(t) - 0.1, "less likely to churn  ", ha="right", color=INK_2, fontsize=8.5)
    ax.text(1.05, len(t) - 0.1, "  more likely to churn", ha="left", color=INK_2, fontsize=8.5)
    ax.set_ylim(-0.6, len(t) + 0.4)
    fig.suptitle("What goes with churn when the other factors are held equal", x=0.01, ha="left", color=INK,
                 fontsize=11.5, fontweight="bold")
    fig.text(0.01, 0.015, "Each row compares sites that differ in that one factor but match on all the others shown. "
             "2x means twice the odds of not renewing.\nOrange: significant (p < 0.05). Line: 95% interval; a line "
             "that crosses 1x means no clear difference. 431 sites, logistic regression.",
             color=INK_2, fontsize=7.5)
    fig.subplots_adjust(bottom=0.17, top=0.9, left=0.3, right=0.97)
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

    # D6. A QC failure threshold. The straight-line model asks whether each extra
    # point of failures adds the same risk. This asks whether sites above 5%, one of
    # the band edges set in Part B, churn more. Exploratory.
    q = s[s.in_qc_comparison].copy()
    q["above_5pct"] = q.qc_fail_rate > 0.05
    thr = lambda d: fisher(kn(d[d.above_5pct]), kn(d[~d.above_5pct]))
    out["qc_threshold_5pct"] = {"all_sites": thr(q),
                                "did_not_run_defect": thr(q[q.affected_exposure == "no"]),
                                "ran_defect": thr(q[q.affected_exposure == "yes"])}

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
        from stg_sites s left join stg_support_tickets t using (site_id) group by 1
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
    results["follow_ups"] = out

    # Figure: three panels, one axis each.
    G, COL = ["Direct (NA, APAC)", "EU (distributor)"], {"Direct (NA, APAC)": BLUE, "EU (distributor)": ORANGE}
    fig, axes = plt.subplots(3, 1, figsize=(9, 12.5), dpi=150, facecolor=SURFACE, gridspec_kw={"hspace": 0.7})
    for ax in axes:
        style(ax)
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=0.8)

    def head(ax, title, sub):
        ax.text(0, 1.17, title, transform=ax.transAxes, fontsize=12, weight="bold", color=INK)
        ax.text(0, 1.06, sub, transform=ax.transAxes, fontsize=9, color=INK_2)

    def bars(ax, rows, xmax, xlabel):
        y, ticks, labels = 0, [], []
        for group in rows:
            for label, g, val, lo, hi, note in group:
                ax.barh(y, val, height=0.62, color=COL[g])
                ax.plot([lo, hi], [y, y], color=INK, linewidth=1.3)
                ax.text(hi + xmax * 0.015, y, note, va="center", fontsize=9, color=INK)
                ticks.append(y); labels.append(f"{label}\n{g}"); y += 1
            y += 0.5
        ax.set_yticks(ticks, labels, fontsize=8.5)
        ax.invert_yaxis(); ax.set_xlim(0, xmax); ax.set_xlabel(xlabel, color=INK_2, fontsize=9)

    r = resp.set_index(["ticket_type", "region_group"])
    bars(axes[0], [[(t, g, r.loc[(t, g), "median"], r.loc[(t, g), "q25"], r.loc[(t, g), "q75"],
                     f"{r.loc[(t, g), 'median']:.1f} h  (n = {int(r.loc[(t, g), 'n']):,})") for g in G]
                   for t in ["QC rejection", "All other"]],
         42, "Hours to first human response  (bar = median, line = middle half of tickets)")
    head(axes[0], "A.  European tickets wait longer, for every kind of ticket",
         "All support tickets in the year, by sales channel. Mann-Whitney U, p < 0.001 for both ticket types")
    rows = []
    for x, lab in [("yes", "Ran the affected firmware"), ("no", "Did not")]:
        grp = []
        for g in G:
            d = s[(s.affected_exposure == x) & (s.region_group == g)]
            k, n = int(d.churn.sum()), len(d)
            lo, hi = wilson(k, n)
            grp.append((lab, g, 100 * k / n, 100 * lo, 100 * hi, f"{k / n:.1%}  ({k} of {n})"))
        rows.append(grp)
    bars(axes[1], rows, 70, "Sites that churned (%)  (line = 95% Wilson interval)")
    ec = out["eu_channel"]
    head(axes[1], "B.  European churn is high where the site ran the affected firmware",
         f"Main cohort, {len(s)} sites. Fisher's exact test: ran it, p = {ec['exposed_churn_eu_vs_direct']['p']:.3f}; "
         f"did not, p = {ec['unexposed_churn_eu_vs_direct']['p']:.2f}")
    ax = axes[2]
    rng = np.random.default_rng(7)
    for i, (o, lab) in enumerate([(0, "Renewed"), (1, "Churned")]):
        d = w[w.churn == o]
        for g in G:
            dd = d[d.region.eq("EU") == (g == G[1])]
            ax.scatter(dd.median_response_hrs, i + rng.uniform(-0.13, 0.13, len(dd)), s=60, color=COL[g],
                       edgecolor=SURFACE, linewidth=1.5, zorder=3, label=g if o == 0 else None)
        m = d.median_response_hrs.median()
        ax.plot([m, m], [i - 0.3, i + 0.3], color=INK, linewidth=2)
        ax.text(m, i - 0.36, f"median {m:.1f} h", ha="center", fontsize=9, color=INK)
    ax.set_yticks([0, 1], [f"Renewed\n({(w.churn == 0).sum()} sites)", f"Churned\n({(w.churn == 1).sum()} sites)"], fontsize=8.5)
    ax.set_ylim(-0.7, 1.5); ax.invert_yaxis()
    ax.set_xlabel("Median hours to first response on the site's QC rejection tickets", color=INK_2, fontsize=9)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    rc = ec["response_churned_vs_renewed"]
    head(ax, "C.  Among sites that filed a QC ticket, churned sites did not wait longer",
         f"Sites that ran the affected firmware and filed before their decision. Mann-Whitney U, p = {rc['mannwhitney_p']:.2f}; "
         f"only {rc['churned']} churned")
    fig.savefig(FIG / "eu_support_churn.png", facecolor=SURFACE, bbox_inches="tight")
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
    (OUT / "stats.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
