#!/usr/bin/env python3
"""Merge T68_results.csv (year=2568) and TCAS69_results.csv (year=2569)
into a single SQLite database: tcas_results.db, table: tcas_results.

Unified schema (16 columns):
  year, สถาบัน, วิทยาเขต, รหัสหลักสูตร, รหัสสาขา*, รหัสโครงการ*,
  คณะ, หลักสูตร, รายละเอียด, สาขา/วิชาเอก, รหัสรับร่วม,
  รับ, สมัคร, ผ่าน, คะแนนสูงสุด, คะแนนต่ำสุด
  (* NULL for T68 rows)
"""

import csv
import os
import re
import sqlite3

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(WORK_DIR, "tcas_results.db")
TABLE    = "tcas_results"

# CSV sources: (filename, year)
SOURCES = [
    ("T68_results.csv",    2568),
    ("TCAS69_results.csv", 2569),
]

# Unified column order for the DB table (year always first)
UNIFIED_COLS = [
    "year",
    "สถาบัน",
    "วิทยาเขต",
    "รหัสหลักสูตร",
    "รหัสสาขา",       # TCAS69 only  → NULL for T68
    "รหัสโครงการ",    # TCAS69 only  → NULL for T68
    "คณะ",
    "หลักสูตร",
    "รายละเอียด",
    "สาขา/วิชาเอก",
    "รหัสรับร่วม",
    "รับ",
    "สมัคร",
    "ผ่าน",
    "คะแนนสูงสุด",
    "คะแนนต่ำสุด",
]

# Columns stored as INTEGER / REAL instead of TEXT
INT_COLS   = {"รับ", "สมัคร", "ผ่าน"}
FLOAT_COLS = {"คะแนนสูงสุด", "คะแนนต่ำสุด"}


def normalize_colname(name):
    """Remove internal whitespace so 'รหัส โครงการ' → 'รหัสโครงการ'."""
    return re.sub(r"\s+", "", name.strip())


def coerce(value, col):
    """Convert a raw string cell to the appropriate Python type."""
    v = value.strip()
    if not v:
        return None
    if col in INT_COLS:
        try:
            return int(v.replace(",", ""))
        except ValueError:
            return None
    if col in FLOAT_COLS:
        try:
            return float(v)
        except ValueError:
            return None
    return v


def load_csv(path):
    """Return (norm_headers, list_of_row_lists)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        raw_headers = next(reader)
        headers = [normalize_colname(h) for h in raw_headers]
        rows = list(reader)
    return headers, rows


def build_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    # ── CREATE TABLE ──────────────────────────────────────────────────────────
    def col_type(c):
        if c == "year":      return "INTEGER"
        if c in INT_COLS:    return "INTEGER"
        if c in FLOAT_COLS:  return "REAL"
        return "TEXT"

    col_defs = ", ".join(f'"{c}" {col_type(c)}' for c in UNIFIED_COLS)
    cur.execute(f'CREATE TABLE "{TABLE}" ({col_defs})')

    # ── INSERT ────────────────────────────────────────────────────────────────
    placeholders = ", ".join("?" for _ in UNIFIED_COLS)
    insert_sql   = f'INSERT INTO "{TABLE}" VALUES ({placeholders})'

    for filename, year in SOURCES:
        path = os.path.join(WORK_DIR, filename)
        if not os.path.exists(path):
            print(f"  SKIP (not found): {filename}")
            continue

        headers, rows = load_csv(path)
        col_idx = {h: i for i, h in enumerate(headers)}

        batch = []
        for raw_row in rows:
            record = []
            for col in UNIFIED_COLS:
                if col == "year":
                    record.append(year)
                elif col in col_idx:
                    raw = raw_row[col_idx[col]] if col_idx[col] < len(raw_row) else ""
                    record.append(coerce(raw, col))
                else:
                    record.append(None)   # column absent in this CSV
            batch.append(record)

        cur.executemany(insert_sql, batch)
        print(f"  {filename} (year={year}): {len(batch):,} rows inserted")

    # ── INDEXES ───────────────────────────────────────────────────────────────
    cur.execute(f'CREATE INDEX idx_year      ON "{TABLE}" (year)')
    cur.execute(f'CREATE INDEX idx_inst      ON "{TABLE}" ("สถาบัน")')
    cur.execute(f'CREATE INDEX idx_code      ON "{TABLE}" ("รหัสหลักสูตร")')

    conn.commit()

    # ── SUMMARY ──────────────────────────────────────────────────────────────
    cur.execute(f'SELECT year, COUNT(*) FROM "{TABLE}" GROUP BY year ORDER BY year')
    print(f"\nRows per year in '{TABLE}':")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]:,} rows")

    cur.execute(f'SELECT COUNT(*) FROM "{TABLE}"')
    total = cur.fetchone()[0]
    print(f"  Total: {total:,} rows")

    conn.close()
    print(f"\nSaved → {os.path.basename(DB_PATH)}")


if __name__ == "__main__":
    build_db()
