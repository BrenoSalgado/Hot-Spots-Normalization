"""FastAPI backend: serves the harmonized burning-activity calendar.

Queries the harmonized daily 0.1-degree grid (Parquet) with DuckDB. Regions can
be a country or an arbitrary bounding box.

Run:  uvicorn main:app --reload --port 8000   (from app/backend)
"""
from __future__ import annotations

import io
import json
from datetime import date
from pathlib import Path
from typing import Optional

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

ROOT = Path(__file__).resolve().parents[2]
GRID = (ROOT / "data" / "agg" / "harmonized_daily_grid.parquet").as_posix()
FACTORS = (ROOT / "data" / "agg" / "factors.parquet").as_posix()
VALIDATION = (ROOT / "data" / "agg" / "validation.json").as_posix()
MODEL = (ROOT / "data" / "agg" / "model.json").as_posix()
FACTORS_CM = (ROOT / "data" / "agg" / "factors_country_month.parquet").as_posix()

app = FastAPI(title="Harmonized Burning Activity Calendar API", version="0.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

con = duckdb.connect(database=":memory:")
con.execute("SET threads TO 4")
# Load once into memory for fast interactive queries (~12M rows).
con.execute(f"CREATE TABLE grid AS SELECT * FROM read_parquet('{GRID}')")
con.execute("CREATE INDEX idx_date ON grid(acq_date)")
con.execute(f"CREATE TABLE factors AS SELECT * FROM read_parquet('{FACTORS}')")
con.execute(f"CREATE TABLE factors_cm AS SELECT * FROM read_parquet('{FACTORS_CM}')")

META = con.execute("SELECT min(acq_date), max(acq_date) FROM grid").fetchone()
COUNTRIES = [r[0] for r in con.execute("SELECT DISTINCT country FROM grid ORDER BY 1").fetchall()]


def region_filter(country: Optional[str], bbox: Optional[str]) -> tuple[str, list]:
    clauses, params = [], []
    if country and country != "all":
        if country not in COUNTRIES:
            raise HTTPException(404, f"unknown country {country}")
        clauses.append("country = ?"); params.append(country)
    if bbox:
        try:
            w, s, e, n = [float(x) for x in bbox.split(",")]
        except ValueError:
            raise HTTPException(400, "bbox must be west,south,east,north")
        clauses.append("cell_lon BETWEEN ? AND ? AND cell_lat BETWEEN ? AND ?")
        params += [w, e, s, n]
    where = " AND ".join(clauses) if clauses else "TRUE"
    return where, params


def rows_to_dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    out = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        for k, v in d.items():
            if isinstance(v, date):
                d[k] = v.isoformat()
        out.append(d)
    return out


@app.get("/api/meta")
def meta():
    with open(VALIDATION, encoding="utf-8") as fh:
        validation = fh.read()
    with open(MODEL, encoding="utf-8") as fh:
        model = json.load(fh)
    return {
        "model": model,
        "date_min": META[0].isoformat(), "date_max": META[1].isoformat(),
        "countries": COUNTRIES, "grid_deg": 0.1,
        "modis_until": "2020-12-31", "viirs_from": "2018-04-01",
        "validation": validation,
    }


@app.get("/api/daily")
def daily(country: Optional[str] = None, bbox: Optional[str] = None,
          start: Optional[str] = None, end: Optional[str] = None):
    """Daily harmonized series for a region."""
    where, params = region_filter(country, bbox)
    start = start or META[0].isoformat(); end = end or META[1].isoformat()
    cur = con.cursor().execute(f"""
        SELECT acq_date, sum(n_harm) AS n_harm, sum(frp_harm) AS frp_harm,
               sum(n_modis) AS n_modis, sum(n_viirs) AS n_viirs, sum(n_viirs_harm) AS n_viirs_harm,
               any_value(source) AS source,
               sum(n_harm * rel_err) AS err_abs
        FROM grid WHERE {where} AND acq_date BETWEEN ? AND ?
        GROUP BY acq_date ORDER BY acq_date
    """, params + [start, end])
    return rows_to_dicts(cur)


@app.get("/api/monthly")
def monthly(country: Optional[str] = None, bbox: Optional[str] = None):
    """Monthly harmonized totals for the whole record + climatology & anomalies."""
    where, params = region_filter(country, bbox)
    cur = con.cursor().execute(f"""
        WITH m AS (
          SELECT year(acq_date) AS year, month(acq_date) AS month,
                 sum(n_harm) AS n_harm, sum(frp_harm) AS frp_harm,
                 sum(n_modis) AS n_modis, sum(n_viirs) AS n_viirs, sum(n_viirs_harm) AS n_viirs_harm,
                 any_value(source) AS source, sum(n_harm * rel_err) AS err_abs
          FROM grid WHERE {where} GROUP BY 1, 2
        ),
        clim AS (
          SELECT month, avg(n_harm) AS clim_mean, stddev_samp(n_harm) AS clim_sd,
                 quantile_cont(n_harm, 0.5) AS clim_median
          FROM m WHERE year BETWEEN 2002 AND 2020 GROUP BY month
        )
        SELECT m.*, clim_mean, clim_sd, clim_median,
               n_harm - clim_mean AS anomaly,
               CASE WHEN clim_sd > 0 THEN (n_harm - clim_mean)/clim_sd END AS zscore
        FROM m JOIN clim USING (month) ORDER BY year, month
    """, params)
    return rows_to_dicts(cur)


@app.get("/api/yearly")
def yearly(country: Optional[str] = None, bbox: Optional[str] = None):
    where, params = region_filter(country, bbox)
    cur = con.cursor().execute(f"""
        SELECT year(acq_date) AS year, sum(n_harm) AS n_harm, sum(frp_harm) AS frp_harm,
               sum(n_modis) AS n_modis, sum(n_viirs) AS n_viirs, sum(n_viirs_harm) AS n_viirs_harm,
               any_value(source) AS source, count(DISTINCT acq_date) AS days_with_fire
        FROM grid WHERE {where} GROUP BY 1 ORDER BY 1
    """, params)
    return rows_to_dicts(cur)


@app.get("/api/grid")
def grid_cells(country: Optional[str] = None, bbox: Optional[str] = None,
               start: Optional[str] = None, end: Optional[str] = None,
               limit: int = Query(60000, le=200000)):
    """Cell totals (0.1 deg) for a period, for the map layer."""
    where, params = region_filter(country, bbox)
    start = start or META[0].isoformat(); end = end or META[1].isoformat()
    cur = con.cursor().execute(f"""
        SELECT cell_lat AS lat, cell_lon AS lon, sum(n_harm) AS n, sum(frp_harm) AS frp
        FROM grid WHERE {where} AND acq_date BETWEEN ? AND ?
        GROUP BY 1, 2 HAVING sum(n_harm) > 0 ORDER BY n DESC LIMIT ?
    """, params + [start, end, limit])
    return rows_to_dicts(cur)


@app.get("/api/calendar")
def calendar(year: int, country: Optional[str] = None, bbox: Optional[str] = None):
    """Day-by-day values for one year (calendar heatmap) with the daily climatology."""
    where, params = region_filter(country, bbox)
    cur = con.cursor().execute(f"""
        WITH d AS (
          SELECT acq_date, sum(n_harm) AS n_harm, sum(frp_harm) AS frp_harm, any_value(source) AS source
          FROM grid WHERE {where} AND year(acq_date) = ? GROUP BY 1
        ),
        clim AS (
          SELECT dayofyear(acq_date) AS doy, sum(n_harm) / 19.0 AS clim_mean
          FROM grid WHERE {where} AND year(acq_date) BETWEEN 2002 AND 2020 GROUP BY 1
        )
        SELECT d.acq_date, d.n_harm, d.frp_harm, d.source, coalesce(clim.clim_mean, 0) AS clim_mean
        FROM d LEFT JOIN clim ON clim.doy = dayofyear(d.acq_date) ORDER BY d.acq_date
    """, params + [year] + params)
    return rows_to_dicts(cur)


@app.get("/api/factors")
def factors(country: Optional[str] = None):
    where = "country = ?" if country else "TRUE"
    params = [country] if country else []
    cur = con.cursor().execute(f"SELECT * FROM factors_cm WHERE {where} ORDER BY country, month", params)
    return rows_to_dicts(cur)


@app.get("/api/export.csv")
def export_csv(country: Optional[str] = None, bbox: Optional[str] = None,
               start: Optional[str] = None, end: Optional[str] = None,
               level: str = Query("daily", pattern="^(daily|monthly|cells)$")):
    where, params = region_filter(country, bbox)
    start = start or META[0].isoformat(); end = end or META[1].isoformat()
    if level == "daily":
        sql = f"""SELECT acq_date, sum(n_harm) AS hotspots_harmonized, sum(frp_harm) AS frp_harmonized_mw,
                         sum(n_modis) AS modis_raw, sum(n_viirs) AS viirs_raw, sum(n_viirs_harm) AS viirs_harmonized,
                         any_value(source) AS source
                  FROM grid WHERE {where} AND acq_date BETWEEN ? AND ? GROUP BY 1 ORDER BY 1"""
    elif level == "monthly":
        sql = f"""SELECT year(acq_date) AS year, month(acq_date) AS month, sum(n_harm) AS hotspots_harmonized,
                         sum(frp_harm) AS frp_harmonized_mw, sum(n_modis) AS modis_raw, sum(n_viirs) AS viirs_raw,
                         sum(n_viirs_harm) AS viirs_harmonized, any_value(source) AS source
                  FROM grid WHERE {where} AND acq_date BETWEEN ? AND ? GROUP BY 1, 2 ORDER BY 1, 2"""
    else:
        sql = f"""SELECT cell_lat, cell_lon, sum(n_harm) AS hotspots_harmonized, sum(frp_harm) AS frp_harmonized_mw
                  FROM grid WHERE {where} AND acq_date BETWEEN ? AND ? GROUP BY 1, 2 ORDER BY 3 DESC"""
    df = con.cursor().execute(sql, params + [start, end]).df()
    buf = io.StringIO(); df.to_csv(buf, index=False); buf.seek(0)
    name = f"burning_calendar_{country or 'bbox'}_{level}_{start}_{end}.csv"
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename={name}"})
