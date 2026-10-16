import asyncio

def failure_message(exc):
    """Return actionable categories, never raw provider text or credentials."""
    code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return '缺少 Gemini 套件：請用後端的 Python 安裝 requirements.txt。'
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return 'Gemini 回應逾時（45 秒），請稍後重試並檢查網路。'
    if str(code) in ('400','401','403'):
        return f'Gemini 驗證或請求被拒絕（HTTP {code}）：請確認金鑰有效、專案權限及模型設定。'
    if str(code)=='404':
        return 'Gemini 找不到指定模型（HTTP 404）：請改用此金鑰可存取的模型 ID。'
    if str(code)=='429':
        return 'Gemini 額度或速率限制（HTTP 429）：請在 AI Studio 確認額度並稍後重試。'
    if str(code) in ('500','502','503','504'):
        return f'Gemini 服務暫時異常（HTTP {code}），請稍後重試。'
    if isinstance(exc, ValueError):
        return 'Gemini 回傳空白或無效結果，請重試。'
    return 'Gemini 連線失敗：請確認後端網路、套件版本及模型設定。'
