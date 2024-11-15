# LinkedIn HR Email Scraper

> **Automate LinkedIn searches to extract HR emails effortlessly!**

---

## **Features**

- Retrieve email addresses of HRs directly from LinkedIn.
- Configure your own search filters and target URL.
- Lightweight and easy-to-use automation tool.
- Supports **Windows** systems (Sorry, no macOS support yet!).

---

## **Quick Setup**

### 1️⃣ **Prepare Your Credentials**

Create a `config.py` file in the project folder with your LinkedIn login credentials:

```python
# config.py
email = "your_email@example.com"  # Replace with your LinkedIn email
password = "your_password"        # Replace with your LinkedIn password
```
⚠️ Keep your credentials secure! Avoid sharing or uploading config.py to public repositories.

### 2️⃣ Chromium Setup (Windows Only)
If Chromium is not already installed, run the following script to set it up:

```python 
python setup.py
```
⚠️ This script only works on Windows as macOS support isn’t available (can't afford a Mac 😅). Please create one for setup.

### 4️⃣ Run the Script
Once setup is complete, execute the main script:

```python 
python main.py
```

### **Customize Target URL**

The script uses LinkedIn's search filters to focus on specific profiles. To customize this:

1. **Locate the Target URL**:  
   In `main.py`, find the following line:  

   ```python
   target_url = "https://www.linkedin.com/search/results/people/?geoUrn=%5B%22103671728%22%5D&keywords=technical%20recruiter&origin=FACETED_SEARCH&sid=fA%40"

### **Workflow Overview**

1. **Setup**:  
   - Add your credentials in `config.py`.  
   - Install required dependencies.  
   - Set up Chromium (if not already installed).

2. **Run**:  
   - Execute `main.py`.  
   - Sit back and let the tool scrape HR emails for you! 🚀

### **Customize**

- **Modify the Target URL**:  
  Update the `target_url` in `main.py` to match your specific search requirements.  
  Use LinkedIn's search filters to focus on profiles by location, job title, industry, and more.

---

### **Important Notes**

- **Privacy**:  
  This tool is for educational purposes. Always adhere to LinkedIn's terms of service.  

- **System Support**:  
  Only **Windows** is supported at this time. Linux and macOS are not supported.  

- **Disclaimer**:  
  Use this tool at your own risk. Automating LinkedIn may violate their policies.  

---

### **Happy Scraping! 🎉**
