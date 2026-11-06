import os
from datetime import datetime, timezone
import trafilatura
from google import genai
from google.genai import types
from openai import OpenAI
from feedgen.feed import FeedGenerator

# --- 設定項目 ---
TARGET_URL = "https://note.com/y_music_lover/n/n78274df25bbd"  # 直前で指定されていた記事URLに変更してください
AUDIO_OUTPUT = "test_episode.mp3"
FEED_OUTPUT = "feed.xml"
BASE_URL = "https://example.com/podcast"

print("1. 記事本文を抽出中...")
downloaded = trafilatura.fetch_url(TARGET_URL)
if not downloaded:
    raise ValueError("URLの取得に失敗しました。")

meta = trafilatura.extract_metadata(downloaded)
article_title = meta.title if (meta and meta.title) else "サンプル記事"
article_content = trafilatura.extract(downloaded, include_comments=False)

if not article_content:
    raise ValueError("本文を抽出できませんでした。")

print(f"   タイトル: {article_title}")
print(f"   本文文字数: {len(article_content)} 文字")

print("\n2. Gemini (gemini-3.8-flash) で音声読み上げ用の台本に整形中...")
client_gemini = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

prompt = f"""
あなたはポッドキャストの朗読原稿を作成するプロのエディターです。
以下の記事を、音声合成（TTS）で聴くための「音声読み上げ用台本」に変換してください。

# 制約事項
1. 要約はせず、すべての内容・論旨を完全に維持すること。
2. 広告や関連記事へのリンクなどのゴミ情報は排除すること。
3. リスナーが耳だけで理解できるよう、見出しの前に「小見出し：〇〇」などを補い、段落間に適切な読点（、）を入れること。
4. 冒頭は「タイトル：{article_title}」から自然に始めること。

# 元記事タイトル
{article_title}

# 元記事本文
{article_content}
"""

gemini_res = client_gemini.models.generate_content(
    model="gemini-3.8-flash",
    contents=prompt,
    config=types.GenerateContentConfig(temperature=0.3)
)
tts_script = gemini_res.text
print(f"   台本整形が完了しました（{len(tts_script)} 文字）。")

print("\n3. OpenAI TTSで音声ファイル (mp3) を生成中...")
client_openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# 長文対応: 1500文字程度にチャンク分割して合成し、1つのmp3に結合
CHUNK_SIZE = 1500
chunks = [tts_script[i:i + CHUNK_SIZE] for i in range(0, len(tts_script), CHUNK_SIZE)]
print(f"   全 {len(chunks)} パートに分割して音声を生成します。")

with open(AUDIO_OUTPUT, "wb") as f_out:
    for idx, chunk in enumerate(chunks, 1):
        print(f"   - パート {idx}/{len(chunks)} を合成中...")
        res = client_openai.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=chunk
        )
        f_out.write(res.content)

audio_size = os.path.getsize(AUDIO_OUTPUT)
print(f"   音声生成完了: {AUDIO_OUTPUT} ({audio_size / (1024 * 1024):.2f} MB)")

print("\n4. ポッドキャスト用 feed.xml を生成中...")
fg = FeedGenerator()
fg.load_extension('podcast')

fg.title('My Private Reading Podcast')
fg.link(href=BASE_URL, rel='alternate')
fg.description('Web記事・ニュースのパーソナル朗読フィード')
fg.language('ja')
fg.podcast.itunes_category('Technology')
fg.podcast.itunes_author('Personal Bot')
fg.podcast.itunes_explicit('no')

fe = fg.add_entry()
fe.id(f"{BASE_URL}/{AUDIO_OUTPUT}")
fe.title(article_title)
fe.description(tts_script[:300] + "...")
fe.published(datetime.now(timezone.utc))
fe.enclosure(
    url=f"{BASE_URL}/{AUDIO_OUTPUT}",
    length=str(audio_size),
    type='audio/mpeg'
)

fg.rss_file(FEED_OUTPUT, pretty=True)
print(f"   フィード生成完了: {FEED_OUTPUT}")

print("\n全工程が正常に完了しました！")
