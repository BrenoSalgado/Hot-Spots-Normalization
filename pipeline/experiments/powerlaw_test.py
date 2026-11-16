import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AGG_DIR, OVERLAP_START, OVERLAP_END
GRID = (AGG_DIR / "daily_grid.parquet").as_posix()
con = duckdb.connect()
ov = con.execute(f"""
WITH m AS (SELECT country, acq_date, gi, gj, sum(n) n_modis, sum(frp_sum) frp_modis FROM read_parquet('{GRID}') WHERE sensor='MODIS' GROUP BY ALL),
     v AS (SELECT country, acq_date, gi, gj, sum(n) n, sum(n_1km) n_1km, sum(n_1km_f5) n_1km_f5, sum(frp_sum) frp_viirs, sum(n_day) n_day FROM read_parquet('{GRID}') WHERE sensor='VIIRS' GROUP BY ALL)
SELECT coalesce(m.country,v.country) country, coalesce(m.acq_date,v.acq_date) acq_date, coalesce(m.gi,v.gi) gi, coalesce(m.gj,v.gj) gj,
       coalesce(n_modis,0) n_modis, coalesce(frp_modis,0) frp_modis, coalesce(n,0) n, coalesce(n_1km,0) n_1km, coalesce(n_1km_f5,0) n_1km_f5, coalesce(frp_viirs,0) frp_viirs, coalesce(n_day,0) n_day
FROM m FULL OUTER JOIN v USING (country, acq_date, gi, gj)
WHERE coalesce(m.acq_date,v.acq_date) BETWEEN '{OVERLAP_START}' AND '{OVERLAP_END}'
""").df()
ov["acq_date"] = pd.to_datetime(ov.acq_date); ov["year"] = ov.acq_date.dt.year; ov["month"] = ov.acq_date.dt.month
print(len(ov))

def sc(o, p):
    o = np.asarray(o, float); p = np.asarray(p, float)
    r2 = 1 - ((o-p)**2).sum()/((o-o.mean())**2).sum()
    lo, lp = np.log1p(o), np.log1p(p); r2l = 1 - ((lo-lp)**2).sum()/((lo-lo.mean())**2).sum()
    return round(r2,3), round(r2l,3), round(p.sum()/o.sum()-1,3)

def evaluate(name, fit, predict):
    preds = []
    for y in sorted(ov.year.unique()):
        tr, te = ov[ov.year != y], ov[ov.year == y].copy()
        te["pred"] = predict(te, fit(tr)); preds.append(te)
    a = pd.concat(preds)
    cd = a[(a.n_modis>0)|(a.pred>0)]
    cm = a.groupby(["country","year","month","gi","gj"])[["n_modis","pred"]].sum()
    ct = a.groupby(["country","year","month"])[["n_modis","pred"]].sum()
    print(f"{name:28s} cellday r2/r2log/bias={sc(cd.n_modis,cd.pred)}  cellmonth={sc(cm.n_modis,cm.pred)}  ctrymonth={sc(ct.n_modis,ct.pred)}")

# 1. linear global on n
evaluate("linear global n", lambda tr: tr.n_modis.sum()/tr.n.sum(), lambda te,f: te.n*f)
# 2. power law global: n_modis = a * n^b, fitted on cell-days with n>0 via log-log regression with +0 (only n>0, modis>=0 -> use log(m+1))
def fit_pl(tr, col="n"):
    d = tr[tr[col]>0]
    x = np.log(d[col]); y = np.log1p(d.n_modis)
    b, a = np.polyfit(x, y, 1)
    # bias correction so totals match
    pred = np.expm1(a + b*x).clip(0)
    return (a, b, d.n_modis.sum()/pred.sum())
def pred_pl(te, p, col="n"):
    a,b,k = p; x = te[col].to_numpy(float)
    out = np.where(x>0, np.expm1(a + b*np.log(np.where(x>0,x,1)))*k, 0.0)
    return out.clip(0)
evaluate("powerlaw global n", fit_pl, pred_pl)
evaluate("powerlaw global n_1km", lambda tr: fit_pl(tr,"n_1km"), lambda te,p: pred_pl(te,p,"n_1km"))
# 3. power law per country
def fit_pl_c(tr, col="n"):
    g = fit_pl(tr, col); out = {}
    for c, d in tr.groupby("country"):
        out[c] = fit_pl(d, col) if (d[col]>0).sum() > 2000 else g
    out["_g"] = g; return out
def pred_pl_c(te, p, col="n"):
    res = np.zeros(len(te))
    for c, idx in te.groupby("country").indices.items():
        res[idx] = pred_pl(te.iloc[idx], p.get(c, p["_g"]), col)
    return res
evaluate("powerlaw per country n", fit_pl_c, pred_pl_c)
# 4. linear with frp: n_modis = a*n + c*frp (NNLS-ish via lstsq clipped)
def fit_lin2(tr):
    X = np.c_[tr.n, tr.frp_viirs]; coef, *_ = np.linalg.lstsq(X, tr.n_modis.to_numpy(float), rcond=None); return coef
evaluate("linear n + frp", fit_lin2, lambda te,c: (te.n*c[0] + te.frp_viirs*c[1]).clip(0))
# 5. power law on n with frp-per-pixel covariate: log1p(M) = a + b log n + c log(1+frp/n)
def fit_pl3(tr):
    d = tr[tr.n>0]; X = np.c_[np.ones(len(d)), np.log(d.n), np.log1p(d.frp_viirs/d.n), d.n_day/d.n]
    coef, *_ = np.linalg.lstsq(X, np.log1p(d.n_modis).to_numpy(), rcond=None)
    pred = np.expm1(X@coef).clip(0); return (coef, d.n_modis.sum()/pred.sum())
def pred_pl3(te, p):
    coef, k = p; n = te.n.to_numpy(float); ok = n>0; nn = np.where(ok, n, 1)
    X = np.c_[np.ones(len(te)), np.log(nn), np.log1p(te.frp_viirs.to_numpy()/nn), te.n_day.to_numpy()/nn]
    return np.where(ok, np.expm1(X@coef).clip(0)*k, 0)
evaluate("powerlaw n + frp/px + dayfrac", fit_pl3, pred_pl3)
def fit_pl3_c(tr):
    g = fit_pl3(tr); out = {"_g": g}
    for c, d in tr.groupby("country"):
        if (d.n>0).sum() > 2000: out[c] = fit_pl3(d)
    return out
def pred_pl3_c(te, p):
    res = np.zeros(len(te))
    for c, idx in te.groupby("country").indices.items():
        res[idx] = pred_pl3(te.iloc[idx], p.get(c, p["_g"]))
    return res
evaluate("powerlaw+cov per country", fit_pl3_c, pred_pl3_c)
