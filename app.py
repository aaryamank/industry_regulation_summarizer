import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
import requests
from io import BytesIO
from datetime import datetime, timedelta
import openai
import re
from fetchers import scrape_dpiit, scrape_powermin, scrape_rbi, scrape_commerce

# === CONFIGURATION ===
openai.api_key = st.secrets["OPENAI_API_KEY"]
cutoff_date = datetime.today() - timedelta(days=90)

# === SUMMARIZER AGENT ===
def summarizer_agent(title, text):
    prompt = f"""
You're an AI assistant that reads Indian government regulatory notification documents.

Document title: {title}

Text:
{text}

Please summarize the key takeaways into 3-7 bullet points, and list potentially impacted sectors. Format:

### Summary
- point 1
- point 2

### Potentially Impacted Sectors
- sector 1
- sector 2
"""
    response = openai.ChatCompletion.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response['choices'][0]['message']['content']

# === UTILS ===
def extract_text_from_pdf(url):
    # try:
    #     response = requests.get(url)
    #     with fitz.open(stream=BytesIO(response.content), filetype="pdf") as doc:
    #         return "\n".join(page.get_text() for page in doc)
    # except Exception as e:
    #     return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(pdf_url, headers=headers)
        response.raise_for_status()

        with open("temp.pdf", "wb") as f:
            f.write(response.content)

        doc = fitz.open("temp.pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()

        return text.strip()

    except Exception as e:
        print(f"❌ Skipped: Could not read PDF — {e}")
        return None

# === MAIN ===
st.set_page_config(page_title="India Regulatory Summary", page_icon="🇮🇳", layout="wide")
st.title("India Regulatory Summary App")
st.markdown("Summarized view of regulatory circulars from Indian ministries")

with st.spinner("Fetching and processing documents..."):
    dpiit_docs = scrape_dpiit(cutoff_date)
    powermin_docs = scrape_powermin(cutoff_date)
    rbi_docs = scrape_rbi(cutoff_date)
    commerce_docs = scrape_commerce(cutoff_date)

    all_docs = dpiit_docs + powermin_docs + rbi_docs + commerce_docs
    summaries_by_ministry = {}

    for doc in all_docs:
        source = doc['source'] if isinstance(doc, dict) else doc[0]
        title = doc['title'] if isinstance(doc, dict) else doc[1]
        url = doc['url'] if isinstance(doc, dict) else doc[2]

        if source not in summaries_by_ministry:
            summaries_by_ministry[source] = []

        text = extract_text_from_pdf(url)
        if not text or not text.strip():
            continue

        summary = summarizer_agent(title, text)
        summaries_by_ministry[source].append({
            "title": title,
            "summary": summary,
            "url": url
        })

# === DISPLAY ===
st.success("✅ Summaries generated!")

for ministry, docs in summaries_by_ministry.items():
    st.header(ministry)
    for doc in docs:
        st.subheader(doc['title'])
        st.markdown(doc['summary'])
        st.markdown(f"[🔗 PDF Link]({doc['url']})")
        st.markdown("---")