import os
import time
import json
import re
from typing import List, Set, Dict, Optional

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from emailcred import link_pass, link_user
from llm_provider import llm_answer, llm_answer_batch
from selenium.webdriver.common.keys import Keys

# ---------------------------------
# Config
# ---------------------------------
JOBS_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search-results/?keywords=reactjs%2C%20nodejs%20Easy%20Apply%2C%20javascript%2C%20full%20stack%20developer%2C%20remote"
)
COOKIES_FILE = "cookies_0.json"


# ---------------------------------
# Driver setup (reuse style from main.py)
# ---------------------------------
service = Service()
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
driver = webdriver.Chrome(service=service, options=options)
wait = WebDriverWait(driver, 15)

# Tracks answers tried for the current open dialog to avoid reusing failing inputs
# Structure: { question_key: set(["value1", "value2"]) }
CURRENT_DIALOG_TRIED: Dict[str, Set[str]] = {}


# ---------------------------------
# Session helpers (single account)
# ---------------------------------

def cookies_path() -> str:
    return os.path.join(os.getcwd(), COOKIES_FILE)


def load_cookies_if_any() -> bool:
    try:
        path = cookies_path()
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            driver.get("https://www.linkedin.com/")
            for c in cookies:
                try:
                    driver.add_cookie(c)
                except Exception:
                    pass
            driver.get("https://www.linkedin.com/feed/")
            # basic readiness
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except Exception:
                pass
            return True
    except Exception:
        pass
    return False


def is_logged_in() -> bool:
    try:
        if "login" in driver.current_url:
            return False
        if driver.find_elements(By.ID, "username"):
            return False
    except Exception:
        pass
    return True


def save_cookies():
    try:
        cookies = driver.get_cookies()
        with open(cookies_path(), "w", encoding="utf-8") as f:
            json.dump(cookies, f)
    except Exception:
        pass


def ensure_logged_in_once():
    # Try cookie session
    driver.delete_all_cookies()
    if load_cookies_if_any():
        if is_logged_in():
            return
    # Manual login once, then save cookies
    driver.get("https://www.linkedin.com/login")
    print("Please complete LinkedIn login in the opened browser window.")
    # Wait until we are out of the login page
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        driver.find_element("id", "username").clear()
        driver.find_element("id", "username").send_keys(link_user)
        driver.find_element("id", "password").clear()
        driver.find_element("id", "password").send_keys(link_pass)
        driver.find_element("xpath", '//button[@type="submit"]').click()
        time.sleep(25)
        WebDriverWait(driver, 20).until(lambda d: "login" not in d.current_url)
    except Exception:
        pass
    if is_logged_in():
        save_cookies()


# ---------------------------------
# Jobs search scraping
# ---------------------------------

def collect_job_links_from_page(seen: Set[str]) -> List[str]:
    links: List[str] = []
    try:
        # Ensure job cards present
        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[data-view-name="job-card"]')))
        cards = driver.find_elements(By.CSS_SELECTOR, 'div[data-view-name="job-card"]')
        print(f"Found {len(cards)} job cards on page.")
        for card in cards:
            try:
                a = card.find_element(By.CSS_SELECTOR, 'a[href*="/jobs/search-results"]')
                print(f"Found job link: {a.get_attribute('href')}")
                href = a.get_attribute("href")
                if not href:
                    continue
                if href not in seen:
                    seen.add(href)
                    links.append(href)
            except Exception:
                continue
    except Exception:
        pass
    return links


def click_view_next_page() -> bool:
    try:
        btn = driver.find_element(By.XPATH, '//button[@aria-label="View next page"]')
        if not btn.is_enabled():
            return False
        # Attempt to capture staleness reference
        try:
            ref = driver.find_element(By.CSS_SELECTOR, 'div[data-view-name="job-card"]')
        except Exception:
            ref = None
        btn.click()
        # wait for page update
        try:
            if ref:
                WebDriverWait(driver, 15).until(EC.staleness_of(ref))
        except Exception:
            pass
        # ensure new content
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[data-view-name="job-card"]'))
            )
        except Exception:
            pass
        return True
    except Exception:
        return False


# ---------------------------------
# Apply flow
# ---------------------------------

# Dataset helpers
DATASET_FILE = os.path.join(os.getcwd(), "data_set.json")

def load_dataset() -> dict:
    try:
        if os.path.exists(DATASET_FILE) and os.path.getsize(DATASET_FILE) > 0:
            with open(DATASET_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_dataset(data: dict) -> None:
    try:
        with open(DATASET_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _first_non_placeholder_option(select_el):
    try:
        options = select_el.find_elements(By.TAG_NAME, "option")
        for opt in options:
            val = (opt.get_attribute("value") or "").strip()
            if val:
                return opt
    except Exception:
        pass
    return None

def fill_missing_dialog_fields():
    """Fill required fields in the open dialog using an LLM for values.
    - Map labels to their inputs by 'for' attribute or nearest following control.
    - For text-like fields, ask LLM for a concise realistic value based on the label and type.
    - For select/radio, collect visible choices and ask LLM to pick one.
    """
    tried = CURRENT_DIALOG_TRIED
    dialog_xpath = '//div[@role="dialog"]'

    def _find_control_for_error(err_el):
        # Try aria-describedby/id linkage
        try:
            described_by = err_el.get_attribute("id")
            if described_by:
                try:
                    ctrl = driver.find_element(By.XPATH, f"{dialog_xpath}//*[@aria-describedby='{described_by}']")
                    return ctrl
                except Exception:
                    pass
        except Exception:
            pass
        # Fallback: nearest form component container
        try:
            container = err_el.find_element(By.XPATH, './ancestor::*[@data-test-single-line-text-form-component or @data-test-form-builder-radio-button or @data-test-dropdown-select-component][1]')
            try:
                return container.find_element(By.XPATH, ".//input|.//textarea|.//select")
            except Exception:
                return None
        except Exception:
            return None

    def _mark_tried(key: Optional[str], val: str):
        if not key:
            return
        s = tried.get(key)
        if s is None:
            s = set()
            tried[key] = s
        s.add(str(val))

    def _has_tried(key: Optional[str], val: str) -> bool:
        if not key:
            return False
        return str(val) in tried.get(key, set())

    # Remove error-based guessing; we will query the LLM directly.

    def _infer_type_from_context(ctrl, msg: str) -> str:
        msg_l = (msg or "").lower()
        tag = (ctrl.tag_name or "").lower() if ctrl else ""
        typ = (ctrl.get_attribute("type") or "").lower() if ctrl and tag == 'input' else ""
        # Checkbox group detection (LinkedIn multipleChoice fieldset)
        try:
            if ctrl is not None:
                in_cb_group = False
                try:
                    ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-checkbox-form-component='true']")
                    in_cb_group = True
                except Exception:
                    in_cb_group = False
                if typ == 'checkbox' or in_cb_group:
                    return 'checkbox'
        except Exception:
            pass
        if tag == 'select':
            return 'select'
        if typ in ('number', 'range'): return 'number'
        if 'decimal' in msg_l and ('larger than 0' in msg_l or 'greater than 0' in msg_l):
            return 'positive_number'
        if typ == 'email' or 'email' in msg_l: return 'email'
        if typ == 'tel' or 'phone' in msg_l or 'mobile' in msg_l: return 'phone'
        if 'url' in msg_l or 'link' in msg_l or 'portfolio' in msg_l or 'github' in msg_l or 'linkedin' in msg_l:
            return 'url'
        if 'year' in msg_l or 'experience' in msg_l or 'ctc' in msg_l or 'salary' in msg_l or 'notice' in msg_l or 'day' in msg_l:
            return 'number'
        if typ == 'file': return 'file'
        if typ == 'radio': return 'radio'
        return 'text'

    # No default guessing; values come from LLM.

    # First, address visible error messages by batching only those fields
    try:
        error_blocks = driver.find_elements(By.CSS_SELECTOR, '[data-test-form-element-error-messages]')
    except Exception:
        error_blocks = []

    if error_blocks:
        batch_items = []
        targets = []  # list of tuples (ctrl, key, kind)
        for err in error_blocks:
            try:
                msg = err.text or ""
                ctrl = _find_control_for_error(err)
                if ctrl is None:
                    continue
                key = None
                try:
                    lbl = ctrl.find_element(By.XPATH, "./ancestor::div[1]//label")
                    key = (lbl.text or '').strip()
                except Exception:
                    pass
                kind = _infer_type_from_context(ctrl, msg)
                if kind == 'file':
                    continue
                tag = (ctrl.tag_name or '').lower()
                typ = (ctrl.get_attribute('type') or '').lower() if tag == 'input' else ''
                item = {"question": key or "", "kind": kind}
                if tag == 'select' or (tag == 'input' and typ == 'radio') or kind == 'checkbox':
                    # collect choices
                    choices = []
                    try:
                        if tag == 'select':
                            opts = ctrl.find_elements(By.TAG_NAME, 'option')
                            for opt in opts:
                                v = (opt.get_attribute('value') or opt.text or '').strip()
                                if v:
                                    choices.append(v)
                        elif tag == 'input' and typ == 'radio':
                            # radio
                            fieldset = None
                            try:
                                fieldset = ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-form-builder-radio-button-form-component='true']")
                            except Exception:
                                fieldset = driver.find_element(By.XPATH, dialog_xpath)
                            radios = fieldset.find_elements(By.XPATH, ".//input[@type='radio']")
                            for r in radios:
                                t = ''
                                try:
                                    rid = r.get_attribute('id')
                                    if rid:
                                        lbl = fieldset.find_element(By.XPATH, f".//label[@for='{rid}']")
                                        t = (lbl.text or '').strip()
                                except Exception:
                                    pass
                                if not t:
                                    try:
                                        t = r.find_element(By.XPATH, "./following-sibling::label").text.strip()
                                    except Exception:
                                        pass
                                if not t:
                                    t = (r.get_attribute('value') or '').strip()
                                if t:
                                    choices.append(t)
                        else:
                            # checkbox group: prefer data-test-text-selectable-option containers
                            try:
                                fs = ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-checkbox-form-component='true']")
                            except Exception:
                                fs = None
                            if fs is not None:
                                try:
                                    items = fs.find_elements(By.CSS_SELECTOR, '[data-test-text-selectable-option]')
                                except Exception:
                                    items = []
                                for it in items:
                                    txt = ''
                                    try:
                                        lbl = it.find_element(By.TAG_NAME, 'label')
                                        txt = (lbl.text or '').strip()
                                    except Exception:
                                        pass
                                    if not txt:
                                        try:
                                            inp = it.find_element(By.TAG_NAME, 'input')
                                            txt = (inp.get_attribute('data-test-text-selectable-option__input') or inp.get_attribute('value') or '').strip()
                                        except Exception:
                                            pass
                                    if txt:
                                        choices.append(txt)
                    except Exception:
                        pass
                    item["choices"] = choices
                batch_items.append(item)
                targets.append((ctrl, key, kind))
            except Exception:
                continue

        if batch_items:
            answers = llm_answer_batch(batch_items)
            for (ctrl, key, kind), ans in zip(targets, answers):
                try:
                    tag = (ctrl.tag_name or '').lower()
                    typ = (ctrl.get_attribute('type') or '').lower() if tag == 'input' else ''
                    if tag in ('input', 'textarea') and typ not in ('radio', 'checkbox'):
                        try:
                            ctrl.clear()
                        except Exception:
                            pass
                        ctrl.send_keys(ans)
                        try:
                            ctrl.send_keys(Keys.TAB)
                        except Exception:
                            pass
                        _mark_tried(key, ans)
                    elif tag == 'select':
                        opts = ctrl.find_elements(By.TAG_NAME, 'option')
                        matched = False
                        for opt in opts:
                            if ((opt.get_attribute('value') or '').strip().lower() == ans.lower()) or ((opt.text or '').strip().lower() == ans.lower()):
                                opt.click(); matched = True; _mark_tried(key, ans); break
                        if not matched:
                            first = _first_non_placeholder_option(ctrl)
                            if first:
                                first.click(); _mark_tried(key, first.get_attribute('value') or first.text or '')
                    elif tag == 'input' and typ == 'radio':
                        _click_radio(ctrl, key, ans)
                except Exception:
                    continue

        # After handling errors specifically, return to let caller retry submit/next
        return
    try:
        labels = driver.find_elements(By.XPATH, f"{dialog_xpath}//label")
    except Exception:
        labels = []

    # No visible errors: batch-fill only empty/unset fields in the dialog
    batch_items = []
    targets = []
    for lbl in labels:
        try:
            question = (lbl.text or "").strip()
            if not question:
                continue
            # try to find associated control via 'for'
            ctrl = None
            for_attr = lbl.get_attribute("for")
            if for_attr:
                try:
                    ctrl = driver.find_element(By.XPATH, f"{dialog_xpath}//*[@id='{for_attr}']")
                except Exception:
                    ctrl = None
            if ctrl is None:
                # fallback: nearest following input/textarea/select within dialog
                try:
                    ctrl = lbl.find_element(By.XPATH, ".//following::input[1]")
                except Exception:
                    ctrl = None
                if ctrl is None:
                    try:
                        ctrl = lbl.find_element(By.XPATH, ".//following::textarea[1]")
                    except Exception:
                        ctrl = None
                if ctrl is None:
                    try:
                        ctrl = lbl.find_element(By.XPATH, ".//following::select[1]")
                    except Exception:
                        ctrl = None

            if ctrl is None:
                continue

            tag = (ctrl.tag_name or "").lower()
            typ = (ctrl.get_attribute("type") or "").lower() if tag == "input" else ""
            # Determine emptiness and prepare batch items
            kind_here = _infer_type_from_context(ctrl, '')
            if tag in ("input", "textarea") and typ not in ("radio", "checkbox"):
                curr = (ctrl.get_attribute('value') or '').strip()
                if curr:
                    continue
                batch_items.append({"question": question, "kind": kind_here})
                targets.append((ctrl, question, 'textlike'))
            elif tag == 'select':
                try:
                    selected = ctrl.get_attribute('value') or ''
                except Exception:
                    selected = ''
                if selected:
                    continue
                choices = []
                try:
                    opts = ctrl.find_elements(By.TAG_NAME, 'option')
                    for opt in opts:
                        v = (opt.get_attribute('value') or opt.text or '').strip()
                        if v:
                            choices.append(v)
                except Exception:
                    pass
                batch_items.append({"question": question, "kind": 'select', "choices": choices})
                targets.append((ctrl, question, 'select'))
            elif tag == 'input' and typ == 'radio':
                # if any checked, skip
                try:
                    name = ctrl.get_attribute('name') or ''
                    if name:
                        any_checked = driver.find_elements(By.XPATH, f"//input[@type='radio' and @name='{name}' and @checked]")
                        if any_checked:
                            continue
                except Exception:
                    pass
                # collect choices
                choices = []
                try:
                    fieldset = None
                    try:
                        fieldset = ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-form-builder-radio-button-form-component='true']")
                    except Exception:
                        fieldset = driver.find_element(By.XPATH, dialog_xpath)
                    radios = fieldset.find_elements(By.XPATH, ".//input[@type='radio']")
                    for r in radios:
                        t = ''
                        try:
                            rid = r.get_attribute('id')
                            if rid:
                                lbl = fieldset.find_element(By.XPATH, f".//label[@for='{rid}']")
                                t = (lbl.text or '').strip()
                        except Exception:
                            pass
                        if not t:
                            try:
                                t = r.find_element(By.XPATH, "./following-sibling::label").text.strip()
                            except Exception:
                                pass
                        if not t:
                            t = (r.get_attribute('value') or '').strip()
                        if t:
                            choices.append(t)
                except Exception:
                    pass
                batch_items.append({"question": question, "kind": 'radio', "choices": choices})
                targets.append((ctrl, question, 'radio'))
            else:
                # Checkbox group: if none checked in the group, ask LLM to pick one.
                try:
                    fs = ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-checkbox-form-component='true']")
                except Exception:
                    fs = None
                if fs is not None:
                    try:
                        any_checked = fs.find_elements(By.XPATH, ".//input[@type='checkbox' and @checked]")
                    except Exception:
                        any_checked = []
                    if any_checked:
                        continue
                    choices = []
                    try:
                        items = fs.find_elements(By.CSS_SELECTOR, '[data-test-text-selectable-option]')
                    except Exception:
                        items = []
                    for it in items:
                        txt = ''
                        try:
                            lbl = it.find_element(By.TAG_NAME, 'label')
                            txt = (lbl.text or '').strip()
                        except Exception:
                            pass
                        if not txt:
                            try:
                                inp = it.find_element(By.TAG_NAME, 'input')
                                txt = (inp.get_attribute('data-test-text-selectable-option__input') or inp.get_attribute('value') or '').strip()
                            except Exception:
                                pass
                        if txt:
                            choices.append(txt)
                    batch_items.append({"question": question, "kind": 'checkbox', "choices": choices})
                    targets.append((ctrl, question, 'checkbox'))
        except Exception:
            continue

    if batch_items:
        answers = llm_answer_batch(batch_items)
        for (ctrl, question, kind_tag), ans in zip(targets, answers):
            try:
                tag = (ctrl.tag_name or '').lower()
                typ = (ctrl.get_attribute('type') or '').lower() if tag == 'input' else ''
                if kind_tag == 'textlike':
                    try:
                        ctrl.clear()
                    except Exception:
                        pass
                    ctrl.send_keys(ans)
                    _mark_tried(question, ans)
                elif kind_tag == 'select':
                    opts = ctrl.find_elements(By.TAG_NAME, 'option')
                    matched = False
                    for opt in opts:
                        if ((opt.get_attribute('value') or '').strip().lower() == ans.lower()) or ((opt.text or '').strip().lower() == ans.lower()):
                            opt.click(); matched = True; _mark_tried(question, ans); break
                    if not matched:
                        first = _first_non_placeholder_option(ctrl)
                        if first:
                            first.click(); _mark_tried(question, first.get_attribute('value') or first.text or '')
                elif kind_tag == 'radio':
                    _click_radio(ctrl, question, ans)
                elif kind_tag == 'checkbox':
                    # Click matching checkbox option within the same fieldset using data-test-text-selectable-option
                    try:
                        fs = ctrl.find_element(By.XPATH, "./ancestor::fieldset[@data-test-checkbox-form-component='true']")
                    except Exception:
                        fs = None
                    candidates = []
                    if fs is not None:
                        try:
                            items = fs.find_elements(By.CSS_SELECTOR, '[data-test-text-selectable-option]')
                        except Exception:
                            items = []
                        for it in items:
                            label_text = ''
                            label_el = None
                            try:
                                label_el = it.find_element(By.TAG_NAME, 'label')
                                label_text = (label_el.text or '').strip()
                            except Exception:
                                label_el = None
                            if not label_text:
                                try:
                                    inp = it.find_element(By.TAG_NAME, 'input')
                                    label_text = (inp.get_attribute('data-test-text-selectable-option__input') or inp.get_attribute('value') or '').strip()
                                except Exception:
                                    pass
                            candidates.append((it, label_el, label_text))
                    # try exact match first
                    picked = False
                    for it, lbl_el, txt in candidates:
                        if (txt or '').strip().lower() == (ans or '').strip().lower():
                            try:
                                try:
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", it)
                                except Exception:
                                    pass
                                try:
                                    if lbl_el is not None:
                                        lbl_el.click()
                                    else:
                                        it.click()
                                except Exception:
                                    # fallback to clicking input
                                    try:
                                        it.find_element(By.TAG_NAME, 'input').click()
                                    except Exception:
                                        pass
                                _mark_tried(question, ans)
                                picked = True
                                break
                            except Exception:
                                pass
                    # if not matched, click first available option
                    if not picked and candidates:
                        it, lbl_el, txt = candidates[0]
                        try:
                            if lbl_el is not None:
                                lbl_el.click()
                            else:
                                it.click()
                        except Exception:
                            try:
                                it.find_element(By.TAG_NAME, 'input').click()
                            except Exception:
                                pass
                        _mark_tried(question, txt)
            except Exception:
                continue


def _click_radio(ctrl_el, question_key: Optional[str], preferred: Optional[str]) -> bool:
    """Click a radio in the same fieldset as ctrl_el.
    - Searches within fieldset[data-test-form-builder-radio-button-form-component]
    - Falls back to dialog scope when fieldset not found
    Preference: preferred -> 'Yes' -> first not tried.
    """
    candidates = []  # list of tuples (input_or_radio_el, label_text, label_el_or_None)

    # Try to scope to the same fieldset
    fs = None
    try:
        fs = ctrl_el.find_element(By.XPATH, "./ancestor::fieldset[@data-test-form-builder-radio-button-form-component='true']")
    except Exception:
        fs = None

    def gather_within(root):
        items = []
        try:
            inputs = root.find_elements(By.XPATH, ".//input[@type='radio']")
        except Exception:
            inputs = []
        for inp in inputs:
            lbl_txt = ''
            lbl_el = None
            try:
                # label by for=ID
                rid = inp.get_attribute('id')
                if rid:
                    try:
                        lbl_el = root.find_element(By.XPATH, f".//label[@for='{rid}']")
                        lbl_txt = (lbl_el.text or '').strip()
                    except Exception:
                        lbl_el = None
                if not lbl_txt:
                    # following-sibling label
                    try:
                        lbl_el2 = inp.find_element(By.XPATH, "./following-sibling::label")
                        lbl_txt = (lbl_el2.text or '').strip() or lbl_txt
                        if lbl_el is None:
                            lbl_el = lbl_el2
                    except Exception:
                        pass
            except Exception:
                pass
            if not lbl_txt:
                lbl_txt = (inp.get_attribute('value') or '').strip()
            items.append((inp, lbl_txt, lbl_el))

        # role radios
        try:
            role_radios = root.find_elements(By.XPATH, ".//*[@role='radiogroup']//*[@role='radio']")
        except Exception:
            role_radios = []
        for rr in role_radios:
            txt = (rr.text or rr.get_attribute('aria-label') or '').strip()
            items.append((rr, txt, None))
        return items

    if fs is not None:
        candidates = gather_within(fs)
    else:
        # Fallback to whole dialog
        try:
            dialog = driver.find_element(By.XPATH, dialog_xpath)
            candidates = gather_within(dialog)
        except Exception:
            candidates = []

    def try_click(elem, lbl_el) -> bool:
        try:
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", elem)
            except Exception:
                pass
            if elem.is_displayed() and elem.is_enabled():
                elem.click()
                return True
        except Exception:
            pass
        # try clicking associated label
        try:
            if lbl_el is not None and lbl_el.is_displayed():
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", lbl_el)
                except Exception:
                    pass
                lbl_el.click()
                return True
        except Exception:
            pass
        # last resort JS click
        try:
            driver.execute_script("arguments[0].click();", elem)
            return True
        except Exception:
            return False

    def matches(txt: str, target: Optional[str]) -> bool:
        if not target:
            return False
        return (txt or '').strip().lower() == str(target).strip().lower()

    # 1) Preferred
    for el, txt, lbl_el in candidates:
        if matches(txt, preferred) and not _has_tried(question_key, txt):
            if try_click(el, lbl_el):
                _mark_tried(question_key, txt)
                return True

    # 2) Yes
    for el, txt, lbl_el in candidates:
        if (txt or '').strip().lower() == 'yes' and not _has_tried(question_key, txt):
            if try_click(el, lbl_el):
                _mark_tried(question_key, txt)
                return True

    # 3) First not tried
    for el, txt, lbl_el in candidates:
        if txt and not _has_tried(question_key, txt):
            if try_click(el, lbl_el):
                _mark_tried(question_key, txt)
                return True

    return False

def easy_apply_on_job(job_url: str):
    try:
        driver.get(job_url)
        # Wait page body
        try:
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            pass

        # Click Easy Apply button
        try:
            apply_btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.ID, "jobs-apply-button-id"))
            )
            apply_btn.click()
        except Exception:
            pass

    # Wait for dialog
        try:
            WebDriverWait(driver, 2).until(
                EC.presence_of_element_located((By.XPATH, '//div[@role="dialog"]'))
            )
            # Reset per-dialog tried cache
            try:
                CURRENT_DIALOG_TRIED.clear()
            except Exception:
                pass
        except Exception:
            return  # No dialog opened, skip

    # Loop through steps
        while True:
            time.sleep(0.5)
            # If submit present and enabled -> try submit; if errors appear, retry up to 3 times
            submit = None
            try:
                submit = driver.find_element(By.XPATH, '//button[@aria-label="Submit application"]')
                if submit.is_enabled():
                    submit.click()
                    time.sleep(0.8)
                    # Check if dialog closed; if still open and errors present, retry filling
                    dialog_still_open = False
                    try:
                        driver.find_element(By.XPATH, '//div[@role="dialog"]')
                        dialog_still_open = True
                    except Exception:
                        dialog_still_open = False
                    if not dialog_still_open:
                        print('Submitted...')
                        break
                    # Retry up to 3 times to resolve errors on submit
                    for _ in range(3):
                        try:
                            errs = driver.find_elements(By.CSS_SELECTOR, '[data-test-form-element-error-messages]')
                        except Exception:
                            errs = []
                        if not errs:
                            # Try submit again
                            try:
                                submit = driver.find_element(By.XPATH, '//button[@aria-label="Submit application"]')
                                if submit.is_enabled():
                                    submit.click()
                                    time.sleep(0.8)
                            except Exception:
                                pass
                            # Check if closed now
                            try:
                                driver.find_element(By.XPATH, '//div[@role="dialog"]')
                                dialog_still_open = True
                            except Exception:
                                dialog_still_open = False
                            if not dialog_still_open:
                                print('Submitted...')
                                break
                        else:
                            fill_missing_dialog_fields()
                            time.sleep(0.5)
                            # Try submit again after filling
                            try:
                                submit = driver.find_element(By.XPATH, '//button[@aria-label="Submit application"]')
                                if submit.is_enabled():
                                    submit.click()
                                    time.sleep(0.8)
                            except Exception:
                                pass
                            # If dialog closes, success
                            try:
                                driver.find_element(By.XPATH, '//div[@role="dialog"]')
                                dialog_still_open = True
                            except Exception:
                                dialog_still_open = False
                            if not dialog_still_open:
                                print('Submitted...')
                                break
                    else:
                        # After retries, still open -> close and skip this job
                        try:
                            close_btn = driver.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                            if close_btn.is_displayed():
                                close_btn.click()
                        except Exception:
                            pass
                        return
            except Exception:
                pass

                # Otherwise try Continue or Review
                next_btn = None
                try:
                    # Prefer enabled ones
                    cands = driver.find_elements(By.XPATH,
                        '//button[@aria-label="Continue to next step" or @aria-label="Review your application"]')
                    for b in cands:
                        if b.is_enabled():
                            next_btn = b
                            break
                except Exception:
                    pass

                if next_btn is not None:
                    try:
                        next_btn.click()
                        time.sleep(0.5)
                        # If errors appear after clicking Next/Review, attempt to fix and retry up to 3 times
                        for _ in range(3):
                            try:
                                text_inputs = driver.find_elements(By.CSS_SELECTOR, 'div[data-test-single-line-text-form-component]')
                            except Exception:
                                text_inputs = []
                            try:
                                error_elems = driver.find_elements(By.CSS_SELECTOR, '[data-test-form-element-error-messages]')
                            except Exception:
                                error_elems = []
                            if not text_inputs and not error_elems:
                                break
                            # Fill only fields with errors first (handled inside helper), then retry Next/Review
                            fill_missing_dialog_fields()
                            time.sleep(0.5)
                            # Try clicking an enabled Next/Review again
                            retried = False
                            try:
                                cands = driver.find_elements(By.XPATH,
                                    '//button[@aria-label="Continue to next step" or @aria-label="Review your application"]')
                                for b in cands:
                                    if b.is_enabled():
                                        b.click()
                                        retried = True
                                        break
                            except Exception:
                                pass
                            time.sleep(0.5)
                            if retried:
                                # Re-evaluate; if cleaned up, we move on; else loop will try again
                                continue
                        else:
                            # After retries, still errors -> close and skip this job
                            try:
                                close_btn = driver.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                                if close_btn.is_displayed():
                                    close_btn.click()
                            except Exception:
                                pass
                            return
                    except Exception:
                        # If can't click, treat as blocked, stop for this job
                        break
                    continue

                # If we reached here, either no next/review visible or all disabled => stop
                break

            # Try closing dialog if still open (best-effort)
            try:
                close_btn = driver.find_element(By.XPATH, '//button[@aria-label="Dismiss"]')
                if close_btn.is_displayed():
                    close_btn.click()
                CURRENT_DIALOG_TRIED.clear()
            except Exception:
                pass
    except Exception:
        pass


# ---------------------------------
# Main
# ---------------------------------

def main():
    try:
        ensure_logged_in_once()
        # Navigate to search URL
        driver.get(JOBS_SEARCH_URL)
        try:
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, 'div[data-view-name="job-card"]')))
        except Exception:
            pass

        all_links: List[str] = []
        seen: Set[str] = set()

        while True:
            # Collect links on current page
            page_links = collect_job_links_from_page(seen)
            all_links.extend(page_links)

            # Try go next page
            moved = click_view_next_page()
            # if not moved:
            break

        # Process collected job URLs
        print(f"Collected {len(all_links)} job links. Starting Easy Apply...")
        for i, url in enumerate(all_links, start=1):
            easy_apply_on_job(url)
            # small jitter
            time.sleep(0.7)
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
