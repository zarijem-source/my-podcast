import sys
import os
import json
import re
import datetime
import subprocess
import asyncio
import edge_tts
import trafilatura
from google import genai
from google.genai import types

if len(sys.argv) < 2:
    print("Error: 記事のURLが指定されていません。")
    sys.exit(1)

article_url = sys.argv[1]
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY が環境変数に設定されていません。")
    sys.exit(1)

# 1. 記事本文とメタデータの抽出
downloaded = trafilatura.fetch_url(article_url)
extracted_text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
raw_metadata = trafilatura.extract_metadata(downloaded)

# 万が一のフォールバック用日本語タイトル（Webページのmetaタグ等から取得）
fallback_title = "無題の記事"
if raw_metadata and raw_metadata.title:
    fallback_title = raw_metadata.title.strip()

if not extracted_text:
    print("Error: 記事本文を抽出できませんでした。")
    sys.exit(1)

# 2. Gemini API を使って日本語タイトル抽出・ファイル命名・朗読用テキスト整形
client = genai.Client(api_key=api_key)

# 記事が極端に長大すぎる場合のセーフティ（約30,000文字まで許可）
input_text = extracted_text[:30000]

prompt = f"""
あなたは日本語の音声コンテンツ編集者です。
提供されたWeb記事や文学作品の本文を解析し、個人用ポッドキャスト朗読用のデータを生成してください。

【重要指示】
1. title（タイトル）:
   - 必ず自然で魅力的な「日本語」で記述してください。英語タイトルは厳禁です。
   - 記事や作品の核心、題名、テーマが直感的に伝わるタイトル（30文字以内）。
   - 小説や青空文庫などの文学作品の場合、作品名と作者名を入れてください（例: 「走れメロス（太宰治）」、「山月記（中島敦）」など）。
   - サイト名や余計なノイズ記号（【】や｜など）は省いてください。

2. speech_text（朗読本文）:
   - 記事の導入から結論までを途中で要約・省略せず、最初から最後まで全文を朗読できるように整えてください。
   - 耳で聴いて分かりやすい自然な話し言葉や読み上げ文に調整し、URL、目次、広告文などのノイズのみを除去してください。

3. safe_slug（ファイル名）:
   - ファイル名に使う英小文字とハイフンのみの短い英語単語（例: hashire-melos）。

記事本文:
{input_text}

以下のJSONフォーマットのみを出力してください（Markdown記法は含めないでください）:
{{
  "title": "必ず日本語のタイトル（例: 羅生門（芥川龍之介））",
  "safe_slug": "short-english-slug",
  "speech_text": "記事全文の朗読テキスト"
}}
"""

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=8192,
            temperature=0.2,
        ),
    )
    data = json.loads(response.text)
    title = data.get("title", fallback_title)
    safe_slug = data.get("safe_slug", "article")
    speech_text = data.get("speech_text", extracted_text)
except Exception as e:
    print(f"Gemini API処理で例外が発生したため、フォールバックします: {e}")
    title = fallback_title
    safe_slug = "article"
    speech_text = extracted_text

if not title or title.strip() == "Web Article":
    title = fallback_title

safe_slug = re.sub(r'[^a-zA-Z0-9\-]', '', safe_slug).lower()[:30]
if not safe_slug:
    safe_slug = "article"

print(f"決定タイトル: {title}")
print(f"スラッグ: {safe_slug}")
print(f"朗読文字数: {len(speech_text)} 文字")

# 3. ファイル名の作成
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
temp_mp3 = f"temp_{timestamp}.mp3"
final_m4a = f"{safe_slug}_{timestamp}.m4a"

# 4. edge-tts で高品質ニューラル音声を生成
VOICE = "ja-JP-NanamiNeural"

async def generate_speech():
    communicate = edge_tts.Communicate(speech_text, VOICE, rate="+5%")
    await communicate.save(temp_mp3)

asyncio.run(generate_speech())

# 5. ffmpeg で標準AAC (M4A) に変換（朗読向けモノラル・48kbpsに圧縮して100MB制限を回避）
subprocess.run([
    "ffmpeg", "-y", "-i", temp_mp3,
    "-metadata", f"title={title}",
    "-ac", "1",
    "-c:a", "aac",
    "-b:a", "48k",
    final_m4a
], check=True)

# 6. update_feed.py が確実に拾うための .title ファイル保存
title_file = os.path.splitext(final_m4a)[0] + ".title"
with open(title_file, "w", encoding="utf-8") as f:
    f.write(title)

if os.path.exists(temp_mp3):
    os.remove(temp_mp3)

print(f"高音質音声の生成完了: {final_m4a} (タイトル: {title})")
