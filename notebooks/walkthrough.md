> This is the walkthrough notebook exported to Markdown so GitHub shows it reliably. The runnable version is `walkthrough.ipynb` in this folder.

# Halvard QC failures and HaloCloud churn: walkthrough

This notebook walks through the analysis in the order it was done. It reads the outputs that the
scripts write, so it adds no new analysis and every number matches `output/stats.json`.

To regenerate the outputs, put the data pack in `data/raw/halvard_data_pack/`, then run
`python src/build.py`, `python src/analysis.py` and `python src/figures.py` from the repo root.

**p-value labels used throughout:** below 0.05 is *significant*; 0.05 to 0.25 is a *possible trend*;
above 0.25 means *we need more data*.


```python
import json
from pathlib import Path
import pandas as pd
from IPython.display import Image, Markdown, display

ROOT = Path.cwd().resolve()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent
OUT, TAB, FIG = ROOT / "output", ROOT / "output" / "tables", ROOT / "output" / "figures"
S = json.loads((OUT / "stats.json").read_text())
pd.set_option("display.precision", 3)

def table(name):
    return pd.read_csv(TAB / f"{name}.csv")

def facts(d, label="value"):
    # A result dictionary as a readable two-column table. [k, n] pairs are churned of sites.
    flat = pd.json_normalize(d, sep=" / ").T
    flat.columns = [label]
    fmt = lambda v: (f"{v[0]} of {v[1]} ({v[0]/v[1]:.1%})" if isinstance(v, list) and len(v) == 2 and v[1]
                     else round(v, 3) if isinstance(v, float) else v)
    display(flat.map(fmt))

def figure(name, width=820):
    # Link to the committed figure instead of embedding it, so the notebook stays small.
    # The image loads from the public repo, and the file is in output/figures.
    url = f"https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/{name}.png"
    display(Markdown(f"![{name}]({url})"))
```

## 1. Data checks

Every check names its rule and where the rule comes from. Four checks fail on the data as delivered,
and each failure has an approved action. The biggest is 1,561 duplicate run IDs, where every copy is
identical in every column, so staging keeps one copy of each.


```python
checks = (OUT / "checks.md").read_text()
display(Markdown(checks))
```


# Data checks

Zero failing rows means the check passes.

| Check | What it tests | Source of the rule | Failing rows | Result | Action |
|---|---|---|---|---|---|
| `sites_pk_unique` | Every site_id appears once in sites | Dictionary: site_id is the primary key | 0 | pass |  |
| `instruments_pk_unique` | Every instrument_id appears once | Dictionary: instrument_id is the primary key | 0 | pass |  |
| `raw_runs_duplicate_ids` | Every run_id appears once in the file as delivered | Dictionary: run_id is the primary key | 1561 | **FAIL** | Approved: stg_runs keeps one copy of each identical pair |
| `raw_runs_duplicates_identical` | Where a run_id repeats in the file, every copy is identical in every column | Diagnostic: tests the duplicate proposal | 0 | pass |  |
| `runs_pk_unique` | Every run_id appears once after staging | Dictionary: run_id is the primary key | 0 | pass |  |
| `events_pk_unique` | Every event_id appears once | Dictionary: event_id is the primary key | 0 | pass |  |
| `tickets_pk_unique` | Every ticket_id appears once | Dictionary: ticket_id is the primary key | 0 | pass |  |
| `subscriptions_one_per_site` | Each site has at most one subscription row | Dictionary: one row per site | 0 | pass |  |
| `every_site_has_subscription` | Every site has a subscription row | Dictionary: one row per site | 0 | pass |  |
| `instruments_site_fk` | Every instrument belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `runs_instrument_fk` | Every run belongs to a known instrument | Dictionary: instrument_id is a foreign key to instruments | 0 | pass |  |
| `events_site_fk` | Every app event belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `tickets_site_fk` | Every ticket belongs to a known site | Dictionary: site_id is a foreign key to sites | 0 | pass |  |
| `runs_firmware_known` | Every run's firmware is a published release | Inference: firmware_releases lists the published releases | 0 | pass |  |
| `region_values` | Region is one of the four documented values | Dictionary: listed values | 0 | pass |  |
| `segment_values` | Segment is one of the three documented values | Dictionary: listed values | 0 | pass |  |
| `model_values` | Model is HX-200 or HX-200 Plus | Dictionary: listed values | 0 | pass |  |
| `qc_status_values` | QC status is pass, fail or skipped | Dictionary: listed values | 0 | pass |  |
| `skipped_before_400` | No run on firmware before 4.0.0 records skipped | Dictionary: skipped arrived in firmware 4.0.0 | 0 | pass |  |
| `status_values` | Subscription status is active, notice or churned | Dictionary: listed values | 0 | pass |  |
| `tier_values` | Tier is Basic or Plus | Dictionary: listed values | 0 | pass |  |
| `runs_in_window` | Every run falls inside 2025-09-01 to 2026-08-31 UTC | Dictionary: extract window | 0 | pass |  |
| `events_in_window` | Every app event falls inside the window | Dictionary: extract window | 0 | pass |  |
| `tickets_in_window` | Every ticket opened inside the window | Dictionary: extract window | 0 | pass |  |
| `runs_after_install` | No run happens before its instrument was installed | Dictionary: install_date is the date the instrument was commissioned | 3 | **FAIL** | Approved: keep the runs, too few to move any rate |
| `tickets_resolve_after_open` | A resolved ticket closes after it opens | Logic | 12 | **FAIL** | Approved: keep the tickets, resolution_hours is blank for them |
| `runs_positive_values` | Sample count and duration are positive | Logic | 0 | pass |  |
| `churned_date_in_window` | A churned site's missed renewal falls inside the window | Inference: churn is observed at a renewal inside the window | 0 | pass |  |
| `active_date_after_extract` | An active or notice site's next renewal is after the extract date | Dictionary: renewal_date is the next renewal for active sites | 4 | **FAIL** | Approved: flag the sites (status_conflict) and leave them out of the churn comparison |
| `renewal_on_anniversary` | Renewal date falls on the start date's anniversary | Inference: HaloCloud is an annual subscription | 0 | pass |  |
| `mart_one_row_per_site` | site_renewal holds exactly one row for every site | Logic: the table is defined as one row per site | 0 | pass |  |
| `mart_rates_in_range` | Every rate and share falls between 0 and 1 | Logic | 0 | pass |  |
| `mart_runs_add_up` | QC pass, fail and skipped on 4.0.0 and later plus pre-4.0.0 runs equal all runs | Logic | 0 | pass |  |
| `mart_qc_rules_applied` | Main-cohort sites without a clean QC rate are exactly the ones the two approved rules leave out | Logic: approved QC comparison rules 1 and 2 | 0 | pass |  |



## 2. The site table

One row per site. Each site gets a **decision date**: the missed renewal for churned sites, and the
last renewal (next renewal minus 12 months) for active and notice sites. Everything about a site is
measured in the **90 days before** that date, so nothing after the decision leaks in.

- **Churn** means `status = churned`. The 9 `notice` sites have not reached their decision yet, so
  they are counted separately.
- **Main cohort:** 431 sites with a full 90 days of data before the decision.
- **Clean QC rate:** fail / (pass + fail) on firmware 4.0.0 and later. Older firmware records a
  skipped QC step as a fail.
- **Ran the affected firmware:** the site ran IA-Panel-3 on an HX-200 on 4.1.0 or 4.1.1 in its
  90-day window.


```python
sites = table("sites_main")
display(sites.groupby("affected_exposure").agg(sites=("site_id", "size"), churned=("churn", "sum")))
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>sites</th>
      <th>churned</th>
    </tr>
    <tr>
      <th>affected_exposure</th>
      <th></th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>no</th>
      <td>295</td>
      <td>32</td>
    </tr>
    <tr>
      <th>yes</th>
      <td>136</td>
      <td>35</td>
    </tr>
  </tbody>
</table>
</div>


## 3. Firmware or a bad control lot?

The pack has no lot data, so the test uses what a lot problem must follow. A bad lot reaches every lab
that uses it in the same weeks. A firmware defect follows each instrument's own firmware version.

**Why these tests:**
- *Logistic regression with month and firmware:* if month adds nothing once firmware is in the model,
  a time-based cause such as a lot does not explain the failures. The likelihood-ratio test compares
  the models with and without month.
- *Two-proportion z-test:* compares failure rates on affected and other firmware in the same months.
- *Wilcoxon signed-rank test:* compares each instrument with itself before and after its own upgrade,
  so instrument differences cancel out.


```python
lm, le = S["lot_model"], S["lot_event_time"]
print(f"Firmware odds ratio {lm['firmware_odds_ratio']:.1f} "
      f"(95% CI {lm['firmware_or_ci'][0]:.1f} to {lm['firmware_or_ci'][1]:.1f}); month adds nothing (p = {lm['month_p']:.2f})")
print(f"Before upgrade {le['before'][0]}/{le['before'][1]} = {le['before'][0]/le['before'][1]:.1%}; "
      f"after {le['after'][0]}/{le['after'][1]} = {le['after'][0]/le['after'][1]:.1%}; "
      f"{le['instruments']} instruments; Wilcoxon p = {le['wilcoxon_p']:.1e}")
display(table("lot_same_window"))
figure("lot_test_event_time")
```

    Firmware odds ratio 19.4 (95% CI 16.6 to 22.8); month adds nothing (p = 0.91)
    Before upgrade 271/1001 = 27.1%; after 41/1080 = 3.8%; 361 instruments; Wilcoxon p = 5.9e-17



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>group</th>
      <th>firmware</th>
      <th>n</th>
      <th>events</th>
      <th>rate</th>
      <th>ci_low</th>
      <th>ci_high</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>HX-200 · IA-Panel-3</td>
      <td>4.0.0</td>
      <td>1346</td>
      <td>31</td>
      <td>0.023</td>
      <td>0.016</td>
      <td>0.033</td>
    </tr>
    <tr>
      <th>1</th>
      <td>HX-200 · IA-Panel-3</td>
      <td>4.0.2</td>
      <td>1348</td>
      <td>49</td>
      <td>0.036</td>
      <td>0.028</td>
      <td>0.048</td>
    </tr>
    <tr>
      <th>2</th>
      <td>HX-200 · IA-Panel-3</td>
      <td>4.1.0</td>
      <td>929</td>
      <td>363</td>
      <td>0.391</td>
      <td>0.360</td>
      <td>0.423</td>
    </tr>
    <tr>
      <th>3</th>
      <td>HX-200 · IA-Panel-3</td>
      <td>4.1.1</td>
      <td>520</td>
      <td>215</td>
      <td>0.413</td>
      <td>0.372</td>
      <td>0.456</td>
    </tr>
    <tr>
      <th>4</th>
      <td>HX-200 Plus · IA-Panel-3</td>
      <td>4.1.0 or 4.1.1</td>
      <td>474</td>
      <td>19</td>
      <td>0.040</td>
      <td>0.026</td>
      <td>0.062</td>
    </tr>
  </tbody>
</table>
</div>



![lot_test_event_time](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/lot_test_event_time.png)


## 4. Adoption and failures

**Why this test:** a weighted linear regression of the weekly failure rate on the share of runs on
the affected firmware. If the defect drives the failures, the fleet rate rises and falls with that
share.


```python
a = S["adoption"]
print(f"Weekly rate = {a['intercept']:.1%} + {a['slope']:.0%} x share on affected firmware; R2 = {a['r2']:.2f}")
figure("adoption_and_failures")
```

    Weekly rate = 2.9% + 38% x share on affected firmware; R2 = 0.93



![adoption_and_failures](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/adoption_and_failures.png)


## 5. Churn comparison

**Why these methods:** comparison tables with 95% Wilson intervals come first, because a reader can
check them by eye. Logistic regression then holds region, segment, tier and run volume equal. App use
and tickets stay out of the main model, because they can sit on the path from failures to churn.


```python
display(table("churn_by_affected_exposure"))
display(table("regression_exposure_no_mediators"))
figure("churn_by_segment_region")
figure("what_goes_with_churn")
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>affected_exposure</th>
      <th>n</th>
      <th>events</th>
      <th>rate</th>
      <th>ci_low</th>
      <th>ci_high</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>no</td>
      <td>295</td>
      <td>32</td>
      <td>0.108</td>
      <td>0.078</td>
      <td>0.149</td>
    </tr>
    <tr>
      <th>1</th>
      <td>yes</td>
      <td>136</td>
      <td>35</td>
      <td>0.257</td>
      <td>0.191</td>
      <td>0.337</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>term</th>
      <th>odds_ratio</th>
      <th>ci_low</th>
      <th>ci_high</th>
      <th>p_value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>C(affected_exposure)[T.yes]</td>
      <td>2.285</td>
      <td>1.283</td>
      <td>4.072</td>
      <td>0.005</td>
    </tr>
    <tr>
      <th>1</th>
      <td>C(region, Treatment('NA-East'))[T.APAC]</td>
      <td>1.327</td>
      <td>0.525</td>
      <td>3.354</td>
      <td>0.551</td>
    </tr>
    <tr>
      <th>2</th>
      <td>C(region, Treatment('NA-East'))[T.EU]</td>
      <td>2.390</td>
      <td>1.181</td>
      <td>4.839</td>
      <td>0.015</td>
    </tr>
    <tr>
      <th>3</th>
      <td>C(region, Treatment('NA-East'))[T.NA-West]</td>
      <td>0.632</td>
      <td>0.264</td>
      <td>1.515</td>
      <td>0.304</td>
    </tr>
    <tr>
      <th>4</th>
      <td>C(segment)[T.reference_lab]</td>
      <td>0.517</td>
      <td>0.216</td>
      <td>1.238</td>
      <td>0.139</td>
    </tr>
    <tr>
      <th>5</th>
      <td>C(segment)[T.research]</td>
      <td>2.898</td>
      <td>1.419</td>
      <td>5.919</td>
      <td>0.003</td>
    </tr>
    <tr>
      <th>6</th>
      <td>C(tier)[T.Plus]</td>
      <td>0.877</td>
      <td>0.482</td>
      <td>1.595</td>
      <td>0.667</td>
    </tr>
    <tr>
      <th>7</th>
      <td>log_runs</td>
      <td>1.189</td>
      <td>0.788</td>
      <td>1.793</td>
      <td>0.410</td>
    </tr>
  </tbody>
</table>
</div>



![churn_by_segment_region](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/churn_by_segment_region.png)



![what_goes_with_churn](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/what_goes_with_churn.png)


## 6. Customer story

**Why this test:** the detection week uses a one-sided binomial test of each week's failures against
the 3.0% rate the same instruments and assay had on 4.0.x. A week counts as clear once p falls below
0.001 with at least 20 runs.


```python
cs = S["customer_story"]
facts({k: str(cs[k])[:10] if "_4" in k or "ticket" in k or "week" in k else cs[k]
       for k in ["release_410", "first_qc_rejection_ticket", "signal_clear_week", "fix_412", "days_signal_to_fix",
                 "exposed_sites", "exposed_churned", "exposed_churned_before_fix", "excess_churned_sites", "excess_arr"]})
figure("visible_before_fixed")
display(table("detection_weekly"))
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>release_410</th>
      <td>2025-11-05</td>
    </tr>
    <tr>
      <th>first_qc_rejection_ticket</th>
      <td>2025-11-19</td>
    </tr>
    <tr>
      <th>signal_clear_week</th>
      <td>2025-11-24</td>
    </tr>
    <tr>
      <th>fix_412</th>
      <td>2026-03-20</td>
    </tr>
    <tr>
      <th>days_signal_to_fix</th>
      <td>116</td>
    </tr>
    <tr>
      <th>exposed_sites</th>
      <td>136</td>
    </tr>
    <tr>
      <th>exposed_churned</th>
      <td>35</td>
    </tr>
    <tr>
      <th>exposed_churned_before_fix</th>
      <td>23</td>
    </tr>
    <tr>
      <th>excess_churned_sites</th>
      <td>20.247</td>
    </tr>
    <tr>
      <th>excess_arr</th>
      <td>129294.479</td>
    </tr>
  </tbody>
</table>
</div>



![visible_before_fixed](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/visible_before_fixed.png)



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>week</th>
      <th>n</th>
      <th>fails</th>
      <th>rate</th>
      <th>p_vs_baseline</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>2025-11-03</td>
      <td>1</td>
      <td>0</td>
      <td>0.000</td>
      <td>1.000e+00</td>
    </tr>
    <tr>
      <th>1</th>
      <td>2025-11-10</td>
      <td>6</td>
      <td>2</td>
      <td>0.333</td>
      <td>1.253e-02</td>
    </tr>
    <tr>
      <th>2</th>
      <td>2025-11-17</td>
      <td>34</td>
      <td>5</td>
      <td>0.147</td>
      <td>3.314e-03</td>
    </tr>
    <tr>
      <th>3</th>
      <td>2025-11-24</td>
      <td>37</td>
      <td>17</td>
      <td>0.459</td>
      <td>1.217e-16</td>
    </tr>
    <tr>
      <th>4</th>
      <td>2025-12-01</td>
      <td>48</td>
      <td>16</td>
      <td>0.333</td>
      <td>4.073e-13</td>
    </tr>
    <tr>
      <th>5</th>
      <td>2025-12-08</td>
      <td>95</td>
      <td>30</td>
      <td>0.316</td>
      <td>1.565e-22</td>
    </tr>
  </tbody>
</table>
</div>


## 7. Follow-up checks

These are exploratory. The primary test is the exposure comparison in section 5.

**Europe.** *Mann-Whitney U* compares response times, which are skewed, by rank. *Fisher's exact
test* compares churn rates in small groups with an exact p-value.


```python
eu = S["follow_ups"]["eu_channel"]
display(table("first_response_by_channel"))
facts(eu["exposed_churn_eu_vs_direct"], "Churn, ran the affected firmware: a = EU, b = direct")
facts(eu["response_churned_vs_renewed"], "Response time: churned vs renewed sites that filed a QC ticket")
figure("eu_support_churn")
display(table("churn_by_exposure_region_segment"))
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>ticket_type</th>
      <th>region_group</th>
      <th>n</th>
      <th>median</th>
      <th>q25</th>
      <th>q75</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>All other</td>
      <td>Direct (NA, APAC)</td>
      <td>1962</td>
      <td>6.2</td>
      <td>3.70</td>
      <td>10.50</td>
    </tr>
    <tr>
      <th>1</th>
      <td>All other</td>
      <td>EU (distributor)</td>
      <td>905</td>
      <td>17.8</td>
      <td>11.10</td>
      <td>28.80</td>
    </tr>
    <tr>
      <th>2</th>
      <td>QC rejection</td>
      <td>Direct (NA, APAC)</td>
      <td>48</td>
      <td>6.2</td>
      <td>3.95</td>
      <td>12.15</td>
    </tr>
    <tr>
      <th>3</th>
      <td>QC rejection</td>
      <td>EU (distributor)</td>
      <td>23</td>
      <td>22.8</td>
      <td>10.30</td>
      <td>34.45</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Churn, ran the affected firmware: a = EU, b = direct</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>a</th>
      <td>21 of 51 (41.2%)</td>
    </tr>
    <tr>
      <th>b</th>
      <td>14 of 85 (16.5%)</td>
    </tr>
    <tr>
      <th>odds_ratio</th>
      <td>3.55</td>
    </tr>
    <tr>
      <th>p</th>
      <td>0.002</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Response time: churned vs renewed sites that filed a QC ticket</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>sites</th>
      <td>31.000</td>
    </tr>
    <tr>
      <th>churned</th>
      <td>5.000</td>
    </tr>
    <tr>
      <th>median_churned</th>
      <td>14.800</td>
    </tr>
    <tr>
      <th>median_renewed</th>
      <td>9.825</td>
    </tr>
    <tr>
      <th>mannwhitney_p</th>
      <td>0.936</td>
    </tr>
  </tbody>
</table>
</div>



![eu_support_churn](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/eu_support_churn.png)



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>region_group</th>
      <th>segment</th>
      <th>affected_exposure</th>
      <th>n</th>
      <th>events</th>
      <th>rate</th>
      <th>ci_low</th>
      <th>ci_high</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>Direct (NA, APAC)</td>
      <td>hospital_lab</td>
      <td>no</td>
      <td>108</td>
      <td>8</td>
      <td>0.074</td>
      <td>0.038</td>
      <td>0.139</td>
    </tr>
    <tr>
      <th>1</th>
      <td>Direct (NA, APAC)</td>
      <td>hospital_lab</td>
      <td>yes</td>
      <td>37</td>
      <td>7</td>
      <td>0.189</td>
      <td>0.095</td>
      <td>0.342</td>
    </tr>
    <tr>
      <th>2</th>
      <td>Direct (NA, APAC)</td>
      <td>reference_lab</td>
      <td>no</td>
      <td>46</td>
      <td>2</td>
      <td>0.043</td>
      <td>0.012</td>
      <td>0.145</td>
    </tr>
    <tr>
      <th>3</th>
      <td>Direct (NA, APAC)</td>
      <td>reference_lab</td>
      <td>yes</td>
      <td>15</td>
      <td>1</td>
      <td>0.067</td>
      <td>0.012</td>
      <td>0.298</td>
    </tr>
    <tr>
      <th>4</th>
      <td>Direct (NA, APAC)</td>
      <td>research</td>
      <td>no</td>
      <td>57</td>
      <td>10</td>
      <td>0.175</td>
      <td>0.098</td>
      <td>0.294</td>
    </tr>
    <tr>
      <th>5</th>
      <td>Direct (NA, APAC)</td>
      <td>research</td>
      <td>yes</td>
      <td>33</td>
      <td>6</td>
      <td>0.182</td>
      <td>0.086</td>
      <td>0.344</td>
    </tr>
    <tr>
      <th>6</th>
      <td>EU (distributor)</td>
      <td>hospital_lab</td>
      <td>no</td>
      <td>44</td>
      <td>6</td>
      <td>0.136</td>
      <td>0.064</td>
      <td>0.267</td>
    </tr>
    <tr>
      <th>7</th>
      <td>EU (distributor)</td>
      <td>hospital_lab</td>
      <td>yes</td>
      <td>18</td>
      <td>4</td>
      <td>0.222</td>
      <td>0.090</td>
      <td>0.452</td>
    </tr>
    <tr>
      <th>8</th>
      <td>EU (distributor)</td>
      <td>reference_lab</td>
      <td>no</td>
      <td>22</td>
      <td>2</td>
      <td>0.091</td>
      <td>0.025</td>
      <td>0.278</td>
    </tr>
    <tr>
      <th>9</th>
      <td>EU (distributor)</td>
      <td>reference_lab</td>
      <td>yes</td>
      <td>14</td>
      <td>3</td>
      <td>0.214</td>
      <td>0.076</td>
      <td>0.476</td>
    </tr>
    <tr>
      <th>10</th>
      <td>EU (distributor)</td>
      <td>research</td>
      <td>no</td>
      <td>18</td>
      <td>4</td>
      <td>0.222</td>
      <td>0.090</td>
      <td>0.452</td>
    </tr>
    <tr>
      <th>11</th>
      <td>EU (distributor)</td>
      <td>research</td>
      <td>yes</td>
      <td>19</td>
      <td>14</td>
      <td>0.737</td>
      <td>0.512</td>
      <td>0.882</td>
    </tr>
  </tbody>
</table>
</div>


**Region and lab type together.** The same counts on a schematic map, one panel per region and one
slot per lab type. Bubble area is lost sites, and the orange wedge is the part that ran the
affected firmware. Every group is under the 80-site minimum, so only the European research-lab
rate is printed, because it is the one group with a test behind it (Fisher's exact, above).


```python
display(table("lost_by_region_and_lab"))
figure("lost_by_region_and_lab")
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>region</th>
      <th>segment</th>
      <th>sites</th>
      <th>lost</th>
      <th>exposed_lost</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>APAC</td>
      <td>hospital_lab</td>
      <td>25</td>
      <td>4</td>
      <td>2</td>
    </tr>
    <tr>
      <th>1</th>
      <td>APAC</td>
      <td>reference_lab</td>
      <td>18</td>
      <td>0</td>
      <td>0</td>
    </tr>
    <tr>
      <th>2</th>
      <td>APAC</td>
      <td>research</td>
      <td>19</td>
      <td>5</td>
      <td>2</td>
    </tr>
    <tr>
      <th>3</th>
      <td>EU</td>
      <td>hospital_lab</td>
      <td>62</td>
      <td>10</td>
      <td>4</td>
    </tr>
    <tr>
      <th>4</th>
      <td>EU</td>
      <td>reference_lab</td>
      <td>36</td>
      <td>5</td>
      <td>3</td>
    </tr>
    <tr>
      <th>5</th>
      <td>EU</td>
      <td>research</td>
      <td>37</td>
      <td>18</td>
      <td>14</td>
    </tr>
    <tr>
      <th>6</th>
      <td>NA-East</td>
      <td>hospital_lab</td>
      <td>67</td>
      <td>6</td>
      <td>1</td>
    </tr>
    <tr>
      <th>7</th>
      <td>NA-East</td>
      <td>reference_lab</td>
      <td>22</td>
      <td>1</td>
      <td>0</td>
    </tr>
    <tr>
      <th>8</th>
      <td>NA-East</td>
      <td>research</td>
      <td>33</td>
      <td>8</td>
      <td>3</td>
    </tr>
    <tr>
      <th>9</th>
      <td>NA-West</td>
      <td>hospital_lab</td>
      <td>53</td>
      <td>5</td>
      <td>4</td>
    </tr>
    <tr>
      <th>10</th>
      <td>NA-West</td>
      <td>reference_lab</td>
      <td>21</td>
      <td>2</td>
      <td>1</td>
    </tr>
    <tr>
      <th>11</th>
      <td>NA-West</td>
      <td>research</td>
      <td>38</td>
      <td>3</td>
      <td>1</td>
    </tr>
  </tbody>
</table>
</div>



![lost_by_region_and_lab](https://raw.githubusercontent.com/this-is-how-we-see/halvard-qc-churn/analysis/output/figures/lost_by_region_and_lab.png)


**App use.** *Cochran-Mantel-Haenszel test:* compares sites that did and did not run the affected
firmware inside each third of HaloCloud use, then combines the three comparisons.


```python
display(table("churn_by_exposure_and_app_use"))
facts(S["follow_ups"]["exposure_within_app_use"], "Ran the affected firmware, within app-use thirds")
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>app_band</th>
      <th>affected_exposure</th>
      <th>n</th>
      <th>events</th>
      <th>rate</th>
      <th>ci_low</th>
      <th>ci_high</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>high</td>
      <td>no</td>
      <td>107</td>
      <td>2</td>
      <td>0.019</td>
      <td>0.005</td>
      <td>0.066</td>
    </tr>
    <tr>
      <th>1</th>
      <td>high</td>
      <td>yes</td>
      <td>27</td>
      <td>1</td>
      <td>0.037</td>
      <td>0.007</td>
      <td>0.183</td>
    </tr>
    <tr>
      <th>2</th>
      <td>low</td>
      <td>no</td>
      <td>76</td>
      <td>21</td>
      <td>0.276</td>
      <td>0.188</td>
      <td>0.386</td>
    </tr>
    <tr>
      <th>3</th>
      <td>low</td>
      <td>yes</td>
      <td>70</td>
      <td>29</td>
      <td>0.414</td>
      <td>0.306</td>
      <td>0.531</td>
    </tr>
    <tr>
      <th>4</th>
      <td>middle</td>
      <td>no</td>
      <td>112</td>
      <td>9</td>
      <td>0.080</td>
      <td>0.043</td>
      <td>0.146</td>
    </tr>
    <tr>
      <th>5</th>
      <td>middle</td>
      <td>yes</td>
      <td>39</td>
      <td>5</td>
      <td>0.128</td>
      <td>0.056</td>
      <td>0.267</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Ran the affected firmware, within app-use thirds</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>pooled_odds_ratio</th>
      <td>1.819</td>
    </tr>
    <tr>
      <th>cmh_p</th>
      <td>0.042</td>
    </tr>
    <tr>
      <th>equal_odds_p</th>
      <td>0.987</td>
    </tr>
  </tbody>
</table>
</div>


**Decisions after the fix, and European research labs.** Both use Fisher's exact test.


```python
fu = S["follow_ups"]
facts(fu["decided_after_fix"], "Renewal after 4.1.2: a = ran it, b = did not")
facts(fu["eu_research_labs"], "European research labs: a = ran it, b = did not")
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Renewal after 4.1.2: a = ran it, b = did not</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>a</th>
      <td>12 of 52 (23.1%)</td>
    </tr>
    <tr>
      <th>b</th>
      <td>14 of 99 (14.1%)</td>
    </tr>
    <tr>
      <th>odds_ratio</th>
      <td>1.821</td>
    </tr>
    <tr>
      <th>p</th>
      <td>0.18</td>
    </tr>
    <tr>
      <th>sites_running_defect_after_fix</th>
      <td>36</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / a</th>
      <td>8 of 36 (22.2%)</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / b</th>
      <td>4 of 16 (25.0%)</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / odds_ratio</th>
      <td>0.857</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / p</th>
      <td>1.0</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / median_days_run_after_fix</th>
      <td>29.5</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / max_days_run_after_fix</th>
      <td>147</td>
    </tr>
    <tr>
      <th>still_running_vs_upgraded / ran_it_within_30_days_of_renewal</th>
      <td>21</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>European research labs: a = ran it, b = did not</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>a</th>
      <td>14 of 19 (73.7%)</td>
    </tr>
    <tr>
      <th>b</th>
      <td>4 of 18 (22.2%)</td>
    </tr>
    <tr>
      <th>odds_ratio</th>
      <td>9.8</td>
    </tr>
    <tr>
      <th>p</th>
      <td>0.003</td>
    </tr>
  </tbody>
</table>
</div>


**The normal QC range for HX-200 IA-Panel-3.** A QC lab reads a control failure rate against its
normal range, not against an average or a slope. The range comes from weekly fleet rates on other
firmware, weeks with at least 20 QC runs: the mean plus three standard deviations. A site runs a
median of about 6 QC runs per assay in its 90 days, too few to set a range of its own, so each site
is compared by what it ran.


```python
r = fu["ia3_weekly_range"]
print(f"Other firmware: {r['normal_weeks']} weeks, mean {r['normal_mean']:.1%}, SD {r['normal_sd']:.1%}, "
      f"highest {r['normal_max']:.1%}; upper limit (mean + 3 SD) {r['upper_limit_3sd']:.1%}")
print(f"4.1.0 and 4.1.1: {r['affected_weeks']} weeks, mean {r['affected_mean']:.1%}, lowest {r['affected_min']:.1%}, "
      f"highest {r['affected_max']:.1%}; {r['affected_weeks_above_limit']} of {r['affected_weeks']} weeks above the limit")
print(f"Median QC runs per site and assay in 90 days: {r['median_qc_runs_per_site_assay_90d']:.0f}")
```

    Other firmware: 53 weeks, mean 3.1%, SD 1.0%, highest 5.1%; upper limit (mean + 3 SD) 6.2%
    4.1.0 and 4.1.1: 35 weeks, mean 38.2%, lowest 14.7%, highest 46.7%; 35 of 35 weeks above the limit
    Median QC runs per site and assay in 90 days: 6


**Normal churn and group-size limits.** Normal churn is the rate for sites that did not run the
affected firmware. A group breaches normal when its rate is above the center line plus 1.96 standard
errors for its size, so the limit widens for small groups.


```python
facts(fu["churn_baseline"], "Normal churn")
display(table("churn_baseline_by_segment"))
display(table("churn_vs_baseline_limits"))
facts(fu["excess_arr_range"], "Excess ARR, three ways")
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Normal churn</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>normal</th>
      <td>32 of 295 (10.8%)</td>
    </tr>
    <tr>
      <th>rate</th>
      <td>0.108</td>
    </tr>
    <tr>
      <th>ci_low</th>
      <td>0.078</td>
    </tr>
    <tr>
      <th>ci_high</th>
      <td>0.149</td>
    </tr>
    <tr>
      <th>before_defect</th>
      <td>8 of 56 (14.3%)</td>
    </tr>
    <tr>
      <th>upper_limit_by_size / 50</th>
      <td>0.195</td>
    </tr>
    <tr>
      <th>upper_limit_by_size / 136</th>
      <td>0.161</td>
    </tr>
    <tr>
      <th>upper_limit_by_size / 300</th>
      <td>0.144</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>segment</th>
      <th>n</th>
      <th>events</th>
      <th>rate</th>
      <th>ci_low</th>
      <th>ci_high</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>hospital_lab</td>
      <td>152</td>
      <td>14</td>
      <td>0.092</td>
      <td>0.056</td>
      <td>0.149</td>
    </tr>
    <tr>
      <th>1</th>
      <td>reference_lab</td>
      <td>68</td>
      <td>4</td>
      <td>0.059</td>
      <td>0.023</td>
      <td>0.142</td>
    </tr>
    <tr>
      <th>2</th>
      <td>research</td>
      <td>75</td>
      <td>14</td>
      <td>0.187</td>
      <td>0.115</td>
      <td>0.289</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>group</th>
      <th>n</th>
      <th>churned</th>
      <th>rate</th>
      <th>upper_limit</th>
      <th>breach</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>Ran the affected firmware</td>
      <td>136</td>
      <td>35</td>
      <td>0.257</td>
      <td>0.161</td>
      <td>True</td>
    </tr>
    <tr>
      <th>1</th>
      <td>EU, ran the affected firmware</td>
      <td>51</td>
      <td>21</td>
      <td>0.412</td>
      <td>0.194</td>
      <td>True</td>
    </tr>
    <tr>
      <th>2</th>
      <td>All main-cohort renewals, 2025Q4</td>
      <td>13</td>
      <td>2</td>
      <td>0.154</td>
      <td>0.278</td>
      <td>False</td>
    </tr>
    <tr>
      <th>3</th>
      <td>All main-cohort renewals, 2026Q1</td>
      <td>287</td>
      <td>42</td>
      <td>0.146</td>
      <td>0.144</td>
      <td>True</td>
    </tr>
    <tr>
      <th>4</th>
      <td>All main-cohort renewals, 2026Q2</td>
      <td>94</td>
      <td>21</td>
      <td>0.223</td>
      <td>0.171</td>
      <td>True</td>
    </tr>
    <tr>
      <th>5</th>
      <td>All main-cohort renewals, 2026Q3</td>
      <td>37</td>
      <td>2</td>
      <td>0.054</td>
      <td>0.209</td>
      <td>False</td>
    </tr>
    <tr>
      <th>6</th>
      <td>Did not run the defect, 2025Q4</td>
      <td>10</td>
      <td>1</td>
      <td>0.100</td>
      <td>0.301</td>
      <td>False</td>
    </tr>
    <tr>
      <th>7</th>
      <td>Did not run the defect, 2026Q1</td>
      <td>196</td>
      <td>19</td>
      <td>0.097</td>
      <td>0.152</td>
      <td>False</td>
    </tr>
    <tr>
      <th>8</th>
      <td>Did not run the defect, 2026Q2</td>
      <td>62</td>
      <td>11</td>
      <td>0.177</td>
      <td>0.186</td>
      <td>False</td>
    </tr>
    <tr>
      <th>9</th>
      <td>Did not run the defect, 2026Q3</td>
      <td>27</td>
      <td>1</td>
      <td>0.037</td>
      <td>0.226</td>
      <td>False</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>Excess ARR, three ways</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>excess_sites</th>
      <td>20.247</td>
    </tr>
    <tr>
      <th>at_mean_arr_of_exposed_churned</th>
      <td>129294.479</td>
    </tr>
    <tr>
      <th>at_mean_arr_of_all_exposed</th>
      <td>135255.995</td>
    </tr>
    <tr>
      <th>churned_arr_minus_expected</th>
      <td>124950.847</td>
    </tr>
  </tbody>
</table>
</div>


**The smallest group worth reporting.** A churn rate for a small group swings by chance. *Power
analysis with an exact binomial test* asks how many sites a group needs before its churn rate can
separate a real change from chance: a 5% false-alarm rate and an 80% chance of catching the change.
The one judgment is the size of change to catch. Catching churn at double normal takes about 82
sites, so a territory cut smaller than that gives sales numbers that chance alone can produce.


```python
display(table("min_group_size"))
display(table("regions_vs_min_group_size"))
```


<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>change</th>
      <th>churn_to_catch</th>
      <th>sites_needed</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>1.5 times normal</td>
      <td>0.163</td>
      <td>269</td>
    </tr>
    <tr>
      <th>1</th>
      <td>double normal</td>
      <td>0.217</td>
      <td>82</td>
    </tr>
    <tr>
      <th>2</th>
      <td>the defect effect</td>
      <td>0.257</td>
      <td>47</td>
    </tr>
    <tr>
      <th>3</th>
      <td>triple normal</td>
      <td>0.325</td>
      <td>27</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>region</th>
      <th>sites</th>
      <th>meets_minimum</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>APAC</td>
      <td>62</td>
      <td>False</td>
    </tr>
    <tr>
      <th>1</th>
      <td>EU</td>
      <td>135</td>
      <td>True</td>
    </tr>
    <tr>
      <th>2</th>
      <td>NA-East</td>
      <td>122</td>
      <td>True</td>
    </tr>
    <tr>
      <th>3</th>
      <td>NA-West</td>
      <td>112</td>
      <td>True</td>
    </tr>
  </tbody>
</table>
</div>


## Limits

- One renewal cycle, so normal churn is an estimate (likely 8% to 15%).
- QC is pass or fail only. The pack holds no control values and no lot numbers.
- App events are a 1-in-10 sample, scaled by 10.
- The pack has no territory field and no HaloCloud version history.
