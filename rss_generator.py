#!/usr/bin/env python3
"""
Scrape https://www.csis.org/analysis and generate rss.xml.
Uses FlareSolverr if available, otherwise falls back to direct HTTP.
DOM selectors match current CSIS markup exactly.
"""

import sys
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

BASE_URL = "https://www.csis.org"
START_URL = "https://www.csis.org/analysis"
OUTPUT_FILE = "rss.xml"
MAX_ITEMS = 40

FLARESOLVERR_ENDPOINT = "http://localhost:8191/v1"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
})


def fetch_html(url):
    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        }
        r = session.post(FLARESOLVERR_ENDPOINT, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        html = (data.get("solution") or {}).get("response")
        if isinstance(html, str) and html.strip():
            return html
    except Exception as e:
        print("FlareSolverr failed:", e)

    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def parse_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    items = []

    for row in soup.select("div.views-row article.article-search-listing"):
        a = row.select_one("h3 a")
        if not a:
            continue

        title = a.get_text(strip=True)
        href = a.get("href")
        if not title or not href:
            continue

        link = urljoin(BASE_URL, href)

        summary_p = row.select_one(".search-listing--summary p")
        summary = summary_p.get_text(" ", strip=True) if summary_p else ""

        date_text = None
        credit = row.select_one(".contributors")
        if credit:
            text = credit.get_text(" ", strip=True)
            if "—" in text:
                date_text = text.split("—")[-1].strip()

        items.append({
            "title": title,
            "link": link,
            "summary": summary,
            "pubdate_raw": date_text
        })

        if len(items) >= MAX_ITEMS:
            break

    return items


def normalize_pubdate(raw):
    if not raw:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    try:
        dt = datetime.strptime(raw, "%B %d, %Y")
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")


def build_rss(items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "CSIS — Analysis"
    ET.SubElement(channel, "link").text = START_URL
    ET.SubElement(channel, "description").text = "Auto-generated CSIS Analysis RSS feed"
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(
        timezone.utc
    ).strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(channel, "ttl").text = "60"

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it["title"]
        ET.SubElement(item, "link").text = it["link"]
        ET.SubElement(item, "guid").text = it["link"]
        ET.SubElement(item, "description").text = it["summary"]
        ET.SubElement(item, "pubDate").text = normalize_pubdate(it["pubdate_raw"])

    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(ET.tostring(rss, encoding="utf-8"))

    print(f"Wrote {OUTPUT_FILE} with {len(items)} items")


def main():
    try:
        html = fetch_html(START_URL)
    except Exception as e:
        print("Fetch failed:", e)
        sys.exit(1)

    items = parse_articles(html)
    build_rss(items)


if __name__ == "__main__":
    main()