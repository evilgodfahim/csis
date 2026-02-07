#!/usr/bin/env python3
"""
Scrape https://www.csis.org/analysis and produce rss.xml in repo root.
Uses FlareSolverr if available (http://localhost:8191), with direct-request fallback.
Designed to run in GitHub Actions.
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
    "User-Agent": "rss-generator-bot/1.0"
})


def fetch_html(url):
    """
    Fetch HTML via FlareSolverr first.
    If unavailable or fails, fall back to a normal HTTP GET.
    """
    try:
        payload = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000
        }
        r = session.post(FLARESOLVERR_ENDPOINT, json=payload, timeout=120)
        r.raise_for_status()
        data = r.json()
        solution = data.get("solution") or {}
        html = solution.get("response")
        if isinstance(html, str) and html.strip():
            return html
    except Exception as e:
        print("FlareSolverr fetch failed:", e)

    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.text


def parse_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    results = []

    articles = soup.select("article.article-search-listing")
    if not articles:
        articles = soup.select(".views-row article")
    if not articles:
        articles = soup.find_all("article")

    for a in articles:
        try:
            a_tag = a.select_one("h3 a") or a.select_one("a")
            if not a_tag:
                continue

            title_span = a_tag.select_one("span")
            title = title_span.get_text(strip=True) if title_span else a_tag.get_text(strip=True)

            href = a_tag.get("href")
            if not href:
                continue
            link = urljoin(BASE_URL, href)

            summary_div = (
                a.select_one(".search-listing--summary")
                or a.select_one(".teaser")
                or a.find("p")
            )
            summary = summary_div.get_text(" ", strip=True) if summary_div else ""

            pubdate = None
            time_tag = a.find("time")
            if time_tag and time_tag.get("datetime"):
                pubdate = time_tag["datetime"]
            elif time_tag:
                pubdate = time_tag.get_text(strip=True)
            else:
                date_meta = a.select_one(".contributors, .credit, .byline, .submitted, .date")
                if date_meta:
                    pubdate = date_meta.get_text(" ", strip=True)

            results.append({
                "title": title,
                "link": link,
                "summary": summary,
                "pubdate_raw": pubdate
            })
        except Exception:
            continue

    seen = set()
    dedup = []
    for it in results:
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        dedup.append(it)
        if len(dedup) >= MAX_ITEMS:
            break

    return dedup


def normalize_pubdate(pubdate_raw):
    if not pubdate_raw:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%Y/%m/%d",
    ):
        try:
            dt = datetime.strptime(pubdate_raw.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            pass

    return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")


def build_rss(items):
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    ET.SubElement(channel, "title").text = "CSIS — Analysis (custom RSS)"
    ET.SubElement(channel, "link").text = START_URL
    ET.SubElement(channel, "description").text = "Auto-generated RSS feed for CSIS Analysis pages."
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(
        timezone.utc
    ).strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(channel, "ttl").text = "60"

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it["title"]
        ET.SubElement(item, "link").text = it["link"]
        ET.SubElement(item, "guid").text = it["link"]
        ET.SubElement(item, "description").text = it["summary"] or ""
        ET.SubElement(item, "pubDate").text = normalize_pubdate(it.get("pubdate_raw"))

    xml_bytes = ET.tostring(rss, encoding="utf-8")
    with open(OUTPUT_FILE, "wb") as f:
        f.write(b'<?xml version="1.0" encoding="utf-8"?>\n')
        f.write(xml_bytes)

    print(f"Wrote {OUTPUT_FILE} with {len(items)} items")


def main():
    try:
        html = fetch_html(START_URL)
    except Exception as e:
        print("ERROR fetching:", e)
        sys.exit(1)

    items = parse_articles(html)
    if not items:
        print("No items found.")
        sys.exit(1)

    build_rss(items)


if __name__ == "__main__":
    main()