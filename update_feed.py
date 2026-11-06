import os
import glob
import datetime
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom

GITHUB_USERNAME = "zarijem-source"
GITHUB_REPO = "my-podcast"
BASE_URL = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}"

PODCAST_TITLE = "My Web Articles Podcast"
PODCAST_DESC = "Personal audio feed generated from web articles."
FEED_FILENAME = "feed.xml"

def get_audio_info(file_path):
    """タイトル（日本語）と再生時間を抽出する"""
    title = ""
    duration_str = "00:05:00"
    base_no_ext = os.path.splitext(file_path)[0]

    # 1. 保存された .title ファイルがあれば最優先で読み込む
    title_path = base_no_ext + ".title"
    if os.path.exists(title_path):
        try:
            with open(title_path, "r", encoding="utf-8") as f:
                title = f.read().strip()
        except Exception:
            pass

    # 2. .title が無い場合は ffprobe でメタデータ（titleタグ）を取得
    if not title:
        try:
            cmd_title = [
                "ffprobe", "-v", "error",
                "-show_entries", "format_tags=title",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path
            ]
            res = subprocess.check_output(cmd_title).decode("utf-8", errors="ignore").strip()
            if res:
                title = res
        except Exception:
            pass

    # 3. どちらも取れなかった場合のフォールバック
    if not title:
        base = os.path.splitext(os.path.basename(file_path))[0]
        title = base.replace("_", " ")

    # 再生時間の取得
    try:
        cmd_dur = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        out_dur = subprocess.check_output(cmd_dur).decode("utf-8", errors="ignore").strip()
        sec = int(float(out_dur))
        duration_str = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"
    except Exception:
        pass

    return title, duration_str

# 音声ファイル（m4a, mp3）を全件収集（一時ファイル除外）
raw_files = glob.glob("*.m4a") + glob.glob("*.mp3")
audio_files = [f for f in raw_files if not f.startswith("temp_")]

# 更新日時が新しい順にソート
audio_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

# RSS 2.0 ルート作成
rss = ET.Element("rss", {
    "version": "2.0",
    "xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
    "xmlns:atom": "http://www.w3.org/2005/Atom"
})

channel = ET.SubElement(rss, "channel")
ET.SubElement(channel, "title").text = PODCAST_TITLE
ET.SubElement(channel, "link").text = BASE_URL
ET.SubElement(channel, "description").text = PODCAST_DESC
ET.SubElement(channel, "language").text = "ja"

ET.SubElement(channel, "atom:link", {
    "href": f"{BASE_URL}/{FEED_FILENAME}",
    "rel": "self",
    "type": "application/rss+xml"
})

now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
ET.SubElement(channel, "lastBuildDate").text = now_utc

for file_path in audio_files:
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    file_time = os.path.getmtime(file_path)
    pub_date = datetime.datetime.fromtimestamp(file_time, tz=datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    
    title, duration = get_audio_info(file_path)
    audio_url = f"{BASE_URL}/{file_name}"
    mime_type = "audio/x-m4a" if file_name.endswith(".m4a") else "audio/mpeg"

    item = ET.SubElement(channel, "item")
    ET.SubElement(item, "title").text = title
    ET.SubElement(item, "link").text = audio_url
    ET.SubElement(item, "description").text = title
    ET.SubElement(item, "pubDate").text = pub_date
    ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = audio_url
    
    ET.SubElement(item, "enclosure", {
        "url": audio_url,
        "length": str(file_size),
        "type": mime_type
    })
    ET.SubElement(item, "itunes:duration").text = duration
    ET.SubElement(item, "itunes:explicit").text = "false"

xml_str = ET.tostring(rss, encoding="utf-8")
parsed = minidom.parseString(xml_str)
pretty_xml = parsed.toprettyxml(indent="  ", encoding="utf-8")

with open(FEED_FILENAME, "wb") as f:
    f.write(pretty_xml)

print(f"{FEED_FILENAME} を全 {len(audio_files)} 件で更新しました。")
