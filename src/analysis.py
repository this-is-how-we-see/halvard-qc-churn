"""Statistical tests and comparison tables.

Usage:  python src/analysis.py   (run src/build.py first)
Writes: output/tables/*.csv, output/stats.json,
        output/figures/lot_test_by_firmware.png, output/figures/lot_test_event_time.png,
        output/figures/adoption_and_failures.png

Part A asks whether a bad QC control lot, rather than the firmware, can explain
the HX-200 IA-Panel-3 failures. The pack has no lot data, so the test uses the
one thing a lot problem must follow: calendar time. A bad lot reaches every lab
that uses it over the same weeks. A firmware defect follows each instrument's
own firmware version.

Part B is the comparison across sites: does QC failure still go with churn
among similar sites?
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


if __name__ == "__main__":
    for d in (TAB, FIG):
        d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(OUT / "halvard.duckdb"), read_only=True)
    con.execute("set TimeZone = 'UTC'")
    results = {}
    lot_test(con, results)
    adoption(con, results)
    comparison(con, results)
    (OUT / "stats.json").write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
