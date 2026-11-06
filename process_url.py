import sys
import os
import io
import json
import re
import datetime
import subprocess
import asyncio
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

# 1. コンテンツの取得（PDF判定およびアクセス拒否対策）
print(f"URLを取得中: {article_url}")

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

raw_data = None
content_type = ""

# ブラウザ偽装ヘッダー付きで取得
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
    print(f"Error: URLからコンテンツを取得できませんでした（アクセス拒否または無効なURL）: {article_url}")
    sys.exit(1)

# --- A. PDF の場合 ---
is_pdf = article_url.lower().split("?")[0].endswith(".pdf") or "application/pdf" in content_type

if is_pdf:
    print
