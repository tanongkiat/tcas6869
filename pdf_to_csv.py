#!/usr/bin/env python3
"""Convert T68*.pdf tables to a consolidated CSV file."""

import csv
import glob
import os
import re
import pdfplumber

WORK_DIR = os.path.dirname(os.path.abspath(__file__))

HEADER = [
    "สถาบัน", "วิทยาเขต", "รหัสหลักสูตร", "คณะ", "หลักสูตร",
    "รายละเอียด", "สาขา/วิชาเอก", "รหัสรับร่วม", "รับ",
    "สมัคร", "ผ่าน", "คะแนนสูงสุด", "คะแนนต่ำสุด",
]

# Normalised header tokens used to detect repeating header rows in the PDF
_HEADER_TOKENS = {"สถาบัน", "วิทยาเขต", "รหัสหลักสูตร", "คณะ", "หลักสูตร",
                  "สมัคร", "ผ่าน"}


def clean(cell):
    """Strip embedded newlines and extra whitespace from a cell value."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell.strip())


def is_header_row(row):
    """Return True if the row looks like a repeated table header."""
    texts = {clean(c) for c in row if c}
    return bool(texts & _HEADER_TOKENS)


def process_pdf(pdf_path):
    """Extract all data rows from a PDF, skipping repeated header rows."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"  {os.path.basename(pdf_path)}: {total} pages")
        for page_num, page in enumerate(pdf.pages, 1):
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if is_header_row(row):
                        continue
                    cleaned = [clean(c) for c in row]
                    # Skip completely empty rows
                    if any(cleaned):
                        rows.append(cleaned)
            if page_num % 50 == 0:
                print(f"    … processed {page_num}/{total} pages")
    return rows


def main():
    pattern = os.path.join(WORK_DIR, "T68*.pdf")
    pdf_files = sorted(glob.glob(pattern))

    if not pdf_files:
        print(f"No PDF files matching 'T68*.pdf' found in:\n  {WORK_DIR}")
        return

    print(f"Found {len(pdf_files)} PDF file(s):")
    for f in pdf_files:
        print(f"  {os.path.basename(f)}")

    all_rows = []
    for pdf_path in pdf_files:
        all_rows.extend(process_pdf(pdf_path))

    output_path = os.path.join(WORK_DIR, "T68_results.csv")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(all_rows)

    print(f"\nDone. {len(all_rows):,} data rows written to:")
    print(f"  {output_path}")


if __name__ == "__main__":
    main()
