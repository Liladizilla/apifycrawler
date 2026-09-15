import asyncio
import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from bs4 import BeautifulSoup
from apify import Actor


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().\-]{7,}\d)")
GOOGLE_PLACES_ENABLED = os.getenv("GOOGLE_PLACES_ENABLED", "false").lower() in {"1", "true", "yes"}


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if not digits:
        return ""
    if digits.startswith("254") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+254" + digits[1:]
    if len(digits) == 9:
        return "+254" + digits
    if len(digits) >= 10:
        return "+" + digits
    return ""


def extract_phones(text: str) -> List[str]:
    if not text:
        return []
    phones = [normalize_phone(match.group(0)) for match in PHONE_RE.finditer(text)]
    phones = [p for p in phones if p]
    return list(dict.fromkeys(phones))


def extract_emails(text: str) -> List[str]:
    if not text:
        return []
    emails = [m.group(0).lower() for m in EMAIL_RE.finditer(text)]
    return list(dict.fromkeys(emails))


def score_record(record: Dict[str, Any]) -> int:
    score = 0
    if record.get("emails"):
        score += 35
    if record.get("phone_numbers"):
        score += 30
    if record.get("address"):
        score += 20
    if record.get("website"):
        score += 10
    if record.get("legal_info", {}).get("source") == "google_places_api":
        score += 10
    return min(score, 100)


def merge_records(record_a: Dict[str, Any], record_b: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(record_a)
    for key in ("phone_numbers", "emails"):
        merged[key] = list(dict.fromkeys((record_a.get(key) or []) + (record_b.get(key) or [])))
    if not merged.get("address"):
        merged["address"] = record_b.get("address") or ""
    if not merged.get("website"):
        merged["website"] = record_b.get("website") or ""
    if not merged.get("source_url"):
        merged["source_url"] = record_b.get("source_url") or ""

    legal = dict(record_a.get("legal_info") or {})
    other_legal = dict(record_b.get("legal_info") or {})
    sources = list(dict.fromkeys((legal.get("sources") or []) + (other_legal.get("sources") or [])))
    legal["sources"] = sources
    legal["source"] = legal.get("source") or other_legal.get("source") or "mixed"
    legal["public_contact_fields"] = {
        "phone": bool(merged.get("phone_numbers")),
        "email": bool(merged.get("emails")),
        "address": bool(merged.get("address")),
    }
    merged["legal_info"] = legal
    merged["quality_score"] = score_record(merged)
    return merged


def dedupe_and_score(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for record in records:
        key_parts = []
        for email in record.get("emails") or []:
            key_parts.append(f"email:{email.lower()}")
        for phone in record.get("phone_numbers") or []:
            key_parts.append(f"phone:{phone}")
        if not key_parts:
            key = f"fallback:{record.get('business_name','').strip().lower()}:{record.get('website','').strip().lower()}"
        else:
            key = key_parts[0]
        if key not in grouped:
            grouped[key] = record
        else:
            grouped[key] = merge_records(grouped[key], record)

    results = list(grouped.values())
    for item in results:
        item["quality_score"] = score_record(item)
    return sorted(results, key=lambda r: r.get("quality_score", 0), reverse=True)


async def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HotelOutreachActor/1.0; +https://example.com)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.text


def extract_address(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        'meta[property="og:street-address"]',
        'meta[name="address"]',
        '[itemprop="streetAddress"]',
        '[itemprop="address"]',
        '[data-testid="address"]',
    ]

    for selector in selectors:
        tag = soup.select_one(selector)
        if tag:
            value = tag.get("content") or tag.get_text(" ", strip=True)
            if value:
                return value.strip()

    text = soup.get_text(" ", strip=True)
    patterns = [
        r"\d+\s+[A-Za-z0-9.()&/-]+(?:\s+[A-Za-z0-9.()&/-]+){0,5},\s*[A-Za-z][A-Za-z .'-]+(?:,\s*[A-Za-z][A-Za-z .'-]+)?",
        r"[A-Za-z0-9.()&/-]+(?:\s+[A-Za-z0-9.()&/-]+){0,5},\s*[A-Za-z][A-Za-z .'-]+(?:,\s*[A-Za-z][A-Za-z .'-]+)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0).strip()
    return ""


def extract_public_info(business_name: str, website: str, url: str, html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    raw_contact_text = " ".join([
        text,
        " ".join(a.get("href", "") for a in soup.select("a[href^='mailto:']")),
        " ".join(a.get("href", "") for a in soup.select("a[href^='tel:']")),
    ])

    emails = extract_emails(raw_contact_text)
    phones = extract_phones(raw_contact_text)
    address = extract_address(html)

    record = {
        "business_name": business_name,
        "website": website,
        "source_url": url,
        "phone_numbers": phones,
        "emails": emails,
        "address": address,
        "legal_info": {
            "source": "public_website",
            "sources": ["public_website"],
            "public_contact_fields": {
                "phone": bool(phones),
                "email": bool(emails),
                "address": bool(address),
            },
            "description": text[:2000],
        },
        "quality_score": 0,
    }
    record["quality_score"] = score_record(record)
    return record


async def google_places_lookup(business_name: str, website: str) -> Optional[Dict[str, Any]]:
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    enabled = os.getenv("GOOGLE_PLACES_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled or not api_key:
        return None

    query = business_name or website or "hotel"
    params = {
        "key": api_key,
        "input": query,
        "inputtype": "textquery",
        "fields": "place_id,formatted_address,international_phone_number,website,name,types",
    }
    url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        place = candidates[0]
        phone = place.get("international_phone_number") or ""
        website_url = place.get("website") or website or ""
        return {
            "business_name": place.get("name") or business_name,
            "website": website_url,
            "address": place.get("formatted_address") or "",
            "phone_numbers": extract_phones(phone),
            "emails": [],
            "legal_info": {
                "source": "google_places_api",
                "sources": ["google_places_api"],
                "public_contact_fields": {
                    "phone": bool(phone),
                    "email": False,
                    "address": bool(place.get("formatted_address")),
                },
            },
        }
    except Exception:
        return None


async def process_item(item: Dict[str, Any]) -> Dict[str, Any]:
    business_name = item.get("business_name") or item.get("name") or "Unknown business"
    website = item.get("website") or item.get("url") or ""
    url = item.get("url") or website

    if not url:
        return {
            "business_name": business_name,
            "website": website,
            "source_url": "",
            "phone_numbers": [],
            "emails": [],
            "address": "",
            "legal_info": {"warning": "No public URL supplied"},
            "quality_score": 0,
        }

    try:
        html = await fetch_html(url)
        record = extract_public_info(business_name, website, url, html)
        google_places_record = await google_places_lookup(business_name, website)
        if google_places_record:
            record = merge_records(record, google_places_record)
        return record
    except Exception as exc:
        fallback = {
            "business_name": business_name,
            "website": website,
            "source_url": url,
            "phone_numbers": [],
            "emails": [],
            "address": "",
            "legal_info": {
                "warning": "Could not fetch public page",
                "error": str(exc),
            },
            "quality_score": 0,
        }
        google_places_record = await google_places_lookup(business_name, website)
        if google_places_record:
            fallback = merge_records(fallback, google_places_record)
        return fallback


def load_csv_batch(csv_path: str) -> List[Dict[str, Any]]:
    path = Path(csv_path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        items: List[Dict[str, Any]] = []
        for row in reader:
            if not row:
                continue
            business_name = (
                row.get("business_name")
                or row.get("name")
                or row.get("businessName")
                or "Unknown business"
            )
            website = (
                row.get("website")
                or row.get("website_url")
                or row.get("url")
                or row.get("Website")
                or ""
            )
            url = row.get("url") or row.get("page_url") or row.get("contact_url") or website or ""
            if not url:
                continue
            items.append({
                "business_name": business_name,
                "website": website,
                "url": url,
            })
    return items


async def main() -> None:
    actor = Actor()
    await actor.init()
    try:
        input_data = await actor.get_input() or {}
        start_urls = input_data.get("startUrls") or []
        csv_file = input_data.get("csv_file") or input_data.get("csvPath")
        if csv_file:
            start_urls = load_csv_batch(csv_file)
        if not start_urls:
            raise ValueError("Input must include a non-empty startUrls list or a valid csv_file path.")

        results = [await process_item(item) for item in start_urls]
        results = dedupe_and_score(results)
        await actor.push_data(results)
    finally:
        await actor.exit()


if __name__ == "__main__":
    asyncio.run(main())
