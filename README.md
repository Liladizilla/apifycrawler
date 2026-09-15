# Hotel outreach Apify actor

This repository contains a Python Apify actor for collecting public contact data from hotel websites and, when explicitly authorized, Google Places API lookups.

## What it does

- accepts a batch of hotels through `startUrls`
- accepts a CSV file with `business_name`, `website`, and `url` rows
- fetches public pages and extracts
  - email addresses
  - phone numbers
  - public address text
  - legal/source metadata
- optionally enriches with Google Places API data when `GOOGLE_PLACES_ENABLED=true` and a valid API key is present
- deduplicates results and assigns a quality score
- pushes cleaned records to the Apify dataset

## Legal / compliance note

Only collect information that is openly published by the business itself. Do not scrape Google Maps or similar protected surfaces in violation of their terms. Use the Google Places API only when you are explicitly authorized to do so and have a valid API key.

## Repository structure

- `actor.py` — main actor logic
- `apify.json` — Apify metadata
- `INPUT_SCHEMA.json` — Apify input specification
- `apify_input_example.json` — example payload
- `dataset_schema.json` — dataset schema
- `.env.example` — environment template for Google API credentials
- `requirements.txt` — project dependencies

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
  "startUrls": [
    {
      "business_name": "Green Valley Hotel",
      "website": "https://greenvalleyhotel.co.ke",
      "url": "https://greenvalleyhotel.co.ke/contact"
    }
  ]
}
```

For CSV mode:

```json
{
  "csv_file": "data/hotel_websites.csv"
}
```

The CSV should contain columns such as:

```csv
business_name,website,url
Green Valley Hotel,https://greenvalleyhotel.co.ke,https://greenvalleyhotel.co.ke/contact
```

## Google Places API mode

Create a `.env` file based on `.env.example`:

```bash
GOOGLE_PLACES_ENABLED=true
GOOGLE_PLACES_API_KEY=your_api_key_here
```

Then run the actor with explicit authorized access only.

## Deployment to Apify

1. initialize the git repo and connect your remote
2. push to GitHub
3. create an Apify actor from the repo or sync it with Apify CLI
4. set the environment variables in Apify for Google Places if needed

Example Apify environment values:

```bash
GOOGLE_PLACES_ENABLED=false
GOOGLE_PLACES_API_KEY=
```

## Dataset output shape

Each result includes:

- `business_name`
- `website`
- `source_url`
- `phone_numbers`
- `emails`
- `address`
- `quality_score`
- `legal_info`

## Verification

Local validation command used:

```bash
.venv/bin/python -m py_compile actor.py
```

and a smoke test confirmed extraction for a sample hotel page.
