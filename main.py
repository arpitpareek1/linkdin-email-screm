from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import config
import json
import os

service = Service()
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(ChromeDriverManager().install())

# Open LinkedIn login page
driver.get("https://www.linkedin.com/login")
time.sleep(5)  # Wait for the page to load
hrefs = []

def get_user_url():
    # Find all <a> tags with the class "app-aware-link scale-down"
    a_tags = driver.find_elements(By.CSS_SELECTOR, 'a.app-aware-link.scale-down')

    # Extract href attributes and store them in an array
    hrefs.extend([a.get_attribute('href') for a in a_tags])

def isLogin():
    return os.path.isfile(os.path.join(os.getcwd(), "cookies.json"))

def autoLogin():
    with open("cookies.json", "r", encoding="utf-8") as read_file:
        cookies = json.load(read_file)
        for cookie in cookies:
            driver.add_cookie(cookie)

    driver.refresh()

def scroll_to_bottom():
    # Scroll to the bottom of the page
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(3)

def click_next_button():
    try:
        # Try to find the "Next" button with aria-label="Next"
        next_button = driver.find_element(By.XPATH, '//button[@aria-label="Next"]')
        if next_button.is_enabled():
            next_button.click()
            time.sleep(5)
            return True
        else:
            return False
    except:
        return False

def get_mailto_links_from_page(user_url):
    driver.get(user_url)
    time.sleep(3)  # Wait for the page to load
    
    mailto_links = set()  # Using a set to store unique mailto links
    
    # Check if the contact info link is available and click it
    try:
        contact_info_link = driver.find_element(By.ID, 'top-card-text-details-contact-info')
        contact_info_link.click()
        time.sleep(2.5)  # Wait for contact info to load
        
        # Find mailto links and store them in a set (to avoid duplicates)
        mailto_tags = driver.find_elements(By.XPATH, '//a[starts-with(@href, "mailto:")]')
        for mailto in mailto_tags:
            # Remove the 'mailto:' part from the href and add to the set
            mailto_link = mailto.get_attribute('href').replace("mailto:", "")
            mailto_links.add(mailto_link)
    except Exception:
        print(f"Contact info not found for {user_url}")
    
    return list(mailto_links)  # Convert the set back to a list before returning

if not isLogin():
    print("🔄 Trying to log in LinkedIn...")
    driver.find_element("id", "username").send_keys(config.email)
    driver.find_element("id", "password").send_keys(config.password)
    driver.find_element("xpath", '//button[@type="submit"]').click()
    print("Logged in LinkedIn")
    time.sleep(25)
    bra_cookies = driver.get_cookies()
    with open("cookies.json", "w", encoding="utf-8") as file:
        json.dump(bra_cookies, file)
else:
    autoLogin()

# Open the desired LinkedIn page
target_url = "https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103671728%22%5D&keywords=technical%20recruiter&origin=FACETED_SEARCH&sid=fA%40"  # Replace with the target URL
driver.get(target_url)
time.sleep(5)  # Wait for the page to load

# Extract URLs from the first page
get_user_url()

# Loop to handle pagination and extract URLs from subsequent pages
while True:
    # Scroll to the bottom to load more results
    scroll_to_bottom()

# Click on the "Next" button and wait for the next page to load
    if not click_next_button():
        print("No more pages or the 'Next' button is disabled.")
        break
    
    # Extract URLs from the current page
    get_user_url()

# Collect mailto links from all URLs
all_mailto_links = []

for url in hrefs:
    print(f"Processing {url}...")
    mailto_links = get_mailto_links_from_page(url)
    if mailto_links:
        all_mailto_links.extend(mailto_links)

# Store the results in a file (final-output.txt)
output_file = "final-output.txt"

# If the file doesn't exist, create it and write the collected mailto links
with open(output_file, "a", encoding="utf-8") as file:
    if all_mailto_links:
        for mailto in all_mailto_links:
            file.write(mailto + "\n")

# Close the browser
driver.quit()
