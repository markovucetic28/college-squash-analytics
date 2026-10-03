import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser

import requests


SOURCE_URL = "https://gocrimson.com/sports/mens-squash/schedule/2024-25"
ROBOTS_URL = "https://gocrimson.com/robots.txt"
USER_AGENT = "CollegeSquashStudentProject/0.1 (educational research)"


def download_schedule(output_path, metadata_path):
    """Download one official schedule after checking the site's robots policy."""
    output_path = Path(output_path)
    metadata_path = Path(metadata_path)

    robots_response = requests.get(ROBOTS_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    robots_response.raise_for_status()

    robots = robotparser.RobotFileParser()
    robots.set_url(ROBOTS_URL)
    robots.parse(robots_response.text.splitlines())
    if not robots.can_fetch(USER_AGENT, SOURCE_URL):
        raise PermissionError(f"robots.txt does not allow fetching {SOURCE_URL}")

    crawl_delay = robots.crawl_delay(USER_AGENT) or robots.crawl_delay("*") or 0
    if crawl_delay:
        time.sleep(crawl_delay)

    response = requests.get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    response.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(response.content)
    metadata = {
        "source_url": SOURCE_URL,
        "robots_url": ROBOTS_URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "http_status": response.status_code,
        "content_type": response.headers.get("content-type"),
        "crawl_delay_seconds": crawl_delay,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    download_schedule(
        "data/raw/harvard_men_2024_25.html",
        "data/raw/harvard_men_2024_25.metadata.json",
    )
    print("Saved the official Harvard 2024-25 men's schedule and source metadata.")

