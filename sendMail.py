from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import json

import config

email = config.email
password = config.password
to_recipient= "your email"
subject_text="testing.."
mail_msg="more testing...."

def send_mail():

    # Click on "Compose" button
    compose_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//div[text()="Compose"]'))
    )
    compose_button.click()

    # Wait briefly for compose window to open
    time.sleep(0.5)
    try:
        # Click on "Recipients" (To) field
        to_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[text()="Recipients"]'))
        )
        to_field.click()
    except Exception:
        print("no button Recipients found")
    # Enter recipient email in "To" field
    to_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(
            (By.XPATH, '//textarea[@aria-label="To recipients"]')
        )
    )
    to_input.send_keys(to_recipient)

    # Enter subject
    subject_input = driver.find_element(By.NAME, "subjectbox")
    subject_input.send_keys(subject_text)

    # Enter email body in "Message Body"
    message_body = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//div[@aria-label="Message Body"]'))
    )
    message_body.send_keys(mail_msg)

    # Click on "Send" button
    send_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//div[text()="Send"]'))
    )
    send_button.click()

    print("Email sent successfully!")

def isLogin():
    return os.path.isfile(os.path.join(os.getcwd(), "mail_cookie.json"))


def autoLogin():
    with open("mail_cookie.json", "r", encoding="utf-8") as read_file:
        cookies = json.load(read_file)
        for cookie in cookies:
            driver.add_cookie(cookie)

    driver.refresh()


driver = webdriver.Chrome()
try:
    # Open Gmail login page
    driver.get("https://mail.google.com/mail/u/1/#inbox")

    # Wait until the email input field is present and enter the email
    email_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"]'))
    )
    email_input.send_keys(email)

    # Click on the Next button (div with id 'identifierNext')
    next_button = driver.find_element(By.ID, "identifierNext")
    next_button.click()
    time.sleep(5)
    # Wait for password input to appear, then enter password
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]'))
    )
    password_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
    password_input.send_keys(password)

    # Click on the Next button (div with id 'passwordNext')
    next_button = driver.find_element(By.ID, "passwordNext")
    next_button.click()

    # Wait for a few seconds to load the inbox
    time.sleep(5)

    # Check for any optional buttons and handle them
    try:
        # If there's a "Cancel" button, click it
        cancel_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//span[text()="Cancel"]/ancestor::button')
            )
        )
        cancel_button.click()
        time.sleep(5)
        print("Clicked 'Cancel' button.")
    except Exception:
        print("No 'Cancel' button found.")

    try:
        # If there's a "Not now" button, click it
        not_now_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (By.XPATH, '//span[text()="Not now"]/ancestor::button')
            )
        )
        not_now_button.click()
        time.sleep(5)
        print("Clicked 'Not now' button.")
    except Exception:
        print("No 'Not now' button found.")

    print("Login process completed.")
except Exception:
    print("error")

bra_cookies = driver.get_cookies()
with open("mail_cookie.json", "w", encoding="utf-8") as file:
    json.dump(bra_cookies, file)

send_mail()
