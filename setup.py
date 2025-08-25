import requests
import wget
import zipfile
import os
import platform
import stat

# Get the latest ChromeDriver version number
version_number = "114.0.5735.90"

# Determine the correct binary name and download URL based on the operating system
system = platform.system().lower()

if system == 'darwin':  # macOS
    binary_name = 'chromedriver_mac64.zip'
elif system == 'windows':
    binary_name = 'chromedriver_win32.zip'
elif system == 'linux':
    binary_name = 'chromedriver_linux64.zip'
else:
    raise OSError(f"Unsupported operating system: {system}")

# Build the download URL
download_url = f"https://chromedriver.storage.googleapis.com/{version_number}/{binary_name}"

# Download the zip file
print(f"Downloading ChromeDriver for {system}...")
try:
    latest_driver_zip = wget.download(download_url, 'chromedriver.zip')
    print("\nDownload completed successfully!")
    
    # Extract the zip file
    with zipfile.ZipFile(latest_driver_zip, 'r') as zip_ref:
        zip_ref.extractall()
    
    # On macOS/Linux, make the chromedriver executable
    if system != 'windows':
        os.chmod('chromedriver', os.stat('chromedriver').st_mode | stat.S_IEXEC)
    
    # Delete the zip file
    os.remove(latest_driver_zip)
    print("ChromeDriver has been installed successfully!")
    
except Exception as e:
    print(f"\nAn error occurred: {str(e)}")
    print("Please check your internet connection and try again.")