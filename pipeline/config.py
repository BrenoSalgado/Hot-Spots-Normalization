"""Shared configuration for the MODIS/VIIRS harmonization pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT                      # zips live in the project root
PARQUET_DIR = ROOT / "data" / "parquet"
AGG_DIR = ROOT / "data" / "agg"
EXPORT_DIR = ROOT / "data" / "export"
REPORT_DIR = ROOT / "reports"

# FIRMS country file names for South America
COUNTRIES = [
    "Argentina", "Bolivia", "Brazil", "Chile", "Colombia", "Ecuador",
    "Falkland_Islands", "French_Guiana", "Guyana", "Paraguay", "Peru",
    "Suriname", "Uruguay", "Venezuela",
]

# Analysis grid (degrees). 0.1 deg ~ 11 km.
GRID_DEG = 0.1
# "MODIS-equivalent" collapse grid for VIIRS (degrees). 0.01 deg ~ 1.1 km.
COLLAPSE_DEG = 0.01

# Overlap window where both sensors are present in the downloaded archive
OVERLAP_START = "2018-04-01"
OVERLAP_END = "2020-12-31"
