import asyncio
import json
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

PORTAL_URL = (
    "https://jobs.dayforcehcm.com/kgs/CANDIDATEPORTAL"
    "?locationString=Virtual&distance=15&locationId=-9999999"
)

KEYWORDS = [
    "network engineer",
    "network administrator",
    "network architect",
    "network manager",
    "it manager",
    "it director",
    "director of it",
    "director of information",
    "director of technology",
    "director of infrastructure",
    "director of operations",
    "director of network",
    "director of security",
    "information technology",
    "infrastructure manager",
    "infrastructure director",
    "systems engineer",
    "systems administrator",
    "systems manager",
    "cybersecurity",
    "security manager",
    "security engineer",
    "nist",
    "compliance",
    "grc",
]

SEEN_FILE = Path("seen_jobs.json")
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "3600"))

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen)))


def job_id(job: dict) -> str:
    return job.get("id") or f"{job['title']}|{job.get('location', '')}"


def matches(job: dict) -> bool:
    text = (job.get("title", "") + " " + job.get("department", "")).lower()
    return any(kw in text for kw in KEYWORDS)


def _extract_from_payload(data) -> list[dict]:
    """Pull job records out of whatever shape the Dayforce API returns."""
    jobs = []

    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        # Try common envelope keys
        for key in ("jobs", "Jobs", "results", "Results", "data", "Data",
                    "jobPostings", "JobPostings", "items", "Items"):
            if key in data and isinstance(data[key], list):
                candidates = data[key]
                break
        else:
            candidates = [data]
    else:
        return jobs

    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = (
            item.get("JobTitle")
            or item.get("jobTitle")
            or item.get("title")
            or item.get("Title")
            or item.get("PositionTitle")
            or item.get("positionTitle")
        )
        if not title:
            continue
        location = (
            item.get("Location")
            or item.get("location")
            or item.get("City")
            or item.get("city")
            or ""
        )
        job_url = (
            item.get("ApplyUrl")
            or item.get("applyUrl")
            or item.get("Url")
            or item.get("url")
            or PORTAL_URL
        )
        dept = (
            item.get("Department")
            or item.get("department")
            or item.get("DepartmentName")
            or ""
        )
        job_id_val = (
            str(item.get("JobPostingId") or item.get("jobPostingId")
                or item.get("Id") or item.get("id") or "")
        )
        jobs.append({
            "id": job_id_val,
            "title": str(title).strip(),
            "location": str(location).strip(),
            "department": str(dept).strip(),
            "url": str(job_url).strip(),
        })

    return jobs


async def fetch_jobs() -> list[dict]:
    api_jobs: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        # Intercept JSON API responses that look like job data
        async def on_response(response):
            url = response.url.lower()
            if response.status != 200:
                return
            ct = response.headers.get("content-type", "")
            if "json" not in ct:
                return
            if not any(kw in url for kw in ("job", "posting", "search", "career", "position")):
                return
            try:
                data = await response.json()
                found = _extract_from_payload(data)
                if found:
                    api_jobs.extend(found)
                    print(f"  API hit: {response.url} → {len(found)} jobs")
            except Exception:
                pass

        page.on("response", on_response)

        print(f"Loading portal: {PORTAL_URL}")
        try:
            await page.goto(PORTAL_URL, wait_until="networkidle", timeout=45_000)
        except Exception as e:
            print(f"  Navigation timeout (proceeding anyway): {e}")

        # Give late API calls a moment to resolve
        await page.wait_for_timeout(4_000)

        if not api_jobs:
            print("  No API jobs captured — falling back to DOM scraping")
            api_jobs = await _dom_scrape(page)

        await browser.close()

    # Deduplicate by id/title+location
    seen_ids: set = set()
    unique: list[dict] = []
    for j in api_jobs:
        key = job_id(j)
        if key not in seen_ids:
            seen_ids.add(key)
            unique.append(j)
    return unique


async def _dom_scrape(page) -> list[dict]:
    """Best-effort DOM scrape when API interception yields nothing."""
    jobs = []
    selectors = [
        "[class*='job-card']",
        "[class*='jobCard']",
        "[class*='job-listing']",
        "[class*='jobListing']",
        "[class*='job-item']",
        "[class*='position']",
        "li[data-job-id]",
        "article[data-job-id]",
    ]
    elements = []
    for sel in selectors:
        try:
            elements = await page.query_selector_all(sel)
            if elements:
                print(f"  DOM selector matched: {sel} ({len(elements)} elements)")
                break
        except Exception:
            continue

    for el in elements:
        try:
            title_el = await el.query_selector(
                "[class*='title'], [class*='Title'], h2, h3, h4, a"
            )
            title = await title_el.inner_text() if title_el else await el.inner_text()
            title = title.strip().splitlines()[0][:120]

            loc_el = await el.query_selector("[class*='location'], [class*='Location']")
            location = (await loc_el.inner_text()).strip() if loc_el else ""

            link_el = await el.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else ""
            if href and not href.startswith("http"):
                href = "https://jobs.dayforcehcm.com" + href

            jobs.append({
                "id": href or title,
                "title": title,
                "location": location,
                "department": "",
                "url": href or PORTAL_URL,
            })
        except Exception:
            continue

    return jobs


def send_email(new_jobs: list[dict]) -> None:
    if not all([SMTP_USER, SMTP_PASS, NOTIFY_EMAIL]):
        print("Email credentials not configured — printing matches:")
        for j in new_jobs:
            print(f"  [{j['title']}] {j['location']}  {j['url']}")
        return

    subject = f"Job Alert: {len(new_jobs)} new matching job(s) at KGS"
    text_lines = ["New matching jobs found at KGS:\n"]
    html_items = ""

    for j in new_jobs:
        dept = f" — {j['department']}" if j["department"] else ""
        text_lines.append(f"• {j['title']}{dept}")
        if j["location"]:
            text_lines.append(f"  Location: {j['location']}")
        text_lines.append(f"  {j['url']}\n")

        html_items += (
            f"<li style='margin-bottom:12px'>"
            f"<strong>{j['title']}</strong>{dept}<br>"
            f"<span style='color:#666'>{j['location']}</span><br>"
            f"<a href='{j['url']}'>{j['url']}</a>"
            f"</li>"
        )

    text_body = "\n".join(text_lines) + f"\nView all jobs: {PORTAL_URL}"
    html_body = f"""
    <html><body style="font-family:sans-serif;max-width:600px;margin:auto">
    <h2 style="color:#1e3a5f">New Job Matches at KGS</h2>
    <ul style="padding-left:20px">{html_items}</ul>
    <p><a href="{PORTAL_URL}">View all open positions</a></p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = NOTIFY_EMAIL
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"Email sent to {NOTIFY_EMAIL}: {len(new_jobs)} new job(s)")


async def check_once() -> None:
    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking jobs...")
    seen = load_seen()

    try:
        all_jobs = await fetch_jobs()
    except Exception as e:
        print(f"Fetch failed: {e}")
        return

    matching = [j for j in all_jobs if matches(j)]
    new_jobs = [j for j in matching if job_id(j) not in seen]

    print(
        f"Total: {len(all_jobs)} | Keyword match: {len(matching)} | New: {len(new_jobs)}"
    )

    if new_jobs:
        send_email(new_jobs)
        seen.update(job_id(j) for j in new_jobs)
        save_seen(seen)
    else:
        print("No new matching jobs.")


async def main() -> None:
    print(f"Job monitor started. Interval: {CHECK_INTERVAL}s")
    print(f"Keywords: {', '.join(KEYWORDS)}\n")
    while True:
        await check_once()
        print(f"Next check in {CHECK_INTERVAL // 60} minutes...")
        await asyncio.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
