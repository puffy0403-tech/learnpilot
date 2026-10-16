import React, {useState} from 'react';

export default function GoalProgress({done, goal, subject, user}) {
  const [failedPhoto, setFailedPhoto] = useState(null);
  const photo = user.user_metadata?.profile_photo;
  const name = user.user_metadata?.display_name || user.email;
  const fraction = goal > 0 ? Math.min(1, Math.max(0, done / goal)) : 0;

  return <div className="goal-progress">
    <div className="goal-progress-lane">
      <div className="goal-progress-person" style={{left: `${fraction * 100}%`}}
        title={`${name} · 已完成 ${Math.round(fraction * 100)}%`}>
        {photo && photo !== failedPhoto
          ? <img src={photo} alt={`${name}的個人照片`} onError={() => setFailedPhoto(photo)}/>
          : <svg viewBox="0 0 40 40" role="img" aria-label="預設個人頭像"><circle cx="20" cy="14" r="7"/><path d="M7 36v-3a13 13 0 0 1 26 0v3Z"/></svg>}
      </div>
      <progress max="1" value={fraction} aria-label={`${subject}每週目標進度`}/>
    </div>
  </div>;
}
