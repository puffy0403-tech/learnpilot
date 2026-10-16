"""Run locally after closing LearnPilot; never uploads database contents."""
import socket
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / '.env')
from database import DB_PATH
from local_storage import inspect_database, restore_database


def main():
    root = Tk()
    root.withdraw()
    try:
        with socket.socket() as probe:
            probe.settimeout(1)
            if probe.connect_ex(('127.0.0.1', 8000)) == 0:
                messagebox.showerror('請先關閉後端', '8000 連接埠仍在使用中。請在 LearnPilot Backend 視窗按 Ctrl+C，再重新執行還原工具。')
                return
        messagebox.showinfo('還原原本帳號與學習資料',
            '請選取原本專案的 backend\\data\\learnpilot.db。\n'
            '若曾自行設定 DATABASE_PATH，請選取該位置的原資料庫。\n'
            '工具會保留來源原檔，並先備份目前資料庫；還原會替換目前資料，不會合併帳號。\n\n'
            f'目前資料位置：\n{DB_PATH.resolve()}\n\n'
            '如果找不到舊資料庫，就無法從只有程式碼的 ZIP 還原舊帳號。')
        selected = filedialog.askopenfilename(title='選取原本的 learnpilot.db', initialdir=str(Path.home() / 'Downloads'),
            filetypes=[('SQLite 資料庫', '*.db'), ('所有檔案', '*')])
        if not selected:
            return
        counts = inspect_database(selected)
        if not counts['users']:
            raise ValueError('這份資料庫沒有帳號，請選取原本有使用紀錄的資料庫。')
        if not messagebox.askyesno('確認還原',
            f'來源：{selected}\n帳號：{counts["users"]} 個；學習紀錄：{counts["study_logs"]} 筆\n\n'
            f'目的地：{DB_PATH.resolve()}\n\n'
            '現有資料會先備份後替換，所有登入需重新登入。是否繼續？'):
            return
        backup = restore_database(selected, DB_PATH)
        messagebox.showinfo('還原完成', f'帳號及學習資料已還原，來源原檔保留。\n備份：{backup or "目的地原本不存在，無舊檔需備份"}\n\n'
            '請重新執行「啟動網頁.bat」。忘記舊密碼時可申請郵件重設；寄信仍需有效的 Resend 設定。')
    except Exception as exc:
        messagebox.showerror('未完成還原', str(exc))
    finally:
        root.destroy()


if __name__ == '__main__':
    main()
