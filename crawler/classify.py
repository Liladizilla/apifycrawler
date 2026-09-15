import pandas as pd

INPUT = "../data/crawled_contacts.csv"
OUTPUT = "../data/enriched_contacts.csv"

df = pd.read_csv(INPUT)

def classify(email):

    email = email.lower()

    if any(x in email for x in [
        "hr@",
        "humanresources@",
        "human.resources@",
        "careers@",
        "career@",
        "recruitment@",
        "recruiting@",
        "jobs@"
    ]):
        return "HR / RECRUITMENT"

    if any(x in email for x in [
        "gm@",
        "generalmanager@",
        "manager@",
        "admin@",
        "office@"
    ]):
        return "MANAGEMENT / ADMIN"

    if any(x in email for x in [
        "info@",
        "contact@",
        "hello@",
        "reception@",
        "frontoffice@"
    ]):
        return "GENERAL"

    if any(x in email for x in [
        "reservation@",
        "reservations@",
        "booking@"
    ]):
        return "RESERVATIONS"

    return "OTHER"


rows = []

for _, row in df.iterrows():

    emails = str(row["emails"])

    if emails == "nan" or not emails:
        continue

    for email in emails.split(";"):

        email = email.strip()

        if not email:
            continue

        rows.append({
            "business_name": row["business_name"],
            "website": row["website"],
            "email": email,
            "email_type": classify(email),
            "source": "website crawl"
        })

out = pd.DataFrame(rows)

out = out.drop_duplicates(
    subset=["business_name", "email"]
)

out.to_csv(
    OUTPUT,
    index=False
)

print(f"Found {len(out)} email/contact records")
