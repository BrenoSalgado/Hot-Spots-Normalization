import sys
from pathlib import Path
import duckdb, numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AGG_DIR, OVERLAP_START, OVERLAP_END
GRID = (AGG_DIR / "daily_grid.parquet").as_posix()
con = duckdb.connect()
ov = con.execute(f"""
WITH m AS (SELECT country, acq_date, gi, gj, sum(n) n_modis FROM read_parquet('{GRID}') WHERE sensor='MODIS' GROUP BY ALL),
     v AS (SELECT country, acq_date, gi, gj, sum(n) n, sum(n_1km) n_1km, sum(n_1km_f5) n_1km_f5 FROM read_parquet('{GRID}') WHERE sensor='VIIRS' GROUP BY ALL)
SELECT coalesce(m.country,v.country) country, coalesce(m.acq_date,v.acq_date) acq_date, coalesce(m.gi,v.gi) gi, coalesce(m.gj,v.gj) gj,
       coalesce(n_modis,0) n_modis, coalesce(n,0) n, coalesce(n_1km,0) n_1km, coalesce(n_1km_f5,0) n_1km_f5
FROM m FULL OUTER JOIN v USING (country, acq_date, gi, gj)
WHERE coalesce(m.acq_date,v.acq_date) BETWEEN '{OVERLAP_START}' AND '{OVERLAP_END}'
""").df()
ov["acq_date"] = pd.to_datetime(ov.acq_date); ov["year"] = ov.acq_date.dt.year; ov["month"] = ov.acq_date.dt.month
# region: use a coarse 2-degree block as alternative to country
ov["block"] = (ov.gi // 20).astype(str) + "_" + (ov.gj // 20).astype(str)

def sc(o, p):
    o = np.asarray(o, float); p = np.asarray(p, float)
    r2 = 1 - ((o-p)**2).sum()/((o-o.mean())**2).sum()
    lo, lp = np.log1p(o), np.log1p(p); r2l = 1 - ((lo-lp)**2).sum()/((lo-lo.mean())**2).sum()
    nr = np.sqrt(((o-p)**2).mean())/o.mean()
    return round(r2,3), round(r2l,3), round(nr,3)

def fit(tr, metric, region, by_month, alpha, beta):
    f_all = tr.n_modis.sum()/tr[metric].sum()
    out = {"f_all": f_all}
    if region is None and not by_month: return out
    keys = ([region] if region else []) + (["month"] if by_month else [])
    if region:
        c = tr.groupby(region)[["n_modis", metric]].sum(); c["f"] = (c.n_modis + beta*f_all)/(c[metric] + beta)
        out["f_region"] = c.f
    if by_month:
        g = tr.groupby(keys)[["n_modis", metric]].sum().reset_index()
        prior = g[region].map(out["f_region"]) if region else f_all
        g["f"] = (g.n_modis + alpha*prior)/(g[metric] + alpha)
        out["f_km"] = g.set_index(keys).f
    out["keys"] = keys; return out

def predict(te, p, metric, region, by_month):
    if region is None and not by_month: return te[metric]*p["f_all"]
    if by_month:
        idx = pd.MultiIndex.from_frame(te[p["keys"]]) if len(p["keys"])>1 else te[p["keys"][0]]
        f = p["f_km"].reindex(idx).to_numpy()
        if region: f = np.where(np.isnan(f), te[region].map(p["f_region"]).to_numpy(), f)
    else:
        f = te[region].map(p["f_region"]).to_numpy()
    f = np.where(np.isnan(f), p["f_all"], f)
    return te[metric].to_numpy()*f

rows=[]
for metric in ["n","n_1km_f5"]:
  for region in [None,"country","block"]:
    for by_month in [False, True]:
      for alpha, beta in [(300,2000),(3000,20000),(30000,200000)]:
        if region is None and not by_month and alpha!=300: continue
        if not by_month and alpha!=300 and region is None: continue
        preds=[]
        for y in sorted(ov.year.unique()):
            tr, te = ov[ov.year!=y], ov[ov.year==y].copy()
            te["pred"] = predict(te, fit(tr,metric,region,by_month,alpha,beta), metric, region, by_month); preds.append(te)
        a = pd.concat(preds)
        cm = a.groupby(["country","year","month","gi","gj"])[["n_modis","pred"]].sum()
        ct = a.groupby(["country","year","month"])[["n_modis","pred"]].sum()
        cw = a.assign(wk=a.acq_date.dt.to_period("W")).groupby(["country","wk"])[["n_modis","pred"]].sum()
        rows.append(dict(metric=metric, region=region, by_month=by_month, alpha=alpha, cellmonth=sc(cm.n_modis,cm.pred), ctrymonth=sc(ct.n_modis,ct.pred), ctryweek=sc(cw.n_modis,cw.pred)))
print(pd.DataFrame(rows).to_string())
