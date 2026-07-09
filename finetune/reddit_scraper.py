import praw
import json
import os
import time

# ── Reddit API credentials ────────────────────────────────────────────────────
CLIENT_ID     = "YOUR_CLIENT_ID_HERE"
CLIENT_SECRET = "YOUR_CLIENT_SECRET_HERE"
USER_AGENT    = "SentinelAI data collector by u/YOUR_REDDIT_USERNAME"

# ── Output ────────────────────────────────────────────────────────────────────
OUTPUT_PATH = "dataset/reddit_raw.json"
os.makedirs("dataset", exist_ok=True)

# ── Target subreddits and search keywords ─────────────────────────────────────
TARGETS = {
    "techsupport": [
        "high CPU process windows",
        "RAM usage too high",
        "unknown process task manager",
        "svchost.exe high cpu",
        "MsMpEng high cpu",
        "system slow windows 11",
        "suspicious process running",
        "CPU 100 percent windows",
        "dwm.exe high memory",
        "laptop overheating process"
    ],
    "sysadmin": [
        "process monitoring windows",
        "anomaly detection endpoint",
        "unusual process behavior",
        "CPU spike windows server",
        "memory leak windows process",
        "windows performance monitoring"
    ],
    "cybersecurity": [
        "suspicious process windows",
        "malware high CPU",
        "process injection detection",
        "endpoint monitoring tools",
        "behavioral anomaly detection",
        "unknown executable running"
    ],
    "WindowsHelp": [
        "high RAM usage windows 11",
        "CPU usage spike",
        "process using too much memory",
        "task manager unusual process",
        "windows running slow processes"
    ],
    "antivirus": [
        "MsMpEng.exe high CPU normal",
        "windows defender scanning cpu",
        "false positive process",
        "high cpu after scan"
    ]
}

def is_good_answer(comment) -> bool:
    """Filter for quality answers only."""
    if not comment.body:
        return False
    if comment.body in ("[deleted]", "[removed]"):
        return False
    if comment.score < 5:
        return False
    if len(comment.body) < 80:
        return False
    if len(comment.body) > 2500:
        return False
    return True

def clean_text(text: str) -> str:
    """Basic text cleaning."""
    text = text.replace("\n\n", " ").replace("\n", " ")
    text = " ".join(text.split())
    return text.strip()

def scrape():
    reddit = praw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    )

    results = []
    seen_ids = set()

    for subreddit_name, keywords in TARGETS.items():
        print(f"\nScraping r/{subreddit_name}...")
        subreddit = reddit.subreddit(subreddit_name)

        for keyword in keywords:
            print(f"  Searching: '{keyword}'")
            try:
                posts = subreddit.search(keyword, limit=15, sort="relevance")

                for post in posts:
                    if post.id in seen_ids:
                        continue
                    if post.score < 3:
                        continue
                    if not post.selftext and not post.title:
                        continue

                    # Get top comments
                    post.comments.replace_more(limit=0)
                    good_comments = [
                        c for c in post.comments.list()
                        if is_good_answer(c)
                    ]

                    if not good_comments:
                        continue

                    # Sort by score, take top answer
                    best_comment = sorted(
                        good_comments,
                        key=lambda c: c.score,
                        reverse=True
                    )[0]

                    question = clean_text(post.title)
                    if post.selftext:
                        question += " " + clean_text(post.selftext[:300])

                    answer = clean_text(best_comment.body)

                    results.append({
                        "input": question,
                        "output": answer,
                        "score": best_comment.score,
                        "subreddit": subreddit_name,
                        "post_id": post.id,
                        "keyword": keyword
                    })

                    seen_ids.add(post.id)

                # Respect Reddit rate limits
                time.sleep(1)

            except Exception as e:
                print(f"    Error on '{keyword}': {e}")
                continue

    # Sort by answer quality (upvotes)
    results.sort(key=lambda x: x["score"], reverse=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDone — collected {len(results)} Q&A pairs")
    print(f"Saved to {OUTPUT_PATH}")

    # Print quality breakdown
    high_quality = [r for r in results if r["score"] > 50]
    medium_quality = [r for r in results if 10 < r["score"] <= 50]
    low_quality = [r for r in results if r["score"] <= 10]

    print(f"\nQuality breakdown:")
    print(f"  High quality (50+ upvotes): {len(high_quality)}")
    print(f"  Medium quality (10-50):     {len(medium_quality)}")
    print(f"  Low quality (<10):          {len(low_quality)}")

if __name__ == "__main__":
    scrape()