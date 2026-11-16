"""Extract South American country CSVs from the FIRMS yearly zips into
Parquet files with a single normalized schema for both sensors.

Output: data/parquet/{sensor}/{year}.parquet
"""
import io
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import COUNTRIES, PARQUET_DIR, RAW_DIR  # noqa: E402

ZIP_RE = re.compile(r"^(modis|viirs-jpss1)_(\d{4})_all_countries\.zip$")

SCHEMA = pa.schema([
    ("sensor", pa.string()),      # MODIS | VIIRS
    ("satellite", pa.string()),   # Terra | Aqua | N20
    ("country", pa.string()),
    ("acq_date", pa.date32()),
    ("acq_time", pa.int16()),     # HHMM UTC
    ("latitude", pa.float32()),
    ("longitude", pa.float32()),
    ("bright", pa.float32()),     # brightness (MODIS ch21/22) | bright_ti4 (VIIRS I4)
    ("bright_bg", pa.float32()),  # bright_t31 | bright_ti5
    ("frp", pa.float32()),        # MW
    ("scan", pa.float32()),
    ("track", pa.float32()),
    ("confidence_raw", pa.string()),
    ("conf_class", pa.string()),  # low | nominal | high (FIRMS classes)
    ("daynight", pa.string()),
    ("type", pa.int8()),
    ("version", pa.string()),
])


def modis_conf_class(c: pd.Series) -> pd.Series:
    c = pd.to_numeric(c, errors="coerce")
    return pd.cut(c, bins=[-1, 29, 79, 100], labels=["low", "nominal", "high"]).astype(str)


def viirs_conf_class(c: pd.Series) -> pd.Series:
    return c.map({"l": "low", "n": "nominal", "h": "high"}).astype(str)


def normalize(df: pd.DataFrame, sensor: str, country: str) -> pd.DataFrame:
    if sensor == "MODIS":
        bright, bg = df["brightness"], df["bright_t31"]
        conf_class = modis_conf_class(df["confidence"])
    else:
        bright, bg = df["bright_ti4"], df["bright_ti5"]
        conf_class = viirs_conf_class(df["confidence"].astype(str))
    out = pd.DataFrame({
        "sensor": sensor,
        "satellite": df["satellite"].astype(str),
        "country": country,
        "acq_date": pd.to_datetime(df["acq_date"]).dt.date,
        "acq_time": pd.to_numeric(df["acq_time"], errors="coerce").fillna(0).astype("int16"),
        "latitude": df["latitude"].astype("float32"),
        "longitude": df["longitude"].astype("float32"),
        "bright": bright.astype("float32"),
        "bright_bg": bg.astype("float32"),
        "frp": pd.to_numeric(df["frp"], errors="coerce").astype("float32"),
        "scan": df["scan"].astype("float32"),
        "track": df["track"].astype("float32"),
        "confidence_raw": df["confidence"].astype(str),
        "conf_class": conf_class,
        "daynight": df["daynight"].astype(str),
        "type": pd.to_numeric(df["type"], errors="coerce").fillna(0).astype("int8"),
        "version": df["version"].astype(str),
    })
    return out


def process_zip(path: Path) -> None:
    m = ZIP_RE.match(path.name)
    if not m:
        return
    prefix, year = m.group(1), m.group(2)
    sensor = "MODIS" if prefix == "modis" else "VIIRS"
    out_dir = PARQUET_DIR / sensor
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{year}.parquet"
    if out_path.exists():
        print(f"skip {out_path.name} (exists)")
        return
    zf = zipfile.ZipFile(path)
    members = {Path(n).name: n for n in zf.namelist()}
    frames = []
    for country in COUNTRIES:
        name = f"{prefix}_{year}_{country}.csv"
        if name not in members:
            continue
        with zf.open(members[name]) as fh:
            df = pd.read_csv(io.TextIOWrapper(fh, encoding="utf-8"), low_memory=False)
        if len(df):
            frames.append(normalize(df, sensor, country))
    if not frames:
        print(f"no SA data in {path.name}")
        return
    full = pd.concat(frames, ignore_index=True)
    table = pa.Table.from_pandas(full, schema=SCHEMA, preserve_index=False)
    pq.write_table(table, out_path, compression="zstd")
    print(f"{path.name}: {len(full):,} rows -> {out_path.relative_to(PARQUET_DIR.parent.parent)}")


def main() -> None:
    zips = sorted(p for p in RAW_DIR.glob("*.zip") if ZIP_RE.match(p.name))
    for z in zips:
        process_zip(z)


if __name__ == "__main__":
    main()
