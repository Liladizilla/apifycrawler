import asyncio
import csv
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from apify import Actor


load_dotenv(Path(__file__).with_name(".env"))

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


def build_search_query(destination: str, search_term: str) -> str:
    destination = (destination or "").strip()
    search_term = (search_term or "").strip()
    if destination and search_term:
        return f"{search_term} in {destination}"
    if destination:
        return destination
    return search_term or "business"


def extract_social_links(html: str) -> Dict[str, List[str]]:
    data: Dict[str, List[str]] = {
        "facebook": [],
        "instagram": [],
        "x": [],
        "linkedin": [],
        "youtube": [],
        "whatsapp": [],
        "tiktok": [],
        "threads": [],
    }
    if not html:
        return data

    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        lower = href.lower()
        if "facebook.com" in lower:
            data["facebook"].append(href)
        if "instagram.com" in lower:
            data["instagram"].append(href)
        if "twitter.com" in lower or "x.com" in lower:
            data["x"].append(href)
        if "linkedin.com" in lower:
            data["linkedin"].append(href)
        if "youtube.com" in lower or "youtu.be" in lower:
            data["youtube"].append(href)
        if "wa.me" in lower or "api.whatsapp.com" in lower:
            data["whatsapp"].append(href)
        if "tiktok.com" in lower:
            data["tiktok"].append(href)
        if "threads.net" in lower:
            data["threads"].append(href)

    return {k: list(dict.fromkeys(v)) for k, v in data.items()}


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
    if record.get("social_media"):
        score += 5
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

    social_a = record_a.get("social_media") or {}
    social_b = record_b.get("social_media") or {}
    merged["social_media"] = {
        key: list(dict.fromkeys((social_a.get(key) or []) + (social_b.get(key) or [])))
        for key in set(social_a) | set(social_b)
    }

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
        '[class*="address"]',
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
    social_media = extract_social_links(html)

    record = {
        "business_name": business_name,
        "website": website,
        "source_url": url,
        "phone_numbers": phones,
        "emails": emails,
        "address": address,
        "social_media": {k: v for k, v in social_media.items() if v},
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


async def google_places_lookup(query: str) -> List[Dict[str, Any]]:
    api_key = os.getenv("GOOGLE_PLACES_API_KEY")
    enabled = os.getenv("GOOGLE_PLACES_ENABLED", "false").lower() in {"1", "true", "yes"}
    if not enabled or not api_key:
        return []

    params = {
        "key": api_key,
        "query": query,
    }
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    try:
        response = httpx.get(url, params=params, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        places = data.get("results") or []
        results: List[Dict[str, Any]] = []
        for place in places[:10]:
            phone = place.get("formatted_phone_number") or place.get("international_phone_number") or ""
            website_url = place.get("website") or ""
            results.append({
                "business_name": place.get("name") or "",
                "website": website_url,
                "address": place.get("formatted_address") or "",
                "phone_numbers": extract_phones(phone),
                "emails": [],
                "social_media": {},
                "legal_info": {
                    "source": "google_places_api",
                    "sources": ["google_places_api"],
                    "public_contact_fields": {
                        "phone": bool(phone),
                        "email": False,
                        "address": bool(place.get("formatted_address")),
                    },
                },
            })
        return results
    except Exception:
        return []


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
            "social_media": {},
            "legal_info": {"warning": "No public URL supplied"},
            "quality_score": 0,
        }

    try:
        html = await fetch_html(url)
        record = extract_public_info(business_name, website, url, html)
        places = await google_places_lookup(f"{business_name} {website}")
        if places:
            place = places[0]
            record = merge_records(record, place)
        return record
    except Exception as exc:
        fallback = {
            "business_name": business_name,
            "website": website,
            "source_url": url,
            "phone_numbers": [],
            "emails": [],
            "address": "",
            "social_media": {},
            "legal_info": {
                "warning": "Could not fetch public page",
                "error": str(exc),
            },
            "quality_score": 0,
        }
        places = await google_places_lookup(f"{business_name} {website}")
        if places:
            fallback = merge_records(fallback, places[0])
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
            business_name = row.get("business_name") or row.get("name") or row.get("businessName") or "Unknown business"
            website = row.get("website") or row.get("website_url") or row.get("url") or row.get("Website") or ""
            url = row.get("url") or row.get("page_url") or row.get("contact_url") or website or ""
            if not url:
                continue
            items.append({
                "business_name": business_name,
                "website": website,
                "url": url,
            })
    return items


async def search_area(destination: str, search_term: str, max_results: int = 10) -> List[Dict[str, Any]]:
    query = build_search_query(destination, search_term)
    places = await google_places_lookup(query)
    results: List[Dict[str, Any]] = []
    for place in places[:max_results]:
        business_name = place.get("business_name") or "Unknown business"
        website = place.get("website") or ""
        if website:
            try:
                html = await fetch_html(website)
                record = extract_public_info(business_name, website, website, html)
                record = merge_records(record, place)
                results.append(record)
            except Exception:
                results.append({
                    **place,
                    "business_name": business_name,
                    "website": website,
                    "source_url": website,
                    "social_media": {},
                    "quality_score": score_record(place),
                })
        else:
            record = {
                "business_name": business_name,
                "website": "",
                "source_url": "",
                "phone_numbers": place.get("phone_numbers") or [],
                "emails": [],
                "address": place.get("address") or "",
                "social_media": {},
                "legal_info": place.get("legal_info") or {},
                "quality_score": score_record(place),
            }
            results.append(record)
    return dedupe_and_score(results)


async def main() -> None:
    actor = Actor()
    await actor.init()
    try:
        input_data = await actor.get_input() or {}
        destination = (input_data.get("destination") or input_data.get("location") or input_data.get("area") or "").strip()
        search_term = (input_data.get("search_term") or input_data.get("query") or input_data.get("what") or "").strip()
        max_results = int(input_data.get("max_results") or 10)
        start_urls = input_data.get("startUrls") or []
        csv_file = input_data.get("csv_file") or input_data.get("csvPath")

        if destination or search_term:
            results = await search_area(destination, search_term, max_results=max_results)
            await actor.push_data(results)
            return

        if csv_file:
            start_urls = load_csv_batch(csv_file)
        if not start_urls:
            raise ValueError("Input must include destination + search_term, or startUrls / csv_file for a direct batch run.")

        results = [await process_item(item) for item in start_urls]
        results = dedupe_and_score(results)
        await actor.push_data(results)
    finally:
        await actor.exit()


if __name__ == "__main__":
    asyncio.run(main())
