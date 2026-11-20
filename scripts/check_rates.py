"""Transactofix rate check.

Reads the exchange rates that Scopex and Aspora publish on their websites,
updates rates/partners.json (latest rates used by the homepage) and appends
each reading to rates/history.csv. Run by .github/workflows/rate-check.yml.
"""
import datetime
import json
import pathlib
import re
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
PARTNERS = ROOT / "rates" / "partners.json"
HISTORY = ROOT / "rates" / "history.csv"

SCOPEX_RE = r"1\s*{cur}\s*=\s*([\d.,]+)\s*INR"
ASPORA_RE = r"Live Google rate:\s*[^\d\s]*\s*1\s*=\s*[^\d\s]*\s*([\d.,]+)"

SOURCES = [
    {"pair": "EUR-INR", "name": "Scopex", "url": "https://scopex.com/send-money/ireland-to-india/",
     "re": SCOPEX_RE.format(cur="EUR"), "fee": 0, "feeNote": "Zero transfer fee"},
    {"pair": "USD-INR", "name": "Scopex", "url": "https://scopex.com/send-money/us-to-india/",
     "re": SCOPEX_RE.format(cur="USD"), "fee": 0, "feeNote": "Zero transfer fee"},
    {"pair": "EUR-INR", "name": "Aspora", "url": "https://www.aspora.com/live-currency-rates/eur-to-inr",
     "re": ASPORA_RE, "fee": 3, "feeNote": "About 3 EUR, exact fee shown in app; first transfer free"},
    {"pair": "GBP-INR", "name": "Aspora", "url": "https://www.aspora.com/live-currency-rates/gbp-to-inr",
     "re": ASPORA_RE, "fee": 3, "feeNote": "Flat 3 GBP; first transfer free"},
    {"pair": "USD-INR", "name": "Aspora", "url": "https://www.aspora.com/live-currency-rates/usd-to-inr",
     "re": ASPORA_RE, "fee": 2.99, "feeNote": "Flat 2.99 USD"},
]

MAX_GAP = 0.05  # a reading more than 5% away from the mid-market rate is rejected


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mid_market(base, quote):
    """Daily mid-market rate, used only as a sanity check."""
    try:
        with urllib.request.urlopen(f"https://open.er-api.com/v6/latest/{base}", timeout=20) as r:
            return float(json.load(r)["rates"][quote])
    except Exception as e:  # noqa: BLE001
        print(f"  mid-market check unavailable for {base}-{quote}: {e}")
        return None


def read_rate(page, src, wait_seconds=25):
    """Open the page and wait until the rate appears in the visible text."""
    page.goto(src["url"], wait_until="domcontentloaded", timeout=60000)
    pattern = re.compile(src["re"], re.I)
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        try:
            text = page.inner_text("body")
        except Exception:  # page still loading
            text = ""
        m = pattern.search(text)
        if m:
            value = float(m.group(1).replace(",", ""))
            if value > 0:
                return value
        page.wait_for_timeout(1000)
    return None


def run(browser):
    data = json.loads(PARTNERS.read_text(encoding="utf-8"))
    pairs = data.setdefault("pairs", {})
    history_lines = []
    ok, failed = [], []

    context = browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        locale="en-IE",
    )
    page = context.new_page()
    mids = {}

    for src in SOURCES:
        label = f"{src['name']} {src['pair']}"
        try:
            rate = read_rate(page, src)
        except Exception as e:  # noqa: BLE001
            print(f"  {label}: page error: {e}")
            rate = None
        if rate is None:
            print(f"  {label}: no rate found, keeping previous value")
            failed.append(label)
            continue

        base, quote = src["pair"].split("-")
        if src["pair"] not in mids:
            mids[src["pair"]] = mid_market(base, quote)
        mid = mids[src["pair"]]
        if mid and abs(rate - mid) / mid > MAX_GAP:
            print(f"  {label}: {rate} is more than 5% from mid-market {mid}, ignored")
            failed.append(label)
            continue

        checked = utc_now()
        entries = pairs.setdefault(src["pair"], [])
        entry = next((e for e in entries if e.get("name") == src["name"]), None)
        if entry is None:
            entry = {"name": src["name"]}
            entries.append(entry)
        entry.update({"rate": rate, "fee": src["fee"], "feeNote": src["feeNote"],
                      "checked": checked, "source": src["url"]})
        history_lines.append(f"{checked},{src['pair']},{src['name']},{rate},{src['fee']},{src['url']}")
        ok.append(f"{label} = {rate}")
        print(f"  {label}: {rate}")

    context.close()

    if history_lines:
        data["updated"] = utc_now()
        PARTNERS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        existing = HISTORY.read_text(encoding="utf-8") if HISTORY.exists() else "checked_utc,pair,provider,rate,fee,source\n"
        if not existing.endswith("\n"):
            existing += "\n"
        HISTORY.write_text(existing + "\n".join(history_lines) + "\n", encoding="utf-8")

    print(f"Updated: {len(ok)}  Skipped: {len(failed)} {failed if failed else ''}")
    return ok, failed


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ok, _failed = run(browser)
        browser.close()
    # Fail the run (so GitHub emails you) only if nothing could be read at all.
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
