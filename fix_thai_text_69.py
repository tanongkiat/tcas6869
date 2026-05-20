#!/usr/bin/env python3
"""Fix Thai text encoding artifacts in T68_results.csv.

Phase 1 – character-level displacement (vowel/tone marks out of order):
  A: C1 + C2 + mark + space  →  C1 + mark + C2   (mark displaced after C2)
  C: C  + space + mark        →  C + mark          (space before mark)
  D: C  + space + า           →  C + ำ             (sara-am split)
  F: C  + leading_vowel + mark → C + mark + leading_vowel

Phase 2 – PDF line-break artifacts (spurious mid-word spaces):
  G: แ + space + consonant    → แ + consonant      (leading vowel แ separated)
  H: known compound proper-noun fragments joined
"""

import csv
import re
import shutil
import os

WORK_DIR = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(WORK_DIR, "TCAS69_results.csv")
BACKUP = os.path.join(WORK_DIR, "TCAS69_results.bak.csv")
DST = SRC  # overwrite in-place

# Thai consonants: U+0E01–U+0E2E
CONS = r"[ก-ฮ]"
# Combining marks: mai-han-akat (ั), sara-i..sara-uu (ิีึืุู), maitaikhu (็),
# tone marks (่้๊๋), thanthakat (์), nikhahit (ํ), yamakkan (๎)
MARK = r"[\u0E31\u0E34-\u0E39\u0E47-\u0E4E]"
# Leading vowels (เแโไใ): U+0E40–U+0E44
LEAD = r"[เแโไใ]"

# ── Phase 1 rules ─────────────────────────────────────────────────────────────
_P1_RULES = [
    # A: two consonants then displaced mark then space -> move mark before C2
    (re.compile(f"({CONS})({CONS})({MARK}) "), r"\1\3\2"),
    # C: consonant then space then mark -> remove space
    (re.compile(f"({CONS}) ({MARK})"),          r"\1\2"),
    # D: consonant then space then sara-a  -> sara-am
    (re.compile(f"({CONS}) า"),                 r"\1ำ"),
    # F: consonant then leading-vowel then mark -> move mark before leading-vowel
    (re.compile(f"({CONS})({LEAD})({MARK})"),   r"\1\3\2"),
]

# ── Phase 2 rules ─────────────────────────────────────────────────────────────
# G: แ (leading vowel) cannot end a syllable – remove any space after it
_RULE_G = re.compile(r"แ ([ก-ฮเโไใ])")

# H: Known compound proper-noun fragments split by PDF line breaks.
#    Each entry: (exact_broken, correct)  – applied as plain string.replace()
_COMPOUND_FIXES = [
    # ── Rajamangala universities ─────────────────────────────────
    ("ราช มงคล",              "ราชมงคล"),
    # ── KMUTT / KMUTNB ──────────────────────────────────────────
    ("พระ จอมเกล้า",          "พระจอมเกล้า"),
    ("เกล้า เจ้าคุณ",         "เกล้าเจ้าคุณ"),
    # ── KMITL (full name reassembled by prior rules except this) ─
    ("เกล้า เจ้าคุณทหารลาดกระบัง", "เกล้าเจ้าคุณทหารลาดกระบัง"),
    # ── Rajabhat universities ────────────────────────────────────
    ("ราชภัฏ อุบลราชธานี",   "ราชภัฏอุบลราชธานี"),
    ("ราชภัฏ นครราชสีมา",    "ราชภัฏนครราชสีมา"),
    ("ราชภัฏบ้านสมเด็จ เจ้าพระยา", "ราชภัฏบ้านสมเด็จเจ้าพระยา"),
    ("สมเด็จ เจ้าพระยา",     "สมเด็จเจ้าพระยา"),
    ("ราชภัฏพิบูล สงคราม",   "ราชภัฏพิบูลสงคราม"),
    ("พิบูล สงคราม",          "พิบูลสงคราม"),
    ("ราชภัฏวไลย อลงกรณ์",  "ราชภัฏวไลยอลงกรณ์"),
    ("วไลย อลงกรณ์",         "วไลยอลงกรณ์"),
    # ── Buddhist / special universities ─────────────────────────
    ("มหามกุฏราช วิทยาลัย",  "มหามกุฏราชวิทยาลัย"),
    ("มกุฏราช วิทยาลัย",     "มกุฏราชวิทยาลัย"),
    ("มหาจุฬาลงกรณ ราชวิทยาลัย", "มหาจุฬาลงกรณราชวิทยาลัย"),
    ("ลงกรณ ราชวิทยาลัย",   "ลงกรณราชวิทยาลัย"),
    ("นราธิวาสราช นครินทร์", "นราธิวาสราชนครินทร์"),
    # ── Huachiew / special ──────────────────────────────────────
    ("หัวเฉียวเฉลิมพระ เกียรติ", "หัวเฉียวเฉลิมพระเกียรติ"),
    ("เฉลิมพระ เกียรติ",     "เฉลิมพระเกียรติ"),
    # ── Maejo ────────────────────────────────────────────────────
    ("แม่โจ้-แพร่เฉลิม พระเกียรติ", "แม่โจ้-แพร่เฉลิมพระเกียรติ"),
    # ── RMUTK / Chakrabongse ────────────────────────────────────
    ("วิทยาเขตจักร พงษภูวนารถ", "วิทยาเขตจักรพงษภูวนารถ"),
    ("จักร พงษภูวนารถ",      "จักรพงษภูวนารถ"),
    # ── Sirindhon International ──────────────────────────────────
    ("สถาบันเทคโนโลยีนานาชาติสิ รินธร", "สถาบันเทคโนโลยีนานาชาติสิรินธร"),
    ("นานาชาติสิ รินธร",     "นานาชาติสิรินธร"),
    ("บัณฑิตวิทยาลัย วิศวกรรมศาสตร์นานาชาติสิ รินธร",
     "บัณฑิตวิทยาลัยวิศวกรรมศาสตร์นานาชาติสิรินธร"),
    ("วิศวกรรมศาสตร์นานาชาติสิ รินธร", "วิศวกรรมศาสตร์นานาชาติสิรินธร"),
    # ── Admission project names ──────────────────────────────────
    ("บุคคลเข้า ศึกษา",      "บุคคลเข้าศึกษา"),
    ("เข้า ศึกษา",            "เข้าศึกษา"),
    ("รูปแบบ ที่",            "รูปแบบที่"),
    ("รูปแบบ ใช้",            "รูปแบบใช้"),
    # ── Faculties with และ split ────────────────────────────────
    ("และ เทคโนโลยี",         "และเทคโนโลยี"),
    ("และ สังคมศาสตร์",       "และสังคมศาสตร์"),
    ("และ วิทยาศาสตร์",       "และวิทยาศาสตร์"),
    ("และ วิศวกรรมศาสตร์",    "และวิศวกรรมศาสตร์"),
    ("และ อุตสาหกรรม",        "และอุตสาหกรรม"),
    ("และ นวัตกรรม",          "และนวัตกรรม"),
    ("และ ทรัพยากร",          "และทรัพยากร"),
    ("และ การสื่อสาร",        "และการสื่อสาร"),
    ("และ เทคโนโลยีสารสนเทศ", "และเทคโนโลยีสารสนเทศ"),
    ("และ การบัญชี",          "และการบัญชี"),
    ("และ การ จัดการ",        "และการจัดการ"),
    ("และ สาธารณสุข",         "และสาธารณสุขศาสตร์"),
    ("และ พัฒนา",             "และพัฒนา"),
    ("และ การพัฒนา",          "และการพัฒนา"),
    ("และ การออกแบบ",         "และการออกแบบ"),
    ("และ บริหารธุรกิจ",      "และบริหารธุรกิจ"),
    ("และ เศรษฐศาสตร์",       "และเศรษฐศาสตร์"),
    ("และ รัฐประศาสน",        "และรัฐประศาสน"),
    ("และ นิติศาสตร์",        "และนิติศาสตร์"),
    ("และ ศิลปศาสตร์",        "และศิลปศาสตร์"),
    ("แ ห่ง ",                "แห่ง "),
    # ── Campus / project fragments ──────────────────────────────
    ("ผลิตบัณฑิตเพื่อ พัฒนา", "ผลิตบัณฑิตเพื่อพัฒนา"),
    ("เพื่อ พัฒนาชุมชน",      "เพื่อพัฒนาชุมชน"),
    ("ส่วน กลาง",             "ส่วนกลาง"),
    ("ใน ส่วนกลาง",           "ในส่วนกลาง"),
    ("แพทยศาสต์ร","แพทยศาสตร์"),
    
]


def fix_thai(text: str) -> str:
    """Apply Phase 1 + Phase 2 rules iteratively until the string stabilises."""
    prev = None
    while prev != text:
        prev = text
        # Phase 1
        for pattern, repl in _P1_RULES:
            text = pattern.sub(repl, text)
        # Phase 2 – G
        text = _RULE_G.sub(r"แ\1", text)
        # Phase 2 – H
        for broken, correct in _COMPOUND_FIXES:
            if broken in text:
                text = text.replace(broken, correct)
    return text


def main():
    # Backup original
    shutil.copy2(SRC, BACKUP)
    print(f"Backed up original -> {os.path.basename(BACKUP)}")

    rows_fixed = 0
    cells_fixed = 0
    out_rows = []

    with open(SRC, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        out_rows.append(header)
        for row in reader:
            new_row = []
            row_changed = False
            for cell in row:
                fixed = fix_thai(cell)
                if fixed != cell:
                    cells_fixed += 1
                    row_changed = True
                new_row.append(fixed)
            out_rows.append(new_row)
            if row_changed:
                rows_fixed += 1

    with open(DST, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(out_rows)

    print(f"Fixed {cells_fixed:,} cells in {rows_fixed:,} rows.")
    print(f"Saved -> {os.path.basename(DST)}")

    # Report remaining suspicious patterns
    import collections
    suspicious = collections.Counter()
    with open(DST, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            for cell in row:
                if re.search(r"[\u0E00-\u0E7F] [\u0E00-\u0E7F]", cell):
                    suspicious[cell] += 1
    if suspicious:
        print(f"\n{len(suspicious)} unique values still contain Thai-space-Thai patterns:")
        for val, cnt in sorted(suspicious.items(), key=lambda x: -x[1])[:30]:
            print(f"  {cnt:4d}  {val!r}")
    else:
        print("\nNo remaining Thai-space-Thai patterns.")


if __name__ == "__main__":
    main()
