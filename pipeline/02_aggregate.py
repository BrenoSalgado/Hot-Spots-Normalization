"""Aggregate normalized detections into a daily 0.1 deg grid per sensor and
satellite. For VIIRS, also compute "MODIS-equivalent" metrics by collapsing
375 m detections into ~1 km clusters (0.01 deg cells) per overpass.

Cells are indexed with integers (floor(lat*10), floor(lon*10)) so joins are
exact; the cell centre in degrees is derived at the end.

Output: data/agg/daily_grid.parquet
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import AGG_DIR, PARQUET_DIR  # noqa: E402

AGG_DIR.mkdir(parents=True, exist_ok=True)
OUT = AGG_DIR / "daily_grid.parquet"

con = duckdb.connect()
con.execute("SET threads TO 8")

modis_glob = (PARQUET_DIR / "MODIS" / "*.parquet").as_posix()
viirs_glob = (PARQUET_DIR / "VIIRS" / "*.parquet").as_posix()

# 0.1 deg cell index (integers) and 0.01 deg collapse index (integers)
IDX10 = "CAST(floor(latitude::DOUBLE * 10) AS INTEGER) AS gi, CAST(floor(longitude::DOUBLE * 10) AS INTEGER) AS gj"
IDX100 = "CAST(floor(latitude::DOUBLE * 100) AS INTEGER) AS ci, CAST(floor(longitude::DOUBLE * 100) AS INTEGER) AS cj"

print("aggregating MODIS ...")
con.execute(f"""
CREATE TABLE modis_grid AS
SELECT sensor, satellite, country, acq_date, gi, gj,
       count(*)                                            AS n,
       sum(CASE WHEN conf_class='high' THEN 1 ELSE 0 END)  AS n_high,
       sum(CASE WHEN conf_class<>'low' THEN 1 ELSE 0 END)  AS n_nominal_plus,
       sum(CASE WHEN daynight='D' THEN 1 ELSE 0 END)       AS n_day,
       sum(CASE WHEN daynight='N' THEN 1 ELSE 0 END)       AS n_night,
       sum(CASE WHEN type=0 THEN 1 ELSE 0 END)             AS n_veg,
       sum(frp)                                            AS frp_sum,
       max(frp)                                            AS frp_max,
       NULL::BIGINT AS n_1km, NULL::BIGINT AS n_1km_f2, NULL::BIGINT AS n_1km_f5,
       NULL::BIGINT AS n_1km_f10, NULL::BIGINT AS n_1km_f20
FROM (SELECT *, {IDX10} FROM read_parquet('{modis_glob}'))
GROUP BY ALL
""")

print("collapsing VIIRS to 1 km clusters ...")
con.execute(f"""
CREATE TABLE viirs_clusters AS
SELECT sensor, satellite, country, acq_date, daynight, ci, cj,
       count(*) AS n_px,
       sum(frp) AS frp_sum
FROM (SELECT *, {IDX100} FROM read_parquet('{viirs_glob}'))
GROUP BY ALL
""")

print("aggregating VIIRS ...")
con.execute(f"""
CREATE TABLE viirs_grid AS
WITH px AS (
  SELECT sensor, satellite, country, acq_date, gi, gj,
         count(*) AS n,
         sum(CASE WHEN conf_class='high' THEN 1 ELSE 0 END)  AS n_high,
         sum(CASE WHEN conf_class<>'low' THEN 1 ELSE 0 END)  AS n_nominal_plus,
         sum(CASE WHEN daynight='D' THEN 1 ELSE 0 END)       AS n_day,
         sum(CASE WHEN daynight='N' THEN 1 ELSE 0 END)       AS n_night,
         sum(CASE WHEN type=0 THEN 1 ELSE 0 END)             AS n_veg,
         sum(frp) AS frp_sum, max(frp) AS frp_max
  FROM (SELECT *, {IDX10} FROM read_parquet('{viirs_glob}'))
  GROUP BY ALL
),
cl AS (
  SELECT sensor, satellite, country, acq_date,
         CAST(floor(ci / 10.0) AS INTEGER) AS gi, CAST(floor(cj / 10.0) AS INTEGER) AS gj,
         count(*) AS n_1km,
         sum(CASE WHEN frp_sum >= 2  THEN 1 ELSE 0 END) AS n_1km_f2,
         sum(CASE WHEN frp_sum >= 5  THEN 1 ELSE 0 END) AS n_1km_f5,
         sum(CASE WHEN frp_sum >= 10 THEN 1 ELSE 0 END) AS n_1km_f10,
         sum(CASE WHEN frp_sum >= 20 THEN 1 ELSE 0 END) AS n_1km_f20
  FROM viirs_clusters
  GROUP BY ALL
)
SELECT px.sensor, px.satellite, px.country, px.acq_date, px.gi, px.gj,
       px.n, px.n_high, px.n_nominal_plus, px.n_day, px.n_night, px.n_veg,
       px.frp_sum, px.frp_max,
       cl.n_1km, cl.n_1km_f2, cl.n_1km_f5, cl.n_1km_f10, cl.n_1km_f20
FROM px JOIN cl USING (sensor, satellite, country, acq_date, gi, gj)
""")

con.execute(f"""
COPY (
  SELECT sensor, satellite, country, acq_date, gi, gj,
         gi / 10.0 + 0.05 AS cell_lat, gj / 10.0 + 0.05 AS cell_lon,
         n, n_high, n_nominal_plus, n_day, n_night, n_veg, frp_sum, frp_max,
         n_1km, n_1km_f2, n_1km_f5, n_1km_f10, n_1km_f20
  FROM (SELECT * FROM modis_grid UNION ALL SELECT * FROM viirs_grid)
  ORDER BY sensor, acq_date, gi, gj
) TO '{OUT.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
""")
n = con.execute(f"SELECT sensor, count(*), sum(n), sum(n_1km) FROM read_parquet('{OUT.as_posix()}') GROUP BY 1").fetchall()
print("done:", n)
