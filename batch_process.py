import os
import sys
import subprocess
import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO = os.environ.get("GITHUB_REPOSITORY")

if not GITHUB_TOKEN or not REPO:
    print("Error: GITHUB_TOKEN または GITHUB_REPOSITORY が設定されていません。")
    sys.exit(1)

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json"
}

url = f"https://api.github.com/repos/{REPO}/issues?state=open&sort=created&direction=asc"
res = requests.get(url, headers=headers)
if res.status_code != 200:
    print(f"Error fetching issues: {res.text}")
    sys.exit(1)

issues = res.json()
if not issues:
    print("未処理の Issue はありません。")
    sys.exit(0)

print(f"未処理の記事が {len(issues)} 件見つかりました。順次処理を開始します。")

for issue in issues:
    if "pull_request" in issue:
        continue

    issue_number = issue["number"]
    target_url = issue["title"].strip()
    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        target_url = issue.get("body", "").strip()

    if not (target_url.startswith("http://") or target_url.startswith("https://")):
        print(f"Issue #{issue_number}: 有効なURLが見つかりませんでした。スキップします。")
        continue

    print(f"\n--- [#{issue_number}] 処理開始: {target_url} ---")
    
    result = subprocess.run([sys.executable, "process_url.py", target_url])
    
    if result.returncode == 0:
        print(f"[#{issue_number}] 成功。Issue をクローズします。")
        requests.patch(
            f"https://api.github.com/repos/{REPO}/issues/{issue_number}",
            headers=headers,
            json={"state": "closed"}
        )
    else:
        print(f"[#{issue_number}] 失敗。エラー調査のため Issue はオープンのまま維持します。")

print("\n全 Issue のバッチ処理が完了しました。")
