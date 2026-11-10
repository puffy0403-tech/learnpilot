// Dates use the browser's local calendar, matching the learning calendar.
export function weekRange(day){
 const start=new Date(day+'T00:00:00');start.setDate(start.getDate()-(start.getDay()+6)%7);
 const end=new Date(start);end.setDate(end.getDate()+6);
 const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
 return {start:iso(start),end:iso(end)};
}
export function currentWeekGoals(goals,day){
 const {start,end}=weekRange(day);
 // Filter by week before choosing the latest goal per subject, so a goal
 // created for next week does not hide an existing goal for this week.
 return goals.filter(g=>!g.target_date||(g.target_date>=start&&g.target_date>=day&&g.target_date<=end))
   .sort((a,b)=>b.id-a.id).filter((g,i,a)=>a.findIndex(x=>x.subject===g.subject)===i);
}
