import os
import json
import time
import re
import requests

OUTPUT_PATH = "dataset/hackernews_raw.json"
os.makedirs("dataset", exist_ok=True)

BASE_URL = "https://hn.algolia.com/api/v1/search"

SEARCH_TERMS = [
    "security",
    "malware",
    "windows",
    "python",
    "monitoring",
    "psutil",
    "endpoint",
    "process",
    "performance",
    "AI",
    "cybersecurity"
]


def clean(text):
    text = re.sub("<.*?>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def search(query):

    r = requests.get(
        BASE_URL,
        params={
            "query": query,
            "hitsPerPage": 50
        },
        timeout=20
    )

    if r.status_code != 200:
        return []

    return r.json()["hits"]


def scrape():

    dataset = []

    seen = set()

    for term in SEARCH_TERMS:

        print("Searching:", term)

        hits = search(term)

        print("Found", len(hits))

        for hit in hits:

            title = hit.get("title") or hit.get("story_title")

            text = hit.get("story_text") or hit.get("comment_text")

            if not title or not text:
                continue

            text = clean(text)

            if len(text) < 40:
                continue

            uid = hit["objectID"]

            if uid in seen:
                continue

            dataset.append({

                "input": title,

                "output": text[:1200],

                "source": "hackernews",

                "keyword": term

            })

            seen.add(uid)

        time.sleep(0.5)

    with open(OUTPUT_PATH, "w", encoding="utf8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print("\nCollected", len(dataset), "entries")


if __name__ == "__main__":
    scrape()