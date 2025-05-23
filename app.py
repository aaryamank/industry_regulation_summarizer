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

client = openai.OpenAI(api_key=openai.api_key)

# === SUMMARIZER AGENT ===
def summarizer_agent(title, text):
    prompt = f"""
You're an AI assistant that reads Indian government regulatory notification documents.

Document title: {title}

Text:
{text}

Please provide:
1. A brief, suitable title for the summary.
2. A concise summary in 3–7 bullet points.
3. A list of potentially impacted sectors.

Respond in the following format:

### Title
<Generated title>

### Summary
- point 1
- point 2

### Potentially Impacted Sectors
- sector 1
- sector 2
"""
    response = client.chat.completions.create(
        model="gpt-4.1-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    return response.choices[0].message.content

# === UTILS ===
def extract_text_from_pdf(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers)
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
st.title("India Ministry-specific Regulation Notifications Summarizer App")
st.markdown("Summarized view of regulatory circulars issued by different Indian ministries")

with st.spinner("Fetching and processing documents..."):
    dpiit_docs = scrape_dpiit(cutoff_date)
    powermin_docs = scrape_powermin(cutoff_date)
    rbi_docs = scrape_rbi(cutoff_date)
    commerce_docs = scrape_commerce(cutoff_date)

    all_sources = {
        "DPIIT": dpiit_docs,
        "Ministry of Power": powermin_docs,
        "RBI": rbi_docs,
        "Ministry of Commerce": commerce_docs
    }

    summaries_by_ministry = {}

    for ministry, docs in all_sources.items():
        summaries_by_ministry[ministry] = []
        for doc in docs:
            source = doc['source'] if isinstance(doc, dict) else doc[0]
            title = doc['title'] if isinstance(doc, dict) else doc[1]
            url = doc['url'] if isinstance(doc, dict) else doc[2]

            text = extract_text_from_pdf(url)
            if not text or not text.strip():
                continue

            summary_text = summarizer_agent(title, text)
            # Split to get generated title if present
            summary_lines = summary_text.strip().split("\n")
            generated_title = summary_lines[1] if len(summary_lines) > 1 and summary_lines[0].startswith("### Title") else title
            full_summary = "\n".join(summary_lines[2:]) if generated_title != title else summary_text

            summaries_by_ministry[ministry].append({
                "title": generated_title,
                "summary": full_summary,
                "url": url
            })

# === DISPLAY ===
st.success("✅ Summaries generated!")

for ministry, docs in summaries_by_ministry.items():
    with st.expander(ministry):
        if docs:
            for doc in docs:
                st.subheader(doc['title'])
                st.markdown(doc['summary'])
                st.markdown(f"[🔗 PDF Link]({doc['url']})")
                st.markdown("---")
        else:
            st.markdown("*No regulations/acts/circulars released in the specified period.*")
