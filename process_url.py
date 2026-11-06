cat << 'EOF' > process_url.py
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
    title = soup.title.string.strip() if soup.title and soup.title.string else "Web Article"
    body_text = trafilatura.extract(html_content, include_comments=False, include_tables=False)
    if not body_text:
        body_text = soup.get_text(separator="\n", strip=True)

if not body_text or len(body_text.strip()) < 50:
    print("Error: 本文テキストを十分に抽出できませんでした。")
    sys.exit(1)

print(f"取得完了: タイトル『{title}』(本文長: {len(body_text)} 文字)")

# 2. Gemini API で読み上げ原稿とタイトルを生成
print("Gemini API で要約・原稿作成中...")
client = genai.Client(api_key=api_key)

prompt = f"""
以下の記事テキストを元に、ポッドキャストで自然に聞き取れる読み上げ原稿（日本語）を作成してください。
出力は以下のJSON形式のみで返してください（Markdownコードブロックは不要）:
{{
  "title": "記事の内容を表すキャッチーで簡潔な日本語タイトル",
  "script": "ポッドキャストのパーソナリティが落ち着いて語りかけるような自然な話し言葉の原稿本文。"
}}

【記事タイトル】
{title}

【本文】
{body_text[:12000]}
"""

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(response_mime_type="application/json")
)

try:
    data = json.loads(response.text)
    clean_title = data.get("title", title).strip()
    tts_script = data.get("script", "").strip()
except Exception as e:
    print(f"JSONパースエラー、代替テキスト抽出を試みます: {e}")
    clean_title = title
    tts_script = response.text.strip()

print(f"生成されたタイトル: {clean_title}")

# 3. edge-tts で音声合成 (.m4a)
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
audio_filename = f"episode_{timestamp}.m4a"
title_filename = f"episode_{timestamp}.title"

print(f"Edge TTS で音声を生成中 ({audio_filename})...")

async def generate_speech():
    communicate = edge_tts.Communicate(tts_script, voice="ja-JP-NanamiNeural")
    await communicate.save(audio_filename)

asyncio.run(generate_speech())

# メタデータ保存用 .title ファイル作成
with open(title_filename, "w", encoding="utf-8") as f:
    f.write(clean_title)

# 4. feed.xml の再生成スクリプトを実行
if os.path.exists("generate_feed.py"):
    print("generate_feed.py を実行して feed.xml を更新中...")
    subprocess.run([sys.executable, "generate_feed.py"], check=True)

print("単一URLの処理がすべて完了しました。")
EOF
