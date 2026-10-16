import asyncio
from ai_diagnostics import failure_message

class AIGenerationFailure(RuntimeError):
    pass

async def generate_with_fallback(generate, prompt, models, *, timeout=25, sleep=asyncio.sleep):
    models = list(dict.fromkeys(m.strip() for m in models if m.strip()))[:2]
    failures = []
    for model in models:
        for attempt in range(2):
            try:
                response = await asyncio.wait_for(generate(model=model, contents=prompt), timeout)
                if not response.text or not response.text.strip():
                    raise ValueError('empty')
                return response.text, model
            except Exception as exc:
                code = str(getattr(exc,'code',None) or getattr(exc,'status_code',None))
                transient = isinstance(exc, TimeoutError) or code in ('500','502','503','504')
                if transient and attempt == 0:
                    await sleep(2)
                    continue
                failures.append(f'{model}：{failure_message(exc)}')
                # Key/permission or quota failures should not cause more API requests.
                if code in ('400','401','403','429') or isinstance(exc, ImportError):
                    raise AIGenerationFailure('；'.join(failures)) from None
                break
    raise AIGenerationFailure('所有候選模型均未成功。'+'；'.join(failures)) from None
