"""Score every season and write the website's data files.

  python scripts/build.py

Writes site/data/index.json and site/data/<ID>.json. Never reads private/.
Prints a flag report (picks that could not be scored) for Robert to review.
"""
from __future__ import annotations

import datetime as dt

from glcore import ROOT, SEASONS, load_json, save_json, score_season, to_number

SITE_DATA = ROOT / "site" / "data"


def category_market_info(cat: dict, prices: dict | None) -> dict:
    live = cat.get("live") or {}
    if live.get("kind") != "price" or not prices:
        return {}
    sym = live["symbol"]
    return {
        "symbol": sym,
        "start": (prices.get("start") or {}).get("values", {}).get(sym),
        "latest": (prices.get("latest") or {}).get(sym),
    }


def flags_for(scored: dict, players: dict) -> list[str]:
    out = []
    for c in scored["categories"]:
        for pid, pick in c["picks"].items():
            name = players.get(pid, {}).get("name", pid)
            if pick in (None, ""):
                out.append(f"{scored['season']['id']} {c['id']}: no pick for {name}")
            elif c["type"] == "closest" and to_number(pick) is None:
                out.append(f"{scored['season']['id']} {c['id']}: {name}'s pick '{pick}' is not a number")
            elif c["type"] == "ranking" and "error" in c["detail"].get(pid, {}):
                out.append(f"{scored['season']['id']} {c['id']}: {name}'s ranking '{pick}' is incomplete")
    return out


def main():
    index = load_json(SEASONS / "index.json")
    players = {k: v for k, v in load_json(ROOT / "players.json").items() if not k.startswith("_")}
    history = load_json(ROOT / "history.json", []) or []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")

    seasons_meta, all_flags = [], []
    for sid in index["seasons"]:
        scored = score_season(sid)
        season = scored["season"]
        for c in scored["categories"]:
            c["market"] = category_market_info(c, scored["prices"])
        out = {
            "generated_at": now,
            "season": {k: v for k, v in season.items() if k not in ("categories", "source_files")},
            "players": [{"id": p, **players.get(p, {"name": p})} for p in season["players"]],
            "categories": scored["categories"],
            "standings_current": scored["standings_current"],
            "standings_projected": scored["standings_projected"],
            "prices_as_of": (scored["prices"] or {}).get("as_of"),
            "prices_start_date": ((scored["prices"] or {}).get("start") or {}).get("date"),
        }
        save_json(SITE_DATA / f"{sid}.json", out)
        seasons_meta.append({"id": sid, "title": season.get("title", sid), "status": season.get("status"),
                             "settlement_date": season.get("settlement_date")})
        all_flags += flags_for(scored, players)

    save_json(SITE_DATA / "index.json", {
        "generated_at": now, "active": index["active"], "seasons": seasons_meta,
        "players": players, "history": history,
    })
    print(f"Built site data for {', '.join(index['seasons'])} -> {SITE_DATA.relative_to(ROOT)}")
    if all_flags:
        print("\nFLAGS for Robert:")
        for f in all_flags:
            print("  -", f)


if __name__ == "__main__":
    main()
