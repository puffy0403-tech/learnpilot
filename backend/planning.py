import re, json, math
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import pandas as pd
def current_week_logs(logs):
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    if logs.empty:
        return logs.copy()
    x = logs.copy()
    x["study_date"] = pd.to_datetime(x["study_date"]).dt.date
    return x[(x["study_date"] >= week_start) & (x["study_date"] <= week_end)]

def build_rule_based_plan(goals, logs):
    if goals.empty:
        return "目前還沒有學習目標。請先在左側設定至少一個每週目標。"

    wk = current_week_logs(logs)
    studied = (
        wk.groupby("subject")["minutes"].sum().div(60).to_dict()
        if not wk.empty else {}
    )

    latest_goals = goals.drop_duplicates("subject", keep="first")
    lines = ["### 下週學習計畫", ""]
    weekdays = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

    day_i = 0
    for _, row in latest_goals.iterrows():
        subject = row["subject"]
        target = float(row["weekly_hours"])
        done = float(studied.get(subject, 0))
        remaining = max(target - done, target * 0.6)
        sessions = max(2, min(5, round(remaining)))
        each = max(0.5, remaining / sessions)

        lines.append(f"**{subject}**：建議安排 {sessions} 次，每次約 {each:.1f} 小時。")
        for _ in range(sessions):
            lines.append(f"- {weekdays[day_i % 7]}：{subject} {each:.1f} 小時")
            day_i += 1
        lines.append("")

    lines.append("> 這是依目前目標與本週完成量產生的基本規劃。")
    return "\n".join(lines)

def parse_plan_calendar(plan_text, start_date):
    if "<!-- learnpilot-v1:" in (plan_text or ""):
        rows, _ = editable_plan_data(plan_text, start_date)
        return pd.DataFrame([dict(date=r["date"], weekday=["週一","週二","週三","週四","週五","週六","週日"][r["date"].weekday()], subject=r["subject"], hours=r["minutes"]/60, content=r["content"]) for r in rows], columns=["date","weekday","subject","hours","content"])
    weekday_map = {
        "週一": 0, "星期一": 0,
        "週二": 1, "星期二": 1,
        "週三": 2, "星期三": 2,
        "週四": 3, "星期四": 3,
        "週五": 4, "星期五": 4,
        "週六": 5, "星期六": 5,
        "週日": 6, "星期日": 6, "週天": 6, "星期天": 6,
    }

    rows = []
    if not plan_text:
        return pd.DataFrame(columns=["date", "weekday", "subject", "hours", "content"])

    for raw_line in plan_text.splitlines():
        line = raw_line.strip().lstrip("-•").strip()
        if not line:
            continue

        day_name = next((d for d in weekday_map if d in line), None)
        if not day_name:
            continue

        day_index = weekday_map[day_name]
        item_date = start_date + timedelta(days=day_index)

        parts = [p.strip() for p in re.split(r"[｜|]", line) if p.strip()]
        first = parts[0] if parts else line
        first = re.sub(
            r"^(週一|週二|週三|週四|週五|週六|週日|星期一|星期二|星期三|星期四|星期五|星期六|星期日|星期天)\s*[：:]\s*",
            "",
            first,
        )

        hours = 1.0
        hour_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:小時|hr|hrs|hour|hours)",
            line,
            re.I,
        )
        if hour_match:
            hours = float(hour_match.group(1))

        subject = re.sub(
            r"\s*\d+(?:\.\d+)?\s*(?:小時|hr|hrs|hour|hours).*",
            "",
            first,
            flags=re.I,
        ).strip() or "學習"

        content = ""
        if len(parts) >= 3:
            content = parts[2]
        elif len(parts) >= 2 and not re.search(r"(小時|hr|hour)", parts[1], re.I):
            content = parts[1]

        rows.append({
            "date": item_date,
            "weekday": ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][day_index],
            "subject": subject,
            "hours": hours,
            "content": content,
        })

    return pd.DataFrame(rows)

def editable_plan_data(text, start):
    marker = "<!-- learnpilot-v1:"
    if marker in (text or ""):
        try:
            payload = text.rsplit(marker, 1)[1].strip().removesuffix("-->").strip()
            data = json.loads(payload)
            rows = [{**r, "date": date.fromisoformat(r["date"])} for r in data["items"]]
            return rows, data["notes"]
        except (ValueError, KeyError, TypeError):
            raise ValueError("計畫格式損壞，請保留原始文字並聯絡管理者。")
    rows, notes = [], []
    for line in (text or "").splitlines():
        # Only consume actual schedule lines; retain all other original text.
        if re.match(r"^\s*[-•*]?\s*(?:週|星期)[一二三四五六日天]\s*[：:]", line):
            cal = parse_plan_calendar(line, start)
            if not cal.empty:
                r = cal.iloc[0]
                minutes_match = re.search(r"(\d+(?:\.\d+)?)\s*分鐘", line)
                minutes = float(minutes_match[1]) if minutes_match else float(r["hours"])*60
                subject = re.sub(r"\s*\d+(?:\.\d+)?\s*分鐘.*", "", r["subject"]).strip()
                rows.append(dict(date=r["date"], subject=subject, minutes=minutes, content=r["content"]))
                continue
        notes.append(line)
    return rows, "\n".join(notes).strip()

def serialize_editable_plan(rows, notes):
    if not rows:
        raise ValueError("請至少新增一個學習項目。")
    cleaned = []
    for i, row in enumerate(rows, 1):
        try:
            day = date.fromisoformat(str(row["date"])[:10])
            minutes = float(row["minutes"])
        except (ValueError, TypeError, KeyError):
            raise ValueError(f"第 {i} 列：請填寫有效日期與分鐘。")
        subject = str(row.get("subject") or "").strip()
        if not subject or subject == "nan":
            raise ValueError(f"第 {i} 列：科目不可空白。")
        if not math.isfinite(minutes) or not 0 <= minutes <= 1440:
            raise ValueError(f"第 {i} 列：分鐘須大於等於 0 且不超過 1440。")
        cleaned.append(dict(date=day.isoformat(), subject=subject, minutes=minutes,
                            content=str(row.get("content") or "")))
    start = date.fromisoformat(min(r["date"] for r in cleaned))
    start -= timedelta(days=start.weekday())
    if any(date.fromisoformat(r["date"]) > start + timedelta(days=6) for r in cleaned):
        raise ValueError("一份計畫請安排在同一週；跨週項目請另建計畫。")
    lines = ["### 學習計畫", str(notes).strip(), ""]
    for r in cleaned:
        day = date.fromisoformat(r["date"])
        weekday = ["週一","週二","週三","週四","週五","週六","週日"][day.weekday()]
        lines.append(f"- {weekday}：{r['subject']}｜{r['minutes']/60:g} 小時｜{r['content']}")
    payload = json.dumps(dict(items=cleaned, notes=str(notes)), ensure_ascii=True)
    return start, "\n".join(lines) + "\n<!-- learnpilot-v1:" + payload + " -->"