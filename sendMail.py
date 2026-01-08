import os
import sys
import time
import ssl
import smtplib
from typing import List

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from email.mime.base import MIMEBase
from email import encoders
from emailcred import email, password


SUBJECT ="Application for Full Stack Developer Position"
TEXT = """
    Hello,
    I hope you are doing well. I am writing to express my interest in the Full Stack Developer position at your company. 
    With over 3 years of experience in building scalable web and IoT applications, I am eager to bring my expertise in React, Node.js, Python, and AWS to your team.
    I can join immediately.
    My technical skills include:
        Frontend: React, Ionic, TypeScript
        Backend: Node.js, Flask, Django, Laravel
        Database: PostgreSQL, MySQL, Redis
        Cloud & DevOps: AWS (EC2, S3, CodeCommit), DigitalOcean
        IoT: MQTT, Arduino
    I am passionate about delivering high-performance, scalable applications and would love the opportunity to contribute to your company's innovative projects. 
    I have attached my resume for your review. Please let me know if we can discuss this opportunity further.

    Looking forward to your response.

    Best regards,
    Arpit Pareek
"""
ATTACHMENT = 'Arpit_Pareek_Resume_FSD.docx'
DELAY = 1.0

def read_recipients() -> List[str]:
    """Read recipients exclusively from emails.txt (one email per line)."""
    default_file = "emails.txt"
    if not os.path.isfile(default_file):
        print(f"Recipients file not found: {default_file}")
        sys.exit(1)
    recipients: List[str] = []
    with open(default_file, "r", encoding="utf-8") as f:
        for line in f:
            addr = line.strip()
            if addr:
                recipients.append(addr)
    seen = set()
    unique: List[str] = []
    for r in recipients:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


def build_message(sender: str, recipient: str, subject: str, text: str | None, attachment: str | None) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if text:
        msg.attach(MIMEText(text, "plain", _charset="utf-8"))
    if attachment:
        try:
            filename = os.path.basename(attachment)
            with open(attachment, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=\"{filename}\"")
            msg.attach(part)
        except FileNotFoundError:
            print(f"Attachment not found, skipping: {attachment}")
    return msg


def main():
    recipients = read_recipients()

    # Establish SMTP connection
    context = ssl.create_default_context()
    server = smtplib.SMTP("smtp.gmail.com", 587)
    try:
        sender = email
        app_password = password
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(sender, app_password)

        for idx, rcpt in enumerate(recipients, start=1):
            print(f"[{idx}/{len(recipients)}] Sending to {rcpt}")
            msg = build_message(sender, rcpt, SUBJECT, TEXT, ATTACHMENT)
            try:
                server.sendmail(sender, [rcpt], msg.as_string())
                print(f"[{idx}/{len(recipients)}] Sent to {rcpt}")
            except Exception as e:
                print(f"[{idx}/{len(recipients)}] Failed to send to {rcpt}: {e}")
            time.sleep(max(0.0, DELAY))
    finally:
        try:
            server.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()

 