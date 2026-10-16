"""Provider adapter. Keys stay on the backend; errors never include provider bodies."""
import asyncio
import json
import os
import re
from urllib.parse import quote
from fastapi import HTTPException


def configuration():
    provider = os.getenv('AI_PROVIDER', 'auto').strip().lower()
    if provider == 'auto':
        provider = 'openai' if os.getenv('OPENAI_API_KEY') else 'gemini'
    if provider not in ('openai', 'gemini'):
        return {'configured': False, 'provider': provider, 'model': '', 'message': 'AI_PROVIDER 請設定為 auto、openai 或 gemini。'}
    key = os.getenv('OPENAI_API_KEY' if provider == 'openai' else 'GEMINI_API_KEY', '').strip()
    model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini').strip() if provider == 'openai' else os.getenv('GEMINI_MODEL', '').strip()
    return {'configured': bool(key and model), 'provider': provider, 'model': model,
            'message': '已讀取設定；實際可用性於傳送時確認。' if key and model else '請在 backend/.env 設定 OPENAI_API_KEY 與 OPENAI_MODEL，或 Gemini 設定，並重新啟動後端。'}


class GeminiAPIError(RuntimeError):
    def __init__(self, status_code, error):
        self.status_code = status_code
        self.code = status_code
        self.provider_status = error.get('status', '') if isinstance(error, dict) else ''
        self.provider_message = str(error.get('message', '')) if isinstance(error, dict) else ''
        self.provider_details = error.get('details', []) if isinstance(error, dict) else []
        # Do not include raw provider output in the exception or logs.
        super().__init__('Gemini API request failed')


def gemini_reason(exc):
    message = getattr(exc, 'provider_message', '').lower()
    details = getattr(exc, 'provider_details', [])
    reasons = ' '.join(str(r.get('reason', '')) for r in details if isinstance(r, dict)).lower() if isinstance(details, list) else ''
    if any(x in message+' '+reasons for x in ('api_key_invalid','api_key_expired','api key not valid','api key expired','invalid api key')):
        return 'api_key'
    if 'api_key_service_blocked' in reasons or 'api key' in message and any(x in message for x in ('blocked','restriction','not allowed')):
        return 'key_restriction'
    if 'location' in message or 'region' in message:
        return 'region'
    if 'billing' in message or 'paid tier' in message:
        return 'billing'
    if any(x in message for x in ('schema','responseformat','response_format','response format','responsemimetype','response_mime_type','responsejsonschema','response_json_schema','additionalproperties','additional_properties')):
        return 'schema'
    return 'other'


def sanitized_provider_detail(exc):
    """Return a bounded diagnostic; never expose keys or full response bodies."""
    detail=getattr(exc,'provider_message','')
    for key_name in ('GEMINI_API_KEY','GOOGLE_API_KEY','OPENAI_API_KEY'):
        key=os.getenv(key_name,'').strip()
        if key:
            detail=detail.replace(key,'[金鑰已隱藏]')
    detail=re.sub(r'AIza[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+','[金鑰已隱藏]',detail)
    detail=re.sub(r'(?i)(bearer\s+)[^\s,;]+',r'\1[金鑰已隱藏]',detail)
    detail=re.sub(r'(?i)((?:api[_-]?key|x-goog-api-key|key)\s*[=:]\s*)[^\s,&;]+',r'\1[金鑰已隱藏]',detail)
    detail=re.sub(r'[\x00-\x1f\x7f]+',' ',detail).strip()
    status=getattr(exc,'provider_status','')
    allowed={'INVALID_ARGUMENT','NOT_FOUND','PERMISSION_DENIED','UNAUTHENTICATED','RESOURCE_EXHAUSTED','FAILED_PRECONDITION','UNAVAILABLE','INTERNAL','DEADLINE_EXCEEDED'}
    prefix=(status+'：') if status in allowed else ''
    return prefix+(detail[:500] or '服務未提供進一步資訊。')


def safe_failure(exc):
    status = getattr(exc, 'status_code', None) or getattr(exc, 'code', None)
    if isinstance(exc, GeminiAPIError):
        reason = gemini_reason(exc)
        if reason == 'api_key':
            return f'Gemini 金鑰無效或已過期（HTTP {status}；api_key），請更新 GEMINI_API_KEY 後重啟後端。'
        if reason == 'key_restriction':
            return f'Gemini 金鑰的服務或使用來源限制拒絕此請求（HTTP {status}；key_restriction）。請檢查 Google AI Studio／Google Cloud 的金鑰限制。'
        if reason == 'region':
            return f'Gemini API 的地區或位置限制拒絕此請求（HTTP {status}；region）。'
        if reason == 'billing':
            return f'Gemini 專案計費或使用層級不符（HTTP {status}；billing），請檢查此金鑰所屬專案。'
        if str(status)=='404':
            return 'Gemini 找不到此模型或此金鑰無法存取（HTTP 404；model），請核對頁面顯示的模型與 AI Studio 可用模型。'
        if str(status)=='400':
            if reason == 'schema':
                return 'Gemini 拒絕輸出格式（HTTP 400；schema；v2）。服務原因：'+sanitized_provider_detail(exc)
            return 'Gemini 拒絕請求參數（HTTP 400；request；v2）。服務原因：'+sanitized_provider_detail(exc)
    if isinstance(exc, ImportError):
        return '缺少 AI 套件，請使用後端 Python 重新安裝 requirements.txt。'
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) or type(exc).__name__ in ('ReadTimeout','ConnectTimeout','APITimeoutError'):
        return 'AI 回應逾時，請稍後重試；對話尚未變更。'
    if str(status) in ('401', '403'):
        return f'AI 金鑰或權限驗證失敗（HTTP {status}），請檢查 backend/.env 與專案權限。'
    if str(status) == '429':
        return 'AI 額度不足或請求過於頻繁（HTTP 429），請檢查 API 額度後重試。'
    if str(status)=='404':
        return 'AI 找不到此模型或帳號無權使用（HTTP 404），請核對模型設定。'
    if str(status)=='400':
        return 'AI 拒絕請求參數或輸出格式（HTTP 400），請核對模型設定與套件版本。'
    if str(status) in ('500','502','503','504'):
        return f'AI 服務暫時異常（HTTP {status}），請稍後重試。'
    if isinstance(exc, ValueError):
        return 'AI 回傳空白、拒絕或不符合計畫格式，請補充需求後重試；尚未變更對話與計畫。'
    return 'AI 服務暫時無法連線，請檢查網路或稍後重試。'


def gemini_schema(output_type):
    """Inline simple Pydantic schemas without legacy SDK schema conversion."""
    root = output_type.model_json_schema()
    definitions = root.get('$defs', {})
    def walk(value):
        if isinstance(value, list):
            return [walk(x) for x in value]
        if not isinstance(value, dict):
            return value
        if '$ref' in value:
            ref=value['$ref']
            if not ref.startswith('#/$defs/') or ref.split('/')[-1] not in definitions:
                raise ValueError('unsupported schema reference')
            value={**definitions[ref.split('/')[-1]], **{k:v for k,v in value.items() if k!='$ref'}}
        result={k:walk(v) for k,v in value.items() if k not in ('$defs','title','default')}
        # All unions in our planner are nullable scalar fields.
        if 'anyOf' in result and all(set(x)=={'type'} for x in result['anyOf']):
            result['type']=[x['type'] for x in result.pop('anyOf')]
        return result
    return walk(root)


def parse_gemini_response(data, output_type):
    candidates=data.get('candidates') or []
    if not candidates:
        raise ValueError('no candidates')
    candidate=candidates[0]
    if candidate.get('finishReason') not in (None, 'STOP'):
        raise ValueError('refused or incomplete')
    text=''.join(p.get('text','') for p in candidate.get('content',{}).get('parts',[]) if not p.get('thought'))
    if not text.strip():
        raise ValueError('empty')
    # JSON-only compatibility mode may return a single fenced JSON object.
    if output_type:
        match=re.fullmatch(r'\s*```(?:json)?\s*([\s\S]*?)\s*```\s*', text)
        if match:
            text=match[1]
        return output_type.model_validate_json(text, strict=True)
    return text


async def ask_gemini(instructions, messages, model, output_type=None):
    import httpx
    model=model.removeprefix('models/')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ValueError('invalid model identifier')
    payload={
        'systemInstruction': {'parts':[{'text':instructions}]},
        'contents':[{'role':'model' if m['role']=='assistant' else 'user','parts':[{'text':m['content']}]} for m in messages],
    }
    schema=gemini_schema(output_type) if output_type else None
    # Nested calendar drafts use JSON-only mode to avoid provider-side schema
    # depth/union constraints; all original local validation still applies.
    json_only=bool(output_type and output_type.model_json_schema().get('$defs'))
    if schema:
        text_format={'mimeType':'application/json'}
        if json_only:
            payload['systemInstruction']['parts'][0]['text']+='\n只輸出一個JSON物件，所有欄位符合以下JSON Schema；欄位型態與null必須正確，不得加入額外欄位：\n'+json.dumps(schema,ensure_ascii=False)
        else:
            text_format['schema']=schema
        payload['generationConfig']={'responseFormat':{'text':text_format}}

    url='https://generativelanguage.googleapis.com/v1beta/models/'+quote(model,safe='')+':generateContent'
    headers={'x-goog-api-key':os.environ['GEMINI_API_KEY'],'Content-Type':'application/json'}
    async with httpx.AsyncClient(timeout=45) as client:
        async def send(body):
            response=await client.post(url,headers=headers,json=body)
            if response.status_code>=400:
                try:
                    data=response.json()
                except ValueError:
                    data={}
                raise GeminiAPIError(response.status_code,data.get('error',{}))
            return parse_gemini_response(response.json(),output_type)
        try:
            return await send(payload)
        except GeminiAPIError as exc:
            if not schema or exc.status_code!=400 or gemini_reason(exc)!='schema':
                raise
            message=exc.provider_message.lower()
            if any(x in message for x in ('unknown name','unknown field','unrecognized','not found')):
                # Older API deployments use responseJsonSchema.
                generation={'responseMimeType':'application/json'}
                if not json_only:
                    generation['responseJsonSchema']=schema
            else:
                # For a rejected schema, JSON-only output still undergoes the
                # same strict Pydantic and scheduling validation locally.
                generation={'responseMimeType':'application/json'}
                payload['systemInstruction']['parts'][0]['text']+='\n只輸出一個JSON物件，所有欄位符合以下JSON Schema，不要加入其他欄位：\n'+json.dumps(schema,ensure_ascii=False)
            payload['generationConfig']=generation
            return await send(payload)


async def ask_ai(instructions, messages, output_type=None):
    cfg = configuration()
    if not cfg['configured']:
        raise HTTPException(503, cfg['message'])
    try:
        if cfg['provider'] == 'openai':
            from openai import AsyncOpenAI
            async with AsyncOpenAI(api_key=os.environ['OPENAI_API_KEY'], timeout=45, max_retries=0) as client:
                if output_type:
                    response = await asyncio.wait_for(client.responses.parse(
                        model=cfg['model'], instructions=instructions, input=messages,
                        text_format=output_type, store=False), 50)
                    if response.output_parsed is None:
                        raise ValueError('incomplete or refused')
                    result = response.output_parsed
                else:
                    response = await asyncio.wait_for(client.responses.create(
                        model=cfg['model'], instructions=instructions, input=messages, store=False), 50)
                    result = response.output_text
        else:
            result = await ask_gemini(instructions, messages, cfg['model'], output_type)
        if result is None or isinstance(result, str) and not result.strip():
            raise ValueError('empty')
        return result, ('OpenAI' if cfg['provider'] == 'openai' else 'Gemini') + ' · ' + cfg['model']
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, safe_failure(exc)) from None
