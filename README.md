# Local business lookup Apify actor

This repository contains a Python Apify actor for a different use case: a user enters a destination or area and a business type, then the actor discovers matching businesses and returns public contact details when they are legally available.

## What it does

- accepts inputs such as `destination = "Nairobi"` and `search_term = "hotel"`
- optionally accepts `location`, `query`, `area`, and `max_results`
- uses authorized Google Places API results when available
- for each candidate business, looks for public contact data including
  - business name
  - email addresses
  - phone numbers
  - website link
  - address
  - social media links
- deduplicates results and assigns a quality score
- pushes structured output rows to the Apify dataset

## Important privacy note

The repo does not include a tracked company list. Sensitive business-name datasets should live outside the repository or be loaded at runtime only when needed. The project intentionally avoids committing location-specific customer lists or scraped company names into Git.

## Legal / compliance note

Only handle information that is publicly exposed and legally available. Do not scrape protected surfaces in violation of terms. For Google Maps / Places data, use the official Places API only when authorized and configured with a valid API key.

## Repository structure

- `actor.py` — main actor logic
- `apify.json` — Apify metadata
- `INPUT_SCHEMA.json` — Apify input specification
- `apify_input_example.json` — example payload
- `dataset_schema.json` — dataset schema
- `.env.example` — environment template for Google API credentials
- `requirements.txt` — dependencies

## Local setup

```bash
cd /home/charischara/hotel-outreach
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m py_compile actor.py
```

## Example input

```json
{
  "destination": "Nairobi",
  "search_term": "hotel",
  "max_results": 10
}
```

Legacy direct-run input still works:

```json
{
  "startUrls": [
    {
      "business_name": "Green Valley Hotel",
      "website": "https://greenvalleyhotel.co.ke",
      "url": "https://greenvalleyhotel.co.ke/contact"
    }
  ]
}
```

## Google Places API mode

Create a `.env` file based on `.env.example`:

```bash
GOOGLE_PLACES_ENABLED=true
GOOGLE_PLACES_API_KEY=your_api_key_here
```

Then run the actor only with an authorized Google account and valid API access.

## Dataset output shape

Each result includes:

- `business_name`
- `website`
- `source_url`
- `phone_numbers`
- `emails`
- `address`
- `social_media`
- `quality_score`
- `legal_info`

## Verification

This project was validated with a local smoke test and a compile check:

```bash
.venv/bin/python -m py_compile actor.py
.venv/bin/python -m pytest tests/test_actor.py -q
```
