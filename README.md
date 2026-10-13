# LearnPilot — React + FastAPI + SQLite

前端 React/Vite，後端 Python/FastAPI。本版本的帳號、登入工作階段、個人資料、目標、學習紀錄與計畫全部存在本機 SQLite，不需要 Supabase。

## 首次啟動（Windows PowerShell）

安裝 Python 3.10+ 與 Node.js（20.19+ 或 22.12+），解壓縮後在 VS Code 開啟 `learnpilot-react`。

第一個終端機，從專案根目錄執行：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

後端會自動建立 `backend/data/learnpilot.db`。不需安裝 SQLite 或手動執行 SQL。

第二個終端機，從專案根目錄執行：

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

開啟 http://localhost:5173，按「建立新帳號」，註冊後即可使用。註冊不寄送驗證信。前後端都請使用 localhost，不要混用 127.0.0.1。保留兩個終端機開啟；Ctrl+C 可停止。

## 下次啟動

在 backend 執行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

在 frontend 執行：

```powershell
npm run dev
```

不需重裝套件或重新複製 .env。修改環境設定後需重啟服務。後端檢查：http://localhost:8000/health，文件：http://localhost:8000/docs。

## 資料與備份

所有資料保存在 `backend/data/learnpilot.db`，請勿刪除或加入版本控制。備份時先停止後端，再複製這個檔案；還原時先停止後端，再以備份檔替換。重新啟動不會清空資料。若設定 DATABASE_PATH，資料會存放於指定路徑；相對路徑依後端的執行目錄解析。

本壓縮檔沒有舊 Supabase 的實際資料，也不會自動從 Supabase 匯入資料。原 Supabase 帳號與密碼不能直接使用，請建立本機帳號；舊資料需要另外匯出及搬移。現有 learnpilot-v1 計畫文字格式仍可解析。

## AI 計畫

在 `backend/.env` 填入 `GEMINI_API_KEY` 和帳號可用的 `GEMINI_MODEL`。留白時使用規則式建議，AI 失敗時也會自動切換為規則式建議。

## 登入與部署

密碼以隨機 salt + PBKDF2-SHA256 儲存，登入 token 的雜湊保存在 SQLite。瀏覽器以 HttpOnly cookie 保留登入 30 天；登出會撤銷該工作階段。API 按登入使用者隔離資料，不能指定其他使用者的 user_id。

目前設定用於本機開發。公開部署須使用 HTTPS、將 COOKIE_SECURE=true、設定 FRONTEND_ORIGINS 為前端實際來源，前端 VITE_API_URL 指向實際後端，並增加登入限流。建議以同站來源部署前後端，以符合 SameSite=Lax cookie 設定。SQLite 檔案需放在持久磁碟，不適用會清空磁碟的短暫執行環境。

## 驗證

在 backend 執行 `python -m unittest discover -s tests`（測試另外需要 `pip install httpx`）。前端建置：在 frontend 執行 `npm run build`。
