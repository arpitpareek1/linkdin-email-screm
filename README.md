
LinkedIn HR Email Scraper
Automate LinkedIn searches to extract HR emails effortlessly!

Features
Retrieve email addresses of HRs directly from LinkedIn.
Configure your own search filters and target URL.
Lightweight and easy-to-use automation tool.
Supports Windows systems (Sorry, no macOS support yet!).
Quick Setup
1️⃣ Prepare Your Credentials
Create a config.py file in the project folder with your LinkedIn login credentials:

python
Copy code
# config.py
email = "your_email@example.com"  # Replace with your LinkedIn email
password = "your_password"        # Replace with your LinkedIn password
⚠️ Keep your credentials secure! Avoid sharing or uploading config.py to public repositories.

2️⃣ Install Dependencies
Ensure Python and pip are installed, then run:

bash
Copy code
pip install -r requirements.txt
3️⃣ Chromium Setup (Windows Only)
If Chromium is not already installed, run the following script to set it up:

bash
Copy code
python setup.py
⚠️ This script only works on Windows as macOS support isn’t available (can't afford a Mac 😅).

4️⃣ Run the Script
Once setup is complete, execute the main script:

bash
Copy code
python main.py
Customize Target URL
The script uses LinkedIn's search filters. Update the target URL in main.py to match your requirements:

python
Copy code
target_url = "https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103671728%22%5D&keywords=technical%20recruiter&origin=FACETED_SEARCH&sid=fA%40"
How to Create a Custom URL
Open LinkedIn and perform an advanced search using filters (location, job title, etc.).
Copy the resulting URL.
Replace the value of target_url in main.py with your custom URL.
Visual Flow
Setup: Add credentials → Install dependencies → Set up Chromium.
Run: Execute main.py → Sit back and let the tool scrape HR emails.
Customize: Modify the target URL to focus on specific profiles.
Important Notes
Privacy: This tool is for educational purposes. Abide by LinkedIn's terms of service.
System Support: Windows is fully supported. Linux/macOS support is not provided.
Disclaimer: Use at your own risk. Automating LinkedIn might violate their policies.
