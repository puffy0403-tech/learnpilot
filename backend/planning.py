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
            lines.append(f"- {weekdays[day_i % 7]}：{subject}｜{each:.1f} 小時｜{suggest_study_content(subject, day_i, logs)}")
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

        # Read duration only from its field, never from the task description.
        duration = first
        if len(parts) >= 2:
            duration_index = 2 if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", parts[1]) else 1
            duration = parts[duration_index] if len(parts) > duration_index else ""
        hours = 1.0
        duration_match = re.search(
            r"(\d+(?:\.\d+)?)\s*(分鐘|小時|hours?|hrs?)", duration, re.I
        )
        if duration_match:
            amount = float(duration_match[1])
            hours = amount / 60 if duration_match[2] == "分鐘" else amount

        subject = re.sub(
            r"\s*\d+(?:\.\d+)?\s*(?:小時|hr|hrs|hour|hours).*",
            "",
            first,
            flags=re.I,
        ).strip() or "學習"

        content = ""
        if len(parts) >= 4 and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", parts[1]):
            content = "｜".join(parts[3:])
        elif len(parts) >= 3:
            content = "｜".join(parts[2:])
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
            rows = [{**r, "date": date.fromisoformat(r["date"]), "start_time": r.get("start_time") or extract_start_time(r.get("content", "")) or "08:00"} for r in data["items"]]
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
                minutes = float(r["hours"])*60
                subject = re.sub(r"\s*\d+(?:\.\d+)?\s*分鐘.*", "", r["subject"]).strip()
                rows.append(dict(date=r["date"], subject=subject, minutes=minutes, content=r["content"], start_time=extract_start_time(line) or "08:00"))
                continue
        notes.append(line)
    return rows, "\n".join(notes).strip()

def validate_daily_starts(values):
    values = values or {}
    if not isinstance(values, dict) or any(str(k) not in [str(i) for i in range(7)] or not isinstance(v, str) or not re.fullmatch(r"(?:[01]\d|2[01]):[0-5]\d", v) for k, v in values.items()):
        raise ValueError("每日開始時間須為 00:00–21:59。")
    return {str(k): v for k, v in values.items()}


def plan_daily_starts(text):
    marker = "<!-- learnpilot-v1:"
    if marker not in (text or ""):
        return {}
    try:
        return validate_daily_starts(json.loads(text.rsplit(marker, 1)[1].strip().removesuffix("-->").strip()).get("daily_starts", {}))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("每日開始時間設定格式錯誤。")


def validate_availability(windows):
    if windows is None:
        return None
    if not isinstance(windows, list) or len(windows)>100:
        raise ValueError("可用時段格式錯誤。")
    cleaned=[]
    for w in windows:
        try:
            day=date.fromisoformat(w['date']).isoformat()
            start,end=w['start_time'],w['end_time']
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start) or not re.fullmatch(r"(?:(?:[01]\d|2[0-3]):[0-5]\d|24:00)", end):
                raise ValueError()
            begin=int(start[:2])*60+int(start[3:])
            finish=int(end[:2])*60+int(end[3:])
            if begin>=finish:
                raise ValueError()
            if any(r['date']==day and begin<r['end'] and r['begin']<finish for r in cleaned):
                raise ValueError()
            cleaned.append(dict(date=day,begin=begin,end=finish))
        except (KeyError,TypeError,ValueError):
            raise ValueError("可用時段須為同日、有效且不重疊的時間範圍。") from None
    return cleaned


def plan_availability(text):
    marker="<!-- learnpilot-v1:"
    if marker not in (text or ""):
        return None
    try:
        windows=json.loads(text.rsplit(marker,1)[1].strip().removesuffix("-->").strip()).get('availability_windows')
        validate_availability(windows)
        return windows
    except (ValueError,TypeError,AttributeError):
        raise ValueError("計畫的可用時段設定損壞。") from None


def serialize_editable_plan(rows, notes, daily_starts=None, availability_windows=None):
    daily_starts = validate_daily_starts(daily_starts)
    windows = validate_availability(availability_windows)
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
                            content=str(row.get("content") or ""),
                            start_time=str(row.get("start_time") or extract_start_time(row.get("content", "")) or "08:00"), kind=str(row.get("kind") or "study")))
        time = cleaned[-1]["start_time"]
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time):
            raise ValueError(f"第 {i} 列：開始時間格式錯誤。")
        begin = int(time[:2])*60+int(time[3:])
        if cleaned[-1]["kind"] != "study" and begin+minutes > 1440:
            raise ValueError(f"第 {i} 列：固定項目不可超過午夜。")
        if cleaned[-1]["kind"] not in ("study", "blocked", "todo"):
            raise ValueError("無效的項目類型。")
        completed = row.get('completed', False)
        if not isinstance(completed, bool):
            raise ValueError("完成狀態須為布林值。")
        if completed and cleaned[-1]['kind'] != 'study':
            raise ValueError("只有讀書計畫可標記完成。")
        if 'completed' in row:
            cleaned[-1]['completed'] = completed
        if row.get('plan_item_id') is not None:
            if type(row['plan_item_id']) is not int or row['plan_item_id'] < 1:
                raise ValueError('讀書項目編號格式錯誤。')
            cleaned[-1]['plan_item_id'] = row['plan_item_id']
        if row.get('completion_key'):
            key = row['completion_key']
            if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{32}', key):
                raise ValueError('完成紀錄識別碼格式錯誤。')
            cleaned[-1]['completion_key'] = key
    cleaned = fit_calendar_slots(cleaned, daily_starts, availability_windows)
    seen_completion_keys = set()
    seen_item_ids = set()
    for row in cleaned:
        item_id = row.get('plan_item_id')
        if item_id in seen_item_ids:
            row.pop('plan_item_id', None)
        elif item_id:
            seen_item_ids.add(item_id)
        key = row.get('completion_key')
        if key in seen_completion_keys:
            row.pop('completion_key', None)
        elif key:
            seen_completion_keys.add(key)
    for i, a in enumerate(cleaned):
        for b in cleaned[:i]:
            if a["date"] == b["date"]:
                am = int(a["start_time"][:2])*60+int(a["start_time"][3:])
                bm = int(b["start_time"][:2])*60+int(b["start_time"][3:])
                if a["minutes"] and b["minutes"] and am < bm+b["minutes"] and bm < am+a["minutes"]:
                    raise ValueError("同一天的項目時間重疊，請調整開始時間或分鐘。")
    start = date.fromisoformat(min(r["date"] for r in cleaned))
    start -= timedelta(days=start.weekday())
    if any(date.fromisoformat(r["date"]) > start + timedelta(days=6) for r in cleaned):
        raise ValueError("一份計畫請安排在同一週；跨週項目請另建計畫。")
    lines = ["### 學習計畫", str(notes).strip(), ""]
    for r in cleaned:
        day = date.fromisoformat(r["date"])
        weekday = ["週一","週二","週三","週四","週五","週六","週日"][day.weekday()]
        lines.append(f"- {weekday}：{r['subject']}｜{r['start_time']}｜{r['minutes']/60:g} 小時｜{r['content']}")
    payload = json.dumps(dict(items=cleaned, notes=str(notes), daily_starts=daily_starts, availability_windows=availability_windows), ensure_ascii=True)
    return start, "\n".join(lines) + "\n<!-- learnpilot-v1:" + payload + " -->"

def free_study_gaps(day, windows, occupied):
    """Free intervals, clipped at calendar cell boundaries and fixed reservations."""
    gaps=[]
    def add(begin,finish):
        while begin<finish:
            stop=min(finish,(begin//120+1)*120)
            gaps.append((begin,stop))
            begin=stop
    busy=sorted((int(r.get('start_time','08:00')[:2])*60+int(r.get('start_time','08:00')[3:]),float(r['minutes'])) for r in occupied if str(r['date'])[:10]==day and float(r['minutes'])>0)
    for w in sorted((w for w in windows if str(w['date'])[:10]==day),key=lambda w:w['start_time']):
        cursor=int(w['start_time'][:2])*60+int(w['start_time'][3:])
        end=int(w['end_time'][:2])*60+int(w['end_time'][3:])
        for begin,length in busy:
            if begin+length<=cursor or begin>=end:
                continue
            if cursor<begin:
                add(cursor,min(begin,end))
            cursor=max(cursor,math.ceil(begin+length))
            if cursor>=end:
                break
        if cursor<end:
            add(cursor,end)
    return gaps


def spread_weekly_task(row, output, windows, week_start, deadline=None):
    """Spread weekly minutes over least-loaded available days; never invent time."""
    dates=[str(week_start+timedelta(days=i)) for i in range(7)]
    if deadline:
        dates=[d for d in dates if d<=deadline]
    gaps={d:free_study_gaps(d,windows,output) for d in dates}
    capacity={d:sum(end-begin for begin,end in gaps[d]) for d in dates}
    loads={d:sum(float(r['minutes']) for r in output if str(r['date'])[:10]==d and r.get('kind','study')=='study') for d in dates}
    assigned={d:0 for d in dates}
    remaining=float(row['minutes'])
    while remaining>0:
        candidates=[d for d in dates if capacity[d]>assigned[d]]
        if not candidates:
            break
        day=min(candidates,key=lambda d:(loads[d]+assigned[d],d))
        # Fifteen-minute allocation units avoid unnecessary one-minute sessions.
        amount=min(15,remaining,capacity[day]-assigned[day])
        assigned[day]+=amount
        remaining-=amount
    for day in dates:
        amount=assigned[day]
        for begin,end in gaps[day]:
            if amount<=0:
                break
            duration=min(amount,end-begin)
            output.append(dict(date=day,start_time=f'{begin//60:02}:{begin%60:02}',minutes=duration,subject=row['subject'],content=row.get('content',''),kind='study'))
            amount-=duration
    return remaining


def schedule_available(rows, fixed, week_start, daily_starts=None):
    """Fit suggestions into free daytime slots; preserve fixed reservations exactly."""
    daily_starts = validate_daily_starts(daily_starts)
    output = [dict(r) for r in fixed]
    serialize_editable_plan(output, "") if output else None
    if any(not week_start <= date.fromisoformat(str(r["date"])[:10]) <= week_start+timedelta(days=6) for r in fixed):
        raise ValueError("保留時間與待辦必須位於選定週。")
    windows=[]
    for offset in range(7):
        day=str(week_start+timedelta(days=offset))
        time=daily_starts.get(str((week_start+timedelta(days=offset)).weekday()),'08:00')
        minimum=int(time[:2])*60+int(time[3:])
        for hour in range(minimum//120*2,22,2):
            begin,finish=max(hour*60,minimum),(hour+2)*60
            busy=[(int(r.get('start_time','08:00')[:2])*60+int(r.get('start_time','08:00')[3:]),float(r['minutes'])) for r in fixed if str(r['date'])[:10]==day]
            # Retain the existing whole-cell exclusion for fixed reservations.
            if any(b<finish and b+length>begin for b,length in busy if length>0):
                continue
            windows.append(dict(date=day,start_time=f'{begin//60:02}:{begin%60:02}',end_time=f'{finish//60:02}:{finish%60:02}'))
    unplaced=0
    for row in rows:
        unplaced+=spread_weekly_task(row,output,windows,week_start)
    return output, unplaced


def suggest_study_content(subject, index=0, logs=None):
    """Concrete fallback tasks without inventing textbook chapters or prior mastery."""
    if re.search(r"英文|英語|English|TOEIC|雅思|IELTS", subject, re.I):
        tasks = ["複習 10 個單字並各造一句；閱讀一篇短文，標記不熟悉的句型；完成 5 題理解題並訂正。", "聆聽一段 3–5 分鐘英語材料兩次，整理主旨與 3 個重點；跟讀關鍵句並錄音檢查。", "複習一個文法主題，完成 10 題練習；整理錯誤原因並寫出 3 個例句。"]
    elif re.search(r"數學|微積分|統計|線性代數", subject):
        tasks = ["選一個目前進度中的概念，整理定義與公式；完成 3–5 題練習，逐題檢查解題步驟並訂正。", "重做近期錯題，標記卡住的步驟；整理一頁公式與適用條件，完成 2 題同類題檢核。"]
    elif re.search(r"程式|Python|Java|資訊|演算法|AI|人工智慧", subject, re.I):
        tasks = ["選一個目前進度中的概念，閱讀筆記並手寫簡要說明；實作一個小範例，測試正常與邊界輸入並記錄問題。", "重做一個近期未完成的練習；檢查錯誤訊息、修正程式，整理解法與下一步待練習項目。"]
    else:
        tasks = [f"閱讀{subject}目前進度中的一個小節，整理 3 個核心概念；完成 3 題練習或自擬問題，核對答案並記錄疑問。", f"不看筆記回想{subject}上次學習重點；針對不熟悉處重讀教材，整理一頁摘要並完成自我測驗。", f"複習{subject}近期錯題或待釐清問題，完成一項應用練習；記錄學到的內容及下一次的學習重點。"]
    content = tasks[index % len(tasks)] + " 依本時段長度調整題數，最後保留約 5 分鐘回顧。"
    if logs is not None and not logs.empty:
        recent = logs[(logs["subject"] == subject) & logs["note"].fillna("").astype(str).str.strip().ne("")]
        if not recent.empty:
            content += " 參考最近學習筆記：" + str(recent.iloc[0]["note"])[:160]
    return content


def ensure_study_content(rows, logs):
    return [{**r, "content": str(r.get("content") or "").strip() or suggest_study_content(r["subject"], i, logs)} for i, r in enumerate(rows)]


def extract_start_time(text):
    match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)\s*[-–—~～至]\s*(?:[01]?\d|2[0-4]):[0-5]\d", str(text or ""))
    return f"{int(match[1]):02}:{match[2]}" if match else None


def fit_calendar_slots(rows, daily_starts=None, availability_windows=None):
    """Sequentially pack study tasks into gaps without exceeding a two-hour cell."""
    daily_starts = validate_daily_starts(daily_starts)
    windows = validate_availability(availability_windows)
    if not rows:
        return []
    start = min(date.fromisoformat(str(r["date"])[:10]) for r in rows)
    week_end = start - timedelta(days=start.weekday()) + timedelta(days=6)
    output = [{**r, "date": str(r["date"])[:10]} for r in rows if r.get("kind", "study") != "study"]
    tasks = sorted(enumerate(r for r in rows if r.get("kind", "study") == "study"), key=lambda pair:(str(pair[1]["date"]),pair[1].get("start_time", "08:00"),pair[0]))
    for _, row in tasks:
        day = date.fromisoformat(str(row["date"])[:10])
        time = row.get("start_time") or extract_start_time(row.get("content", "")) or "08:00"
        cursor = int(time[:2])*60+int(time[3:])
        remaining = float(row["minutes"])
        minimum = daily_starts.get(str(day.weekday()), "00:00")
        cursor = max(cursor, int(minimum[:2])*60+int(minimum[3:]))
        time = f"{cursor//60:02}:{cursor%60:02}"
        if remaining == 0:
            if windows is not None and not any(w['date']==str(day) and w['begin']<=cursor<w['end'] for w in windows):
                raise ValueError("零分鐘項目也須位於對話確認的可用時段內。")
            output.append({**row, "date":str(day), "start_time":time, "kind":"study"})
        while remaining > 0:
            if cursor >= 1440:
                day += timedelta(days=1)
                cursor = 0
            if day > week_end:
                raise ValueError("本週可用時段不足，請減少時數或另建下一週計畫；未刪除任何任務。")
            minimum = daily_starts.get(str(day.weekday()), "00:00")
            cursor = max(cursor, int(minimum[:2])*60+int(minimum[3:]))
            allowed_end=1440
            if windows is not None:
                available=sorted((w for w in windows if w['date']==str(day) and w['end']>cursor),key=lambda w:w['begin'])
                if not available:
                    day += timedelta(days=1)
                    cursor=0
                    continue
                cursor=max(cursor,available[0]['begin'])
                allowed_end=available[0]['end']
            slot_end = min(allowed_end, (cursor//120+1)*120)
            occupied = sorted((int(r.get("start_time", "08:00")[:2])*60+int(r.get("start_time", "08:00")[3:]), float(r["minutes"])) for r in output if str(r["date"])==str(day) and float(r["minutes"])>0)
            gap_end = slot_end
            for begin, length in occupied:
                if begin+length <= cursor or begin >= slot_end:
                    continue
                if begin <= cursor:
                    cursor = min(slot_end, int(math.ceil(begin+length)))
                    gap_end = cursor
                    break
                gap_end = min(gap_end, begin)
                break
            if gap_end <= cursor:
                continue
            amount = min(remaining, gap_end-cursor)
            output.append({**row, "date":str(day), "start_time":f"{cursor//60:02}:{cursor%60:02}", "minutes":amount, "kind":"study"})
            remaining -= amount
            cursor = int(math.ceil(cursor+amount))
    return sorted(output, key=lambda r:(str(r["date"]),r.get("start_time", "08:00")))
