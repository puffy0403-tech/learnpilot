# LearnPilot — React + FastAPI + SQLite

前端 React/Vite，後端 Python/FastAPI。本版本的帳號、登入工作階段、個人資料、目標、學習紀錄與計畫全部存在本機 SQLite，不需要 Supabase。

## 首次啟動（Windows PowerShell）

安裝 Python 3.10+ 與 Node.js（20.19+ 或 22.12+），解壓縮後在 VS Code 開啟 `learnpilot-main`。

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

在 `backend/.env` 設定 OpenAI 或 Gemini。`AI_PROVIDER=auto` 時，有 OPENAI_API_KEY 就使用 OpenAI，否則使用 Gemini。一般「產生建議計畫」在 AI 未設定或失敗時仍可改用規則式建議；「AI 規劃對話」需要可用的 AI 設定，失敗時保留既有對話並顯示原因。

## 登入與部署

密碼以隨機 salt + PBKDF2-SHA256 儲存，登入 token 的雜湊保存在 SQLite。瀏覽器以 HttpOnly cookie 保留登入 30 天；登出會撤銷該工作階段。API 按登入使用者隔離資料，不能指定其他使用者的 user_id。

目前設定用於本機開發。公開部署須使用 HTTPS、將 COOKIE_SECURE=true、設定 FRONTEND_ORIGINS 為前端實際來源，前端 VITE_API_URL 指向實際後端，並增加登入限流。建議以同站來源部署前後端，以符合 SameSite=Lax cookie 設定。SQLite 檔案需放在持久磁碟，不適用會清空磁碟的短暫執行環境。

## 驗證

在 backend 執行 `python -m unittest discover -s tests`（測試另外需要 `pip install httpx`）。前端建置：在 frontend 執行 `npm run build`。

## 新增功能使用方式

1. 在「AI Study Plan」先設定週起始日、保留空白及固定待辦，再產生建議。AI／規則任務由系統放入剩餘空檔，預設學習時間為 08:00–22:00；可手動設定其他時間。
2. 每筆計畫可修改開始時間、分鐘及詳細內容。保留空白與待辦在上方修改；儲存時以該設定為準。系統拒絕重疊、跨午夜及跨週安排。
3. 日曆顯示全天 12 個兩小時時段。點選卡片查看全文，再按「開始倒計時」；可暫停／繼續。倒計時保存在本瀏覽器，重新整理可恢復；一次計時一項任務。計時結束不會自動新增學習紀錄。
4. 按「啟用學習提醒與鬧鐘」後，排程開始時及倒計時結束時提醒。瀏覽器通知需允許權限；關閉網頁、電腦休眠或瀏覽器暫停背景分頁時不保證即時提醒。
5. 本週目標頁顯示目標日期與剩餘天數。
6. 「學習報告」選擇週／月及日期，自動整理實際紀錄、科目時數、達成率與回顧建議，可下載文字報告。報告使用目前設定目標，非歷史目標快照；月目標按天數換算。
7. 舊版無開始時間的計畫預設顯示於 08:00，請編輯調整後再儲存。

測試：在 backend 執行 `python -m pytest tests -q`（需要 pytest 與 httpx）。

## 日曆與讀書內容更新

- 灰色：保留空白；橘色：固定待辦；綠色：讀書計畫。卡片與圖例均附文字標籤。
- 今天所在欄以紫色底與「今天」標籤顯示；查看其他週時不會錯標。
- 點選卡片查看日期、起始時間、讀書時數及完整讀書計畫。
- 新生成的建議包含具體學習步驟、練習與檢核；未設定 Gemini 時會使用規則式內容。既有計畫保留原文，請重新生成才能取得新建議。

顏色修正版：未安排格子以灰底顯示；橘色固定待辦、綠色讀書計畫使用更明顯的色塊。今天仍以紫色欄位標示。舊資料缺少 kind 時，僅依「保留空白」「固定待辦」精確名稱補足分類，其他項目視為讀書計畫。
更新時覆蓋 frontend/src/features.jsx 與 frontend/src/style.css，重新啟動前端；保留原有 backend/data 及 .env。

時間同步修正：詳細視窗與日曆卡片使用該筆計畫的 start_time，另顯示按分鐘計算的結束時間。舊計畫若無 start_time，但內容含 14:00–16:00 等明確時段，會讀取該起始時間；完全無時間資料時維持 08:00，請手動調整並儲存。計畫文字匯出也保留起始時間。

## 時段對齊
新生成的讀書計畫以兩小時格子的起點安排（08:00、10:00 等），每筆最多 120 分鐘。保留時間或固定待辦佔用到的格子會整格避開，可能因此減少可排時間；不足時顯示未安排分鐘。跨格子的既有或手動計畫會在日曆分段顯示，每段詳細內容、倒計時皆以目前點選的分段時間計算；原計畫總時數仍保留。既有任意開始時間不會自動移動，重新生成可取得對齊時段的新排程。

讀書時數限制：儲存時檢查每筆 study 須在所在兩小時格內完成。例如 14:00 最多 120 分鐘、14:30 最多 90 分鐘、15:45 最多 15 分鐘。超過時會提示拆成另一筆，保留空白與固定待辦可跨格。

合計時數更新：以同一兩小時時段內所有科目合計 120 分鐘為上限，依日期、原起始時間與項目順序排列。儲存與讀取時自動將重疊、超出的讀書時數拆分到後續空檔，避開保留空白及固定待辦。跨午夜可接續到下一天；若超出本週則提示調整或另建下週計畫，不會默默刪除任務。先前「超出即拒絕」的讀書限制已改為自動順延。

保留空白與固定待辦編輯區：編輯列與新增按鈕沿用日曆的灰色／橘色配色，編輯列顯示類型標籤，窄螢幕自動換行。

## 每日讀書開始時間
AI Study Plan 的編輯區可分別設定一週七天的開始時間（00:00–21:59；預設 08:00）。產生建議時，僅安排在每日設定時間至 22:00，並避開保留空白及固定待辦。非整點時間可用，例如 13:30 會先安排 30 分鐘至 14:00。
按「套用至現有讀書項目」可將每天的讀書項目改從設定時間依序安排；儲存時自動避開固定事項。單純儲存則只順延早於設定時間的項目。設定隨計畫保存，再次編輯會還原。
更新本功能須一起更新 frontend/src/main.jsx、features.jsx、style.css 以及 backend/main.py、planning.py，並重新啟動前後端；請保留原有 .env 與 backend/data。

## AI 規劃對話（新增）

1. 更新檔案前，保留原本 backend/data 與 backend/.env。請勿以壓縮檔內的初始資料覆蓋自己的紀錄。
2. 先關閉前後端視窗，執行「安裝或更新套件.bat」，更新本功能需要的 OpenAI 套件。也可在 backend 使用虛擬環境執行 `python -m pip install -r requirements.txt`。
3. 在既有 backend/.env 加入以下設定；保留其他設定及金鑰，不要直接用 .env.example 覆寫：

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=填入你的OpenAI_API金鑰
OPENAI_MODEL=gpt-4.1-mini
```

若繼續使用 Gemini，可設 AI_PROVIDER=gemini 並填寫 GEMINI_API_KEY、GEMINI_MODEL。
OpenAI API 需有可用額度，ChatGPT 訂閱與 API 計費分開；金鑰只存放後端，不需貼在對話框。

4. 重新執行「啟動網頁.bat」。側邊欄開啟「AI 規劃對話」，選定週起始日，開始描述科目、希望讀多久、明確可用日期及時間、固定行程與困擾。
5. 助理會逐步提問並整理需求。條件足夠後，按「根據對話產生建議計畫」。草稿列出學習內容、時段、安排依據及時間不足而未安排的分鐘。
6. 確認後按「匯入目前計畫編輯區」，可調整內容，再按「儲存計畫並查看日曆」。匯入會替換目前尚未儲存的編輯內容；編輯既有計畫時，最後儲存會更新該份計畫。
7. 對話以目前登入帳號與週起始日分開儲存在 SQLite，重新整理可還原。每個對話最多 30 輪，超過可產生草稿或按「開始新對話」。清除對話不會刪除已儲存計畫。
8. 草稿會保留「對話確認的讀書時段」，儲存及再次編輯仍受此限制。若要更改時間，回到對話重新產生，或在編輯區明確按「解除對話時段限制」。

系統會以登入者的目標、最近 15 筆學習紀錄、編輯區的時間設定及此週對話提供規劃。傳送與產生草稿時，這些資料會交由設定的 AI 服務處理。OpenAI 請求設定 store=False；對話保存在本機 SQLite。服務連線與實際模型品質需在自己的有效金鑰環境驗證。

程式新增 backend/ai_service.py、backend/chat_planner.py、frontend/src/PlanningChat.jsx，並更新 main.py、database.py、planning.py、requirements.txt、.env.example、main.jsx 及 style.css；更新時需一起套用並重啟前後端。

API 實作參考：
- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/docs/models/gpt-4.1-mini

## Gemini 對話連線相容修正
保留 Gemini 模型與既有金鑰。本版的 Gemini 路徑以後端 HTTP 請求傳送 Google 文件的 generationConfig.responseFormat.text JSON Schema 格式，避免舊 SDK response_schema 轉換路徑的相容性問題。遇到明確的 HTTP 400 輸出格式錯誤時，至多改用一種相容格式重試一次；仍以相同 Pydantic 與排程規則驗證，格式不完整不寫入對話。金鑰、權限、額度、模型404、請求400與格式400錯誤分開顯示，不顯示原始服務回應。

如果只要修正這次連線問題：從新壓縮檔取 backend/ai_service.py 與 backend/requirements.txt，覆蓋自己專案的同名檔案；保留 .env 與 data。必要時重新執行「安裝或更新套件.bat」，然後關閉舊後端並重新啟動網站。

backend/.env 保持：
```dotenv
AI_PROVIDER=gemini
GEMINI_API_KEY=你原本的Gemini金鑰
GEMINI_MODEL=gemini-3.5-flash-lite
```

此修正未使用你的金鑰進行真實連線；若仍失敗，請提供新版顯示的 HTTP 代碼與原因標記（api_key、model、schema、request、billing、region等），不用提供金鑰。
參考：https://ai.google.dev/gemini-api/docs/generate-content/structured-output

## Gemini 計畫草稿相容修正 v2
此版只需將 backend/ai_service.py 覆蓋到目前執行的專案，再停止後端並重新啟動；保留既有 .env 與 backend/data，不需重新建立帳號或清除對話。
複雜的計畫草稿改為 JSON 輸出模式，將欄位要求寫在提示中，不傳送巢狀遠端 schema；本機仍以同一 Pydantic 模型嚴格檢查型態與額外欄位，再驗證日期、分鐘、固定事項與可用時段。一般對話保留原本格式。
HTTP 400 錯誤加上 v2 標記與長度受限、隱藏金鑰的服務原因。若仍失敗，請提供整段新版錯誤訊息，不要提供金鑰。尚未使用使用者金鑰測試，因此無法保證這次錯誤的根因已被排除。

## Gemini 產生計畫對話順序修正 v3
已確認服務錯誤：Requests ending with a model turn are not supported。產生草稿時原先直接送出以助理回覆結尾的歷史對話；現在將按下「產生建議計畫」轉為明確的最後一則使用者請求，再呼叫 AI。既有對話紀錄不會因此增加或被修改。
已套用 v2 的使用者，本次只需覆蓋 backend/chat_planner.py，停止後端後重新啟動；保留 ai_service.py 的 v2 修正、.env 與 backend/data，不需重裝套件。

## 對話頁的保留空白與固定待辦（新增）
AI 規劃對話頁可直接新增、修改、移除灰色「保留空白」及橘色「固定待辦」，設定與 AI Study Plan 共用同一份當次編輯資料。修改會清除舊草稿；重新產生時，最新表單內容會傳送給 AI 與排程器。此介面的表單設定為準，過往對話中的已移除或已修改事項不會被 AI 再加回。對話若提到新的固定行程，請先在表單填寫。
表單提供日期、開始時間、分鐘與說明；檢查日期在選定七天內、分鐘為正值、不可跨午夜及不可重疊。傳送或產生期間鎖住表單。
產生後需按「匯入目前計畫編輯區」，確認再儲存，才更新正式日曆。未儲存的表單設定不會獨立寫入資料庫。

更新方法：先關閉前後端，解壓後執行「套用至目前專案.bat」。預設套用到 %USERPROFILE%\Downloads\learnpilot-react-gemini-fix\learnpilot-react；也可把其他既有專案資料夾拖曳到這個批次檔。更新程式備份並覆蓋 frontend/src 下的 main.jsx、PlanningChat.jsx、features.jsx、style.css，以及 backend/chat_planner.py。保留 .env、backend/data、.venv 和其他檔案。更新後在原本專案執行「啟動網頁.bat」。不需重裝套件。
手動更新也只需覆蓋上述五個原始碼檔案，前後端需一起更新以支援 fixed_items_authoritative 請求參數。

## 整週分散排程修正
原先排程會從第一天開始依序填滿空檔，容易把整週任務集中在前幾天。本版對未指定日期／時刻的任務，依每一天已安排的讀書分鐘數，優先分配給負擔較少且仍有空檔的日期，再依兩小時日曆格、固定事項與可用時段放入任務。一般產生建議與 AI 對話草稿皆適用。
保留每項任務與每週總分鐘，使用15分鐘分配單位；沒有可用時段的日子不排入，短時段可使用剩餘分鐘。明確指定日期、開始時刻及截止日期的限制優先。任務量少或指定日期受限時，不保證七天都安排讀書，也不會為填滿日曆而增加時數。
AI 對話草稿新增七天實際時數分配，分析備註也列出七天分鐘數。對話應提供整週可用時間與休息日；若只確認某幾天，系統不會擅自加入其他日子。
更新：先關閉前後端，在解壓縮後的 learnpilot-react 中執行「套用至目前專案.bat」，套用到原本已安裝好環境的專案，再重新啟動前後端。不需重裝套件。手動更新需一起覆蓋 backend/planning.py、backend/chat_planner.py、frontend/src/PlanningChat.jsx、frontend/src/style.css。
完成後重新產生建議計畫、匯入並儲存，正式學習日曆才會套用整週分配；既有已儲存計畫不會自動改動。

## 忘記密碼與電子郵件重設

登入頁提供「忘記密碼？」；輸入註冊 Email 後，開啟郵件中的連結，輸入並確認新密碼。連結 30 分鐘有效且只能使用一次；成功後所有舊登入都會失效，原有學習資料保留。已存在的帳號也能使用，不需重新註冊。

管理者需設定 Resend 寄信服務（https://resend.com）：驗證寄件網域並建立具有寄信權限的 API key。在既有 `backend/.env` 加入以下設定，保留其他設定，不要將實際金鑰提交到 GitHub：

```dotenv
RESEND_API_KEY=你的寄信金鑰
RESET_EMAIL_FROM=LearnPilot <noreply@你的已驗證網域>
PASSWORD_RESET_URL=https://你的前端網站/
```

在 Codex 雲端可改用環境設定中的安全金鑰欄位，允許目的地 `api.resend.com`，並設定其他兩個非機密變數。修改後重啟後端。`PASSWORD_RESET_URL` 必須是使用者能開啟的前端登入頁，不能使用 API 網址；本機開發可用 `http://localhost:5173/`，公開部署需 HTTPS。寄件地址須通過 Resend 驗證；若仍使用測試寄件網域，收件人受服務商限制。

未設定寄信服務時會明確顯示「密碼重設寄信服務尚未設定」，不會提供繞過驗證的改密碼入口。請求回覆不透露帳號是否存在或郵件是否送達，請檢查垃圾郵件，必要時聯絡管理者確認寄信服務。重寄受 Email 60 秒及來源 IP 10 秒間隔限制；部署反向代理時應另在可信任的入口設定整體限流。

重設 token 只以 SHA-256 雜湊存入 SQLite；原始 token 只出現在郵件連結的 fragment，前端載入後即從網址移除。請不要分享重設連結。舊資料庫會自動新增所需資料表，不會清除既有資料。正式部署須讓前後端共用同一個持久 SQLite 檔案。

## 更新後看不到「忘記密碼？」

GitHub 更新不會自動修改電腦上的檔案。新版入口位於「登入」頁的「建立新帳號」旁；註冊頁請先按「已有帳號？登入」。

1. 從 GitHub 的 Code → Download ZIP 取得最新版本並完整解壓縮。
2. 關閉原本的前後端命令列視窗。
3. 將原本正在使用的專案資料夾，拖曳到新版資料夾中的「套用至目前專案.bat」，確認目標路徑後繼續。新版腳本會備份並複製全部後端 Python、新前端模組、依賴清單與測試，保留 `.env`、`backend/data`、`.venv` 及 `node_modules`。不要用舊更新腳本只複製部分檔案。
4. 在原本專案根目錄執行 `backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt`，然後在 frontend 執行 `npm.cmd ci`。
5. 在原本專案重新執行「啟動網頁.bat」，開啟登入頁並按 Ctrl+F5。

若使用 `git pull` 更新，仍需停止舊服務並更新依賴後重新啟動。若使用部署網站，需部署最新 `main`、重新建置前端並重啟後端。只有完成更新後按鈕才會出現；真正寄信仍須另行設定 Resend。

### 按下重設卻未收到信

畫面的「申請已收到」不表示 Resend 已接受或送達。確認此 Email 是目前這個本機 SQLite 裡註冊的帳號；如果換了專案資料夾或資料庫，原帳號可能不在其中。連續點擊也會限流，請等 60 秒再試。

更新後重新啟動後端，按一次寄送，再查看「LearnPilot Backend」視窗的 `MAIL_` 訊息（不含 Email、金鑰或連結）：

- `MAIL_ACCOUNT_NOT_FOUND`：目前資料庫沒有符合的帳號，請確認註冊 Email 與資料庫位置；不要刪除既有資料庫。
- `MAIL_THROTTLED`：等 60 秒再試。
- `MAIL_TEST_RECIPIENT`：`onboarding@resend.dev` 測試寄件地址只能寄給 Resend 帳號本人的 Email。若要寄給其他人，請先驗證自己的寄件網域。
- `MAIL_SENDER_DOMAIN` / `MAIL_PERMISSION`：確認寄件網域驗證成功、寄件地址正確、API key 有寄信權限。
- `MAIL_AUTH`：金鑰無效；在 `.env` 更新金鑰後重啟後端。
- `MAIL_LIMIT`：Resend 寄信額度或頻率受限。
- `MAIL_CONNECTION`：本機網路、防火牆或 TLS 連線失敗，不要關閉憑證驗證。
- `MAIL_REJECTED`：寄信服務拒絕，請查看 Resend 的 Logs。
- `MAIL_ACCEPTED`：Resend 接受了請求，請至 Emails 查看 Delivered / Bounced 等狀態，並檢查收件匣、垃圾郵件及收信規則。

排查時只提供以上代碼或遮蔽個資的服務錯誤，勿分享 API key、完整 `.env` 或重設連結。真實送達仍須在使用者本機及 Resend 設定中確認。

## 找回舊帳號：重新下載專案後登入失敗或不寄重設信

程式碼 ZIP 不包含個人帳號或資料庫。`MAIL_ACCOUNT_NOT_FOUND` 表示「目前正在使用的資料庫」沒有這個帳號，不是重設郵件已經寄出。不能只靠一個 Email 重建舊帳號或繞過驗證修改密碼。

本版在 Windows 上，若目前專案已有 `backend/data/learnpilot.db`，會繼續使用它；若是全新下載且沒有該檔，預設使用 `%LOCALAPPDATA%\LearnPilot\data\learnpilot.db`，讓之後的新下載版本可以讀取同一份資料。既有 `DATABASE_PATH` 設定優先，Linux 雲端預設位置不變。後端啟動會顯示 `DATA_LOCATION` 路徑與帳號數，不顯示 Email、密碼或金鑰。帳號、紀錄與計畫仍屬於本機資料，不會自動跨電腦同步。

恢復舊資料：

1. 先關閉所有 LearnPilot 前後端視窗。在新版專案完成套件安裝後，雙擊「還原原本帳號資料.bat」。工具使用 Python 隨附的 Tkinter；如果未安裝 Tcl/Tk，請透過 Python 安裝程式加入 Tcl/Tk 元件。
2. 在選檔視窗選取原本使用的專案裡的 `backend/data/learnpilot.db`，例如 Downloads 下較早的專案資料夾。若之前設定過 `DATABASE_PATH`，請選該位置的檔案。只在自己電腦選取，不需上傳資料庫或金鑰。
3. 工具檢查資料庫格式並顯示帳號及學習紀錄數量。確認來源與目的地後才會開始；現有目的地先備份到同層 `backups`，原始來源檔案保留。這是整份資料還原，不會合併兩份資料庫。還原後舊登入與密碼重設 token 會撤銷。
4. 重新執行「啟動網頁.bat」，再使用舊帳號登入，或按「忘記密碼？」寄送重設信。保留目前專案的 `.env`，確認寄信設定已完成。

請勿刪除所有舊專案或資料庫；先確認資料恢復。若找不到任何包含原帳號的資料庫，ZIP 無法還原帳號，需在目前版本建立新帳號。Windows 還原對話框與批次檔尚未於 Windows 實機驗證；底層還原及 API 流程已以測試驗證。

新版「啟動網頁.bat」會先檢查 8000、5173 連接埠；若已有舊服務，會停止本次啟動並提示關閉舊視窗，不會強制終止其他程序。新版更新腳本也會更新頂層批次檔及全部後端 Python 工具。
