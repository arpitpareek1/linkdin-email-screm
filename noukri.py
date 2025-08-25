import os
import json
import re
import time
import random
from typing import Dict, Any, List
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ----------------------------
# Config
# ----------------------------
BASE_URL = "https://www.naukri.com/"
SEARCH_URL = (
    "https://www.naukri.com/node-js-developer-react-js-developer-jobs-in-pune?k=node%20js%20developer%2C%20react%20js%20developer&l=pune&experience=3&nignbevent_src=jobsearchDeskGNB"
)
SNAPSHOT_PATH = "noukrisnapshort.json"  # cookies + storages provided by you
OUTPUT_FILE = "naukri-contacts.json"
MAX_PAGES = int(os.getenv("MAX_PAGES", "1000"))  # cap pages; override via env MAX_PAGES

# ----------------------------
# Driver
# ----------------------------
service = Service()
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
# dont load images
options.add_argument("--disable-image-loading")
# options.add_argument("--headless=new")  # optional
driver = webdriver.Chrome(service=service, options=options)

# ----------------------------
# Snapshot helpers (cookies + storage)
# ----------------------------
def load_snapshot(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def clear_web_state(drv):
    drv.delete_all_cookies()
    drv.execute_script("localStorage.clear(); sessionStorage.clear();")

def apply_snapshot(drv, snapshot: Dict[str, Any], base_url: str):
    # Must be on origin to set cookies/storage
    drv.get(base_url)

    # Cookies (JS cannot set HttpOnly, but Selenium can add most)
    drv.delete_all_cookies()
    for c in snapshot.get("cookies", []):
        cookie = {k: v for k, v in c.items() if k in {
            "name", "value", "path", "domain", "secure", "httpOnly", "expiry", "sameSite"
        }}
        try:
            drv.add_cookie(cookie)
        except Exception:
            # Some cookies may fail based on domain/samesite/secure rules
            pass

    # localStorage
    ls = snapshot.get("localStorage", {}) or {}
    if ls:
        drv.execute_script("""
            const data = arguments[0];
            window.localStorage.clear();
            for (const [k, v] of Object.entries(data)) {
              window.localStorage.setItem(k, v);
            }
        """, ls)

    # sessionStorage
    ss = snapshot.get("sessionStorage", {}) or {}
    if ss:
        drv.execute_script("""
            const data = arguments[0];
            window.sessionStorage.clear();
            for (const [k, v] of Object.entries(data)) {
              window.sessionStorage.setItem(k, v);
            }
        """, ss)

    # Let app pick up new state
    drv.refresh()

# ----------------------------
# Scraping helpers
# ----------------------------
def collect_job_links(max_pages: int) -> List[str]:
    links: List[str] = []
    seen = set()

    driver.get(SEARCH_URL)
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))

    page = 1
    while page <= max_pages:
        # Collect a tags with class 'title'
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.title"))
            )
        except Exception:
            pass

        anchors = driver.find_elements(By.CSS_SELECTOR, "a.title")
        for a in anchors:
            try:
                href = a.get_attribute("href")
                if href:
                    full = urljoin(BASE_URL, href)
                    if full not in seen:
                        seen.add(full)
                        links.append(full)
            except Exception:
                continue

        # Find and click Next button:
        # <a class="styles_btn-secondary__2AsIP"><span>Next</span>...</a>
        next_candidates = driver.find_elements(By.CSS_SELECTOR, "a.styles_btn-secondary__2AsIP")
        next_link = None
        for el in next_candidates:
            try:
                span = el.find_element(By.TAG_NAME, "span")
                if span.text.strip().lower() == "next" and el.is_enabled():
                    next_link = el
                    break
            except Exception:
                continue

        if not next_link:
            break  # no more next

        try:
            next_link.click()
        except Exception:
            break

        # Wait for page to update
        time.sleep(random.uniform(2.0, 3.0))
        page += 1

    return links

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
# Simple phone pattern (India and general). You may refine as needed.
# PHONE_RE = re.compile(r"(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}")

def extract_contacts_from_job(url: str) -> Dict[str, Any]:
    data = {"url": url, "emails": []}
    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        # Look for the description container
        # class="styles_job-desc-container__txpYf"
        desc_nodes = driver.find_elements(By.CSS_SELECTOR, ".styles_job-desc-container__txpYf")
        text_blob = " ".join([n.text for n in desc_nodes]) if desc_nodes else driver.page_source

        emails = set(EMAIL_RE.findall(text_blob))
        # phones = set(PHONE_RE.findall(text_blob))

        data["emails"] = sorted(emails)
        # PHONE_RE may capture tuple groups sometimes; normalize to strings
        # flat_phones = set()
        # for ph in phones:
        #     if isinstance(ph, tuple):
        #         ph = "".join(ph)
        #     flat_phones.add(re.sub(r"\s+", " ", ph).strip())
        # data["phones"] = sorted(flat_phones)
    except Exception:
        pass
    return data

def append_results(path: str, items: List[Dict[str, Any]]):
    existing = []
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f) or []
        except Exception:
            existing = []

    # Merge by URL
    by_url = {row.get("url"): row for row in existing if isinstance(row, dict) and "url" in row}
    for it in items:
        u = it.get("url")
        if not u:
            continue
        if u in by_url:
            # merge emails/phones
            prev = by_url[u]
            prev_emails = set(prev.get("emails", []))
            # prev_phones = set(prev.get("phones", []))
            prev_emails.update(it.get("emails", []))
            # prev_phones.update(it.get("phones", []))
            prev["emails"] = sorted(prev_emails)
            # prev["phones"] = sorted(prev_phones)
        else:
            by_url[u] = it

    merged = list(by_url.values())
    with open(path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

# ----------------------------
# Main
# ----------------------------
def main():
    # Apply snapshot to log in without form
    if not os.path.isfile(SNAPSHOT_PATH):
        print(f"Snapshot file not found: {SNAPSHOT_PATH}")
        driver.quit()
        return

    snap = load_snapshot(SNAPSHOT_PATH)
    driver.get(BASE_URL)
    clear_web_state(driver)
    apply_snapshot(driver, snap, BASE_URL)

    # Collect job links with page cap
    print(f"Collecting job links up to {MAX_PAGES} pages...")
    job_links = collect_job_links(MAX_PAGES)
    print(f"Collected {len(job_links)} links.")

    # Visit each job and extract contacts
    results = []
    for idx, link in enumerate(job_links, start=1):
        print(f"[{idx}/{len(job_links)}] Visiting: {link}")
        # time.sleep(random.uniform(0.8, 2.0))  # small jitter
        info = extract_contacts_from_job(link)
        # Only keep if any data found
        if info.get("emails") or info.get("phones"):
            results.append(info)

    append_results(OUTPUT_FILE, results)
    print(f"Saved {len(results)} new entries to {OUTPUT_FILE}")
    driver.quit()

if __name__ == "__main__":
    main()