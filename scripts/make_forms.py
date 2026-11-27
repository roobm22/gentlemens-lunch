"""Generate the yearly picks materials from seasons/<ID>/season.json.

  python scripts/make_forms.py GL27                      # sheet + form script
  python scripts/make_forms.py GL27 --form-url <URL>     # add the live form link + QR code to the sheet

Writes forms/<ID>/:
  picks_sheet.html  printable sheet for the lunch (open in a browser, Ctrl+P)
  picks_sheet.pdf   the same sheet as a one-page PDF (printed with headless Edge/Chrome)
  build_form.gs     Google Apps Script that builds the Google Form (paste into script.google.com, Run)
  form_map.json     question title -> category id, used by the importer after the form closes

"Today" reference values come from seasons/<ID>/prices.json (run fetch_prices.py first) plus any
"reference" / "reference_text" set on a category in season.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from glcore import ROOT, SEASONS, load_json, save_json

SITE_URL = "https://roobm22.github.io/gentlemens-lunch/"


def fmt(v, unit):
    if v is None:
        return ""
    if unit == "rate":
        return f"{v:.2f}%"
    if unit == "index":
        return f"{v:,.0f}"
    return f"${v:,.0f}" if abs(v) >= 1000 else f"${v:,.2f}"


def points_text(cat):
    t = cat["type"]
    if t == "winner_runnerup":
        return "5 / 3"
    if t == "ranking" or t == "closest":
        return "5 / 3 / 1"
    return str(cat["points"])


def help_text(cat, today):
    t = cat["type"]
    if t == "winner_runnerup":
        h = "5 points if your pick wins it all, 3 if your pick is the runner-up."
        if not cat.get("choices"):
            h += " Type the name; spelling doesn't need to be perfect."
        return h
    if t == "exact":
        n = cat["points"]
        return f"{n} point{'s' if n != 1 else ''} if you're right."
    if t == "ranking":
        return ("For each company, we count how many spots off you are. Lowest total gets 5, then 3, then 1. "
                "Use each company once." + (f" Today's order: {today}." if today else ""))
    if cat.get("unit") == "date":
        h = "Closest date gets 5, next closest 3, then 1, counting days early or late."
        return h + (f" {today}." if today else "")
    unit_hint = {"rate": "a percentage like 4.25", "index": "a number like 7500"}.get(cat.get("unit"), "a number like 150 (no $ or commas)")
    h = f"Closest guess gets 5, next closest 3, then 1. Over or under both count. Enter {unit_hint}."
    if today:
        h += f" Today: {today}."
    return h


def full_help(cat, today):
    """Form help text: how it scores, then exactly how it settles."""
    h = help_text(cat, today)
    if cat.get("settles"):
        h += "\nHow it settles: " + cat["settles"]
    return h


def today_values(season, prices):
    latest = (prices or {}).get("latest", {})
    caps = (prices or {}).get("market_caps", {})
    out = {}
    for c in season["categories"]:
        if c.get("reference_text"):
            out[c["id"]] = c["reference_text"]
        elif c.get("reference") is not None:
            out[c["id"]] = fmt(c["reference"], c.get("unit"))
        elif c["type"] == "ranking" and all(t in caps for t in c["items"]):
            out[c["id"]] = " > ".join(sorted(c["items"], key=lambda t: -caps[t]))
        elif (c.get("live") or {}).get("kind") == "price" and c["live"]["symbol"] in latest:
            out[c["id"]] = fmt(latest[c["live"]["symbol"]], c.get("unit"))
    return out


def nice_date(iso):
    d = dt.date.fromisoformat(iso[:10])
    return d.strftime("%a, %b %d, %Y").replace(" 0", " ")


# ---------------------------------------------------------------- printable sheet

def make_sheet(season, today, form_url, out, as_of=None):
    """One-page printable sheet (US Letter). Each row says how the category settles (sheet_settles: a short
    version of "settles"; the full text is on the website and the form)."""
    groups = []
    for c in season["categories"]:
        if not groups or groups[-1][0] != c["group"]:
            groups.append((c["group"], []))
        groups[-1][1].append(c)
    gnotes = season.get("settlement") or {
        "Sports": "pick the winner",
        "Markets": f"values at the close on {nice_date(season['settlement_date'])} (Bitcoin: 4:00 pm ET)"}
    rows, n = [], 0
    for g, cats in groups:
        note = gnotes.get(g, "")
        rows.append(f'<tr class="grp"><td colspan="5"><span class="g">{html.escape(g)}</span>'
                    f'{" <small>" + html.escape(note) + "</small>" if note else ""}</td></tr>')
        for c in cats:
            n += 1
            if c["type"] == "ranking":
                blank = '<div class="rank">' + "".join(f"<span>{i}.</span>" for i in range(1, 8)) + "</div>"
            elif c.get("choices") and len(c["choices"]) <= 3:
                blank = " &nbsp; ".join(f"&#9744; {html.escape(x)}" for x in c["choices"])
            elif c.get("unit") == "date":
                blank = '<span class="hint">month / day / year</span>'
            else:
                blank = ""
            how = c.get("sheet_settles") or c.get("settles") or c.get("sheet_note") or ""
            rows.append(
                f'<tr><td class="n">{n}</td><td class="cat"><b>{html.escape(c["name"])}</b>'
                f'{"<div class=how>" + html.escape(how) + "</div>" if how else ""}</td>'
                f'<td class="pts">{points_text(c)}</td><td class="today">{html.escape(today.get(c["id"], ""))}</td>'
                f'<td class="ans">{blank}</td></tr>')
    qr = ""
    if form_url:
        qr = (f'<div class="qr"><div id="qr"></div><div>Scan to enter<br>your picks</div></div>'
              '<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>'
              f'<script>new QRCode(document.getElementById("qr"), {{text: {json.dumps(form_url)}, width: 64, height: 64}});</script>')
    today_hdr = "Today"
    if as_of:
        d = dt.date.fromisoformat(as_of[:10])
        today_hdr = f"Today ({d.month}/{d.day})"
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(season['title'])}: Picks</title>
<style>
  :root {{ --green:#0f4d2e; --burgundy:#7b1e30; --line:#d9d3c2; }}
  @page {{ size: letter; margin: 0.35in 0.4in; }}
  * {{ box-sizing: border-box; }}
  body {{ font: 10.5px/1.25 Georgia, 'Times New Roman', serif; color:#1f2420; margin: 0 auto; padding: 16px; max-width: 8.5in; background:#fff;
         -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  header {{ display:flex; justify-content:space-between; align-items:flex-end; gap:14px; border-bottom:2.5px solid var(--green); padding-bottom:5px; }}
  h1 {{ margin:0; font-size:21px; color:var(--green); }}
  .sub {{ margin:2px 0 0; font-size:9.5px; }}
  .right {{ display:flex; gap:12px; align-items:flex-end; }}
  .name {{ font-size:12px; white-space:nowrap; }} .name span {{ display:inline-block; width:150px; border-bottom:1px solid #000; }}
  .qr {{ display:flex; gap:6px; align-items:center; font-size:9px; }}
  table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
  th, td {{ border-bottom:1px solid var(--line); padding:2px 4px; vertical-align:top; text-align:left; }}
  th {{ font: 700 8px/1.2 Arial, Helvetica, sans-serif; text-transform:uppercase; letter-spacing:.05em; color:#555; }}
  tr.grp td {{ background:#efe9d8; padding:2.5px 4px; }}
  tr.grp .g {{ color:var(--green); font-weight:700; letter-spacing:.05em; text-transform:uppercase; font-size:9.5px; }}
  tr.grp small {{ font: 8.5px/1.25 Arial, Helvetica, sans-serif; color:#444; }}
  td.n {{ width:14px; color:#777; }}
  td.cat {{ width:49%; }} td.cat b {{ font-size:11.5px; }}
  .how {{ font: 9px/1.25 Arial, Helvetica, sans-serif; color:#444; margin-top:1px; }}
  td.pts {{ width:46px; white-space:nowrap; }}
  td.today {{ width:92px; color:#555; font: 8.5px/1.25 Arial, Helvetica, sans-serif; }}
  td.ans {{ font-size:10.5px; }}
  .hint {{ color:#aaa; font-size:8px; }}
  .rank {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:1px 6px; }} .rank span {{ border-bottom:1px solid #999; padding-top:5px; font-size:8px; color:#777; }}
  .rules {{ margin:5px 0 0; font: 8.5px/1.35 Arial, Helvetica, sans-serif; color:#333; }} .rules b {{ color:var(--green); }}
  .print {{ margin:8px 0; }}
  @media print {{ body {{ padding:0; max-width:none; }} .print {{ display:none; }} tr {{ break-inside:avoid; }} }}
</style></head><body>
<header><div><h1>{html.escape(season['title'])}: Picks</h1>
<p class="sub"><b>Picks due {nice_date(season['picks_close'])}, 11:59 pm ET</b> &middot; Settles {nice_date(season['settlement_date'])} &middot; {SITE_URL}</p></div>
<div class="right"><div class="name">Name: <span>&nbsp;</span></div>{qr}</div></header>
<p class="print"><button onclick="window.print()">Print this sheet</button></p>
<table><thead><tr><th>#</th><th>Category &amp; how it settles</th><th>Points</th><th>{today_hdr}</th><th>Your pick</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="rules"><b>Scoring.</b> Pick the champion: 5 if your pick wins, 3 if it's the runner-up.
Closest number or date: 5 / 3 / 1 for the three closest, over or under; ties share the points and the next-closest still gets the next tier.
Ranking: add up how many spots off you are for each company; lowest total wins 5 / 3 / 1.
Right answer: points as listed. Ties for first overall are Co-Champions. The winner gets $20 from everyone and the burgundy jacket.
"Today" values are for reference only; official starting prices are locked at the close on the day picks are due.
Full settlement rules for every category: Rules tab at {SITE_URL}</p>
</body></html>"""
    (out / "picks_sheet.html").write_text(page, encoding="utf-8")


BROWSERS = [  # Chrome first: it writes the PDF before exiting (Edge's launcher can return early)
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "google-chrome", "chromium", "chrome", "msedge",
]


def make_pdf(out):
    """Print picks_sheet.html to picks_sheet.pdf with headless Edge/Chrome and check it fits on one page."""
    exe = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if not exe:
        print("WARN no Edge/Chrome found; skipped picks_sheet.pdf")
        return
    src, pdf = out / "picks_sheet.html", out / "picks_sheet.pdf"
    pdf.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([exe, "--headless", "--disable-gpu", f"--user-data-dir={prof}", "--no-pdf-header-footer",
                        "--virtual-time-budget=8000", f"--print-to-pdf={pdf}", src.as_uri()],
                       check=True, capture_output=True, timeout=180)
        for _ in range(20):  # give a detached browser process a moment to finish writing
            if pdf.exists():
                break
            time.sleep(0.5)
    if not pdf.exists():
        print("WARN the browser didn't write picks_sheet.pdf")
        return
    try:
        from pypdf import PdfReader
        pages = len(PdfReader(pdf).pages)
        print(f"PDF: {pages} page{'s' if pages != 1 else ''}" + ("" if pages == 1 else "  <-- WARN: doesn't fit on one page"))
    except ImportError:
        pass


# ---------------------------------------------------------------- Google Form (Apps Script)

def make_form_script(season, today, players, out):
    items, fmap = [], {"Who are you?": "_player"}
    groups_seen = set()
    for c in season["categories"]:
        if c["group"] not in groups_seen:
            groups_seen.add(c["group"])
            if len(groups_seen) > 1:
                items.append({"kind": "page", "title": c["group"]})
            else:
                items.append({"kind": "section", "title": c["group"]})
        title = c["question"]
        h = full_help(c, today.get(c["id"]))
        if c["type"] == "ranking":
            rows = [f"{i}{'st' if i == 1 else 'nd' if i == 2 else 'rd' if i == 3 else 'th'}" for i in range(1, 8)]
            rows[0] += " (largest)"
            rows[-1] += " (smallest)"
            items.append({"kind": "grid", "title": title, "help": h, "rows": rows, "cols": c["items"]})
            fmap[title] = {"id": c["id"], "grid_rows": rows}
            continue
        if c.get("choices"):
            kind = "mc" if len(c["choices"]) <= 3 else "list"
            items.append({"kind": kind, "title": title, "help": h, "choices": c["choices"]})
        elif c["type"] == "closest" and c.get("unit") == "date":
            items.append({"kind": "date", "title": title, "help": h})
        elif c["type"] == "closest":
            items.append({"kind": "number", "title": title, "help": h})
        else:
            items.append({"kind": "text", "title": title, "help": h})
        fmap[title] = c["id"]

    desc = (f"Welcome to the {season['title']} pool! Pick the winners of this year's big events and guess where the markets "
            f"finish on {nice_date(season['settlement_date'])}. Picks are due {nice_date(season['picks_close'])} at 11:59 pm ET. "
            "After you submit, you'll get a link to change your picks until the deadline. "
            "Starting prices for the market picks are locked when the form closes. "
            f"Standings and everyone's picks: {SITE_URL}")
    confirm = f"Your picks are in. Good luck! Follow the standings at {SITE_URL}"
    close_at = dt.datetime.fromisoformat(season["picks_close"]).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    js = f"""// {season['title']}: Google Form builder. Generated by scripts/make_forms.py. Don't hand-edit; regenerate instead.
// How to use: go to https://script.google.com > New project > paste this whole file > Save > Run "buildForm".
// Approve the permissions prompt (it's your own script). Then open View > Logs (or Execution log) for the links.

var TITLE = {json.dumps(season['title'])};
var DESCRIPTION = {json.dumps(desc)};
var CONFIRMATION = {json.dumps(confirm)};
var PLAYERS = {json.dumps([players[p]['name'] for p in season['players']])};
var CLOSE_AT = {json.dumps(close_at)};  // picks deadline (UTC)
var ITEMS = {json.dumps(items, indent=1)};

function buildForm() {{
  var form = FormApp.create(TITLE);
  form.setDescription(DESCRIPTION);
  form.setConfirmationMessage(CONFIRMATION);
  form.setProgressBar(true);
  form.setAllowResponseEdits(true);           // players can fix picks before the deadline
  form.setShowLinkToRespondAgain(false);
  try {{ form.setCollectEmail(false); }} catch (e) {{}}            // no Google account needed
  try {{ form.setLimitOneResponsePerUser(false); }} catch (e) {{}}  // (true would force sign-in)
  try {{ form.setRequireLogin(false); }} catch (e) {{}}

  form.addListItem().setTitle('Who are you?').setChoiceValues(PLAYERS).setRequired(true);

  ITEMS.forEach(function (it) {{
    if (it.kind === 'section') {{ form.addSectionHeaderItem().setTitle(it.title); return; }}
    if (it.kind === 'page') {{ form.addPageBreakItem().setTitle(it.title); return; }}
    var item;
    if (it.kind === 'list') item = form.addListItem().setChoiceValues(it.choices);
    else if (it.kind === 'date') item = form.addDateItem().setIncludesYear(true);
    else if (it.kind === 'mc') item = form.addMultipleChoiceItem().setChoiceValues(it.choices);
    else if (it.kind === 'grid') {{
      item = form.addGridItem().setRows(it.rows).setColumns(it.cols);
      item.setValidation(FormApp.createGridValidation()
        .setHelpText('Use each company once.').requireLimitOneResponsePerColumn().build());
    }} else {{
      item = form.addTextItem();
      if (it.kind === 'number') {{
        item.setValidation(FormApp.createTextValidation()
          .setHelpText('Numbers only (no $ or commas).').requireNumber().build());
      }}
    }}
    item.setTitle(it.title).setHelpText(it.help).setRequired(true);
  }});

  var sheet = SpreadsheetApp.create(TITLE + ' (Responses)');
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());
  try {{ form.setPublished(true); }} catch (e) {{}}

  // Close the form automatically at the deadline.
  PropertiesService.getScriptProperties().setProperty('FORM_ID', form.getId());
  ScriptApp.newTrigger('closeForm').timeBased().at(new Date(CLOSE_AT)).create();

  Logger.log('SHARE THIS LINK with the family: ' + form.getPublishedUrl());
  Logger.log('Edit the form: ' + form.getEditUrl());
  Logger.log('Responses sheet: ' + sheet.getUrl());
}}

function closeForm() {{
  var form = FormApp.openById(PropertiesService.getScriptProperties().getProperty('FORM_ID'));
  form.setAcceptingResponses(false);
  form.setCustomClosedFormMessage('Picks are closed. See everyone\\'s picks at {SITE_URL}');
}}
"""
    (out / "build_form.gs").write_text(js, encoding="utf-8")
    save_json(out / "form_map.json", fmap)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("season")
    ap.add_argument("--form-url")
    ap.add_argument("--no-pdf", action="store_true", help="skip printing picks_sheet.pdf")
    a = ap.parse_args()
    season = load_json(SEASONS / a.season / "season.json")
    prices = load_json(SEASONS / a.season / "prices.json")
    players = {k: v for k, v in load_json(ROOT / "players.json").items() if not k.startswith("_")}
    today = today_values(season, prices)
    out = ROOT / "forms" / a.season
    out.mkdir(parents=True, exist_ok=True)
    make_sheet(season, today, a.form_url, out, as_of=(prices or {}).get("as_of"))
    make_form_script(season, today, players, out)
    print(f"Wrote {out.relative_to(ROOT)}/picks_sheet.html, build_form.gs, form_map.json")
    if not a.no_pdf:
        make_pdf(out)
        print(f"Wrote {out.relative_to(ROOT)}/picks_sheet.pdf")


if __name__ == "__main__":
    main()
