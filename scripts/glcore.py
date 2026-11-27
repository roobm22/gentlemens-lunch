"""Gentlemen's Lunch core: load season data and score it.

Data lives in seasons/<ID>/:
  season.json   categories, dates, players
  picks.json    {player_id: {category_id: pick}}
  results.json  {category_id: {...}}  curated outcomes (status "final" or "live")
  prices.json   auto-fetched market data (latest + start), optional

Scoring types (see CLAUDE.md §4):
  winner_runnerup  5 for the champion, 3 for the runner-up
  exact            fixed points for the right answer (coin flip, elections, props)
  closest          |pick - value|, dense rank of distinct distances -> 5/3/1
                   (unit "date": distance in days, e.g. MLB Opening Day)
  ranking         sum of |guessed position - true position|, lowest wins -> 5/3/1
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASONS = ROOT / "seasons"


def load_json(path: Path, default=None):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------- matching

def _load_aliases() -> dict:
    raw = load_json(ROOT / "aliases.json", {}) or {}
    out = {}
    for canonical, variants in raw.items():
        if canonical.startswith("_"):
            continue
        out[canonical.casefold().strip()] = canonical
        for v in variants:
            out[v.casefold().strip()] = canonical
    return out


ALIASES = _load_aliases()


def canon(value) -> str | None:
    """Canonical form of a free-text answer (alias table, case-insensitive)."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return ALIASES.get(s.casefold(), s)


def same(a, b) -> bool:
    ca, cb = canon(a), canon(b)
    return ca is not None and cb is not None and ca.casefold() == cb.casefold()


def to_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("$", "").replace(",", "").strip()
    pct = s.endswith("%")
    s = s.rstrip("%").strip()
    try:
        n = float(s)
    except ValueError:
        return None
    return n / 100 if pct else n


DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y")


def to_date(value) -> dt.date | None:
    """Parse a date pick or result (ISO, M/D/YYYY as Google Forms exports it, or 'March 24, 2027')."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    s = str(value).strip()
    for f in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s[:10] if f == "%Y-%m-%d" else s, f).date()
        except ValueError:
            continue
    return None


def closest_number(value, unit=None) -> float | None:
    """Numeric value for a 'closest' pick: dates count as days."""
    if unit == "date":
        d = to_date(value)
        return float(d.toordinal()) if d else None
    return to_number(value)


def parse_order(value) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").replace(";", ",").split(",")
    return [str(i).strip().upper() for i in items if str(i).strip()]


def dense_tier_points(scores: dict, tiers: list[int], lower_is_better=True) -> dict:
    """Dense-rank distinct scores; tier i gets tiers[i]. Ties share a tier and the
    next distinct score gets the next tier (matches the GL25 Excel formulas)."""
    distinct = sorted({round(v, 9) for v in scores.values()}, reverse=not lower_is_better)
    rank = {v: i for i, v in enumerate(distinct)}
    out = {}
    for player, v in scores.items():
        r = rank[round(v, 9)]
        out[player] = tiers[r] if r < len(tiers) else 0
    return out


# ---------------------------------------------------------------- scoring

def live_value(cat: dict, prices: dict | None):
    """Current (not yet final) value for market-driven categories."""
    if not prices:
        return None
    live = cat.get("live") or {}
    kind = live.get("kind")
    latest = prices.get("latest", {})
    caps = prices.get("market_caps", {})
    if kind == "price":
        return latest.get(live["symbol"])
    if kind == "rank_by_market_cap" and caps:
        items = cat["items"]
        if all(t in caps for t in items):
            return sorted(items, key=lambda t: -caps[t])
    if kind == "market_cap_over_under" and live.get("ticker") in caps:
        return "Over" if caps[live["ticker"]] >= live["threshold"] else "Under"
    if kind == "top_market_cap" and caps:
        names = live.get("names", {})
        avail = {t: c for t, c in caps.items() if t in names}
        if avail:
            top = max(avail, key=avail.get)
            return names[top]
    return None


def score_category(cat: dict, players: list[str], picks: dict, result: dict | None, prices: dict | None):
    """Return dict with status, display result, per-player points and detail."""
    ctype = cat["type"]
    pts_cfg = cat["points"]
    result = result or {}
    status = result.get("status", "pending")
    out = {"status": status, "points": {p: 0 for p in players}, "detail": {}}

    def pick_of(p):
        return (picks.get(p) or {}).get(cat["id"])

    if ctype == "winner_runnerup":
        winner, runner = result.get("winner"), result.get("runner_up")
        # runner_up may be a list when several players tie for 2nd (golf)
        runners = runner if isinstance(runner, list) else ([runner] if runner else [])
        if status == "final" or winner:
            for p in players:
                pk = pick_of(p)
                if same(pk, winner):
                    out["points"][p] = pts_cfg[0]
                elif any(same(pk, r) for r in runners):
                    out["points"][p] = pts_cfg[1]
        out["result"] = {"winner": winner, "runner_up": runner}

    elif ctype == "exact":
        answer = result.get("answer")
        if answer is None and status != "final":
            lv = live_value(cat, prices)
            if lv is not None:
                answer, status = lv, "live"
        if answer is not None:
            for p in players:
                if same(pick_of(p), answer):
                    out["points"][p] = pts_cfg if isinstance(pts_cfg, int) else pts_cfg[0]
        out["result"] = {"answer": answer}

    elif ctype == "closest":
        unit = cat.get("unit")
        value = closest_number(result.get("value"), unit)
        if value is None and status != "final":
            value = closest_number(live_value(cat, prices), unit)
            if value is not None:
                status = "live"
        if value is not None:
            dists = {}
            for p in players:
                n = closest_number(pick_of(p), unit)
                if n is not None:
                    dists[p] = abs(n - value)  # for dates: days early or late
                    out["detail"][p] = {"distance": dists[p]}
            for p, pts in dense_tier_points(dists, pts_cfg).items():
                out["points"][p] = pts
        if unit == "date" and value is not None:
            value = dt.date.fromordinal(int(value)).isoformat()
        out["result"] = {"value": value}

    elif ctype == "ranking":
        order = result.get("order")
        if not order and status != "final":
            order = live_value(cat, prices)
            if order:
                status = "live"
        if order:
            order = [o.upper() for o in order]
            true_pos = {t: i for i, t in enumerate(order)}
            scores = {}
            for p in players:
                guess = parse_order(pick_of(p))
                if sorted(guess) != sorted(order):
                    out["detail"][p] = {"error": "pick is not a full ordering of the list"}
                    continue
                s = sum(abs(i - true_pos[t]) for i, t in enumerate(guess))
                scores[p] = s
                out["detail"][p] = {"score": s}
            for p, pts in dense_tier_points(scores, pts_cfg).items():
                out["points"][p] = pts
        out["result"] = {"order": order}
    else:
        raise ValueError(f"unknown category type {ctype}")

    if status == "pending" and any(out["points"].values()):
        status = "live"
    out["status"] = status
    return out


def score_season(season_id: str) -> dict:
    d = SEASONS / season_id
    season = load_json(d / "season.json")
    picks = load_json(d / "picks.json", {})
    results = load_json(d / "results.json", {})
    prices = load_json(d / "prices.json")
    players = season["players"]

    cats_out = []
    current = {p: 0 for p in players}
    projected = {p: 0 for p in players}
    for cat in season["categories"]:
        res = results.get(cat["id"])
        sc = score_category(cat, players, picks, res, prices)
        for p in players:
            projected[p] += sc["points"][p]
            if sc["status"] == "final":
                current[p] += sc["points"][p]
        cats_out.append({
            **cat,
            "status": sc["status"],
            "result": sc["result"],
            "points_awarded": sc["points"],
            "detail": sc["detail"],
            "picks": {p: (picks.get(p) or {}).get(cat["id"]) for p in players},
            "result_meta": {k: v for k, v in (res or {}).items()
                            if k in ("date", "source", "note", "score")},
        })

    def ranked(totals):
        order = sorted(players, key=lambda p: -totals[p])
        rows, last, rank = [], None, 0
        for i, p in enumerate(order):
            if totals[p] != last:
                rank, last = i + 1, totals[p]
            rows.append({"player": p, "points": totals[p], "rank": rank})
        return rows

    return {
        "season": season,
        "categories": cats_out,
        "current": current,
        "projected": projected,
        "standings_current": ranked(current),
        "standings_projected": ranked(projected),
        "prices": prices,
    }
