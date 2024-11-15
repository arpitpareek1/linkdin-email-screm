import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json

# Path to the file containing email addresses
file_path = 'emails.txt'

# Read emails from the file
def read_emails(file_path):
    with open(file_path, 'r') as file:
        emails = file.readlines()
    return [email.strip() for email in emails]

# Function to filter duplicates without using set()
def filter_duplicates(emails):
    unique_emails = []
    for email in emails:
        if email not in unique_emails:
            unique_emails.append(email)
        else: 
            print(email)
    return unique_emails

def organize_emails_by_domain(emails):
    domain_dict = {}
    for email in emails:
        broken_email = email.split('@')
        # Split email to get username and domain
        username, domain = broken_email[0], broken_email[1].split('.')[0] 
        
        # Create an entry if domain is not yet in the dictionary
        if domain not in domain_dict:
            domain_dict[domain] = []
        
        # Append user info to the domain entry
        domain_dict[domain].append({
            "name": username,
            "email": email
        })
    
    return domain_dict

# Function to save data to a JSON file
def save_to_json(data, filename="filtered_emails.json"):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)
    print(f"Data saved to {filename}")


# Function to send email
def send_email(receiver_email):
    # Set up the server and login details (use your email server configuration)
    sender_email = "dssadfa7@gmail.com"
    sender_password = "gmnk bpsu sdxk bgbh"
    subject = "Your Subject"
    body = "This is the email body."

    # Create the email
    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain"))

    try:
        # Connect to the server and send the email
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_email, message.as_string())
        print(f"Email sent to {receiver_email}")
    except Exception as e:
        print(f"Failed to send email to {receiver_email}: {e}")

def main():
    emails = read_emails(file_path)
    unique_emails = filter_duplicates(emails)
    for email in unique_emails:
        send_email(email)

    # # Organize emails by domain
    # organized_emails = organize_emails_by_domain(unique_emails)

    # # Save to JSON file
    # save_to_json(organized_emails)

if __name__ == "__main__":
    main()
