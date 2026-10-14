"""Provedores com API no formato da OpenAI (Chat Completions): OpenAI e Google Gemini.

O Gemini oferece um endpoint compatível com a OpenAI, então o mesmo código serve
para os dois — só mudam o endereço, a chave e o nome do modelo.
"""

import asyncio
import json
import logging

import httpx

from app.ia.base import (MAX_PASSOS_FERRAMENTAS, ErroIA, Executor, Ferramenta, RespostaIA,
                         historico_valido)

log = logging.getLogger(__name__)

URL_OPENAI = "https://api.openai.com/v1"
URL_GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai"


class OpenAICompativel:
    def __init__(self, url_base: str, chave: str, modelo: str, esforco: str = "",
                 cliente: httpx.AsyncClient | None = None):
        self.url = url_base.rstrip("/")
        self.modelo = modelo
        self.esforco = esforco  # reasoning_effort, só para modelos de raciocínio da OpenAI
        self.cliente = cliente or httpx.AsyncClient(timeout=90)
        self.headers = {"Authorization": f"Bearer {chave}"}

    def _esquema(self, parametros: dict) -> dict:
        # O endpoint do Gemini é mais restrito com JSON Schema e recusa "additionalProperties".
        if self.url != URL_GEMINI:
            return parametros
        return {k: v for k, v in parametros.items() if k != "additionalProperties"}

    async def _post(self, corpo: dict) -> dict:
        ultimo_erro = None
        for tentativa in range(4):
            try:
                resp = await self.cliente.post(f"{self.url}/chat/completions", headers=self.headers, json=corpo)
            except httpx.TransportError as erro:
                ultimo_erro = erro
            else:
                if resp.status_code < 400:
                    return resp.json()
                ultimo_erro = ErroIA(f"HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code not in (408, 409, 429) and resp.status_code < 500:
                    raise ultimo_erro  # erro do pedido (chave, modelo): tentar de novo não resolve
            await asyncio.sleep(2 ** tentativa)
        raise ErroIA(str(ultimo_erro))

    async def conversar(self, sistema: str, contexto: str, historico: list[dict],
                        ferramentas: list[Ferramenta], executar: Executor) -> RespostaIA:
        mensagens = [{"role": "system", "content": f"{sistema}\n\n{contexto}".strip()}]
        mensagens += [{"role": m["papel"], "content": m["texto"]} for m in historico_valido(historico)]
        if len(mensagens) == 1:
            raise ErroIA("Histórico vazio: não há mensagem do lead para responder.")
        tools = [{"type": "function", "function": {"name": f.nome, "description": f.descricao,
                                                   "parameters": self._esquema(f.parametros)}}
                 for f in ferramentas]

        textos = []  # a IA pode escrever antes de chamar uma ferramenta: guardamos tudo
        for _ in range(MAX_PASSOS_FERRAMENTAS):
            corpo = {"model": self.modelo, "messages": mensagens}
            if tools:
                corpo["tools"] = tools
            if self.esforco:
                corpo["reasoning_effort"] = self.esforco
            dados = await self._post(corpo)
            try:
                escolha = dados["choices"][0]
                mensagem = escolha["message"]
            except (KeyError, IndexError) as erro:
                raise ErroIA(f"Resposta inesperada: {str(dados)[:300]}") from erro

            if escolha.get("finish_reason") == "content_filter":
                return RespostaIA(texto="", recusou=True)
            texto = (mensagem.get("content") or "").strip()
            if texto:
                textos.append(texto)
            pedidos = mensagem.get("tool_calls") or []
            if not pedidos:
                return RespostaIA(texto="\n\n".join(textos))

            mensagens.append({"role": "assistant", "content": mensagem.get("content"), "tool_calls": pedidos})
            for pedido in pedidos:
                funcao = pedido.get("function") or {}
                try:
                    argumentos = json.loads(funcao.get("arguments") or "{}")
                    saida = await executar(funcao.get("name", ""), argumentos)
                except Exception as erro:
                    saida = f"Erro: {erro}"
                mensagens.append({"role": "tool", "tool_call_id": pedido.get("id"), "content": saida})

        return RespostaIA(texto="\n\n".join(textos))
