import React, {useEffect, useState} from 'react';

const messages = [
  '把目標化為每天看得見的進步。',
  '今天多懂一點，明天就多一分自信。',
  '不用一次做到最好，先完成今天的一小步。',
  '每一次專心，都在為未來累積力量。',
  '慢慢學、穩穩走，你正在前進。',
  '把大目標拆小，讓今天的努力有方向。',
  '遇到不懂的地方，就是新的起點。',
  '今天的練習，會成為明天的底氣。',
  '不必和別人比，看看自己又學會了什麼。',
  '先開始十分鐘，也是一個很好的開始。',
  '每一次訂正，都讓理解更清楚。',
  '留一點時間回顧，讓學到的東西留下來。',
  '休息一下再出發，也是在照顧學習的節奏。',
  '把注意力放在眼前這一步，你做得到。',
  '學習有快有慢，持續嘗試就有機會。',
  '今天完成的小事，都值得被看見。',
  '把疑問記下來，答案就有了起點。',
  '先求理解，再用練習讓自己更熟悉。',
  '你花在學習上的心力，正在累積。',
  '給自己一點耐心，新的能力需要時間。',
  '比昨天更清楚一點，就是值得肯定的進步。',
  '專注一個小目標，讓今天更踏實。',
  '走得慢沒關係，找回適合自己的步調。',
  '把學會的內容說出來，看看自己懂了多少。',
  '今天的問題，可能就是下一次突破的線索。',
  '完成一項，再開始下一項。',
  '願意重新嘗試，就是向前的力量。',
  '安排適合自己的計畫，讓努力更有方向。',
  '每一段用心的學習，都有它的價值。',
  '為今天的努力留個紀錄，也給自己一點肯定。',
  '帶著好奇心開始，帶著新收穫結束今天。',
];

export function encouragementForDate(date = new Date()) {
  // Use the browser's calendar date; UTC arithmetic avoids DST day-length shifts.
  const day = Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000);
  return messages[((day % messages.length) + messages.length) % messages.length];
}

export default function DailyEncouragement() {
  const [message, setMessage] = useState(encouragementForDate);
  useEffect(() => {
    let timer;
    function refresh() {
      const now = new Date();
      setMessage(encouragementForDate(now));
      clearTimeout(timer);
      const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
      timer = setTimeout(refresh, Math.max(1, midnight.getTime() - now.getTime()) + 50);
    }
    function visible() {if (document.visibilityState === 'visible') refresh();}
    refresh();
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', visible);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', visible);
    };
  }, []);
  return <p className="daily-encouragement">{message}</p>;
}
