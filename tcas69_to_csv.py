#!/usr/bin/env python3
"""Convert TCAS69*.pdf tables to TCAS69_results.csv.

Applies the same Thai-text artifact fixes used for T68:
  Phase 1 – displaced vowel/tone marks (regex)
  Phase 2 – PDF line-break spurious spaces (regex + lookup table)
"""

import csv
import glob
import os
import re

import pdfplumber

WORK_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Thai-fix rules (same logic as fix_thai_text.py) ───────────────────────────
CONS = r"[ก-ฮ]"
MARK = r"[\u0E31\u0E34-\u0E39\u0E47-\u0E4E]"
LEAD = r"[เแโไใ]"

_P1_RULES = [
    # A: C1+C2+mark+space → C1+mark+C2  (displaced mark with trailing space)
    (re.compile(f"({CONS})({CONS})({MARK}) "), r"\1\3\2"),
    # B: ฑ+C+mark → ฑ+mark+C  (ฑ never forms clusters; mark always belongs to ฑ)
    (re.compile(r"ฑ([ก-ฮ])([\u0E31\u0E34-\u0E39\u0E47-\u0E4E])"), r"ฑ\2\1"),
    # C: C+space+mark → C+mark
    (re.compile(f"({CONS}) ({MARK})"),          r"\1\2"),
    # D: C+space+า → C+ำ  (sara-am reconstruction)
    (re.compile(f"({CONS}) า"),                 r"\1ำ"),
    # F: C+leading_vowel+mark → C+mark+leading_vowel
    (re.compile(f"({CONS})({LEAD})({MARK})"),   r"\1\3\2"),
]

_RULE_G = re.compile(r"แ ([ก-ฮเโไใ])")

# sara-am mis-encoded as mai-ek + sara-a  (seen in TCAS69 headers)
_RULE_AM = re.compile(r"([\u0E48-\u0E4B]) า")   # tone mark + space-less sara-a

_COMPOUND_FIXES = [
    ("ราช มงคล",              "ราชมงคล"),
    ("พระ จอมเกล้า",          "พระจอมเกล้า"),
    ("เกล้า เจ้าคุณ",         "เกล้าเจ้าคุณ"),
    ("เกล้า เจ้าคุณทหารลาดกระบัง", "เกล้าเจ้าคุณทหารลาดกระบัง"),
    ("ราชภัฏ อุบลราชธานี",   "ราชภัฏอุบลราชธานี"),
    ("ราชภัฏ นครราชสีมา",    "ราชภัฏนครราชสีมา"),
    ("ราชภัฏบ้านสมเด็จ เจ้าพระยา", "ราชภัฏบ้านสมเด็จเจ้าพระยา"),
    ("สมเด็จ เจ้าพระยา",     "สมเด็จเจ้าพระยา"),
    ("ราชภัฏพิบูล สงคราม",   "ราชภัฏพิบูลสงคราม"),
    ("พิบูล สงคราม",          "พิบูลสงคราม"),
    ("ราชภัฏวไลย อลงกรณ์",  "ราชภัฏวไลยอลงกรณ์"),
    ("วไลย อลงกรณ์",         "วไลยอลงกรณ์"),
    ("มหามกุฏราช วิทยาลัย",  "มหามกุฏราชวิทยาลัย"),
    ("มกุฏราช วิทยาลัย",     "มกุฏราชวิทยาลัย"),
    ("มหาจุฬาลงกรณ ราชวิทยาลัย", "มหาจุฬาลงกรณราชวิทยาลัย"),
    ("ลงกรณ ราชวิทยาลัย",   "ลงกรณราชวิทยาลัย"),
    ("นราธิวาสราช นครินทร์", "นราธิวาสราชนครินทร์"),
    ("หัวเฉียวเฉลิมพระ เกียรติ", "หัวเฉียวเฉลิมพระเกียรติ"),
    ("เฉลิมพระ เกียรติ",     "เฉลิมพระเกียรติ"),
    ("แม่โจ้-แพร่เฉลิม พระเกียรติ", "แม่โจ้-แพร่เฉลิมพระเกียรติ"),
    ("วิทยาเขตจักร พงษภูวนารถ", "วิทยาเขตจักรพงษภูวนารถ"),
    ("จักร พงษภูวนารถ",      "จักรพงษภูวนารถ"),
    ("นานาชาติสิ รินธร",     "นานาชาติสิรินธร"),
    ("บุคคลเข้า ศึกษา",      "บุคคลเข้าศึกษา"),
    ("เข้า ศึกษา",            "เข้าศึกษา"),
    ("รูปแบบ ที่",            "รูปแบบที่"),
    ("รูปแบบ ใช้",            "รูปแบบใช้"),
    ("และ เทคโนโลยี",         "และเทคโนโลยี"),
    ("และ สังคมศาสตร์",       "และสังคมศาสตร์"),
    ("และ วิทยาศาสตร์",       "และวิทยาศาสตร์"),
    ("และ วิศวกรรมศาสตร์",    "และวิศวกรรมศาสตร์"),
    ("และ นวัตกรรม",          "และนวัตกรรม"),
    ("และ ทรัพยากร",          "และทรัพยากร"),
    ("และ การสื่อสาร",        "และการสื่อสาร"),
    ("และ การบัญชี",          "และการบัญชี"),
    ("และ การออกแบบ",         "และการออกแบบ"),
    ("และ บริหารธุรกิจ",      "และบริหารธุรกิจ"),
    ("และ นิติศาสตร์",        "และนิติศาสตร์"),
    ("แ ห่ง ",                "แห่ง "),
    ("ผลิตบัณฑิตเพื่อ พัฒนา", "ผลิตบัณฑิตเพื่อพัฒนา"),
    ("ใน ส่วนกลาง",           "ในส่วนกลาง"),
]


def fix_thai(text):
    """Apply Phase 1 + Phase 2 fix rules iteratively until stable."""
    if not text:
        return text
    prev = None
    while prev != text:
        prev = text
        for pattern, repl in _P1_RULES:
            text = pattern.sub(repl, text)
        text = _RULE_G.sub(r"แ\1", text)
        text = _RULE_AM.sub(r"\1ำ", text)
        for broken, correct in _COMPOUND_FIXES:
            if broken in text:
                text = text.replace(broken, correct)
    return text


def clean(cell):
    """Strip embedded newlines and extra whitespace."""
    if cell is None:
        return ""
    return re.sub(r"\s+", " ", cell.strip())


# Tokens that identify a header row
_HEADER_TOKENS = {"สถาบัน", "วิทยาเขต", "รหัสหลักสูตร", "คณะ", "หลักสูตร",
                  "สมัคร", "ผ่าน"}


def is_header_row(row):
    texts = {clean(c) for c in row if c}
    return bool(texts & _HEADER_TOKENS)


def detect_header(pdf_path):
    """Return the cleaned header list from the first table in the PDF."""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if is_header_row(row):
                        # clean + fix each header cell
                        hdr = [fix_thai(clean(c)) for c in row]
                        # normalise คะแนนต่่าสุด → คะแนนต่ำสุด
                        hdr = [h.replace("ต่่า", "ต่ำ").replace("ต่ำา", "ต่ำ")
                                 .replace("ต่าสุด", "ต่ำสุด") for h in hdr]
                        return hdr
    return None


def process_pdf(pdf_path):
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"  {os.path.basename(pdf_path)}: {total} pages")
        for page_num, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                for row in table:
                    if is_header_row(row):
                        continue
                    cleaned = [fix_thai(clean(c)) for c in row]
                    if any(cleaned):
                        rows.append(cleaned)
            if page_num % 100 == 0:
                print(f"    … {page_num}/{total}")
    return rows


def main():
    pattern = os.path.join(WORK_DIR, "TCAS69*.pdf")
    pdf_files = sorted(glob.glob(pattern))

    if not pdf_files:
        print(f"No PDF files matching 'TCAS69*.pdf' found in:\n  {WORK_DIR}")
        return

    print(f"Found {len(pdf_files)} PDF file(s):")
    for f in pdf_files:
        print(f"  {os.path.basename(f)}")

    # Auto-detect header from first PDF
    header = detect_header(pdf_files[0])
    if header is None:
        print("ERROR: could not detect header row.")
        return
    print(f"\nDetected {len(header)} columns: {header}\n")

    all_rows = []
    for pdf_path in pdf_files:
        all_rows.extend(process_pdf(pdf_path))

    output_path = os.path.join(WORK_DIR, "TCAS69_results.csv")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(all_rows)

    print(f"\nDone. {len(all_rows):,} data rows → {os.path.basename(output_path)}")


if __name__ == "__main__":
    main()
