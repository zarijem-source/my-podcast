import os
import sys
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,image/*,*/*;q=0.8",
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

# 判定フラグの準備
clean_url = article_url.lower().split("?")[0]
is_image = clean_url.endswith((".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")) or "image/" in content_type
is_pdf = clean_url.endswith(".pdf") or "application/pdf" in content_type

fallback_title = "無題の記事"
body_text = ""

# Geminiクライアントの初期化
client = genai.Client(api_key=api_key)

if is_image:
    print("画像ファイルとして検知しました。GeminiのOCR機能でテキストを抽出します...")
    ext = os.path.splitext(urllib.parse.urlparse(article_url).path)[1] or ".png"
    temp_ocr_filename = f"temp_ocr_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    with open(temp_ocr_filename, "wb") as f:
        f.write(raw_data)
    try:
        print("Geminiへ画像をアップロード中...")
        uploaded_file = client.files.upload(file=temp_ocr_filename)
        
        # 処理完了（ACTIVE）になるまで待機
        while uploaded_file.state.name == "PROCESSING":
            print("画像ファイルを処理中...", end="\r")
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name != "ACTIVE":
            raise Exception(f"ファイルの処理に失敗しました。状態: {uploaded_file.state.name}")

        ocr_
