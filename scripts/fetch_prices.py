"""Refresh live market data for a season (default: the active one).

Writes seasons/<ID>/prices.json:
  {"as_of": ..., "source": ..., "latest": {symbol: price}, "market_caps": {ticker: usd},
   "start": {...}  # starting prices, preserved as-is}

Usage:
  python scripts/fetch_prices.py            # active season, latest prices
  python scripts/fetch_prices.py GL26
  python scripts/fetch_prices.py GL26 --start 2025-12-26   # (re)record starting prices
  python scripts/fetch_prices.py GL25 --close-on 2025-12-24  # print closes for a date

Yahoo Finance via yfinance is a convenience feed for interim updates. Final
settlement values go in results.json after checking the official source
(CLAUDE.md §6).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import yfinance as yf

from glcore import SEASONS, load_json, save_json


def season_symbols(season: dict) -> tuple[list[str], list[str]]:
    prices, caps = [], []
    for cat in season["categories"]:
        live = cat.get("live") or {}
        if live.get("kind") == "price":
            prices.append(live["symbol"])
        elif live.get("kind") == "rank_by_market_cap":
            caps += cat["items"]
        elif live.get("kind") == "top_market_cap":
            caps += list(live.get("names", {}).keys())
        elif live.get("kind") == "market_cap_over_under":
            caps.append(live["ticker"])  # e.g. ANT; no data until it lists, which is fine
    return sorted(set(prices)), sorted(set(caps))


def closes(symbols: list[str], start: str, end: str):
    data = yf.download(symbols, start=start, end=end, progress=False,
                       auto_adjust=False, threads=False)["Close"]
    return data


def latest_prices(symbols: list[str]) -> dict:
    out = {}
    for s in symbols:
        try:
            out[s] = round(float(yf.Ticker(s).fast_info["lastPrice"]), 4)
        except Exception as e:  # noqa: BLE001
            print(f"WARN no price for {s}: {e}", file=sys.stderr)
    return out


def market_caps(tickers: list[str]) -> dict:
    out = {}
    for t in tickers:
        try:
            out[t] = int(yf.Ticker(t).fast_info["marketCap"])
        except Exception as e:  # noqa: BLE001
            print(f"WARN no market cap for {t}: {e}", file=sys.stderr)
    return out


def close_on(symbols: list[str], date: str) -> dict:
    d = dt.date.fromisoformat(date)
    data = closes(symbols, (d - dt.timedelta(days=7)).isoformat(), (d + dt.timedelta(days=1)).isoformat())
    row = data.loc[:date].tail(1)
    return {s: round(float(row[s].iloc[0]), 4) for s in symbols if s in row and row[s].notna().iloc[0]}, str(row.index[-1].date())


def refresh_latest(sid: str) -> None:
    season = load_json(SEASONS / sid / "season.json")
    syms, cap_tickers = season_symbols(season)
    path = SEASONS / sid / "prices.json"
    prices = load_json(path, {}) or {}
    prices["latest"] = latest_prices(syms)
    prices["market_caps"] = market_caps(cap_tickers)
    prices["as_of"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    prices["source"] = "Yahoo Finance (yfinance), interim only"
    save_json(path, prices)
    print(f"Updated {path.relative_to(SEASONS.parent)}")


def active_season() -> str:
    idx = load_json(SEASONS / "index.json")
    return idx["active"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("season", nargs="?")
    ap.add_argument("--start", help="record starting prices as the close on this date")
    ap.add_argument("--close-on", help="print closes for this date (no file changes)")
    args = ap.parse_args()

    if not args.season and not args.start and not args.close_on:
        # Daily refresh: the active season plus any next-season preview (for its "Today" values).
        idx = load_json(SEASONS / "index.json")
        for sid in idx["seasons"]:
            st = (load_json(SEASONS / sid / "season.json") or {}).get("status")
            if sid == idx["active"] or st in ("planning", "picks_open"):
                refresh_latest(sid)
        return

    sid = args.season or active_season()
    season = load_json(SEASONS / sid / "season.json")
    syms, cap_tickers = season_symbols(season)

    if args.close_on:
        vals, used = close_on(syms + cap_tickers, args.close_on)
        print(f"Closes for {args.close_on} (last trading day used: {used})")
        for k, v in vals.items():
            print(f"  {k:10s} {v}")
        return

    path = SEASONS / sid / "prices.json"
    prices = load_json(path, {}) or {}

    if args.start:
        vals, used = close_on(syms, args.start)
        prices["start"] = {"date": used, "source": "Yahoo Finance daily close (yfinance)", "values": vals}
    else:
        prices["latest"] = latest_prices(syms)
        prices["market_caps"] = market_caps(cap_tickers)
        prices["as_of"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
        prices["source"] = "Yahoo Finance (yfinance), interim only"
    save_json(path, prices)
    print(f"Updated {path.relative_to(SEASONS.parent)}")


if __name__ == "__main__":
    main()
