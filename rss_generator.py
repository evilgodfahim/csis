#!/usr/bin/env python3
"""
Scrape https://www.csis.org/analysis and produce rss.xml in repo root.
Designed to run in GitHub Actions (commits RSS file back to repo).
"""
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

BASE_URL = "https://www.csis.org"
START_URL = "https://www.csis.org/analysis"
OUTPUT_FILE = "rss.xml"
MAX_ITEMS = 40  # how many items to include

session = requests.Session()
session.headers.update({
    "User-Agent": "rss-generator-bot/1.0 (+https://github.com/yourname/yourrepo)"
})

def fetch_html(url):
    r = session.get(url, timeout=20)
    r.raise_for_status()
    return r.text

def parse_articles(html):
    soup = BeautifulSoup(html, "html.parser")
    # Try selectors seen in screenshots:
    # 1) article.article-search-listing
    # 2) views-row > article
    results = []

    # primary selection
    articles = soup.select("article.article-search-listing")
    if not articles:
        # fallback: any article within .views-row or top-level article tags
        articles = soup.select(".views-row article")
    if not articles:
        articles = soup.find_all("article")

    for a in articles:
        try:
            # title and relative link
            a_tag = a.select_one("h3 a") or a.select_one("a")
            if not a_tag:
                continue
            title_span = a_tag.select_one("span")
            title = (title_span.get_text(strip=True) if title_span else a_tag.get_text(strip=True))
            href = a_tag.get("href")
            if not href:
                continue
            link = urljoin(BASE_URL, href)

            # summary (teaser)
            summary_div = a.select_one(".search-listing--summary") or a.select_one(".teaser") or a.find("p")
            summary = summary_div.get_text(" ", strip=True) if summary_div else ""

            # try to find a date inside article (time tag, meta, or contributor area)
            pubdate = None
            time_tag = a.find("time")
            if time_tag and time_tag.get("datetime"):
                pubdate = time_tag["datetime"]
            elif time_tag:
                pubdate = time_tag.get_text(strip=True)
            else:
                # look for meta tags or date-like spans
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

    # deduplicate by link and keep order found
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
    """
    Try to convert found date strings into RFC-2822 dates. If fails, return current time.
    Accepts ISO-like strings or common date formats.
    """
    if not pubdate_raw:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    # Try ISO parse
    try:
        # Trim fractional seconds and timezone if present
        dt = None
        # Common ISO formats
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(pubdate_raw.strip(), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                break
            except Exception:
                continue
        if dt is None:
            # Try many common human formats
            for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
                try:
                    dt = datetime.strptime(pubdate_raw.strip(), fmt)
                    dt = dt.replace(tzinfo=timezone.utc)
                    break
                except Exception:
                    continue
        if dt is None:
            raise ValueError
        return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
    except Exception:
        # fallback: current time
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

def build_rss(items):
    # Basic RSS 2.0 feed using ElementTree
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "CSIS — Analysis (custom RSS)"
    ET.SubElement(channel, "link").text = START_URL
    ET.SubElement(channel, "description").text = "Auto-generated RSS feed for CSIS Analysis pages."
    ET.SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
    ET.SubElement(channel, "ttl").text = "60"  # minutes clients can cache

    for it in items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = it["title"]
        ET.SubElement(item, "link").text = it["link"]
        ET.SubElement(item, "guid").text = it["link"]
        ET.SubElement(item, "description").text = it["summary"] or ""
        pubdate = normalize_pubdate(it.get("pubdate_raw"))
        ET.SubElement(item, "pubDate").text = pubdate

    # pretty print (rough) and write file with XML declaration
    xml_bytes = ET.tostring(rss, encoding="utf-8")
    # Add declaration:
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
        print("No items found. Exiting.")
        sys.exit(1)
    build_rss(items)

if __name__ == "__main__":
    main()
