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

# Curated daily curriculum: 8 topics × 4 practice rounds = 32 distinct days.
ENGLISH_DAYS = [
("酒店入住","reservation","The room does not match my reservation.","Could you check the booking again?"),("餐厅点餐","allergy","I am allergic to peanuts.","Does this dish contain any nuts?"),("火车延误","delay","My train has been delayed.","What is the fastest alternative route?"),("药房沟通","symptom","I have had a sore throat since yesterday.","Is there anything suitable for this?"),("旅行团集合","meeting point","I booked the morning walking tour.","Could you show me the meeting point?"),("商店退换","receipt","I bought this yesterday, but it does not work.","May I exchange it with this receipt?"),("工作社交","recommend","It is my first time in London.","What would you recommend nearby?"),("求助电话","location","I am near the north entrance of the station.","Could you tell me what to do next?")]
ECON_DAYS = [
("供需错配｜好房间为何遇不到付费用户","供给存在不等于匹配有效","把高质量房间按用户付费意愿、兴趣和在线时段分层，观察匹配后的进房与付费，而不是只看总曝光。"),("边际收益｜多给一次曝光值不值","比较再增加一单位资源带来的新增结果","按曝光档位看新增停留和新增付费；若后续曝光只搬运原有用户，边际收益会快速下降。"),("价格分层｜同一服务为何有不同套餐","按需求差异设计版本能提高匹配效率","会员可按权益组合分层，但要保证规则透明，并观察套餐是否扩大付费而非只迁移老用户。"),("网络效应｜人越多产品一定越好吗","用户增加只有在提高他人价值时才形成网络效应","人数增加可能提升热闹感，也可能降低发言机会；应分别看听众留存和上麦成功率。"),("沉没成本｜已经投入很多还要继续吗","过去且不可收回的投入不应决定下一步","评估旧活动时用未来新增收益与未来成本比较，不因已投入运营工时就继续低效活动。"),("信息不对称｜用户为何不敢进陌生房","双方掌握的信息不同会增加决策成本","用真实标签、活跃状态和近期内容样本降低不确定性，再看高意向用户的点击是否改善。"),("替代效应｜推荐增长可能只是搬家","一个入口增长可能来自另一个入口下降","观察推荐房新增时，同时检查关注页和搜索页是否下降，并用全站有效互动判断净增长。"),("激励相容｜奖励为何会带偏行为","规则应让个人最优行为接近平台目标","若只奖励开房时长，主播可能挂机；把有效互动、健康留存和投诉率一起纳入更接近目标。")]
PSYCH_DAYS = [
("认知解离｜把想法看成一句话","想法是心理事件，不自动等于事实","把‘我一定做不好’改写成‘我注意到自己正在想：我一定做不好’，再选择一个五分钟动作。"),("可控圈｜把注意力放回下一步","区分可控制、可影响和暂时不可控","列出三栏，只从可控制栏选一件十分钟内能开始的事。"),("情绪标记｜准确命名会降低混乱","具体区分担心、失望、疲惫和羞耻","写‘我现在更接近___，强度是10分中的___’，再判断需要信息、休息还是行动。"),("实施意图｜用如果那么降低启动成本","提前把触发场景与小动作绑定","写‘如果我打开电脑仍不知从哪开始，那么我先写任务标题并计时五分钟’。"),("注意力残留｜频繁切换为何更累","切换后部分注意仍停留在上一件事","结束任务前写一句下一步和卡点，再切换；回来时直接从记录继续。"),("自我同情｜像对待朋友一样校准要求","承认困难并给出支持","把苛责句改成‘我现在很乱，但可以先完成最小版本’。"),("行为激活｜先用小行动改变环境","动力有时出现在行动之后","先做两分钟可见动作：打开文档、换衣服或走到门口，然后再决定是否继续。"),("证据检查｜把事实和预测分开","焦虑预测需要和可观察证据分列","写支持证据、反对证据和未知信息，最后选择一个能增加信息的小动作。")]


def generate_courses(_previous):
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().toordinal()
    index, phase = day % 8, (day // 8) % 4
    practice = ["圈出时间、地点与问题，再朗读两遍。","遮住中文复述情节，再核对遗漏。","替换地点和时间，口头造一个新版本。","录下复述，第二遍只修一个问题。"][phase]
    e = ENGLISH_DAYS[index]
    english = {"id":f"english-{TODAY}-{phase}","title":f"Everyday English｜{e[0]}","focus":f"关注问题、请求和确认三步；{practice}","paragraphs":[f"Today I need to handle a problem during my trip. {e[2]} I take a breath and explain the situation in one short sentence. I give the important details first, because the other person needs to know what happened before they can help me.",f"Then I make a clear and polite request: ‘{e[3]}’ I listen for the key information, especially a time, place, price, or next action. If I miss a word, I ask the other person to say it again more slowly.","Before I leave, I repeat the plan in my own words. This gives the other person a chance to correct me. I do not need perfect grammar: explain what happened, ask for what I need, and confirm what I will do next."],"translations":[f"今天练习{e[0]}。我先用一句短句说清情况：{e[2]}",f"接着礼貌提出请求：{e[3]}，重点听时间、地点、价格或下一步。","离开前用自己的话复述方案。解决问题不需要完美语法，按说明、请求、确认三步即可。"],"words":[[e[1],e[0],e[2]],["explain","解释","Let me explain what happened."],["request","请求","I have a small request."],["confirm","确认","Could I confirm the time?"],["slowly","慢一点","Could you speak more slowly?"],["next","接下来","What should I do next?"]],"remember":f"说明问题—提出请求—复述确认。{practice}","question":"没听清时最有效的做法是什么？","options":["假装听懂。","请对方说慢一点并复述关键信息。","只重复自己的问题。"],"correct":1,"explanation":"请求放慢并复述能降低听力压力和误解风险。","apply":f"用{e[0]}场景录一段30秒语音，包含问题、请求和确认。","example":f"{e[2]} {e[3]} Let me confirm what I should do next."}
    def lesson(kind, item):
        title, mechanism, example = item
        psych = kind == "psychology"
        paragraphs = [f"今天的核心是：{mechanism}。这个概念不是一句口号，而是帮助我们拆开现象、条件和行动。先描述发生了什么，再说明哪些是事实、哪些是解释，最后写出一个能够观察的变化。",f"具体例子：{example} 把动作做小，是为了降低启动成本并获得新信息。不要把一次结果当成永久结论，也不要用示例数字代替真实数据；先标清假设，再决定怎样验证。", "应用时问三个问题：如果这个解释成立，什么会先变化？还有什么原因会造成同样现象？最小验证动作是什么？这个顺序能把模糊感受变成可检查的判断，并帮助你说明结论的边界。"]
        return {"id":f"{kind}-{TODAY}-{phase}","title":title,"focus":f"关注机制、替代解释和下一步。第{phase+1}轮练习。","paragraphs":paragraphs,"remember":"合上内容后复述：现象—机制—替代解释—验证动作。","question":"怎样避免只记住一个空洞名词？","options":["只背名称。","马上下结论。","写清机制、替代解释和验证动作。"],"correct":2,"explanation":"能连接现象、机制和证据，概念才会帮助决策。","apply":"选一个今天的真实现象，写一个机制假设、一个替代解释和最小验证。","example":example}
    courses = {"english":english,"economics":lesson("economics", ECON_DAYS[index]),"psychology":lesson("psychology", PSYCH_DAYS[index])}
    if not all(valid_course(course) for course in courses.values()): raise ValueError("daily curriculum is incomplete")
    return courses


if __name__ == "__main__":
    main()
