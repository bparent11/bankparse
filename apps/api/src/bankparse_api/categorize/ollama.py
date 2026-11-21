"""Minimal client for a LOCAL Ollama server (https://ollama.com). Labels never leave the machine."""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from bankparse_api.config import get_settings


class LLMError(Exception):
    """The local LLM could not be reached or answered something unusable."""


@dataclass
class InstalledModel:
    name: str
    size_gb: float


@dataclass
class OllamaStatus:
    ok: bool
    models: list[InstalledModel]
    reason: str | None


class OllamaClient:
    def __init__(self, url: str | None = None, timeout: float = 600):
        self.url = (url or get_settings().ollama_url).rstrip("/")
        self.timeout = timeout

    def status(self) -> OllamaStatus:
        try:
            response = httpx.get(f"{self.url}/api/tags", timeout=5)
            response.raise_for_status()
        except httpx.HTTPError:
            return OllamaStatus(False, [], f"Ollama ne répond pas sur {self.url}. Lancez l'application Ollama.")
        models = [
            InstalledModel(m["name"], round(m.get("size", 0) / 1e9, 1))
            for m in response.json().get("models", [])
            if "embed" not in m.get("name", "")  # embedding models cannot classify
        ]
        if not models:
            return OllamaStatus(
                True, [], "Aucun modèle installé dans Ollama : installez-en un, par exemple « ollama pull gemma4:e2b »."
            )
        return OllamaStatus(True, sorted(models, key=lambda m: m.size_gb), None)

    def _chat(self, model: str, system: str, user: str, schema: dict) -> dict | None:
        payload = {
            "model": model,
            "stream": False,
            "think": False,  # reasoning models "think" for hundreds of tokens otherwise: ~10x slower
            "keep_alive": "10m",
            "format": schema,
            "options": {"temperature": 0},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        try:
            response = httpx.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
            if response.status_code == 400 and "think" in response.text:
                payload.pop("think")  # models without a thinking mode reject the option
                response = httpx.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            answer = json.loads(response.json()["message"]["content"])
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama injoignable ou en erreur ({type(exc).__name__}).") from exc
        except (KeyError, ValueError, TypeError):
            return None
        return answer if isinstance(answer, dict) else None

    def classify(self, model: str, system: str, user: str, categories: list[str]) -> str | None:
        """One category among ``categories`` (forced by a JSON schema), or None if the answer is unusable."""
        schema = {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": categories}},
            "required": ["category"],
        }
        category = (self._chat(model, system, user, schema) or {}).get("category")
        return category if category in categories else None

    def classify_batch(
        self, model: str, system: str, user: str, categories: list[str], ids: list[int]
    ) -> dict[int, str]:
        """Several independent operations in one request (the prompt is read once: ~3x faster)."""
        schema = {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "enum": ids},
                            "category": {"type": "string", "enum": categories},
                        },
                        "required": ["id", "category"],
                    },
                }
            },
            "required": ["results"],
        }
        results = (self._chat(model, system, user, schema) or {}).get("results")
        out: dict[int, str] = {}
        for item in results if isinstance(results, list) else []:
            if isinstance(item, dict) and item.get("id") in ids and item.get("category") in categories:
                out[item["id"]] = item["category"]
        return out
