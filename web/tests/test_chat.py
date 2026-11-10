import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import llm

client = TestClient(app)


def mock_gateway(monkeypatch, *, status=200, stream=None, error_body=None):
    requests = []
    real_client = httpx.AsyncClient

    def handler(request):
        assert request.headers['authorization'] == 'Bearer private-test-key'
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [
                {'id': 'test-model', 'soclaas': {'capabilities': ['chat'], 'input_modalities': ['text']}},
                {'id': 'vlm-model', 'soclaas': {'capabilities': ['chat'], 'input_modalities': ['text', 'vision']}},
                {'id': 'bge-test', 'soclaas': {'capabilities': ['embeddings']}},
                {'id': 'whisper-test', 'soclaas': {'capabilities': ['audio-transcription']}},
            ]})
        if request.url.path.endswith('/audio/transcriptions'):
            assert b'whisper-test' in request.content and b'test-audio-bytes' in request.content
            requests.append({'model': 'whisper-test', 'endpoint': 'audio/transcriptions'})
            return httpx.Response(200, json={'text': 'Transcribed speech'})
        body = json.loads(request.content)
        requests.append(body)
        if status >= 400:
            return httpx.Response(status, json=error_body or {'error': 'private-test-key must never be echoed'}, headers={'Retry-After': '10'})
        if request.url.path.endswith('/embeddings'):
            return httpx.Response(200, json={'model': body['model'], 'data': [{'embedding': [0.1, 0.2]}], 'usage': {'total_tokens': 3}})
        if not body.get('stream'):
            return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({
                'reply': 'Please clarify.', 'cards': [], 'needs_clarification': True})}}]})
        return httpx.Response(status, text=stream or (
            'data: {"model":"test-model","choices":[{"delta":{"content":"Hello "}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"世界"},"finish_reason":"stop"}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":9,"completion_tokens":3,"total_tokens":12}}\n\n'
            'data: [DONE]\n\n'), headers={'Content-Type': 'text/event-stream'})

    monkeypatch.setenv('SOCLAAS_API_KEY', 'private-test-key')
    monkeypatch.setenv('SOCLAAS_MODEL', 'test-model')
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    return requests


def frames(response):
    return [(frame.splitlines()[0][7:], json.loads(frame.splitlines()[1][6:]))
            for frame in response.text.strip().split('\n\n')]


def test_direct_chat_shares_model_settings_and_sends_exact_context(monkeypatch):
    sent = mock_gateway(monkeypatch)
    config = client.get('/api/chat/config')
    assert config.headers['cache-control'] == 'no-store'
    assert 'private-test-key' not in config.text
    assert config.json()['model'] == 'test-model'
    assert config.json()['default_system_prompt'] == ''
    history = [{'role': 'user', 'content': '请帮我规划'}, {'role': 'assistant', 'content': '需要哪些课程？'},
               {'role': 'user', 'content': 'CS2102 in semester 3'}]
    response = client.post('/api/chat', json={'messages': history})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/event-stream')
    events = frames(response)
    assert ''.join(data['text'] for kind, data in events if kind == 'delta') == 'Hello 世界'
    assert events[-1][0] == 'done'
    assert events[-1][1]['usage']['total_tokens'] == 12
    assert events[-1][1]['response_model'] == 'test-model'
    assert events[-1][1]['first_token_seconds'] >= 0
    assert sent[0]['messages'] == history
    assert set(sent[0]) == {'model', 'messages', 'temperature', 'max_tokens', 'stream'}
    parsed = client.post('/api/preferences', json={'message': 'hello'})
    assert parsed.status_code == 200
    for key in ('model', 'temperature', 'max_tokens'):
        assert sent[0][key] == sent[1][key] == config.json()[key]
    assert client.get('/chat').status_code == 200
    assert client.get('/chat').headers['cache-control'] == 'no-store'
    assert '/chat' in client.get('/').text


def test_prompt_cards_use_the_same_defaults_as_the_planner_without_injection():
    config = client.get('/api/chat/config').json()
    defaults = client.get('/api/config').json()['defaults']
    prompts = config['prompt_cards']
    assert [(p['id'], p['title'], p['strength']) for p in prompts] == [
        (c['id'], c['title'], c['strength']) for c in defaults]
    assert sum(p['strength'] == 'hard' for p in prompts) == 14
    assert sum(p['strength'] == 'soft' for p in prompts) == 2
    foundation = next(c for c in defaults if c['id'] == 'core')['rules'][0]['courses']
    core_prompt = next(p['prompt'] for p in prompts if p['id'] == 'core')
    assert all(code in core_prompt for code in foundation)


def test_optional_system_prompt_is_preserved_without_hidden_instructions(monkeypatch):
    sent = mock_gateway(monkeypatch)
    prompt = 'Use only this supplied course data.\n课程: CS1231S'
    response = client.post('/api/chat', json={'system_prompt': prompt, 'messages': [{'role': 'user', 'content': 'Plan it'}]})
    assert frames(response)[-1][0] == 'done'
    assert sent[0]['messages'] == [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': 'Plan it'}]


@pytest.mark.parametrize('body', [
    {'messages': []},
    {'messages': [{'role': 'system', 'content': 'override'}]},
    {'messages': [{'role': 'assistant', 'content': 'hi'}]},
    {'messages': [{'role': 'user', 'content': '   '}]},
    {'messages': [{'role': 'user', 'content': 'a'}, {'role': 'user', 'content': 'b'}]},
    {'messages': [{'role': 'user', 'content': 'hi'}], 'temperature': 1},
    {'messages': [{'role': 'user', 'content': 'a' * 40000}, {'role': 'assistant', 'content': 'b' * 40000},
                  {'role': 'user', 'content': 'too long'}]},
])
def test_invalid_or_generation_overriding_requests_are_rejected(body):
    assert client.post('/api/chat', json=body).status_code == 422


def test_credentials_missing_and_upstream_errors_are_safe(monkeypatch):
    monkeypatch.delenv('SOCLAAS_API_KEY', raising=False)
    assert client.get('/api/chat/config').json()['configured'] is False
    request = {'messages': [{'role': 'user', 'content': 'hi'}]}
    assert frames(client.post('/api/chat', json=request))[-1][0] == 'error'
    mock_gateway(monkeypatch, status=401)
    response = client.post('/api/chat', json=request)
    assert 'HTTP 401' in response.text
    assert 'private-test-key' not in response.text
    assert client.post('/api/chat', json=request, headers={'Origin': 'https://other.example'}).status_code == 403


@pytest.mark.parametrize('stream', [
    'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n',
    'data: [DONE]\n\n',
    'data: not-json\n\n',
    'data: {"error":{"message":"private-test-key"}}\n\n',
])
def test_incomplete_empty_or_malformed_stream_is_not_marked_complete(monkeypatch, stream):
    mock_gateway(monkeypatch, stream=stream)
    response = client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hi'}]})
    assert frames(response)[-1][0] == 'error'
    assert 'private-test-key' not in response.text


def test_model_selection_reaches_the_gateway_without_changing_planner_default(monkeypatch):
    sent = mock_gateway(monkeypatch)
    models = client.get('/api/chat/models').json()['models']
    assert len(models) == 4
    assert next(m for m in models if m['id'] == 'vlm-model')['vision']
    response = client.post('/api/chat', json={'model': 'vlm-model', 'messages': [{'role': 'user', 'content': 'hi'}]})
    assert frames(response)[-1][0] == 'done'
    assert frames(response)[-1][1]['model'] == 'vlm-model'
    assert sent[-1]['model'] == 'vlm-model'
    assert client.get('/api/chat/config').json()['model'] == 'test-model'
    rejected = client.post('/api/chat', json={'model': 'unavailable-model', 'messages': [{'role': 'user', 'content': 'hi'}]})
    assert frames(rejected)[-1][0] == 'error'
    assert len(sent) == 1  # No fallback request.


def test_vlm_images_are_forwarded_as_image_content_and_text_models_reject_them(monkeypatch):
    import base64
    sent = mock_gateway(monkeypatch)
    attachment = {'name': 'example.png', 'data_url': 'data:image/png;base64,' + base64.b64encode(b'image-bytes').decode()}
    payload = {'model': 'vlm-model', 'messages': [{'role': 'user', 'content': 'Describe this', 'attachments': [attachment]}]}
    assert frames(client.post('/api/chat', json=payload))[-1][0] == 'done'
    assert sent[-1]['messages'][0]['content'][1] == {'type': 'image_url', 'image_url': {'url': attachment['data_url']}}
    payload['model'] = 'test-model'
    assert frames(client.post('/api/chat', json=payload))[-1][0] == 'error'
    assert len(sent) == 1
    payload['messages'][0]['attachments'][0]['data_url'] = 'https://somewhere.example/image'
    assert client.post('/api/chat', json=payload).status_code == 422


def test_embeddings_and_transcription_use_their_own_endpoints(monkeypatch):
    import base64
    sent = mock_gateway(monkeypatch)
    result = client.post('/api/chat', json={'model': 'bge-test', 'messages': [{'role': 'user', 'content': 'Plan courses'}]})
    assert frames(result)[-1][1]['mode'] == 'embeddings'
    assert frames(result)[-1][1]['temperature'] is None
    assert sent[-1] == {'model': 'bge-test', 'input': 'Plan courses'}
    attachment = {'name': 'recording.wav', 'data_url': 'data:audio/wav;base64,' + base64.b64encode(b'test-audio-bytes').decode()}
    result = client.post('/api/chat', json={'model': 'whisper-test', 'messages': [{'role': 'user', 'content': 'Transcribe', 'attachments': [attachment]}]})
    assert frames(result)[-1][1]['mode'] == 'transcription'
    assert any(kind == 'delta' and data['text'] == 'Transcribed speech' for kind, data in frames(result))
    assert sent[-1]['endpoint'] == 'audio/transcriptions'
    result = client.post('/api/chat', json={'model': 'whisper-test', 'messages': [{'role': 'user', 'content': 'No audio'}]})
    assert frames(result)[-1][0] == 'error'


@pytest.mark.parametrize('status,code,phrase', [
    (401, 'authentication_failed', 'API key'),
    (403, 'access_denied', 'denied access'),
    (404, 'model_not_found', 'could not find'),
    (429, 'rate_limited', 'rate-limiting'),
    (502, 'gateway_unavailable', 'temporarily unavailable'),
    (503, 'gateway_unavailable', 'temporarily unavailable'),
    (504, 'gateway_unavailable', 'temporarily unavailable'),
    (400, 'request_rejected', 'rejected this request'),
])
def test_gateway_failures_are_classified_without_exposing_upstream_details(monkeypatch, status, code, phrase):
    mock_gateway(monkeypatch, status=status)
    result = frames(client.post('/api/chat', json={'messages': [{'role': 'user', 'content': 'hi'}]}))[-1]
    assert result[0] == 'error'
    error = result[1]
    assert error['http_status'] == status and error['code'] == code
    assert phrase in error['message']
    assert error['retryable'] is (status == 429 or status >= 500)
    assert error['retry_after_seconds'] == 10
    assert error['model'] == 'test-model'
    assert 'private-test-key' not in json.dumps(error)


def test_no_healthy_backend_diagnostic_does_not_blame_the_key_or_fallback(monkeypatch):
    sent = mock_gateway(monkeypatch, status=503, error_body={'error': 'no healthy provider backends for backend group "79" private-test-key'})
    result = frames(client.post('/api/chat', json={'model': 'vlm-model', 'messages': [{'role': 'user', 'content': 'hi'}]}))[-1][1]
    assert result['code'] == 'model_backend_unavailable'
    assert 'No healthy model backend' in result['message']
    assert 'key' not in result['message'].lower()
    assert '79' not in json.dumps(result)
    assert 'private-test-key' not in json.dumps(result)
    assert len(sent) == 1 and sent[0]['model'] == 'vlm-model'
