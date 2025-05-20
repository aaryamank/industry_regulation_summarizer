# === fetchers.py ===
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import requests
import time
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import fitz  # PyMuPDF
import streamlit as st
import openai
import json
import pandas as pd
from datetime import datetime, timedelta
import re

# Define a cutoff
cutoff_date = datetime.today() - timedelta(days=90)

def parse_date(date_str):
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y")
    except:
        try:
            return datetime.strptime(date_str.strip(), "%d-%m-%Y")
        except:
            return None

def extract_date_from_dpiit_url(pdf_url):
    """
    Attempts to extract a date from a DPIIT PDF URL such as:
    - https://dpiit.gov.in/sites/default/files/QCO_LaboratoryGlassware_24January2024.pdf
    - https://dpiit.gov.in/sites/default/files/notification_Amendment_23November2012%20%206_0.pdf
    """
    from datetime import datetime
    import re

    # Extract the filename
    filename = pdf_url.split('/')[-1]
    
    # Remove extension and decode URL
    filename = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    filename = re.sub(r'%20', ' ', filename)

    # Try to find a pattern like 24January2024 or 23November2012
    match = re.search(r'(\d{1,2})\s*([A-Za-z]+)\s*(\d{4})', filename)
    if match:
        day, month_str, year = match.groups()
        try:
            date_obj = datetime.strptime(f"{day} {month_str} {year}", "%d %B %Y")
            return date_obj
        except ValueError:
            try:
                date_obj = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
                return date_obj
            except ValueError:
                return None
    return None
            
def parse_date_string(date_str):
    # Try parsing formats like "May 16, 2025"
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except:
            continue
    return None

def clean_commerce_date(date_str):
    # Remove ordinal suffixes (st, nd, rd, th)
    cleaned = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str, flags=re.IGNORECASE)
    # Replace dots with spaces
    cleaned = cleaned.replace('.', ' ')
    # Normalize whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned.title()  # Ensures consistent capitalization for parsing

# 1. DPIIT
def scrape_dpiit(cutoff_date):
    url = "https://dpiit.gov.in/policies-rules-and-acts/notifications"
    base_url = "https://dpiit.gov.in"
    soup = BeautifulSoup(requests.get(url).content, "html.parser")
    results = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            link_tag = row.find("a", href=True)
            if link_tag and link_tag['href'].endswith(".pdf"):
                pdf_url = urljoin(base_url, link_tag["href"])
                doc_date = extract_date_from_dpiit_url(pdf_url)

                if doc_date and doc_date >= cutoff_date:
                    title = link_tag.text.strip()
                    results.append({
                        "source": "DPIIT",
                        "title": title,
                        "url": pdf_url,
                        "date": doc_date.strftime("%Y-%m-%d")
                    })

    return results

# 2. Power Ministry
def scrape_powermin(cutoff_date):
    base_url = "https://powermin.gov.in"
    url = "https://powermin.gov.in/en/circular?field_division_value=Act+%26+Notifications&field_date_value%5Bvalue%5D%5Bdate%5D=&title="
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    results = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            if len(cols) >= 5:
                subject = cols[1].get_text(strip=True)
                date_text = cols[2].get_text(strip=True)
                link_tag = cols[4].find("a", href=True)
                doc_date = parse_date(date_text)
                if doc_date and doc_date >= cutoff_date and link_tag:
                    pdf_url = urljoin(base_url, link_tag['href'])
                    results.append({"source": "Power Ministry", "title": subject, "url": pdf_url, "date": doc_date.strftime("%Y-%m-%d")})
    return results

# 3. RBI
def scrape_rbi(cutoff_date):
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://website.rbi.org.in/web/rbi/notifications?delta=100")

    # Scroll to load all content
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    soup = BeautifulSoup(driver.page_source, "html.parser")
    driver.quit()

    results = []
    base_url = "https://website.rbi.org.in"
    items = soup.find_all("div", class_="notification-row-each-inner")
    # print(f"🔎 Notifications found: {len(items)}")

    for block in items:
        a_tag = block.find("a", class_="mtm_list_item_heading")
        title = a_tag.get_text(strip=True) if a_tag else "Untitled"

        date_tag = block.find("div", class_="notification-date")
        date_str = date_tag.get_text(strip=True) if date_tag else ""
        doc_date = parse_date_string(date_str)

        pdf_tag = block.find("a", class_="matomo_download download_link", href=True)
        pdf_url = urljoin(base_url, pdf_tag["href"]) if pdf_tag else None

        if doc_date and doc_date >= cutoff_date and pdf_url:
            results.append({
                "source": "RBI",
                "title": title,
                "url": pdf_url,
                "date": doc_date.strftime("%Y-%m-%d")
            })

    # print(f"✅ Final RBI Notifications with PDFs: {len(results)}")
    return results

# 4. Commerce
def scrape_commerce(cutoff_date):
    url = "https://commerce.gov.in/acts-and-schemes/"
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(res.content, "html.parser")
    cards = soup.select(".whats-new-wrapper")
    results = []

    for card in cards:
        heading = card.select_one("h3")
        meta = card.select_one("p")
        link = card.select_one("a.innr-btn")
        if not heading or not meta or not link:
            continue

        title = heading.get_text(strip=True)
        raw_date = meta.get_text(strip=True).split("|")[0].strip()

        # Clean and normalize date string
        normalized_date = clean_commerce_date(raw_date)

        # Try multiple formats
        doc_date = None
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                doc_date = datetime.strptime(normalized_date, fmt)
                break
            except ValueError:
                continue

        if not doc_date:
            continue

        pdf_url = link.get("href")
        if not pdf_url or ".pdf" not in pdf_url.lower():
            continue
        if doc_date < cutoff_date:
            continue

        results.append({
            "source": "Commerce",
            "title": title,
            "url": pdf_url,
            "date": doc_date.strftime("%Y-%m-%d")
        })

    return results