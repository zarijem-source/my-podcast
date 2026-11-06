import sys
import os
import re
import json
from datetime import datetime, timezone
import trafilatura
import requests
from openai import OpenAI

if len(sys.argv) < 2:
    print("エラー: 記事URLが指定されていません。")
    sys.exit(1)

raw_input = sys.argv[1]

# URLのみを抽出
url_match = re.search(r'https?://[^\s]+', raw_input)
target_url = url_match.group(0) if url_match else raw_input.strip()

print(f"1. 記事を抽出中: {target_url}")
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

response = requests.get(target_url, headers=headers, timeout=15)
response.raise_for_status()
downloaded = response.text

# HTMLが取得できていることを確認してから抽出
metadata = trafilatura.extract_metadata(downloaded)
article_text = trafilatura.extract(downloaded, include_comments=False)

if not article_text:
    raise ValueError(f"記事本文を抽出できませんでした: {target_url}")

title = metadata.title if (metadata and metadata.title) else "Untitled Episode"

print(f"   タイトル: {title}")
print(f"   本文文字数: {len(article_text)} 文字")

print("2. 台本を生成中 (OpenAI GPT-4o-mini)...")
client_openai = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

prompt = f"""
以下の記事を、ポッドキャストで読み上げるための自然な日本語の朗読原稿（モノローグ）にリライトしてください。
- 挨拶から始め、自然な語り口にする
- 見出し記号や箇条書き記号は使わず、耳で聴いて分かりやすい文章にする
- 記事の要点を網羅しつつテンポよくまとめる

記事本文:
{article_text[:12000]}
"""

gpt_res = client_openai.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "あなたはポッドキャストの朗読原稿を作成するプロの放送作家です。"},
        {"role": "user", "content": prompt}
    ],
    temperature=0.3
)
script_text = gpt_res.choices[0].message.content.strip()
print(f"   台本生成完了: {len(script_text)} 文字")

print("3. latest.json を書き出し中...")
data = {
    "title": title,
    "url": target_url,
    "text": script_text,
    "updated_at": datetime.now(timezone.utc).isoformat()
}

with open("latest.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"完了: latest.json を生成しました（{title}）")
