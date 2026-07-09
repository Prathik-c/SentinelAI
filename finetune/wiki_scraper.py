import requests
import json
import os
import time

OUTPUT_PATH = "dataset/wiki_raw.json"

os.makedirs("dataset", exist_ok=True)

SEARCH_API = "https://en.wikipedia.org/w/api.php"

SUMMARY_API = "https://en.wikipedia.org/api/rest_v1/page/summary"

TOPICS = [

    "Service Host",

    "Windows Defender",

    "Microsoft Defender Antivirus",

    "Desktop Window Manager",

    "Client Server Runtime Process",

    "Local Security Authority Subsystem Service",

    "Windows Explorer",

    "Task Manager",

    "Windows Update",

    "Malware",

    "Computer virus",

    "Trojan horse (computing)",

    "Rootkit",

    "Spyware",

    "Ransomware",

    "Anomaly detection",

    "Intrusion detection system",

    "Endpoint security",

    "Windows process",

    "Operating system"
]


def search_page(topic):

    params = {
        "action": "query",
        "list": "search",
        "format": "json",
        "srsearch": topic
    }

    r = requests.get(
        SEARCH_API,
        params=params,
        timeout=20
    )

    if r.status_code != 200:
        return None

    data = r.json()

    results = data["query"]["search"]

    if not results:
        return None

    return results[0]["title"]


def fetch_summary(title):

    url = SUMMARY_API + "/" + title.replace(" ", "_")

    r = requests.get(url, timeout=20)

    if r.status_code != 200:
        return None

    data = r.json()

    return {
        "title": data.get("title"),
        "summary": data.get("extract", "")
    }


def scrape():

    dataset = []

    for topic in TOPICS:

        print("Searching:", topic)

        title = search_page(topic)

        if title is None:
            print("Not found")
            continue

        print("Using page:", title)

        summary = fetch_summary(title)

        if summary is None:
            continue

        text = summary["summary"]

        if len(text) < 100:
            continue

        dataset.append({

            "input": f"What is {summary['title']}?",

            "output": text,

            "source": "Wikipedia"

        })

        time.sleep(0.5)

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf8"
    ) as f:

        json.dump(
            dataset,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()

    print("Collected", len(dataset), "articles")


if __name__ == "__main__":
    scrape()