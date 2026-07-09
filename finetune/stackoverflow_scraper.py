import requests
import json
import os
import re
import time

OUTPUT_PATH = "dataset/stackoverflow_raw.json"
os.makedirs("dataset", exist_ok=True)

BASE_URL = "https://api.stackexchange.com/2.3"

SEARCH_TERMS = [
    "psutil",
    "python psutil",
    "cpu usage python",
    "memory usage python",
    "process monitoring python",
    "windows process python",
    "python performance monitoring",
    "process list psutil",
    "cpu percentage psutil",
    "memory leak python",
    "system monitoring python",
    "python windows api process",
    "python process information",
    "resource monitoring python",
    "python task manager"
]


def clean_html(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_questions(query, pagesize=10):
    params = {
        "site": "stackoverflow",
        "q": query,
        "sort": "votes",
        "order": "desc",
        "pagesize": pagesize,
        "filter": "withbody"
    }

    r = requests.get(
        f"{BASE_URL}/search/advanced",
        params=params,
        timeout=20
    )

    if r.status_code != 200:
        print("Search failed:", r.status_code)
        return []

    return r.json().get("items", [])


def fetch_answers(question_id):
    params = {
        "site": "stackoverflow",
        "sort": "votes",
        "order": "desc",
        "pagesize": 3,
        "filter": "withbody"
    }

    r = requests.get(
        f"{BASE_URL}/questions/{question_id}/answers",
        params=params,
        timeout=20
    )

    if r.status_code != 200:
        return []

    return r.json().get("items", [])


def scrape():

    results = []
    seen = set()

    for term in SEARCH_TERMS:

        print("Searching:", term)

        questions = fetch_questions(term)

        print("Found", len(questions), "questions")

        for q in questions:

            qid = q["question_id"]

            if qid in seen:
                continue

            answers = fetch_answers(qid)

            if not answers:
                continue

            answer = answers[0]

            question = clean_html(
                q["title"] + "\n" + q.get("body", "")
            )

            answer_text = clean_html(
                answer.get("body", "")
            )

            if len(answer_text) < 40:
                continue

            results.append({
                "input": question[:700],
                "output": answer_text[:2500],
                "source": "stackoverflow",
                "score": answer.get("score", 0),
                "keyword": term
            })

            seen.add(qid)

        time.sleep(1)

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf8"
    ) as f:

        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("Collected", len(results), "examples")


if __name__ == "__main__":
    scrape()