from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import config
import json
import os
from typing import Optional
from llm_provider import llm_answer

# ----------------------------
# Constants / Configuration
# ----------------------------
SEARCH_URL = (
    "https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103671728%22%5D&keywords=recruiter&origin=GLOBAL_SEARCH_HEADER&sid=VE_"
)
OUTPUT_FILE = "final-output.txt"
MAX_PAGES = 200  # default safety cap, can be changed
PAGE_BREAK_INTERVAL = 30  # take a break after this many pages
BATCH_SIZE = 10  # switch account after every 10 profile visits

service = Service()
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
# # options.add_argument("--headless=new")
# Defer driver creation until after LLM check passes
driver = None

# ----------------------------
# Global state containers
# ----------------------------
hrefs = []
seen_hrefs = set()
written_emails = set()

# ----------------------------
# Functions
# ----------------------------

def get_user_url():
    # Wait for profile links to be present and select stable anchors
    # LinkedIn profile links have data-test-app-aware-link and hrefs containing '/in/'
    WebDriverWait(driver, 15).until(
        EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]'))
    )
    a_tags = driver.find_elements(By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]')

    # Extract hrefs, normalize, and deduplicate
    urls = []
    for a in a_tags:
        href = a.get_attribute('href')
        if not href:
            continue
        # Keep only real profile URLs
        if '/in/' in href:
            # Strip tracking query to avoid duplicates
            base = href.split('?')[0]
            urls.append(base)

    # Deduplicate while preserving order
    seen = set()
    unique_urls = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    # Add only new URLs globally
    for u in unique_urls:
        if u not in seen_hrefs:
            seen_hrefs.add(u)
            hrefs.append(u)

def cookies_path_for(account_index: int) -> str:
    return os.path.join(os.getcwd(), f"cookies_{account_index}.json")

def has_cookies(account_index: int) -> bool:
    return os.path.isfile(cookies_path_for(account_index))

def load_cookies(account_index: int):
    """Load cookies for an account into the current driver session (does not navigate)."""
    try:
        with open(cookies_path_for(account_index), "r", encoding="utf-8") as read_file:
            cookies = json.load(read_file)
            for cookie in cookies:
                driver.add_cookie(cookie)
    except Exception:
        pass

def is_logged_in_current_page():
    # Heuristics: if login form present or URL contains '/login', we're logged out
    if "login" in driver.current_url:
        return False
    try:
        login_inputs = driver.find_elements(By.ID, 'username')
        if login_inputs:
            return False
    except Exception:
        pass
    return True

def save_cookies_for(account_index: int):
    try:
        bra_cookies = driver.get_cookies()
        with open(cookies_path_for(account_index), "w", encoding="utf-8") as file:
            json.dump(bra_cookies, file)
    except Exception:
        pass

def ensure_logged_in_with_account(account_index: int):
    """Ensure logged in as the specified account. Prefer cookies; only do form login once to mint cookies."""
    # Try cookie-based session first
    try:
        driver.delete_all_cookies()
    except Exception:
        pass
    driver.get("https://www.linkedin.com/")
    if has_cookies(account_index):
        load_cookies(account_index)
        driver.get("https://www.linkedin.com/feed/")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        except Exception:
            pass
        if is_logged_in_current_page():
            return

    # Fallback: one-time credential login to mint cookies for this account
    creds = config.cred[account_index]
    driver.get("https://www.linkedin.com/login")
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element("id", "username").clear()
        driver.find_element("id", "username").send_keys(creds['email'])
        driver.find_element("id", "password").clear()
        driver.find_element("id", "password").send_keys(creds['password'])
        driver.find_element("xpath", '//button[@type="submit"]').click()
        WebDriverWait(driver, 20).until(lambda d: "login" not in d.current_url)
        save_cookies_for(account_index)
    except Exception:
        pass

def switch_account(account_index: int):
    """Switch to a different account by reloading its cookies or logging in once if needed."""
    try:
        driver.delete_all_cookies()
    except Exception:
        pass
    driver.get("https://www.linkedin.com/")
    if has_cookies(account_index):
        load_cookies(account_index)
        driver.get("https://www.linkedin.com/feed/")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        except Exception:
            pass
        # If still not logged in (cookies expired), mint new cookies via one login
        if not is_logged_in_current_page():
            ensure_logged_in_with_account(account_index)
    else:
        ensure_logged_in_with_account(account_index)

def scroll_to_bottom():
    # Scroll to the bottom of the page
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)

def load_all_results_on_page(max_scrolls: int = 1):
    """Scrolls incrementally and stops when no new profile anchors appear or max_scrolls hit."""
    try:
        prev_count = len(driver.find_elements(By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]'))
        for _ in range(max_scrolls):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            # time.sleep(0.8)
            # Wait briefly for any new results to render
            WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]'))
            )
            curr_count = len(driver.find_elements(By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]'))
            if curr_count <= prev_count:
                break
            prev_count = curr_count
    except Exception:
        # Fail-soft: do nothing if scrolling/waiting fails
        pass

def click_next_button():
    try:
        # Try to find the "Next" button with aria-label="Next"
        next_button = driver.find_element(By.XPATH, '//button[@aria-label="Next"]')
        if not next_button.is_enabled():
            return False

        # Capture a reference result element to wait for staleness
        try:
            first_result = driver.find_element(By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]')
        except Exception:
            first_result = None

        next_button.click()

        # Wait for page content to update: either staleness of old first result or presence of anchors
        wait = WebDriverWait(driver, 15)
        if first_result:
            try:
                wait.until(EC.staleness_of(first_result))
            except Exception:
                pass
        # Ensure new results are present
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]')))
        return True
    except:
        return False

def get_mailto_links_from_page(user_url):
    # Use the lightweight overlay contact info page instead of loading the full profile
    overlay_url = user_url.rstrip('/') + '/overlay/contact-info/'
    mailto_links = set()

    try:
        driver.get(overlay_url)
        # If redirected to login, re-apply cookies of the current account and retry
        if not is_logged_in_current_page():
            # Attempt to recover session without repeated logins by reapplying current cookies
            # We don't know which account index here; the caller ensures proper account is active.
            driver.get("https://www.linkedin.com/feed/")
            # proceed regardless; caller will ensure login before calling again if needed
            driver.get(overlay_url)
        # Wait for basic DOM readiness
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))

        # Extract mailto links directly
        mailto_tags = driver.find_elements(By.XPATH, '//a[starts-with(@href, "mailto:")]')
        for mailto in mailto_tags:
            href = mailto.get_attribute('href')
            if href and href.startswith('mailto:'):
                mailto_links.add(href.replace('mailto:', ''))

        # Fallback: if none found on overlay, optionally try full profile (still avoid long sleeps)
        if not mailto_links:
            driver.get(user_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            try:
                contact_info_link = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.ID, 'top-card-text-details-contact-info'))
                )
                contact_info_link.click()
                WebDriverWait(driver, 8).until(
                    EC.presence_of_all_elements_located((By.XPATH, '//a[starts-with(@href, "mailto:")]'))
                )
                mailto_tags = driver.find_elements(By.XPATH, '//a[starts-with(@href, "mailto:")]')
                for mailto in mailto_tags:
                    href = mailto.get_attribute('href')
                    if href and href.startswith('mailto:'):
                        mailto_links.add(href.replace('mailto:', ''))
            except Exception:
                print(f"Contact info not found for {user_url}")
    except Exception:
        print(f"Failed to load overlay for {user_url}")

    return list(mailto_links)

# ----------------------------
# Email persistence helpers
# ----------------------------
def load_existing_emails(path: str) -> set:
    existing = set()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    email = line.strip()
                    if email:
                        existing.add(email)
        except Exception:
            pass
    return existing

def append_unique_emails(path: str, emails: list, seen: set) -> None:
    if not emails:
        return
    try:
        with open(path, "a", encoding="utf-8") as file:
            for e in emails:
                if e not in seen:
                    file.write(e + "\n")
                    seen.add(e)
    except Exception:
        pass


# ----------------------------
# Orchestration helpers
# ----------------------------
def wait_for_search_ready(timeout: int = 15):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]'))
        )
    except Exception:
        time.sleep(3)


def paginate_and_collect(max_pages: int = MAX_PAGES, page_break_interval: int = PAGE_BREAK_INTERVAL):
    """Pagination loop that avoids re-scrolling the same page repeatedly.
    For each page:
      1) Load all results via limited incremental scrolls
      2) Extract URLs
      3) Click Next and wait for change; break if no change or no Next
    """
    page_counter = 0
    while True:
        page_counter += 1
        # 1) Load all results on current page with limited scrolls
        load_all_results_on_page(max_scrolls=4)

        # 2) Extract URLs from the current page
        get_user_url()

        if page_counter >= max_pages:
            print(f"Reached max_pages={max_pages}, stopping pagination.")
            break

        # Before clicking Next, capture current URL and a reference anchor to verify change
        current_url = driver.current_url
        try:
            ref_anchor = driver.find_element(By.CSS_SELECTOR, 'a[data-test-app-aware-link][href*="/in/"]')
        except Exception:
            ref_anchor = None

        # 3) Attempt to go to next page
        if not click_next_button():
            print("No more pages or the 'Next' button is disabled.")
            break

        # Wait for actual page change (URL change or staleness of ref anchor)
        wait = WebDriverWait(driver, 15)
        changed = False
        try:
            wait.until(lambda d: d.current_url != current_url)
            changed = True
        except Exception:
            pass
        if not changed and ref_anchor is not None:
            try:
                wait.until(EC.staleness_of(ref_anchor))
                changed = True
            except Exception:
                pass

        if not changed:
            print("Page did not change after clicking Next; stopping to avoid reprocessing the same page.")
            break

        # Small break every N pages to look human
        if page_counter % page_break_interval == 0:
            pause = random.uniform(15, 30)
            print(f"Taking a short break for {pause:.1f}s after {page_counter} pages...")
            time.sleep(pause)


def process_profiles_and_write(urls: list, output_path: str, account_index: Optional[int] = None):
    """Process profiles and write emails.
    If account_index is provided, use only that account for all profiles.
    Otherwise, rotate accounts every BATCH_SIZE profiles.
    """
    global written_emails
    written_emails = load_existing_emails(output_path)
    current_account = None
    total_accounts = len(getattr(config, 'cred', []))
    if total_accounts == 0:
        print("No credentials found in config.cred; cannot process profiles.")
        return

    # If a fixed account is specified, switch once up front
    fixed_account = account_index if account_index is not None else None
    if fixed_account is not None:
        print(f"Switching to fixed account #{fixed_account} for processing all profiles...")
        switch_account(fixed_account)
        current_account = fixed_account

    for idx, url in enumerate(urls, start=1):
        # Determine active account for this iteration
        if fixed_account is None:
            account_for_this = ((idx - 1) // BATCH_SIZE) % total_accounts
            if current_account != account_for_this:
                print(f"Switching to account #{account_for_this} for profiles {idx}..")
                switch_account(account_for_this)
                current_account = account_for_this
        else:
            account_for_this = fixed_account  # no switching per-profile

        print(f"Processing {url} ({idx}/{len(urls)}) using account #{account_for_this}...")
        # Small jitter between profile visits
        time.sleep(random.uniform(0.8, 2.2))
        emails = get_mailto_links_from_page(url)
        if not emails:
            continue
        append_unique_emails(output_path, emails, written_emails)


# ----------------------------
# LLM readiness check
# ----------------------------
def check_llm_ready() -> bool:
    try:
        expected_name = (os.getenv("USER_NAME") or input("Enter your name to verify LLM is working: ").strip())
        if not expected_name:
            print("No name provided; skipping LLM check.")
            return True
        prompt = f"My name is {expected_name}. What is my name? Answer only the name."
        ans = (llm_answer(prompt, "text") or "").strip()
        # Normalize for comparison
        if ans.lower() == expected_name.strip().lower():
            print("LLM check passed.")
            return True
        print(f"LLM check failed. Expected '{expected_name}', got '{ans}'.")
        return False
    except Exception as e:
        print(f"LLM check encountered an error: {e}")
        return False


# ----------------------------
# Main entry point
# ----------------------------
def main():
    # Pre-flight: verify LLM is responding before starting Selenium workflow
    if not check_llm_ready():
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
        return
    # Initialize driver only after LLM readiness is confirmed
    global driver
    driver = webdriver.Chrome(service=service, options=options)
    # Step 1: Use account 0 to collect all profile URLs
    print("Activating account #0 to collect profile URLs...")
    switch_account(0)
    driver.get(SEARCH_URL)
    wait_for_search_ready()

    paginate_and_collect(max_pages=MAX_PAGES, page_break_interval=PAGE_BREAK_INTERVAL)

    # Step 2: Process collected URLs using only account #1 for contact info (fallback to #0 if not available)
    processing_account = 1 if len(getattr(config, 'cred', [])) > 1 else 0
    print(f"Processing collected profiles using account #{processing_account} for contact info...")
    process_profiles_and_write(hrefs, OUTPUT_FILE, account_index=processing_account)

    driver.quit()


if __name__ == "__main__":
    main()
