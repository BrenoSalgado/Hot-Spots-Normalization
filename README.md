# Harmonized Burning Activity Calendar

https://youtu.be/r27FLiKzIDo?si=hsf79szndPlhci-f

NASA Space Apps 2026 — challenge *Harmonization of MODIS and VIIRS hotspots* (CONAE).

One consistent hotspot time series for South America, 2002–2025, built from NASA FIRMS
country archives: MODIS (Terra + Aqua, 2002–2020) and VIIRS NOAA-20 / JPSS-1 (2018–2025).
A web app turns it into a burning-activity calendar: pick a country or draw any area, pick a
year, see trends, seasonal cycle, anomalies and where it burned, and download the analytics.

## Layout

```
pipeline/            data pipeline (Python)
  01_extract.py      FIRMS zips -> normalized Parquet (data/parquet/{MODIS,VIIRS}/{year}.parquet)
  02_aggregate.py    daily 0.1° grid per sensor; VIIRS collapsed into 1 km clusters (data/agg/daily_grid.parquet)
  03_harmonize.py    factor fitting, cross-validation, harmonized grid, report
  experiments/       alternative models that were tested and rejected (power law, FRP covariates)
app/backend/main.py  FastAPI + DuckDB API over the harmonized grid
app/frontend/        React + Leaflet + d3 web app
reports/validation.md  model comparison, factors, figures
data/agg/            harmonized_daily_grid.parquet, factors.parquet, validation.json, model.json
```

## Method

1. **Common grid.** Both sensors are aggregated to 0.1° cells per day (count, FRP sum, day/night,
   confidence class). VIIRS 375 m pixels are also collapsed into 1 km clusters per overpass so a
   "MODIS-like" count is available as a candidate metric.
2. **Calibration in the overlap window** (2018-04-01 → 2020-12-31). The conversion is a linear
   ratio estimator, *MODIS = f × VIIRS metric*, fitted per 2° block and month of year, with
   empirical-Bayes shrinkage toward the block factor and then toward the continental factor
   (0.257 MODIS hotspots per VIIRS pixel) where data are sparse.
3. **Model selection by leave-one-year-out cross-validation.** Nine linear variants
   (continental, country, 2° block; with/without monthly factors; raw vs 1 km-collapsed metrics)
   plus power-law and FRP-covariate alternatives were compared. The selected model
   (`block_month_n`) reaches R² 0.80 at cell × month, R² 0.99 and NRMSE 0.26 at country × month,
   with no bias. Notably, the 1 km collapse does **not** improve on raw pixel counts, and a single
   continental factor is only slightly worse — the regional/seasonal factors mainly reduce
   country-level error.
4. **Harmonized series.** MODIS observations are kept as-is through 2020; from 2021 on, VIIRS is
   converted to MODIS-equivalent units. Each value carries the cross-validated relative error of
   its country, shown as uncertainty in the app. In 2018–2020 both sensors are available, so the
   app also shows harmonized VIIRS against observed MODIS as a visible validation.

Why MODIS-equivalent and not the other way round: the 19-year record is MODIS, and a detection
that MODIS never made cannot be invented; scaling VIIRS down preserves the historical calendar
and keeps VIIRS detail available in the raw columns.

Known limits: only ~2.75 years of overlap in the downloaded archive (adding Suomi-NPP VIIRS from
2012 and MODIS 2021–2025 would lengthen it to 8–13 years); factors are per 2° block, so very local
changes in fire size distribution are not captured; dates are UTC.

## Run

Python 3.12, Node 22.

```bash
pip install -r requirements.txt
```

```bash
python -I pipeline/01_extract.py
```

```bash
python -I pipeline/02_aggregate.py
```

```bash
python -I pipeline/03_harmonize.py
```

Backend (port 8000):

```bash
python -m uvicorn main:app --port 8000 --app-dir app/backend
```

Frontend (port 5173, proxies `/api` to the backend):

```bash
npm --prefix app/frontend install
```

```bash
npm --prefix app/frontend run dev
```

## API

| endpoint | purpose |
|---|---|
| `GET /api/meta` | date range, countries, selected model, validation table |
| `GET /api/monthly?country=Brazil` or `?bbox=w,s,e,n` | monthly series with climatology, anomaly, z-score |
| `GET /api/yearly?...` | annual totals and source sensor |
| `GET /api/calendar?year=2024&...` | day-by-day values with daily climatology |
| `GET /api/grid?start=&end=&...` | 0.1° cell totals for the map |
| `GET /api/export.csv?level=daily|monthly|cells&...` | CSV download |
| `GET /api/factors?country=Argentina` | country × month factors and relative error |

## Data

FIRMS country yearly archives (`modis_YYYY_all_countries.zip`, `viirs-jpss1_YYYY_all_countries.zip`)
placed in the project root. Fourteen South American countries are processed (see `pipeline/config.py`).
