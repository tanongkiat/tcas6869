#!/usr/bin/env python3
"""Serve index.html and a search API backed by tcas_results.db.

Usage:
    python3 server.py
Then open http://localhost:8000/ in your browser.
"""

import json
import os
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

WORK_DIR          = os.path.dirname(os.path.abspath(__file__))
DB_PATH           = os.path.join(WORK_DIR, "tcas_results.db")
HTML_PATH         = os.path.join(WORK_DIR, "index.html")
COMPARE_HTML_PATH = os.path.join(WORK_DIR, "compare.html")
PORT              = int(os.environ.get("PORT", 8000))

SEARCH_COLS = ['"สถาบัน"', '"วิทยาเขต"', '"คณะ"', '"หลักสูตร"', '"สาขา/วิชาเอก"']


def _yr(row):
    """Extract the per-year stats dict from a DB row dict, or None."""
    if row is None:
        return None
    return {
        "รับ":    row["รับ"],
        "สูงสุด": row["คะแนนสูงสุด"],
        "ต่ำสุด": row["คะแนนต่ำสุด"],
    }


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self._serve_file(HTML_PATH, "text/html; charset=utf-8")
        elif parsed.path in ("/compare", "/compare.html"):
            self._serve_file(COMPARE_HTML_PATH, "text/html; charset=utf-8")
        elif parsed.path == "/api/search":
            self._handle_search(parsed.query)
        elif parsed.path == "/api/compare":
            self._handle_compare(parsed.query)
        else:
            self._send(404, "application/json", b'{"error":"not found"}')

    # ── file serving ──────────────────────────────────────────────────────────

    def _serve_file(self, path, content_type):
        try:
            with open(path, "rb") as f:
                data = f.read()
            self._send(200, content_type, data)
        except FileNotFoundError:
            self._send(404, "text/plain", b"File not found")

    # ── search API ────────────────────────────────────────────────────────────

    def _handle_search(self, query_string):
        params   = urllib.parse.parse_qs(query_string)
        q        = params.get("q",        [""])[0].strip()
        year_raw = params.get("year",     [""])[0].strip()
        try:
            page = max(1, int(params.get("page", ["1"])[0]))
        except ValueError:
            page = 1
        try:
            per_page = min(200, max(1, int(params.get("per_page", ["50"])[0])))
        except ValueError:
            per_page = 50
        offset = (page - 1) * per_page

        conditions, args = [], []

        # Each whitespace-separated token is ANDed — all must match somewhere
        for token in q.split():
            like = f"%{token}%"
            conditions.append(
                "(" + " OR ".join(f"{c} LIKE ?" for c in SEARCH_COLS) + ")"
            )
            args.extend([like] * len(SEARCH_COLS))

        if year_raw:
            try:
                conditions.append("year = ?")
                args.append(int(year_raw))
            except ValueError:
                pass

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            cur.execute(f'SELECT COUNT(*) FROM "tcas_results" {where}', args)
            total = cur.fetchone()[0]

            cur.execute(
                f'SELECT * FROM "tcas_results" {where} LIMIT ? OFFSET ?',
                args + [per_page, offset],
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            payload = {
                "total":    total,
                "page":     page,
                "per_page": per_page,
                "rows":     rows,
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", data)

        except Exception as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")
            self._send(500, "application/json; charset=utf-8", err)

    # ── compare API ───────────────────────────────────────────────────────────

    def _handle_compare(self, query_string):
        params   = urllib.parse.parse_qs(query_string)
        q        = params.get("q", [""])[0].strip()
        try:
            page = max(1, int(params.get("page", ["1"])[0]))
        except ValueError:
            page = 1
        try:
            per_page = min(200, max(1, int(params.get("per_page", ["100"])[0])))
        except ValueError:
            per_page = 100

        conditions, args = [], []
        for token in q.split():
            like = f"%{token}%"
            conditions.append(
                "(" + " OR ".join(f"{c} LIKE ?" for c in SEARCH_COLS) + ")"
            )
            args.extend([like] * len(SEARCH_COLS))

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cur  = conn.cursor()
            cur.execute(
                f'SELECT * FROM "tcas_results" {where} '
                f'ORDER BY "\u0e2a\u0e16\u0e32\u0e1a\u0e31\u0e19", "\u0e04\u0e13\u0e30", "\u0e2b\u0e25\u0e31\u0e01\u0e2a\u0e39\u0e15\u0e23", year',
                args,
            )
            all_rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            # Group by รหัสหลักสูตร — preserves ORDER BY ordering
            groups = {}   # code -> {"r68": row|None, "r69": row|None, "base": row}
            order  = []   # insertion order
            for row in all_rows:
                code = row["\u0e23\u0e2b\u0e31\u0e2a\u0e2b\u0e25\u0e31\u0e01\u0e2a\u0e39\u0e15\u0e23"]
                if code not in groups:
                    groups[code] = {"r68": None, "r69": None, "base": row}
                    order.append(code)
                yr_key = "r68" if row["year"] == 2568 else "r69"
                groups[code][yr_key] = row

            pairs = [
                {
                    "\u0e23\u0e2b\u0e31\u0e2a\u0e2b\u0e25\u0e31\u0e01\u0e2a\u0e39\u0e15\u0e23": code,
                    "\u0e2a\u0e16\u0e32\u0e1a\u0e31\u0e19":  g["base"]["\u0e2a\u0e16\u0e32\u0e1a\u0e31\u0e19"],
                    "\u0e27\u0e34\u0e17\u0e22\u0e32\u0e40\u0e02\u0e15": g["base"]["\u0e27\u0e34\u0e17\u0e22\u0e32\u0e40\u0e02\u0e15"],
                    "\u0e04\u0e13\u0e30":     g["base"]["\u0e04\u0e13\u0e30"],
                    "\u0e2b\u0e25\u0e31\u0e01\u0e2a\u0e39\u0e15\u0e23":  g["base"]["\u0e2b\u0e25\u0e31\u0e01\u0e2a\u0e39\u0e15\u0e23"],
                    "\u0e2a\u0e32\u0e02\u0e32/\u0e27\u0e34\u0e0a\u0e32\u0e40\u0e2d\u0e01": g["base"]["\u0e2a\u0e32\u0e02\u0e32/\u0e27\u0e34\u0e0a\u0e32\u0e40\u0e2d\u0e01"],
                    "y68": _yr(g["r68"]),
                    "y69": _yr(g["r69"]),
                }
                for code, g in ((c, groups[c]) for c in order)
            ]

            total  = len(pairs)
            offset = (page - 1) * per_page
            payload = {
                "total":    total,
                "page":     page,
                "per_page": per_page,
                "rows":     pairs[offset: offset + per_page],
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", data)

        except Exception as e:
            err = json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8")
            self._send(500, "application/json; charset=utf-8", err)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send(self, code, content_type, data: bytes):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quiet log
        print(f"  {self.address_string()} — {fmt % args}")


def main():
    if not os.path.exists(DB_PATH):
        raise SystemExit(f"DB not found: {DB_PATH}\nRun csv_to_sqlite.py first.")
    print(f"Serving on http://0.0.0.0:{PORT}/")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
