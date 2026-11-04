"""Local Ollama planner. Only control metadata leaves the harness; no student rows."""
import json
import os
from urllib.parse import urlparse
import httpx


class AgentUnavailable(RuntimeError):
    pass


class AgentPolicyError(ValueError):
    pass


class OllamaPlanner:
    mode = 'llm'

    def __init__(self, url=None, model=None, client=None):
        self.url = (url or os.getenv('TUTORIA_LLM_URL', 'http://127.0.0.1:11434')).rstrip('/')
        self.model = model or os.getenv('TUTORIA_LLM_MODEL', 'qwen2.5:0.5b-instruct')
        parsed = urlparse(self.url)
        if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', 'ollama'} or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise AgentUnavailable('El planificador solo admite el servidor Ollama local configurado')
        self.client = client

    def choose(self, allowed, summary):
        schema = {'type': 'object', 'properties': {'action': {'type': 'string', 'enum': allowed}},
                  'required': ['action'], 'additionalProperties': False}
        request = {
            'model': self.model, 'stream': False, 'format': schema,
            'messages': [
                {'role': 'system', 'content': 'Eres el agente de preparación académica. Elige una sola acción permitida para continuar. '
                    'El código limpia, entrena y predice. No apruebas ni publicas. Devuelve únicamente el JSON con action.'},
                {'role': 'user', 'content': json.dumps({'allowed_actions': allowed, 'summary': summary})}],
            'options': {'temperature': 0, 'num_predict': 64, 'num_ctx': 2048},
        }
        try:
            if self.client is None:
                with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
                    response = client.post(self.url+'/api/chat', json=request)
            else:
                response = self.client.post(self.url+'/api/chat', json=request)
            response.raise_for_status()
            decision = json.loads(response.json()['message']['content'])
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise AgentUnavailable('Ollama no está disponible o devolvió una respuesta inválida; no se creó ningún lote') from None
        if not isinstance(decision, dict) or set(decision) != {'action'} or decision['action'] not in allowed:
            raise AgentPolicyError('El LLM intentó una acción fuera del estado permitido')
        return decision['action']


def configured_planner():
    mode = os.getenv('TUTORIA_AGENT_MODE', 'rules')
    if mode == 'rules':
        return None
    if mode == 'llm':
        return OllamaPlanner()
    raise AgentUnavailable('TUTORIA_AGENT_MODE debe ser rules o llm')
