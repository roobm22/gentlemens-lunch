"""One-off importer: build seasons/GL24, GL25, GL26 from the Word/Excel/PDF archive.

Reads Old Example Files/ (never modifies it). Writes season.json + picks.json, and
results.json/prices.json where the archive contains results (GL25 workbook).
Re-running overwrites season.json and picks.json; results.json is only created if
missing, so curated results are never clobbered.

Usage: python scripts/oneoff/import_archive.py GL25 [GL26 GL24]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import docx  # python-docx
import openpyxl

from glcore import ROOT, SEASONS, canon, load_json, save_json

ARCHIVE = ROOT / "Old Example Files"
PLAYERS = ["robert", "carlos", "jack", "bob", "pablo", "max", "tony", "jose"]
NAME_TO_ID = {"robert": "robert", "carlos": "carlos", "jack": "jack", "bob": "bob", "pablo": "pablo",
              "max": "max", "tony": "tony", "anthony": "tony", "jose": "jose"}


def sport(cid, name, question, date, group="Sports"):
    return {"id": cid, "name": name, "question": question, "group": group,
            "type": "winner_runnerup", "points": [5, 3], "date": date}


def exact(cid, name, question, date, pts=3, group="Politics", choices=None, live=None):
    c = {"id": cid, "name": name, "question": question, "group": group,
         "type": "exact", "points": pts, "date": date}
    if choices:
        c["choices"] = choices
    if live:
        c["live"] = live
    return c


def closest(cid, name, question, date, symbol=None, unit="usd", group="Markets", source=None):
    c = {"id": cid, "name": name, "question": question, "group": group,
         "type": "closest", "points": [5, 3, 1], "date": date, "unit": unit}
    if symbol:
        c["live"] = {"kind": "price", "symbol": symbol}
    if source:
        c["source"] = source
    return c


TOP_MCAP_NAMES = {"NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft", "GOOG": "Google"}


def clean_pick(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    num = s.replace("$", "").replace(",", "").strip().rstrip("/").strip()
    pct = num.endswith("%")
    try:
        f = float(num.rstrip("%"))
        if pct:
            return round(f / 100, 6)
        return int(f) if f.is_integer() else f
    except ValueError:
        return canon(s)


def write_season(sid, season, picks, results=None, prices=None):
    d = SEASONS / sid
    save_json(d / "season.json", season)
    save_json(d / "picks.json", picks)
    if results is not None and not (d / "results.json").exists():
        save_json(d / "results.json", results)
    if prices is not None and not (d / "prices.json").exists():
        save_json(d / "prices.json", prices)
    print(f"wrote {d.relative_to(ROOT)}")


# ------------------------------------------------------------------ GL25

def gl25():
    s = "2025-12-24"
    cats = [
        closest("approval", "Trump approval (Rasmussen)",
                "Donald Trump approval rating on 12/24/2025 (Rasmussen Reports daily tracking poll, 'Total Approve')",
                s, unit="pct", group="Politics", source="Rasmussen Reports daily tracking poll"),
        sport("super_bowl", "Super Bowl LIX", "Winner of the 2025 Super Bowl", "2025-02-09"),
        exact("sb_coin_flip", "Super Bowl coin flip", "Super Bowl coin flip: Heads or Tails", "2025-02-09",
              pts=1, group="Sports", choices=["Heads", "Tails"]),
        sport("cfp", "College Football Playoff", "NCAAF: College Football Champion 2025", "2025-01-20"),
        sport("march_madness", "March Madness", "2025 March Madness winner (NCAA men's)", "2025-04-07"),
        sport("masters", "The Masters", "2025 Masters winner", "2025-04-13"),
        sport("stanley_cup", "Stanley Cup", "2025 Stanley Cup champion", "2025-06-17"),
        sport("nba", "NBA Finals", "2025 NBA champion", "2025-06-22"),
        sport("ucl", "Champions League", "2025 UEFA Champions League winner", "2025-05-31"),
        sport("wimbledon", "Men's Wimbledon", "2025 Men's Wimbledon champion", "2025-07-13"),
        sport("world_series", "World Series", "2025 World Series champion", "2025-11-01"),
        closest("sp500", "S&P 500", "S&P 500 close on 12/24/2025", s, "^GSPC"),
        closest("gold", "Gold", "Price of gold (GC00, marketwatch.com) on 12/24/2025", s, "GC=F"),
        closest("oil", "Crude oil", "Price of crude oil (CL00, marketwatch.com) on 12/24/2025", s, "CL=F"),
        closest("bitcoin", "Bitcoin", "Price of Bitcoin (marketwatch.com) on 12/24/2025", s, "BTC-USD"),
        exact("top_mcap", "Top US company by market cap", "Top US company by market cap on 12/24/2025", s,
              group="Markets", live={"kind": "top_market_cap", "names": TOP_MCAP_NAMES}),
        closest("tgt", "Target (TGT)", "Target stock price on 12/24/2025", s, "TGT"),
        closest("tsla", "Tesla (TSLA)", "Tesla stock price on 12/24/2025", s, "TSLA"),
        closest("coin", "Coinbase (COIN)", "Coinbase stock price on 12/24/2025", s, "COIN"),
        closest("cmg", "Chipotle (CMG)", "Chipotle stock price on 12/24/2025", s, "CMG"),
        closest("aapl", "Apple (AAPL)", "Apple stock price on 12/24/2025", s, "AAPL"),
    ]
    season = {
        "id": "GL25", "year": 2025, "title": "Gentlemen's Lunch 2025", "status": "final",
        "picks_made_at": "Big Thanksgiving 2024", "picks_close": "2024-12-27",
        "settlement_date": s, "settlement_holiday": "Big Christmas 2025",
        "players": PLAYERS, "categories": cats,
        "source_files": ["Old Example Files/GL Standings 2025.xlsx"],
    }

    wb = openpyxl.load_workbook(ARCHIVE / "GL Standings 2025.xlsx", data_only=True)
    ws = wb["Picks"]
    picks = {p: {} for p in PLAYERS}
    for i, cat in enumerate(cats):
        row = 3 + i
        for j, p in enumerate(PLAYERS):
            picks[p][cat["id"]] = clean_pick(ws.cell(row=row, column=5 + j).value)

    # Sports results from the workbook ("Winner_RunnerUp"); markets are filled from
    # settlement closes separately (see BUILD_PLAN §5.1).
    results = {}
    for i, cat in enumerate(cats):
        raw = ws.cell(row=3 + i, column=3).value
        if cat["type"] == "winner_runnerup":
            w, r = str(raw).split("_", 1)
            results[cat["id"]] = {"status": "final", "winner": canon(w), "runner_up": canon(r),
                                  "date": cat["date"], "source": "GL25 workbook (Robert)"}
        elif cat["id"] == "sb_coin_flip":
            results[cat["id"]] = {"status": "final", "answer": canon(raw), "date": cat["date"],
                                  "source": "GL25 workbook (Robert)"}

    st = wb["Stocks"]
    sym_rows = {"^GSPC": 3, "GC=F": 4, "CL=F": 5, "BTC-USD": 6, "TGT": 7, "TSLA": 8, "COIN": 9, "CMG": 10, "AAPL": 11}
    prices = {"start": {"date": "2024-12-27", "source": "GL25 workbook 'Stocks' tab (12/27/2024 1:11 pm ET)",
                        "values": {sym: float(st.cell(row=r, column=4).value) for sym, r in sym_rows.items()}}}
    write_season("GL25", season, picks, results, prices)


# ------------------------------------------------------------------ GL26

def read_docx_tables(path):
    d = docx.Document(path)
    tables = []
    for t in d.tables:
        rows = []
        for row in t.rows:
            cells, prev = [], None
            for c in row.cells:
                if c._tc is prev:
                    continue
                prev = c._tc
                cells.append(c.text.strip())
            rows.append(cells)
        tables.append(rows)
    return d, tables


def gl26():
    s = "2026-11-25"
    mag7 = ["AAPL", "AMZN", "GOOG", "META", "MSFT", "NVDA", "TSLA"]
    cats = [
        sport("super_bowl", "Super Bowl LX", "Winner of the 2026 Super Bowl", "2026-02-08"),
        exact("sb_coin_flip", "Super Bowl coin flip", "Super Bowl coin flip: Heads or Tails", "2026-02-08",
              pts=1, group="Sports", choices=["Heads", "Tails"]),
        sport("cfp", "College Football Playoff", "NCAAF: College Football Champion 2026", "2026-01-19"),
        sport("olympic_hockey", "Olympic men's hockey", "2026 Winter Olympics: men's ice hockey champion", "2026-02-22"),
        sport("wbc", "World Baseball Classic", "2026 World Baseball Classic winner", "2026-03-17"),
        sport("march_madness", "March Madness", "2026 March Madness winner (NCAA men's)", "2026-04-06"),
        sport("masters", "The Masters", "2026 Masters winner", "2026-04-12"),
        sport("stanley_cup", "Stanley Cup", "2026 Stanley Cup champion", "2026-06-15"),
        sport("nba", "NBA Finals", "2026 NBA champion", "2026-06-15"),
        sport("ucl", "Champions League", "2026 UEFA Champions League winner", "2026-05-30"),
        sport("wimbledon", "Men's Wimbledon", "2026 Men's Wimbledon champion", "2026-07-12"),
        sport("world_cup", "FIFA World Cup", "2026 FIFA World Cup champion", "2026-07-19"),
        sport("world_series", "World Series", "2026 World Series champion", "2026-11-01"),
        exact("house", "Midterms: House", "Midterm elections: House majority (Republican or Democrat)", "2026-11-03",
              choices=["Democrat", "Republican"]),
        exact("senate", "Midterms: Senate", "Midterm elections: Senate majority (Republican or Democrat)", "2026-11-03",
              choices=["Democrat", "Republican"]),
        exact("cabinet_first_out", "First to leave Trump's Cabinet", "Who will be the first to leave Trump's Cabinet?", s),
        closest("sp500", "S&P 500", "S&P 500 close on 11/25/2026", s, "^GSPC"),
        closest("gold", "Gold", "Price of gold (GC00, marketwatch.com) on 11/25/2026", s, "GC=F"),
        closest("oil", "Crude oil", "Price of crude oil (CL00, marketwatch.com) on 11/25/2026", s, "CL=F"),
        closest("bitcoin", "Bitcoin", "Price of Bitcoin (marketwatch.com) on 11/25/2026", s, "BTC-USD"),
        {"id": "mag7", "name": "Magnificent 7 ranking",
         "question": "Rank the Magnificent 7 from highest market cap (1) to lowest (7) on 11/25/2026",
         "group": "Markets", "type": "ranking", "points": [5, 3, 1], "date": s, "items": mag7,
         "live": {"kind": "rank_by_market_cap"}},
        closest("unh", "UnitedHealth (UNH)", "UnitedHealth stock price on 11/25/2026", s, "UNH"),
        closest("nflx", "Netflix (NFLX)", "Netflix stock price on 11/25/2026", s, "NFLX"),
        closest("aapl", "Apple (AAPL)", "Apple stock price on 11/25/2026", s, "AAPL"),
        closest("ba", "Boeing (BA)", "Boeing stock price on 11/25/2026", s, "BA"),
        closest("cost", "Costco (COST)", "Costco stock price on 11/25/2026", s, "COST"),
    ]
    season = {
        "id": "GL26", "year": 2026, "title": "Gentlemen's Lunch 2026", "status": "active",
        "picks_made_at": "Big Christmas 2025", "settlement_date": s,
        "settlement_holiday": "Big Thanksgiving 2026", "players": PLAYERS, "categories": cats,
        "source_files": ["Old Example Files/2026 Picks.docx",
                         "Old Example Files/(Jack's own 2026 picks PDF)"],
    }
    _, tables = read_docx_tables(ARCHIVE / "2026 Picks.docx")
    rows = tables[0]
    header = [h.lower() for h in rows[0]]
    col = {NAME_TO_ID[h]: i for i, h in enumerate(header) if h in NAME_TO_ID}
    body = rows[1:]
    assert len(body) == len(cats), f"expected {len(cats)} rows, got {len(body)}"
    picks = {p: {} for p in PLAYERS}
    for cat, row in zip(cats, body):
        for p in PLAYERS:
            v = row[col[p]]
            if cat["type"] == "ranking":
                picks[p][cat["id"]] = ",".join(x.strip().upper() for x in v.split(","))
            else:
                picks[p][cat["id"]] = clean_pick(v)
    # Jack's own PDF says $51.50 for crude; the compiled docx says $52 (CLAUDE.md §12 #4).
    picks["jack"]["oil"] = 51.5
    write_season("GL26", season, picks, results={})


# ------------------------------------------------------------------ GL24

def gl24():
    s = "2024-11-27"
    cats = [
        sport("super_bowl", "Super Bowl LVIII", "Winner of the 2024 Super Bowl", "2024-02-11"),
        exact("sb_coin_flip", "Super Bowl coin flip", "Super Bowl coin flip: Heads or Tails", "2024-02-11",
              pts=1, group="Sports", choices=["Heads", "Tails"]),
        sport("cfp", "College Football Playoff", "NCAAF: College Football Champion 2024", "2024-01-08"),
        sport("march_madness", "March Madness", "2024 March Madness winner (NCAA men's)", "2024-04-08"),
        sport("masters", "The Masters", "2024 Masters winner", "2024-04-14"),
        sport("stanley_cup", "Stanley Cup", "2024 Stanley Cup champion", "2024-06-24"),
        sport("nba", "NBA Finals", "2024 NBA champion", "2024-06-17"),
        sport("ucl", "Champions League", "2024 UEFA Champions League winner", "2024-06-01"),
        sport("wimbledon", "Men's Wimbledon", "2024 Men's Wimbledon champion", "2024-07-14"),
        sport("euro", "Men's Euro", "2024 Men's soccer Euro winner", "2024-07-14"),
        sport("world_series", "World Series", "2024 World Series champion", "2024-10-30"),
        exact("gop_vp", "GOP VP nominee", "Republican VP nominee", "2024-07-15"),
        exact("gop_nominee", "GOP nominee", "Republican presidential nominee", "2024-07-15"),
        exact("president_elect", "President-elect", "President-elect of the United States", "2024-11-06"),
        exact("senate", "Senate majority", "Senate majority: D or R", "2024-11-06", choices=["Democrat", "Republican"]),
        closest("sp500", "S&P 500", "S&P 500 close on 11/27/2024", s, "^GSPC"),
        closest("gold", "Gold", "Price of gold (GC00, marketwatch.com) on 11/27/2024", s, "GC=F"),
        closest("oil", "Crude oil", "Price of crude oil (marketwatch.com) on 11/27/2024", s, "CL=F"),
        closest("bitcoin", "Bitcoin", "Price of Bitcoin (marketwatch.com) on 11/27/2024", s, "BTC-USD"),
        exact("top_mcap", "Top US company by market cap", "Top US company by market cap", s, group="Markets",
              live={"kind": "top_market_cap", "names": TOP_MCAP_NAMES}),
        closest("nvda", "Nvidia (NVDA)", "Nvidia stock price on 11/27/2024 (picks were pre-split; scored split-adjusted ÷10)",
                s, "NVDA"),
        closest("pfe", "Pfizer (PFE)", "Pfizer stock price on 11/27/2024", s, "PFE"),
        closest("cost", "Costco (COST)", "Costco stock price on 11/27/2024 (listed as 'CSCO' on the sheet)", s, "COST"),
        closest("uber", "Uber (UBER)", "Uber stock price on 11/27/2024", s, "UBER"),
        closest("aapl", "Apple (AAPL)", "Apple stock price on 11/27/2024", s, "AAPL"),
    ]
    season = {
        "id": "GL24", "year": 2024, "title": "Gentlemen's Lunch 2024", "status": "final",
        "picks_made_at": "Big Christmas 2023", "picks_close": "2024-01-04",
        "settlement_date": s, "settlement_holiday": "Big Thanksgiving 2024",
        "players": PLAYERS, "categories": cats,
        "source_files": ["Old Example Files/Gentlemen's Luncheon 2024 Picks.docx"],
        "notes": ["NVDA split 10-for-1 on 2024-06-10; all NVDA picks predate it and are divided by 10 (ranking unchanged)."],
    }
    d = docx.Document(ARCHIVE / "Gentlemen's Luncheon 2024 Picks.docx")
    names = [p.text.split(":", 1)[1].strip().lower() for p in d.paragraphs if p.text.strip().lower().startswith("name:")]
    _, tables = read_docx_tables(ARCHIVE / "Gentlemen's Luncheon 2024 Picks.docx")
    assert len(names) == len(tables) == 8, (names, len(tables))
    picks = {p: {} for p in PLAYERS}
    for name, rows in zip(names, tables):
        pid = NAME_TO_ID[name]
        body = rows[1:]
        assert len(body) == len(cats), f"{name}: {len(body)} rows"
        for cat, row in zip(cats, body):
            v = clean_pick(row[2])
            if cat["id"] == "nvda" and isinstance(v, (int, float)):
                v = round(v / 10, 3)
            picks[pid][cat["id"]] = v
    write_season("GL24", season, picks, results={})


# ------------------------------------------------------------------ GL23

def gl23():
    s = "2023-12-22"
    cats = [
        sport("super_bowl", "Super Bowl LVII", "Winner of the 2023 Super Bowl", "2023-02-12"),
        exact("sb_coin_flip", "Super Bowl coin flip", "Super Bowl coin flip: Heads or Tails", "2023-02-12",
              pts=1, group="Sports", choices=["Heads", "Tails"]),
        sport("cfp", "College Football Playoff", "NCAAF: College Football Champion 2023", "2023-01-09"),
        sport("world_cup", "FIFA World Cup (Qatar)", "World Cup champion", "2022-12-18"),
        sport("march_madness", "March Madness", "2023 March Madness winner (NCAA men's)", "2023-04-03"),
        sport("masters", "The Masters", "2023 Masters winner", "2023-04-09"),
        sport("us_open_golf", "US Open (golf)", "2023 US Open golf winner", "2023-06-18"),
        sport("stanley_cup", "Stanley Cup", "2023 Stanley Cup champion", "2023-06-13"),
        sport("nba", "NBA Finals", "2023 NBA champion", "2023-06-12"),
        sport("wimbledon", "Men's Wimbledon", "2023 Men's Wimbledon champion", "2023-07-16"),
        sport("british_open", "The Open (British Open)", "2023 British Open champion", "2023-07-23"),
        sport("ucl", "Champions League", "2023 UEFA Champions League winner", "2023-06-10"),
        sport("world_series", "World Series", "2023 World Series champion", "2023-11-01"),
        closest("approval", "Biden approval (Rasmussen)",
                "Joe Biden approval rating on 12/22/2023 (Rasmussen Reports, 'Total Approve')", s,
                unit="pct", group="Politics", source="Rasmussen Reports daily tracking poll"),
        exact("ga_runoff", "Georgia Senate runoff", "Georgia Senate runoff: Warnock or Walker", "2022-12-06",
              choices=["Raphael Warnock", "Herschel Walker"]),
        closest("sp500", "S&P 500", "S&P 500 close on 12/22/2023", s, "^GSPC"),
        closest("gold", "Gold", "Price of gold (COMEX futures) on 12/22/2023", s, "GC=F"),
        closest("oil", "Crude oil", "Price of crude oil (marketwatch.com) on 12/22/2023", s, "CL=F"),
        closest("bitcoin", "Bitcoin", "Price of Bitcoin (marketwatch.com) on 12/22/2023", s, "BTC-USD"),
        closest("dis", "Disney (DIS)", "Disney stock price on 12/22/2023", s, "DIS"),
        closest("aapl", "Apple (AAPL)", "Apple stock price on 12/22/2023", s, "AAPL"),
        closest("dkng", "DraftKings (DKNG)", "DraftKings stock price on 12/22/2023", s, "DKNG"),
        closest("coin", "Coinbase (COIN)", "Coinbase stock price on 12/22/2023", s, "COIN"),
        closest("meta", "Meta (META)", "Facebook/Meta stock price on 12/22/2023", s, "META"),
    ]
    season = {
        "id": "GL23", "year": 2023, "title": "Gentlemen's Lunch 2023", "status": "final",
        "picks_made_at": "Big Thanksgiving 2022", "settlement_date": s,
        "settlement_holiday": "Big Christmas 2023", "players": PLAYERS, "categories": cats,
        "source_files": ["Old Example Files/Gentlemen's Luncheon 2023 Picks.docx"],
    }
    path = ARCHIVE / "Gentlemen's Luncheon 2023 Picks.docx"
    d = docx.Document(path)
    names = [p.text.split(":", 1)[1].strip().split()[0].lower()
             for p in d.paragraphs if p.text.strip().lower().startswith("name:")]
    _, tables = read_docx_tables(path)
    assert len(names) == len(tables) == 8, (names, len(tables))
    picks = {p: {} for p in PLAYERS}
    for name, rows in zip(names, tables):
        body = rows[1:]
        assert len(body) == len(cats), f"{name}: {len(body)} rows"
        for cat, row in zip(cats, body):
            v = clean_pick(row[2])
            if cat["id"] == "ga_runoff":
                v = {"warnock": "Raphael Warnock", "walker": "Herschel Walker"}.get(str(v).lower(), v)
            picks[NAME_TO_ID[name]][cat["id"]] = v
    write_season("GL23", season, picks, results={})


if __name__ == "__main__":
    targets = sys.argv[1:] or ["GL25", "GL26", "GL24", "GL23"]
    for t in targets:
        {"GL25": gl25, "GL26": gl26, "GL24": gl24, "GL23": gl23}[t]()
    idx = SEASONS / "index.json"
    if not idx.exists():
        save_json(idx, {"active": "GL26", "seasons": ["GL26", "GL25", "GL24", "GL23"]})
