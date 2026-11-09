"""Scoring tests. Run: python scripts/tests/test_scoring.py

1. Reproduce Robert's GL25 workbook (2025-12-16 snapshot) cell-for-cell.
2. Unit tests for ties, rankings, bad picks and aliases.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import openpyxl

from glcore import ROOT, SEASONS, load_json, score_category, same, dense_tier_points

PLAYERS = ["robert", "carlos", "jack", "bob", "pablo", "max", "tony", "jose"]

# Values in the workbook's Standings!C30:C50 on 2025-12-16 (markets were not final yet).
SNAPSHOT = {"approval": 0.47, "sp500": 6816.51, "gold": 4329.5, "oil": 55.57, "bitcoin": 86957,
            "tgt": 97.56, "tsla": 475.31, "coin": 250.42, "cmg": 35.95, "aapl": 274.11}


def test_gl25_workbook():
    season = load_json(SEASONS / "GL25" / "season.json")
    picks = load_json(SEASONS / "GL25" / "picks.json")
    results = load_json(SEASONS / "GL25" / "results.json")
    wb = openpyxl.load_workbook(ROOT / "Old Example Files" / "GL Standings 2025.xlsx", data_only=True)
    ws = wb["Standings"]

    current = {p: 0 for p in PLAYERS}
    projected = {p: 0 for p in PLAYERS}
    mismatches = []
    for i, cat in enumerate(season["categories"]):
        cid = cat["id"]
        if cid in SNAPSHOT:
            res = {"status": "live", "value": SNAPSHOT[cid]}
        elif cid == "top_mcap":
            res = {"status": "live", "answer": "Nvidia"}
        else:
            res = results[cid]
        sc = score_category(cat, PLAYERS, picks, res, None)
        for j, p in enumerate(PLAYERS):
            cell = ws.cell(row=4 + i, column=4 + j).value
            expected = 0 if cell in (None, "-") else int(cell)
            got = sc["points"][p]
            if got != expected:
                mismatches.append(f"{cid}/{p}: workbook {expected}, engine {got}")
            projected[p] += got
            if sc["status"] == "final":
                current[p] += got
    assert not mismatches, "\n".join(mismatches)

    exp_current = {p: int(ws.cell(row=25, column=4 + j).value) for j, p in enumerate(PLAYERS)}
    exp_proj_part = {p: int(ws.cell(row=26, column=4 + j).value) for j, p in enumerate(PLAYERS)}
    assert current == exp_current, (current, exp_current)
    assert projected == {p: exp_current[p] + exp_proj_part[p] for p in PLAYERS}, projected
    assert projected["jose"] == 30 and projected["bob"] == 28 and current["bob"] == 17
    print("GL25 workbook: all", len(season["categories"]) * 8, "cells and both totals match")


def test_dense_ties():
    # two tie for closest -> both 5; next distinct -> 3; next -> 1; rest 0
    pts = dense_tier_points({"a": 1.0, "b": 1.0, "c": 2.0, "d": 5.0, "e": 9.0}, [5, 3, 1])
    assert pts == {"a": 5, "b": 5, "c": 3, "d": 1, "e": 0}, pts


def test_ranking():
    cat = {"id": "mag7", "type": "ranking", "points": [5, 3, 1],
           "items": ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA", "TSLA"]}
    truth = ["GOOG", "MSFT", "AAPL", "AMZN", "NVDA", "META", "TSLA"]
    picks = {
        "robert": {"mag7": "GOOG,NVDA,MSFT,AAPL,AMZN,TSLA,META"},  # Robert's example from CLAUDE.md
        "perfect": {"mag7": truth},
        "short": {"mag7": "NVDA,AAPL"},
    }
    sc = score_category(cat, list(picks), picks, {"status": "final", "order": truth}, None)
    # Robert: GOOG 0, NVDA |1-4|=3, MSFT |2-1|=1, AAPL |3-2|=1, AMZN |4-3|=1, TSLA |5-6|=1, META |6-5|=1 -> 8
    assert sc["detail"]["robert"]["score"] == 8, sc["detail"]
    assert sc["points"] == {"perfect": 5, "robert": 3, "short": 0}, sc["points"]
    assert "error" in sc["detail"]["short"]


def test_aliases():
    assert same("OKC Thunder", "Oklahoma City Thunder")
    assert same("Scotty Scheffler", "scottie scheffler")
    assert same("LA Dodgers", "Los Angeles Dodgers")
    assert not same("Michigan", "Michigan State")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
