"""Direct SoCLaaS interface with capability-aware model selection."""
import base64
import binascii
import json
import os
import re
from time import perf_counter
from typing import Literal

import httpx
from pydantic import Field, field_validator, model_validator

from backend.llm import BASE_URL, ModelError, available_model_details, model_settings
from backend.schemas import StrictModel
from backend.defaults import default_cards
from backend.minors import minor_prompt_cards

MAX_REQUEST_BYTES = 12 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 6 * 1024 * 1024
IMAGE_TYPES = {'image/png', 'image/jpeg', 'image/webp', 'image/gif'}
AUDIO_TYPES = {'audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3', 'audio/mp4',
               'audio/x-m4a', 'audio/webm', 'video/webm', 'audio/ogg', 'audio/flac',
               'audio/aac', 'video/mp4'}


class Attachment(StrictModel):
    name: str = Field(min_length=1, max_length=180)
    data_url: str = Field(max_length=9 * 1024 * 1024)

    @field_validator('data_url')
    @classmethod
    def supported_file(cls, value):
        match = re.fullmatch(r'data:([a-z0-9.+/-]+);base64,([A-Za-z0-9+/=]+)', value)
        if not match or match[1] not in IMAGE_TYPES | AUDIO_TYPES:
            raise ValueError('Upload a supported image or audio file')
        try:
            data = base64.b64decode(match[2], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError('Invalid file encoding') from exc
        if not data or len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError('Attachment is empty or larger than 6 MB')
        return value

    @property
    def mime(self):
        return self.data_url[5:].split(';', 1)[0]

    @property
    def size_bytes(self):
        encoded = self.data_url.split(',', 1)[1]
        return len(encoded) * 3 // 4 - (len(encoded) - len(encoded.rstrip('=')))


class ChatMessage(StrictModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=40000)
    attachments: list[Attachment] = Field(default_factory=list, max_length=4)

    @field_validator('content')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Message cannot be blank')
        return value

    @model_validator(mode='after')
    def user_files_only(self):
        if self.role != 'user' and self.attachments:
            raise ValueError('Only user messages can contain attachments')
        return self


class ChatRequest(StrictModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=61)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    # Retained only for reproducibility of old exported conversations.
    system_prompt: str = Field(default='', max_length=16000)

    @model_validator(mode='after')
    def conversation(self):
        roles = [m.role for m in self.messages]
        if roles != ['user' if i % 2 == 0 else 'assistant' for i in range(len(roles))] or roles[-1] != 'user':
            raise ValueError('Conversation must alternate user/assistant and end with a user message')
        if sum(len(m.content) for m in self.messages) + len(self.system_prompt) > 80000:
            raise ValueError('Conversation is too long; start a new chat')
        if sum(a.size_bytes for m in self.messages for a in m.attachments) > MAX_ATTACHMENT_BYTES:
            raise ValueError('Attachments exceed the conversation file limit; start a new chat')
        return self


async def chat_models():
    """Return only public model metadata, discovered with this user's key."""
    models = []
    for raw in await available_model_details():
        info = raw.get('soclaas') or {}
        capabilities = info.get('capabilities', ['chat'])
        mode = ('chat' if 'chat' in capabilities else 'embeddings' if 'embeddings' in capabilities
                else 'transcription' if 'audio-transcription' in capabilities else 'unsupported')
        models.append({'id': raw['id'], 'name': info.get('display_name') or raw['id'],
                       'mode': mode, 'vision': 'vision' in info.get('input_modalities', []),
                       'alias_of': info.get('alias_of'), 'capabilities': capabilities})
    return models


def chat_config():
    prompts = []
    for card in default_cards():
        prompt = card.title.rstrip('.') + '. ' + card.description
        # The short card description abbreviates the foundation list; a usable
        # prompt must include every course in the actual shared default rule.
        for rule in card.rules:
            if rule.type == 'require_courses':
                prompt += ' Required courses: ' + ', '.join(rule.courses) + '.'
        prompts.append({'id': card.id, 'title': card.title, 'description': card.description,
                        'strength': card.strength, 'prompt': prompt})
    return {**model_settings(), 'provider': 'SoCLaaS',
            'configured': bool(os.getenv('SOCLAAS_API_KEY')),
            'default_system_prompt': '', 'max_messages': 61, 'max_characters': 80000,
            'max_request_bytes': MAX_REQUEST_BYTES, 'max_attachment_bytes': MAX_ATTACHMENT_BYTES,
            'prompt_cards': prompts, 'minor_prompt_cards': minor_prompt_cards()}


def event(kind, data):
    return f'event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'


def upstream_messages(request):
    messages = []
    if request.system_prompt.strip():
        messages.append({'role': 'system', 'content': request.system_prompt})
    for message in request.messages:
        content = message.content
        if message.attachments:
            content = [{'type': 'text', 'text': content}] + [
                {'type': 'image_url', 'image_url': {'url': a.data_url}} for a in message.attachments]
        messages.append({'role': message.role, 'content': content})
    return messages


def usage_counts(usage):
    return {k: v for k, v in usage.items() if k in {'prompt_tokens', 'completion_tokens', 'total_tokens'}
            and isinstance(v, int) and v >= 0} if isinstance(usage, dict) else None


def gateway_error(response, model, elapsed):
    """Classify failures without echoing credentials or internal gateway details."""
    status = response.status_code
    details = {'http_status': status, 'model': model, 'elapsed_seconds': round(elapsed, 3),
               'retryable': status == 429 or status >= 500}
    prefix = f'{model}: '
    if status == 401:
        details.update(code='authentication_failed', message=prefix + 'SoCLaaS rejected the API key (HTTP 401). Check the backend key and restart the server.')
    elif status == 403:
        details.update(code='access_denied', message=prefix + 'SoCLaaS denied access to this model (HTTP 403). Check model permissions or choose another model.')
    elif status == 404:
        details.update(code='model_not_found', message=prefix + 'SoCLaaS could not find this model (HTTP 404). Refresh the model list and select it again.')
    elif status == 429:
        details.update(code='rate_limited', message=prefix + 'SoCLaaS is rate-limiting requests (HTTP 429). Wait before retrying.')
    elif status >= 500:
        # The body is inspected only for a known diagnostic. Raw provider errors
        # can contain internal routing IDs, URLs or credentials and are not sent.
        try:
            no_backend = 'no healthy provider backends' in response.text.lower()
        except (httpx.ResponseNotRead, UnicodeError):
            no_backend = False
        reason = ' No healthy model backend is available.' if no_backend else ''
        details.update(code='model_backend_unavailable' if no_backend else 'gateway_unavailable',
                       message=prefix + f'The model service is temporarily unavailable on SoCLaaS (HTTP {status}).' + reason + ' Retry later or choose another model.')
    else:
        details.update(code='request_rejected', message=prefix + f'SoCLaaS rejected this request (HTTP {status}). Check the input and this model’s supported features.')
    retry_after = response.headers.get('retry-after', '')
    if retry_after.isdigit() and int(retry_after) <= 86400:
        details['retry_after_seconds'] = int(retry_after)
    return details


async def stream_chat(request: ChatRequest):
    settings = model_settings()
    settings['model'] = request.model or settings['model']
    key = os.getenv('SOCLAAS_API_KEY')
    if not key:
        yield event('error', {'message': 'Configure SOCLAAS_API_KEY in .env, then restart the backend.'})
        return
    started = perf_counter()
    try:
        # Never silently fall back to Qwen for a missing/denied selected model.
        selected = next((m for m in await chat_models() if m['id'] == settings['model']), None)
        if not selected or selected['mode'] == 'unsupported':
            raise ModelError('This model is unavailable for your key. Refresh the model list and choose another model.')
        files = [a for m in request.messages for a in m.attachments]
        mode = selected['mode']
        if mode == 'chat' and any(a.mime not in IMAGE_TYPES for a in files):
            raise ModelError('This model accepts text/images, not audio. Choose a transcription model for audio files.')
        if mode == 'chat' and files and not selected['vision']:
            raise ModelError('The selected model does not support images. Choose a VLM or start a text-only chat.')
        if mode == 'embeddings' and files:
            raise ModelError('The selected embedding model accepts text only. Start a text-only chat.')
        audio = request.messages[-1].attachments
        if mode == 'transcription' and (len(audio) != 1 or audio[0].mime not in AUDIO_TYPES):
            raise ModelError('Attach one audio file to transcribe with this model.')
        metadata = {**settings, 'provider': 'SoCLaaS', 'mode': mode,
                    'response_model': None, 'usage': None, 'finish_reason': None, 'first_token_seconds': None}
        if mode != 'chat':
            metadata['temperature'] = metadata['max_tokens'] = None
        yield event('meta', metadata)
        async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:
            if mode == 'embeddings':
                payload = {'model': settings['model'], 'input': request.messages[-1].content}
                response = await client.post(f'{BASE_URL}/embeddings', headers={'Authorization': f'Bearer {key}'}, json=payload)
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get('data'), list) or not result['data']:
                    raise ValueError('Missing embedding data')
                metadata['response_model'] = result.get('model')
                metadata['usage'] = usage_counts(result.get('usage'))
                output = json.dumps(result, ensure_ascii=False, indent=2)
                yield event('delta', {'text': '```json\n' + output + '\n```'})
                metadata['finish_reason'] = 'stop'
            elif mode == 'transcription':
                attachment = audio[0]
                data = base64.b64decode(attachment.data_url.split(',', 1)[1])
                filename = re.sub(r'[^a-zA-Z0-9._-]', '_', attachment.name)
                response = await client.post(f'{BASE_URL}/audio/transcriptions', headers={'Authorization': f'Bearer {key}'},
                    data={'model': settings['model']}, files={'file': (filename, data, attachment.mime)})
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get('text'), str):
                    raise ValueError('Missing transcription')
                yield event('delta', {'text': result['text']})
                metadata['response_model'] = result.get('model')
                metadata['usage'] = usage_counts(result.get('usage'))
                metadata['finish_reason'] = 'stop'
            else:
                received_content = terminated = False
                async with client.stream('POST', f'{BASE_URL}/chat/completions',
                        headers={'Authorization': f'Bearer {key}'},
                        json={**settings, 'messages': upstream_messages(request), 'stream': True}) as response:
                    if response.is_error:
                        await response.aread()
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith('data:') or not line[5:].strip():
                            continue
                        raw = line[5:].strip()
                        if raw == '[DONE]':
                            terminated = True
                            break
                        chunk = json.loads(raw)
                        if chunk.get('error'):
                            raise ValueError('Gateway reported a stream error')
                        if isinstance(chunk.get('model'), str):
                            metadata['response_model'] = chunk['model'][:200]
                        if chunk.get('usage'):
                            metadata['usage'] = usage_counts(chunk['usage'])
                        choices = chunk.get('choices', [])
                        if not choices:
                            continue
                        choice = choices[0]
                        if choice.get('finish_reason'):
                            metadata['finish_reason'] = str(choice['finish_reason'])[:80]
                            terminated = True
                        content = choice.get('delta', {}).get('content')
                        if content is not None and not isinstance(content, str):
                            raise ValueError('Unsupported stream content')
                        if content:
                            if not received_content:
                                metadata['first_token_seconds'] = round(perf_counter() - started, 3)
                            received_content = True
                            yield event('delta', {'text': content})
                if not received_content or not terminated:
                    raise ValueError('Empty or interrupted upstream response')
        metadata['elapsed_seconds'] = round(perf_counter() - started, 3)
        yield event('done', metadata)
    except ModelError as exc:
        yield event('error', {'message': str(exc)})
    except httpx.TimeoutException:
        yield event('error', {'message': 'SoCLaaS timed out. Retry the message when ready.'})
    except httpx.HTTPStatusError as exc:
        yield event('error', gateway_error(exc.response, settings['model'], perf_counter() - started))
    except httpx.HTTPError:
        yield event('error', {'message': 'Unable to reach SoCLaaS. Check your connection and retry.'})
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        yield event('error', {'message': 'SoCLaaS returned an empty, incomplete or unsupported response. Retry the message.'})
