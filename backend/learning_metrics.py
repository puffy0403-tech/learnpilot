"""Account-scoped feedback views and descriptive learning metrics."""
from collections import Counter, defaultdict

LEVELS={1:'不太理解',2:'部分理解',3:'能獨立完成',4:'能向別人解釋'}

def log_views(c, rows):
    logs=[dict(r) for r in rows]
    if not logs:
        return []
    feedback={r['study_log_id']:dict(r) for r in c.execute('SELECT f.* FROM learning_feedback f JOIN study_logs l ON l.id=f.study_log_id WHERE l.user_id=?',(logs[0]['user_id'],))}
    for log in logs:
        log['feedback']=feedback.get(log['id'])
    return logs

def effectiveness(c,user_id,start,end,logs):
    from learning_context import current_date
    cutoff=min(str(end),str(current_date()))
    # One current version per week, so copies of a plan do not inflate counts.
    items=[dict(r) for r in c.execute('''WITH chosen AS (
        SELECT id,ROW_NUMBER() OVER(PARTITION BY week_start ORDER BY selected_at IS NOT NULL DESC,selected_at DESC,id DESC) AS rank
        FROM plans WHERE user_id=?)
        SELECT i.* FROM plan_items i JOIN chosen p ON p.id=i.plan_id AND p.rank=1
        WHERE i.kind='study' AND i.scheduled_date BETWEEN ? AND ?''',(user_id,str(start),cutoff))]
    done=sum(bool(r['completed_at']) for r in items)
    reported=[l for l in logs if l['planned_minutes'] is not None and l['time_source'] in ('manual','self_reported')]
    distribution=Counter(l['feedback']['understanding'] for l in logs if l.get('feedback') and l['feedback']['understanding'] is not None)
    groups=defaultdict(list)
    for l in sorted(logs,key=lambda x:(x['study_date'],x['id'])):
        f=l.get('feedback')
        if f and f['understanding'] is not None and f['topic'].strip():
            groups[(l['subject'],f['topic'] or '未分主題')].append(l)
    trends=[]
    for (subject,topic),values in groups.items():
        if len({v['study_date'] for v in values})>=2:
            trends.append(dict(subject=subject,topic=topic,first=values[0]['feedback']['understanding'],last=values[-1]['feedback']['understanding']))
    return dict(due_items=len(items),completed_items=done,completion_rate=done/len(items) if items else None,
        comparison_records=len(reported),planned_minutes=sum(l['planned_minutes'] for l in reported),actual_minutes=sum(l['minutes'] for l in reported),
        estimated_records=sum(l['time_source']=='planned' for l in logs),unknown_time_records=sum(l['time_source']=='legacy' for l in logs),
        understanding_distribution=dict(distribution),unrated_records=sum(not l.get('feedback') or l['feedback']['understanding'] is None for l in logs),trends=trends)

def effectiveness_text(m):
    rate='尚無應完成項目' if m['completion_rate'] is None else f"{m['completed_items']}/{m['due_items']} 項（{m['completion_rate']*100:.0f}%）"
    comparison='尚無同時具有預計與實際時間的紀錄' if not m['comparison_records'] else f"{m['comparison_records']} 筆，預計 {m['planned_minutes']:g} 分鐘，實際 {m['actual_minutes']:g} 分鐘，差異 {m['actual_minutes']-m['planned_minutes']:+g} 分鐘"
    lines=['學習成效追蹤',f'計畫完成率：{rate}（各週目前選用版本，截至今天或期間截止日）',f'時間比較：{comparison}',f"沿用預計時間：{m['estimated_records']} 筆；舊紀錄時間來源未確認：{m['unknown_time_records']} 筆",'理解程度（自評）：'+ '、'.join(f"{name} {m['understanding_distribution'].get(level,0)} 筆" for level,name in LEVELS.items()),f"尚未填理解程度：{m['unrated_records']} 筆"]
    if not m['trends']:
        lines.append('理解變化：尚無足夠的跨日同科目、同主題回饋，無法判斷變化。')
    for t in m['trends']:
        lines.append(f"{t['subject']}／{t['topic']}：{LEVELS[t['first']]} → {LEVELS[t['last']]}（本期間首次至最近一次自評）")
    lines.append('自評與完成率不等同測驗成績；總學習時間可能含預計時間，不合成學習成效總分。')
    return '\n'.join(lines)
