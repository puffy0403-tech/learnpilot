import asyncio
import json
import httpx
import pytest
from fastapi import HTTPException
from ai_service import ask_ai, gemini_schema, GeminiAPIError, safe_failure
from chat_planner import ChatReply, Draft


def mock_transport(monkeypatch, handler):
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('AI_PROVIDER','gemini')
    monkeypatch.setenv('GEMINI_API_KEY','secret-test-value')
    monkeypatch.setenv('GEMINI_MODEL','gemini-3.5-flash-lite')


def success(text=None):
    return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':text or json.dumps(dict(reply='請問哪一天可以讀？',summary='英文',ready=False))}]}}]})


def test_current_format_and_role_history(monkeypatch):
    calls=[]
    def handler(req):
        data=json.loads(req.content);calls.append(data)
        assert req.url.path.endswith('/gemini-3.5-flash-lite:generateContent')
        assert req.headers['x-goog-api-key']=='secret-test-value'
        assert 'secret-test-value' not in str(req.url)
        assert data['generationConfig']['responseFormat']['text']['schema']['additionalProperties'] is False
        assert [m['role'] for m in data['contents']]==['user','model','user']
        return success()
    mock_transport(monkeypatch,handler)
    reply,source=asyncio.run(ask_ai('教練',[dict(role=r,content='內容') for r in ['user','assistant','user']],ChatReply))
    assert reply.ready is False and len(calls)==1 and source.startswith('Gemini')


def test_unknown_current_field_uses_legacy_schema_once(monkeypatch):
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        if len(calls)==1:
            return httpx.Response(400,json={'error':{'message':'Unknown name "responseFormat" at generation_config','status':'INVALID_ARGUMENT'}})
        assert 'responseJsonSchema' in body['generationConfig']
        assert 'responseFormat' not in body['generationConfig']
        return success()
    mock_transport(monkeypatch,handler)
    result,_=asyncio.run(ask_ai('教練',[dict(role='user',content='英文')],ChatReply))
    assert result.summary=='英文' and len(calls)==2


def test_rejected_schema_uses_json_only_and_validates(monkeypatch):
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        if len(calls)==1:
            return httpx.Response(400,json={'error':{'message':'Schema is not supported: additionalProperties','status':'INVALID_ARGUMENT'}})
        assert body['generationConfig']=={'responseMimeType':'application/json'}
        assert 'JSON Schema' in body['systemInstruction']['parts'][0]['text']
        return success('```json\n{"reply":"已整理","summary":"英文","ready":true}\n```')
    mock_transport(monkeypatch,handler)
    result,_=asyncio.run(ask_ai('教練',[dict(role='user',content='英文')],ChatReply))
    assert result.ready is True and len(calls)==2


@pytest.mark.parametrize('status,message,expected',[
    (400,'API key not valid. Please pass a valid API key. secret-test-value','api_key'),
    (404,'model not found secret-test-value','HTTP 404'),
    (403,'Permission denied secret-test-value','HTTP 403'),
    (429,'quota secret-test-value','HTTP 429'),
    (400,'Other invalid field secret-test-value','request'),
])
def test_service_errors_distinct_redacted_and_not_retried(monkeypatch,status,message,expected):
    calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(status,json={'error':{'message':message,'status':'INVALID_ARGUMENT'}})
    mock_transport(monkeypatch,handler)
    with pytest.raises(HTTPException) as error:
        asyncio.run(ask_ai('教練',[dict(role='user',content='英文')],ChatReply))
    assert expected in error.value.detail and 'secret-test-value' not in error.value.detail
    assert len(calls)==1


def test_invalid_json_response_never_accepted(monkeypatch):
    mock_transport(monkeypatch,lambda req:success('{"reply":"hello","summary":"英文","ready":"false","extra":"bad"}'))
    with pytest.raises(HTTPException) as error:
        asyncio.run(ask_ai('教練',[dict(role='user',content='英文')],ChatReply))
    assert error.value.status_code==503


def test_schema_inlines_refs_and_nullable_fields():
    schema=gemini_schema(Draft)
    text=json.dumps(schema)
    assert '$ref' not in text and '$defs' not in text and '"default"' not in text
    assert schema['properties']['tasks']['items']['properties']['deadline']['type']==['string','null']
    assert schema['properties']['tasks']['items']['additionalProperties'] is False


def test_empty_truncated_or_blocked_response_rejected(monkeypatch):
    for response in [{'candidates':[]},{'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'{}'}]}}]}]:
        mock_transport(monkeypatch,lambda req:httpx.Response(200,json=response))
        with pytest.raises(HTTPException):
            asyncio.run(ask_ai('教練',[dict(role='user',content='英文')],ChatReply))
        monkeypatch.undo()


def calendar_draft_json():
    return json.dumps(dict(summary='安排英文',assumptions=[],questions=[],windows=[dict(date='2026-10-13',start_time='19:00',end_time='21:00')],additional_fixed_items=[],tasks=[dict(subject='英文',content='閱讀與檢核',minutes=120,date=None,start_time=None,deadline=None)]))


def test_nested_calendar_draft_uses_json_mode_without_remote_schema(monkeypatch):
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        assert body['generationConfig']=={'responseFormat':{'text':{'mimeType':'application/json'}}}
        assert 'JSON Schema' in body['systemInstruction']['parts'][0]['text']
        return success(calendar_draft_json())
    mock_transport(monkeypatch,handler)
    draft,_=asyncio.run(ask_ai('產生計畫',[dict(role='user',content='英文週二晚上讀兩小時')],Draft))
    assert draft.tasks[0].minutes==120 and len(calls)==1


def test_nested_json_mode_legacy_fallback_never_resends_schema(monkeypatch):
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        if len(calls)==1:
            return httpx.Response(400,json={'error':{'message':'Unknown name "responseFormat"','status':'INVALID_ARGUMENT'}})
        assert body['generationConfig']=={'responseMimeType':'application/json'}
        return success(calendar_draft_json())
    mock_transport(monkeypatch,handler)
    draft,_=asyncio.run(ask_ai('產生計畫',[dict(role='user',content='英文')],Draft))
    assert draft.summary=='安排英文' and len(calls)==2


def test_nested_invalid_calendar_reply_still_rejected(monkeypatch):
    invalid=json.loads(calendar_draft_json());invalid['tasks'][0]['minutes']='120'
    mock_transport(monkeypatch,lambda req:success(json.dumps(invalid)))
    with pytest.raises(HTTPException):
        asyncio.run(ask_ai('產生計畫',[dict(role='user',content='英文')],Draft))


def test_request_diagnostic_includes_reason_but_redacts_credentials(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','private-secret-value')
    exc=GeminiAPIError(400,dict(status='INVALID_ARGUMENT',message='Invalid generationConfig setting. key=private-secret-value\nAlso AIzaSuperSecretToken12345'))
    detail=safe_failure(exc)
    assert 'v2' in detail and 'Invalid generationConfig setting' in detail
    assert 'private-secret-value' not in detail and 'AIzaSuperSecretToken12345' not in detail
    assert '\n' not in detail


def test_calendar_request_passes_gemini_final_user_turn_requirement(monkeypatch):
    from chat_planner import draft_request_messages
    calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        if body['contents'][-1]['role']=='model':
            return httpx.Response(400,json={'error':{'status':'INVALID_ARGUMENT','message':'Requests ending with a model turn are not supported'}})
        return success(calendar_draft_json())
    mock_transport(monkeypatch,handler)
    history=[dict(role='user',content='英文週二19:00–21:00讀兩小時'),dict(role='assistant',content='已確認，可以產生草稿。')]
    with pytest.raises(HTTPException) as error:
        asyncio.run(ask_ai('產生計畫',history,Draft))
    assert 'Requests ending with a model turn' in error.value.detail
    draft,_=asyncio.run(ask_ai('產生計畫',draft_request_messages(history),Draft))
    assert draft.tasks[0].minutes==120
    assert calls[0]['contents'][-1]['role']=='model'
    assert calls[1]['contents'][-1]['role']=='user'
    assert len(history)==2 and history[-1]['role']=='assistant'
