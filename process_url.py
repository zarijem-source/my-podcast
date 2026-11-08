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

print("Gemini API を使って原稿の分割と生成中...")
client = genai.Client(api_key=api_key)

# 長文を丸ごと、または十分な長さをカバーできるように拡張
input_text = body_text[:60000]

prompt = f"""
あなたは日本語の音声コンテンツ編集者です。
提供された長文の記事や文学作品の本文を解析し、個人用ポッドキャスト朗読用のデータを生成してください。
音声ファイルが長すぎるとファイルサイズやリスニングの面で問題が生じるため、必要に応じて**複数のパート（JSONの配列形式）**に分割してください（1パートあたり概ね10分〜15分程度のボリュームを目安に分割）。

【重要指示・原文尊重の原則】
1. 情報の欠落禁止: 原文のニュアンス、事実関係、筆者の主張や論理展開を絶対に省略・要約しすぎず、すべての重要な情報を各パートにしっかりと割り振ってください。
2. ナビゲーション追加: パート2以降がある場合、冒頭に「続いて後半では〜」といった聴き手向けの自然なサポート文（接続の導入）を入れてください。
3. title (タイトル): 各パートごとに「〇〇（第1部：前半）」のように、自然で魅力的な日本語の連番タイトルにしてください。
4. safe_slug (スラッグ): 英数字とハイフンのみ。小文字。

以下のJSONフォーマット（配列）で必ず出力してください。分割が不要な短い記事であっても、要素が1つの配列 `[...]` で出力してください。

[
  {{
    "part": 1,
    "title": "記事のタイトル（第1部：前半）",
    "safe_slug": "article-slug",
    "speech_text": "朗読テキスト（パート1）..."
  }},
  {{
    "part": 2,
    "title": "記事のタイトル（第2部：後半）",
    "safe_slug": "article-slug",
    "speech_text": "朗読テキスト（パート2）..."
  }}
]

【提供された本文】
{input_text}
"""

parts_data = []
try:
    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=8192,
            temperature=0.2,
        )
    )
    parsed_json = json.loads(response.text)
    if isinstance(parsed_json, list):
        parts_data = parsed_json
    elif isinstance(parsed_json, dict):
        parts_data = [parsed_json]
except Exception as e:
    print(f"Gemini API処理で例外が発生したため、分割なしのフォールバックを行います: {e}")

# 万が一パースに失敗した場合は従来の単一構成として扱う
if not parts_data:
    parts_data = [{
        "part": 1,
        "title": fallback_title,
        "safe_slug": "article",
        "speech_text": body_text
    }]

VOICE = "ja-JP-NanamiNeural"
base_timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# 各パートごとに順番に音声ファイルを生成・保存する
for idx, part_item in enumerate(parts_data):
    p_title = part_item.get("title", fallback_title)
    if not p_title or p_title.strip() == "Web Article":
        p_title = fallback_title

    p_slug = part_item.get("safe_slug", "article")
    p_slug = re.sub(r'[^a-zA-Z0-9\-]', '', p_slug).lower()[:30]
    if not p_slug:
        p_slug = "article"

    p_text = part_item.get("speech_text", body_text)

    print(f"\n--- パート {idx + 1} / {len(parts_data)} 処理中 ---")
    print(f"決定タイトル: {p_title}")
    print(f"スラッグ: {p_slug}")
    print(f"朗読文字数: {len(p_text)} 文字")

    # 複数パートになる場合はタイムスタンプに連番やインデックスを付与してユニークにする
    part_suffix = f"_pt{idx + 1}" if len(parts_data) > 1 else ""
    temp_mp3 = f"temp_{base_timestamp}{part_suffix}.mp3"
    final_m4a = f"{p_slug}_{base_timestamp}{part_suffix}.m4a"

    async def generate_speech():
        communicate = edge_tts.Communicate(p_text, VOICE, rate="+5%")
        await communicate.save(temp_mp3)

    asyncio.run(generate_speech())

    subprocess.run([
        "ffmpeg", "-y", "-i", temp_mp3,
        "-metadata", f"title={p_title}",
        "-ac", "1",
        "-c:a", "aac",
        "-b:a", "48k",
        final_m4a
    ], check=True)

    title_file = os.path.splitext(final_m4a)[0] + ".title"
    with open(title_file, "w", encoding="utf-8") as f:
        f.write(p_title)

    if os.path.exists(temp_mp3):
        os.remove(temp_mp3)

    print(f"音声生成完了: {final_m4a} (タイトル: {p_title})")

print(f"\n全 {len(parts_data)} パートの生成処理が完了しました。")
