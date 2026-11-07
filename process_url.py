import sys
import os
import io
import json
import re
import datetime
import subprocess
import asyncio
import time
import urllib.parse
import urllib.request
import edge_tts
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader
from google import genai
from google.genai import types

if len(sys.argv) < 2:
    print("Error: 記事またはPDFのURLが指定されていません。")
    sys.exit(1)

article_url = sys.argv[1]
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY が環境変数に設定されていません。")
    sys.exit(1)

print(f"URLを取得中: {article_url}")

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

raw_data = None
content_type = ""

try:
    req = urllib.request.Request(article_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        content_type = response.info().get_content_type()
        raw_data = response.read()
except Exception as e:
    print(f"urllibでの取得に失敗したため、trafilatura.fetch_url を試行します: {e}")
    downloaded_str = trafilatura.fetch_url(article_url)
    if downloaded_str:
        raw_data = downloaded_str.encode("utf-8") if isinstance(downloaded_str, str) else downloaded_str
        content_type = "text/html"

if not raw_data:
    print(f"Error: URLからコンテンツを取得できませんでした: {article_url}")
    sys.exit(1)

is_pdf = article_url.lower().split("?")[0].endswith(".pdf") or "application/pdf" in content_type
title = ""
body_text = ""

if is_pdf:
    print("PDFドキュメントとして解析中...")
    try:
        reader = PdfReader(io.BytesIO(raw_data))
        extracted_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                extracted_text.append(text)
        body_text = "\n".join(extracted_text)
        title = os.path.basename(urllib.parse.urlparse(article_url).path) or "PDF Document"
    except Exception as e:
        print(f"PDF解析エラー: {e}")
        sys.exit(1)
else:
    print("Webページとして解析中...")
    html_content = raw_data.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html_content, "html.parser")
    title = soup.title
