import pandas as pd

INPUT = "../data/websites.csv"
OUTPUT = "../data/hotel_websites.csv"

df = pd.read_csv(INPUT)

keywords = [
    "hotel",
    "resort",
    "lodge",
    "guest house",
    "guesthouse",
    "bed & breakfast",
    "bed and breakfast",
    "serviced accommodation",
    "apartment hotel",
]

pattern = "|".join(keywords)

mask = (
    df["category"]
    .fillna("")
    .str.lower()
    .str.contains(pattern, regex=True)
)

hotels = df[mask].copy()

hotels = hotels.drop_duplicates(
    subset=["website"],
    keep="first"
)

hotels.to_csv(OUTPUT, index=False)

print(f"Found {len(hotels)} hotel-like businesses")
print(hotels[["business_name", "category", "website"]].to_string(index=False))