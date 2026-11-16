"""Harmonize VIIRS (NOAA-20) hotspots into MODIS-equivalent units.

Method
------
1. Candidate VIIRS metrics per 0.1 deg cell-day: raw pixel count (n) and the
   1 km-collapsed cluster counts with FRP thresholds (n_1km*, from 02).
2. Linear ratio estimator f = sum(MODIS) / sum(VIIRS metric), fitted in the
   overlap window (2018-04 .. 2020-12) at one of several granularities:
   continental (naive), country x month, 2-degree block x month. Factors are
   shrunk (empirical Bayes) toward the region factor and then toward the
   continental factor, so quiet regions/months are not dominated by noise.
3. Leave-one-year-out cross-validation compares all variants; the best model
   by cell x month R2 (tie-break: country x month NRMSE) is selected.
   Nonlinear (power-law) alternatives were tested in
   experiments/powerlaw_test.py and were worse, so only linear models remain.
4. The chosen model converts the whole VIIRS record. The harmonized series is
   MODIS where MODIS exists (<= 2020-12-31) and MODIS-equivalent VIIRS after.

Outputs: data/agg/harmonized_daily_grid.parquet, data/agg/factors.parquet,
         data/agg/validation.json, reports/validation.md (+ figures)
"""
import json
import sys
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import AGG_DIR, GRID_DEG, OVERLAP_END, OVERLAP_START, REPORT_DIR  # noqa: E402

GRID = (AGG_DIR / "daily_grid.parquet").as_posix()
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR = REPORT_DIR / "figs"
FIG_DIR.mkdir(exist_ok=True)

BLOCK_CELLS = 20          # 2-degree blocks (20 cells of 0.1 deg)
ALPHA, BETA = 3000.0, 20000.0   # shrinkage pseudo-counts (VIIRS metric units)

# (name, metric, region key or None, by_month)
MODELS = [
    ("naive_global_n", "n", None, False),
    ("global_month_n", "n", None, True),
    ("country_n", "n", "country", False),
    ("country_month_n", "n", "country", True),
    ("block_n", "n", "block", False),
    ("block_month_n", "n", "block", True),
    ("country_month_n1km", "n_1km", "country", True),
    ("country_month_n1km_f5", "n_1km_f5", "country", True),
    ("block_month_n1km_f5", "n_1km_f5", "block", True),
]

con = duckdb.connect()
con.execute("SET threads TO 8")

# ---------------------------------------------------------------- cell-day tables
print("building cell-day tables ...")
con.execute(f"""
CREATE TABLE m AS
SELECT country, acq_date, gi, gj,
       sum(n) AS n_modis,
       sum(CASE WHEN satellite='Aqua' THEN n ELSE 0 END) AS n_modis_aqua,
       sum(frp_sum) AS frp_modis
FROM read_parquet('{GRID}') WHERE sensor='MODIS' GROUP BY ALL
""")
con.execute(f"""
CREATE TABLE v AS
SELECT country, acq_date, gi, gj,
       sum(n) AS n, sum(n_1km) AS n_1km, sum(n_1km_f2) AS n_1km_f2,
       sum(n_1km_f5) AS n_1km_f5, sum(n_1km_f10) AS n_1km_f10, sum(n_1km_f20) AS n_1km_f20,
       sum(frp_sum) AS frp_viirs
FROM read_parquet('{GRID}') WHERE sensor='VIIRS' GROUP BY ALL
""")

overlap = con.execute(f"""
SELECT coalesce(m.country, v.country) AS country,
       coalesce(m.acq_date, v.acq_date) AS acq_date,
       coalesce(m.gi, v.gi) AS gi, coalesce(m.gj, v.gj) AS gj,
       coalesce(n_modis,0) AS n_modis, coalesce(n_modis_aqua,0) AS n_modis_aqua,
       coalesce(frp_modis,0) AS frp_modis,
       coalesce(v.n,0) AS n, coalesce(n_1km,0) AS n_1km, coalesce(n_1km_f2,0) AS n_1km_f2,
       coalesce(n_1km_f5,0) AS n_1km_f5, coalesce(n_1km_f10,0) AS n_1km_f10,
       coalesce(n_1km_f20,0) AS n_1km_f20, coalesce(frp_viirs,0) AS frp_viirs
FROM m FULL OUTER JOIN v USING (country, acq_date, gi, gj)
WHERE coalesce(m.acq_date, v.acq_date) BETWEEN '{OVERLAP_START}' AND '{OVERLAP_END}'
""").df()
overlap["acq_date"] = pd.to_datetime(overlap["acq_date"])
overlap["year"] = overlap.acq_date.dt.year
overlap["month"] = overlap.acq_date.dt.month
overlap["block"] = (overlap.gi // BLOCK_CELLS).astype(str) + "_" + (overlap.gj // BLOCK_CELLS).astype(str)
print(f"overlap cell-days: {len(overlap):,}")


# ---------------------------------------------------------------- factor fitting
def fit_factors(df, metric, region, by_month, target="n_modis"):
    """Shrunk ratio-estimator factors. Returns dict with f_all, f_region (Series), f_km (Series)."""
    tot = df[[target, metric]].sum()
    out = {"f_all": float(tot[target] / max(tot[metric], 1e-9)), "region": region, "by_month": by_month,
           "metric": metric}
    if region:
        c = df.groupby(region)[[target, metric]].sum()
        c["f"] = (c[target] + BETA * out["f_all"]) / (c[metric] + BETA)
        out["f_region"] = c["f"]
    if by_month:
        keys = ([region] if region else []) + ["month"]
        g = df.groupby(keys)[[target, metric]].sum().reset_index()
        prior = g[region].map(out["f_region"]) if region else out["f_all"]
        g["f"] = (g[target] + ALPHA * prior) / (g[metric] + ALPHA)
        g["sum_target"], g["sum_metric"] = g[target], g[metric]
        out["f_km"] = g.set_index(keys)["f"]
        out["table"] = g[keys + ["f", "sum_target", "sum_metric"]]
    return out


def factor_vector(df, p):
    """Per-row factor for a fitted model p."""
    f = np.full(len(df), np.nan)
    if p["by_month"]:
        keys = ([p["region"]] if p["region"] else []) + ["month"]
        idx = pd.MultiIndex.from_frame(df[keys]) if len(keys) > 1 else df[keys[0]]
        f = p["f_km"].reindex(idx).to_numpy()
    if p["region"]:
        fr = df[p["region"]].map(p["f_region"]).to_numpy()
        f = np.where(np.isnan(f), fr, f)
    return np.where(np.isnan(f), p["f_all"], f)


def predict(df, p):
    return df[p["metric"]].to_numpy(float) * factor_vector(df, p)


def scores(obs, pred) -> dict:
    obs = np.asarray(obs, float); pred = np.asarray(pred, float)
    ss_res = ((obs - pred) ** 2).sum(); ss_tot = ((obs - obs.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    lo, lp = np.log1p(obs), np.log1p(pred)
    r2_log = 1 - ((lo - lp) ** 2).sum() / max(((lo - lo.mean()) ** 2).sum(), 1e-9)
    nrmse = np.sqrt(((obs - pred) ** 2).mean()) / max(obs.mean(), 1e-9)
    bias = pred.sum() / max(obs.sum(), 1e-9) - 1
    return {"r2": float(r2), "r2_log": float(r2_log), "nrmse": float(nrmse), "bias": float(bias)}


# ---------------------------------------------------------------- cross-validation
print("cross-validating ...")
years = sorted(int(y) for y in overlap.year.unique())
cv_rows, country_err, cv_preds = [], {}, {}
for name, metric, region, by_month in MODELS:
    preds = []
    for y in years:
        train, test = overlap[overlap.year != y], overlap[overlap.year == y].copy()
        test["pred"] = predict(test, fit_factors(train, metric, region, by_month))
        preds.append(test)
    allp = pd.concat(preds)
    cv_preds[name] = allp
    cell_month = allp.groupby(["country", "year", "month", "gi", "gj"])[["n_modis", "pred"]].sum()
    ctry_month = allp.groupby(["country", "year", "month"])[["n_modis", "pred"]].sum()
    ctry_week = allp.assign(wk=allp.acq_date.dt.to_period("W")).groupby(["country", "wk"])[["n_modis", "pred"]].sum()
    row = {"model": name, "metric": metric, "region": region or "continent", "by_month": by_month}
    row.update({f"cellmonth_{k}": v for k, v in scores(cell_month.n_modis, cell_month.pred).items()})
    row.update({f"ctrymonth_{k}": v for k, v in scores(ctry_month.n_modis, ctry_month.pred).items()})
    row.update({f"ctryweek_{k}": v for k, v in scores(ctry_week.n_modis, ctry_week.pred).items()})
    cv_rows.append(row)
    cmr = ctry_month.reset_index()
    country_err[name] = {c: float(np.sqrt(((g.n_modis - g.pred) ** 2).mean()) / max(g.n_modis.mean(), 1e-9))
                         for c, g in cmr.groupby("country")}

cv = pd.DataFrame(cv_rows).set_index("model")
# balanced selection: mean rank over cell-month R2 (linear and log), country-month and country-week NRMSE
ranks = pd.concat([cv.cellmonth_r2.rank(ascending=False), cv.cellmonth_r2_log.rank(ascending=False),
                   cv.ctrymonth_nrmse.rank(), cv.ctryweek_nrmse.rank()], axis=1)
cv["mean_rank"] = ranks.mean(axis=1)
cv = cv.sort_values(["mean_rank", "cellmonth_r2"], ascending=[True, False])
print(cv[["mean_rank", "cellmonth_r2", "cellmonth_r2_log", "ctrymonth_nrmse", "ctryweek_nrmse", "ctrymonth_bias"]].round(3).to_string())
best = cv.index[0]
b_metric, b_region, b_month = cv.loc[best, "metric"], cv.loc[best, "region"], bool(cv.loc[best, "by_month"])
b_region = None if b_region == "continent" else b_region
print("selected model:", best)

# ---------------------------------------------------------------- final factors
P = fit_factors(overlap, b_metric, b_region, b_month, "n_modis")
P_frp = fit_factors(overlap, "frp_viirs", b_region, b_month, "frp_modis")
P_aqua = fit_factors(overlap, b_metric, b_region, b_month, "n_modis_aqua")  # same-overpass diagnostic

# factor lookup table at the model's granularity
keys = ([b_region] if b_region else []) + (["month"] if b_month else [])
if keys:
    tab = P["table"].rename(columns={"f": "factor_n"})
    tab["factor_frp"] = P_frp["table"].set_index(keys)["f"].reindex(pd.MultiIndex.from_frame(tab[keys]) if len(keys) > 1 else tab[keys[0]]).to_numpy()
    tab["factor_n_aqua"] = P_aqua["table"].set_index(keys)["f"].reindex(pd.MultiIndex.from_frame(tab[keys]) if len(keys) > 1 else tab[keys[0]]).to_numpy()
else:
    tab = pd.DataFrame({"factor_n": [P["f_all"]], "factor_frp": [P_frp["f_all"]], "factor_n_aqua": [P_aqua["f_all"]],
                        "sum_target": [overlap.n_modis.sum()], "sum_metric": [overlap[b_metric].sum()]})
tab["model"], tab["metric"], tab["factor_n_all"], tab["factor_frp_all"] = best, b_metric, P["f_all"], P_frp["f_all"]
if b_region == "block":
    bi = tab.block.str.split("_", expand=True).astype(int)
    tab["lat_min"], tab["lon_min"] = bi[0] * BLOCK_CELLS / 10.0, bi[1] * BLOCK_CELLS / 10.0
    tab["lat_max"], tab["lon_max"] = tab.lat_min + BLOCK_CELLS / 10.0, tab.lon_min + BLOCK_CELLS / 10.0
tab.to_parquet(AGG_DIR / "factors.parquet", index=False)

# per-country x month factors of the equivalent country model (for the report / API)
Pc = fit_factors(overlap, b_metric, "country", True, "n_modis")
ctab = Pc["table"].rename(columns={"f": "factor_n"})
ctab["rel_err"] = ctab.country.map(country_err[best])
ctab.to_parquet(AGG_DIR / "factors_country_month.parquet", index=False)

# ---------------------------------------------------------------- apply to full record
print("writing harmonized grid ...")
full = con.execute("""
SELECT coalesce(m.country, v.country) AS country, coalesce(m.acq_date, v.acq_date) AS acq_date,
       coalesce(m.gi, v.gi) AS gi, coalesce(m.gj, v.gj) AS gj,
       n_modis, frp_modis, v.n AS n_viirs, v.n_1km AS n_viirs_1km, frp_viirs,
       v.n, v.n_1km, v.n_1km_f5
FROM m FULL OUTER JOIN v USING (country, acq_date, gi, gj)
""").df()
full["acq_date"] = pd.to_datetime(full.acq_date)
full["month"] = full.acq_date.dt.month
full["block"] = (full.gi // BLOCK_CELLS).astype(str) + "_" + (full.gj // BLOCK_CELLS).astype(str)
has_v = full.n_viirs.notna().to_numpy()
fac_n = factor_vector(full, P)
fac_frp = factor_vector(full, P_frp)
full["n_viirs_harm"] = np.where(has_v, full[b_metric].fillna(0).to_numpy(float) * fac_n, np.nan)
full["frp_viirs_harm"] = np.where(has_v, full.frp_viirs.fillna(0).to_numpy(float) * fac_frp, np.nan)
full["rel_err"] = full.country.map(country_err[best]).fillna(0.5)
is_modis_era = full.acq_date <= pd.Timestamp(OVERLAP_END)
full["n_harm"] = np.where(is_modis_era, full.n_modis.fillna(0), full.n_viirs_harm).astype(float)
full["frp_harm"] = np.where(is_modis_era, full.frp_modis.fillna(0), full.frp_viirs_harm).astype(float)
full["n_harm"] = full.n_harm.fillna(0); full["frp_harm"] = full.frp_harm.fillna(0)
full["source"] = np.where(is_modis_era, "MODIS", "VIIRS_harmonized")
full["cell_lat"] = full.gi / 10.0 + 0.05
full["cell_lon"] = full.gj / 10.0 + 0.05
out_cols = ["country", "acq_date", "gi", "gj", "cell_lat", "cell_lon", "n_modis", "frp_modis", "n_viirs",
            "n_viirs_1km", "frp_viirs", "n_viirs_harm", "frp_viirs_harm", "rel_err", "n_harm", "frp_harm", "source"]
full = full.sort_values(["acq_date", "country", "gi", "gj"])
full["acq_date"] = full.acq_date.dt.date
con.register("full_df", full[out_cols])
OUT = (AGG_DIR / "harmonized_daily_grid.parquet").as_posix()
con.execute(f"COPY (SELECT * FROM full_df) TO '{OUT}' (FORMAT PARQUET, COMPRESSION ZSTD)")
print(con.execute(f"SELECT count(*), min(acq_date), max(acq_date), sum(n_harm) FROM read_parquet('{OUT}')").fetchall())

# ---------------------------------------------------------------- report & figures
print("writing report ...")
cv.to_json(AGG_DIR / "validation.json", orient="index", indent=2)
with open(AGG_DIR / "model.json", "w", encoding="utf-8") as fh:
    json.dump({"selected": best, "metric": b_metric, "region": b_region or "continent", "by_month": b_month,
               "alpha": ALPHA, "beta": BETA, "block_deg": BLOCK_CELLS / 10.0, "f_all": P["f_all"],
               "overlap": [OVERLAP_START, OVERLAP_END], "cv_years": years}, fh, indent=2)

overlap["pred"] = predict(overlap, P)
overlap["pred_naive"] = overlap.n * overlap.n_modis.sum() / overlap.n.sum()
mo = overlap.groupby(overlap.acq_date.dt.to_period("M"))[["n_modis", "n", "pred"]].sum()
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(mo.index.to_timestamp(), mo.n_modis, label="MODIS (Terra+Aqua) observed", lw=2)
ax.plot(mo.index.to_timestamp(), mo.n, label="VIIRS NOAA-20 raw", alpha=.6)
ax.plot(mo.index.to_timestamp(), mo.pred, "--", label=f"VIIRS harmonized ({best})", lw=2)
ax.set_ylabel("hotspots / month"); ax.set_title("South America, overlap window"); ax.legend(); fig.tight_layout()
fig.savefig(FIG_DIR / "overlap_monthly.png", dpi=130); plt.close(fig)

fig, axes = plt.subplots(1, 4, figsize=(14, 3.5), sharey=True)
for ax, ctry in zip(axes, ["Brazil", "Argentina", "Bolivia", "Paraguay"]):
    g = overlap[overlap.country == ctry].groupby("month")[["n_modis", "n", "n_1km_f5"]].sum()
    ax.plot(g.index, g.n / g.n_modis, "o-", label="raw VIIRS / MODIS")
    ax.plot(g.index, g.n_1km_f5 / g.n_modis, "s-", label="1 km clusters (FRP>=5) / MODIS")
    ax.axhline(1, color="k", lw=.5); ax.set_title(ctry); ax.set_xlabel("month")
axes[0].set_ylabel("ratio"); axes[0].legend(fontsize=8); fig.tight_layout()
fig.savefig(FIG_DIR / "ratio_by_month.png", dpi=130); plt.close(fig)

allp = cv_preds[best]
cm = allp.groupby(["country", "year", "month", "gi", "gj"])[["n_modis", "pred"]].sum()
cm = cm[(cm.n_modis > 0) | (cm.pred > 0)]
fig, ax = plt.subplots(figsize=(5, 5))
ax.hexbin(cm.pred + 1, cm.n_modis + 1, xscale="log", yscale="log", gridsize=50, bins="log", cmap="viridis")
lim = [1, max(cm.n_modis.max(), cm.pred.max()) + 1]
ax.plot(lim, lim, "r--", lw=1); ax.set_xlabel("harmonized VIIRS + 1 (held-out year)"); ax.set_ylabel("observed MODIS + 1")
ax.set_title("cell x month, leave-one-year-out"); fig.tight_layout()
fig.savefig(FIG_DIR / "cellmonth_scatter.png", dpi=130); plt.close(fig)

# map of block factors
if b_region == "block":
    fig, ax = plt.subplots(figsize=(6, 7))
    bl = tab.groupby("block")[["factor_n", "lat_min", "lon_min"]].mean()
    sc_ = ax.scatter(bl.lon_min + 1, bl.lat_min + 1, c=bl.factor_n, s=60, marker="s", cmap="magma", vmin=0, vmax=0.8)
    plt.colorbar(sc_, label="MODIS hotspots per VIIRS pixel (annual mean of monthly factors)")
    ax.set_title("Harmonization factor by 2-degree block"); ax.set_xlabel("lon"); ax.set_ylabel("lat"); fig.tight_layout()
    fig.savefig(FIG_DIR / "block_factors.png", dpi=130); plt.close(fig)

with open(REPORT_DIR / "validation.md", "w", encoding="utf-8") as fh:
    fh.write("# Harmonization validation\n\n")
    fh.write(f"Overlap window: {OVERLAP_START} to {OVERLAP_END}. Cell size {GRID_DEG} deg. ")
    fh.write(f"Cell-days in overlap: {len(overlap):,}. Years held out one at a time: {years}.\n\n")
    fh.write("All models are linear ratio estimators (MODIS = f x VIIRS metric) with empirical-Bayes shrinkage "
             f"(alpha={ALPHA:g} toward the region factor, beta={BETA:g} toward the continental factor). "
             "Power-law and FRP-covariate alternatives were tested in `pipeline/experiments/powerlaw_test.py` and "
             "performed worse at every aggregation level.\n\n")
    fh.write("## Model comparison (leave-one-year-out)\n\n")
    cols = ["metric", "region", "by_month", "mean_rank", "cellmonth_r2", "cellmonth_r2_log", "ctrymonth_r2", "ctrymonth_nrmse",
            "ctryweek_nrmse", "ctrymonth_bias"]
    fh.write(cv[cols].round(3).to_markdown() + "\n\n")
    fh.write("Selection: lowest mean rank over cell x month R2 (linear and log), country x month NRMSE and country x week NRMSE.\n\n")
    fh.write(f"**Selected model: `{best}`** (metric `{b_metric}`, region `{b_region or 'continent'}`, "
             f"monthly factors: {b_month}). Continental factor: {P['f_all']:.3f} MODIS hotspots per VIIRS pixel.\n\n")
    fh.write("## Equivalent country x month factors (MODIS hotspots per VIIRS pixel)\n\n")
    piv = ctab.pivot(index="country", columns="month", values="factor_n").round(3)
    fh.write(piv.to_markdown() + "\n\n")
    fh.write("Country-level relative error of the selected model (NRMSE at country x month, held-out years):\n\n")
    fh.write(ctab.groupby("country").rel_err.first().round(3).to_markdown() + "\n\n")
    fh.write("## Figures\n\n![](figs/overlap_monthly.png)\n\n![](figs/ratio_by_month.png)\n\n"
             "![](figs/cellmonth_scatter.png)\n\n")
    if b_region == "block":
        fh.write("![](figs/block_factors.png)\n")
print("done")
