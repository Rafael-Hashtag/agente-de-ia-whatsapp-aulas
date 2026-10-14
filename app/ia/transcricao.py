"""Transcrição dos áudios que o lead manda (Whisper, pela OpenAI ou pela Groq)."""

import logging

import httpx

log = logging.getLogger(__name__)

PROVEDORES = {
    # provedor: (url base, modelo)
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini-transcribe"),
    "groq": ("https://api.groq.com/openai/v1", "whisper-large-v3-turbo"),
}


class Transcritor:
    def __init__(self, provedor: str, chave: str, cliente: httpx.AsyncClient | None = None):
        self.url, self.modelo = PROVEDORES[provedor]
        self.headers = {"Authorization": f"Bearer {chave}"}
        self.cliente = cliente or httpx.AsyncClient(timeout=120)

    async def transcrever(self, audio: bytes) -> str | None:
        try:
            resp = await self.cliente.post(
                f"{self.url}/audio/transcriptions",
                headers=self.headers,
                files={"file": ("audio.ogg", audio, "audio/ogg")},
                data={"model": self.modelo, "language": "pt", "response_format": "json"},
            )
            resp.raise_for_status()
            return (resp.json().get("text") or "").strip() or None
        except (httpx.HTTPError, ValueError) as erro:
            log.error("Falha ao transcrever áudio: %s", erro)
            return None
