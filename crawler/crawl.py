import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import re
import time

INPUT = "../data/hotel_websites.csv"
OUTPUT = "../data/crawled_contacts.csv"

EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)

PRIORITY_WORDS = [
    "contact",
    "contact-us",
    "about",
    "career",
    "careers",
    "job",
    "jobs",
    "recruit",
    "recruitment",
    "team",
    "management",
]

headers = {
    "User-Agent": "Mozilla/5.0"
}

df = pd.read_csv(INPUT)

results = []

for _, row in df.iterrows():

    hotel = row["business_name"]
    website = row["website"]

    print(f"\n[{hotel}]")
    print(website)

    try:
        r = requests.get(
            website,
            headers=headers,
            timeout=15,
            allow_redirects=True
        )

        soup = BeautifulSoup(r.text, "lxml")

        base_domain = urlparse(r.url).netloc

        pages = {
            r.url
        }

        # Find useful internal pages
        for a in soup.find_all("a", href=True):

            href = urljoin(r.url, a["href"])
            parsed = urlparse(href)

            if parsed.netloc != base_domain:
                continue

            text = (
                a.get_text(" ", strip=True)
                + " "
                + href
            ).lower()

            if any(word in text for word in PRIORITY_WORDS):
                pages.add(href)

        emails = set()
        visited = []

        for page in list(pages)[:15]:

            try:

                response = requests.get(
                    page,
                    headers=headers,
                    timeout=15
                )

                visited.append(page)

                # HTML text
                found = EMAIL_RE.findall(response.text)

                for email in found:
                    emails.add(email.lower())

                # mailto
                page_soup = BeautifulSoup(
                    response.text,
                    "lxml"
                )

                for link in page_soup.select(
                    'a[href^="mailto:"]'
                ):
                    email = link["href"][7:].split("?")[0]
                    emails.add(email.lower())

                time.sleep(0.5)

            except Exception as e:
                print("Page error:", e)

        results.append({
            "business_name": hotel,
            "website": website,
            "emails": "; ".join(sorted(emails)),
            "pages_crawled": len(visited),
            "status": "success"
        })

    except Exception as e:

        print("SITE ERROR:", e)

        results.append({
            "business_name": hotel,
            "website": website,
            "emails": "",
            "pages_crawled": 0,
            "status": str(e)
        })

    time.sleep(1)

pd.DataFrame(results).to_csv(
    OUTPUT,
    index=False
)

print("\nFinished.")
