import html
import json
import os
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
TODAY = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")
LIVE = "https://cocogaoo.github.io/mushroom-workbench/daily-content.json"


def read_json(url):
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            return json.load(response)
    except Exception:
        return None


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def latest_news():
    try:
        request = urllib.request.Request("https://www.globaldatinginsights.com/feed/", headers={"User-Agent": "MushroomWorkbench/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            root = ET.fromstring(response.read())
        items = []
        for index, item in enumerate(root.findall(".//item")):
            title, link = clean(item.findtext("title")), clean(item.findtext("link"))
            if not title or not re.match(r"https://(www\.)?globaldatinginsights\.com/", link):
                continue
            description = clean(item.findtext("description"))[:260]
            published = clean(item.findtext("pubDate"))
            try:
                date = datetime.strptime(published[:16], "%a, %d %b %Y").strftime("%Y-%m-%d")
            except Exception:
                date = TODAY
            items.append({"id": f"gdi-{TODAY}-{index}", "title": title, "date": date, "summary": description or "打开原文查看这条行业动态。", "url": link})
            if len(items) == 3:
                break
        return items
    except Exception:
        return []


def valid_course(course):
    required = ["id", "title", "focus", "paragraphs", "remember", "question", "options", "correct", "explanation", "apply", "example"]
    return isinstance(course, dict) and all(k in course for k in required) and len(course["paragraphs"]) >= 3 and all(len(x) >= 40 for x in course["paragraphs"]) and len(course["options"]) == 3 and course["correct"] in (0, 1, 2)


def generate_courses(previous):
    old_titles = []
    if isinstance(previous, dict):
        old_titles = [v.get("title", "") for v in previous.get("courses", {}).values() if isinstance(v, dict)]
    prompt = f'''为一位中文母语、英语初级、从事海外社交和语音房产品运营的成年人生成 {TODAY} 的三节每日课程。不要重复这些旧标题：{old_titles}。
只返回合法 JSON，不要 Markdown。顶层键必须为 english、economics、psychology。每节课必须包含：
id（分别以 english-{TODAY}、economics-{TODAY}、psychology-{TODAY} 开头）、title、focus、paragraphs（恰好3段，每段有实质内容）、remember、question、options（恰好3项）、correct（0到2）、explanation、apply、example。
英语课另含 translations（对应3段中文理解）和 words（6组 [英文关键词,中文义,英文例句]）；正文用自然的英国旅行、电影或日常交流英语，CEFR A2-B1，三段合计250到400词。
经济学课解释一个经济运转机制，给出语音房或互联网产品的具体例子，明确哪些数字只是示例，避免投资建议。
心理学课用于开阔视野和日常减压，使用可靠的一般心理学概念，避免诊断、治疗承诺和强迫积极。
三课都要教“关注什么、怎么记、怎么运用”；选择题答案必须能从正文推出。中文内容务实、具体，不说空话。'''
    body = json.dumps({"model": "openai/gpt-4o", "temperature": 0.7, "messages": [{"role": "user", "content": prompt}]}, ensure_ascii=False).encode()
    request = urllib.request.Request("https://models.github.ai/inference/chat/completions", data=body, headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=90) as response:
        result = json.load(response)
    content = result["choices"][0]["message"]["content"].strip()
    fence = chr(96) * 3
    content = content.removeprefix(fence + "json").removeprefix(fence).removesuffix(fence).strip()
    courses = json.loads(content)
    if set(courses) != {"english", "economics", "psychology"} or not all(valid_course(courses[k]) for k in courses):
        raise ValueError("model returned an incomplete course")
    return courses


def main():
    previous = read_json(LIVE)
    if not previous:
        seed = ROOT / "daily-content.json"
        if not seed.exists():
            seed = ROOT / "public" / "daily-content.json"
        previous = json.loads(seed.read_text())
    try:
        courses = generate_courses(previous)
        content = {"date": TODAY, "generatedAt": datetime.now(timezone.utc).isoformat(), "courses": courses, "news": latest_news() or previous.get("news", [])}
    except Exception as error:
        print(f"Daily generation failed; keeping last successful content: {error}")
        content = previous
    site = ROOT / "site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir()
    index = ROOT / "index.html"
    if not index.exists():
        index = ROOT.parent / "蘑菇工作台.html"
    shutil.copy(index, site / "index.html")
    (site / "daily-content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2))
    (site / ".nojekyll").touch()
    print(f"Prepared daily site content dated {content['date']}")


if __name__ == "__main__":
    main()
