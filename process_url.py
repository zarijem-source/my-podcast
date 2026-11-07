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
fallback_title = "無題の記事"
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
        fallback_title = os.path.basename(urllib.parse.urlparse(article_url).path) or "PDF Document"
    except Exception as e:
        print(f"PDF解析エラー: {e}")
        sys.exit(1)
else:
    print("HTMLドキュメントとして解析中...")
    extracted = trafilatura.extract(raw_data, include_comments=False, include_tables=False)
    if not extracted:
        print("Error: 記事本文を抽出できませんでした。")
        sys.exit(1)
    body_text = extracted
    metadata = trafilatura.extract_metadata(raw_data)
    if metadata and metadata.title:
        fallback_title = metadata.title.strip()

print("Gemini API を使って原稿とタイトルを生成中...")
client = genai.Client(api_key=api_key)

input_text = body_text[:30000]

prompt = f"""
あなたは日本語の音声コンテンツ編集者です。
提供されたWeb記事や文学作品の本文を解析し、個人用ポッドキャスト朗読用のデータを生成してください。

【重要指示】
1. title (タイトル):
   - 必ず自然で魅力的な「日本語」で記述してください。英語タイトルは厳禁です。
   - 記事や作品の核心、題名、テーマが直感的に伝わるタイトル（30文字以内）。
2. safe_slug (スラッグ):
   - 英数字とハイフンのみ。小文字。
3. speech_text (朗読テキスト):
   - 提供された本文から、図表、広告、無関係なナビゲーションを排除し、朗読に最適な純粋なテキストにしてください。

【提供された本文】
{input_text}
"""

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=8192,
            temperature=0.2,
        )
    )
    data = json.loads(response.text)
    title = data.get("title", fallback_title)
    safe_slug = data.get("safe_slug", "article")
    speech_text = data.get("speech_text", body_text)
except Exception as e:
    print(f"Gemini API処理で例外が発生したため、フォールバックします: {e}")
    title = fallback_title
    safe_slug = "article"
    speech_text = body_text

if not title or title.strip() == "Web Article":
    title = fallback_title

safe_slug = re.sub(r'[^a-zA-Z0-9\-]', '', safe_slug).lower()[:30]
if not safe_slug:
    safe_slug = "article"

print(f"決定タイトル: {title}")
print(f"スラッグ: {safe_slug}")
print(f"朗読文字数: {len(speech_text)} 文字")

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
temp_mp3 = f"temp_{timestamp}.mp3"
final_m4a = f"{safe_slug}_{timestamp}.m4a"

VOICE = "ja-JP-NanamiNeural"

async def generate_speech():
    communicate = edge_tts.Communicate(speech_text, VOICE, rate="+5%")
    await communicate.save(temp_mp3)

asyncio.run(generate_speech())

subprocess.run([
    "ffmpeg", "-y", "-i", temp_mp3,
    "-metadata", f"title={title}",
    "-ac", "1",
    "-c:a", "aac",
    "-b:a", "48k",
    final_m4a
], check=True)

title_file = os.path.splitext(final_m4a)[0] + ".title"
with open(title_file, "w", encoding="utf-8") as f:
    f.write(title)

if os.path.exists(temp_mp3):
    os.remove(temp_mp3)

print(f"高音質音声の生成完了: {final_m4a} (タイトル: {title})")