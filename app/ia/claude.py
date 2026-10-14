"""Provedor Anthropic (Claude), pelo SDK oficial `anthropic`."""

import anthropic

from app.ia.base import (MAX_PASSOS_FERRAMENTAS, ErroIA, Executor, Ferramenta, RespostaIA,
                         historico_valido)

# Modelos que aceitam output_config.effort (nos mais antigos o parâmetro dá erro).
_PREFIXOS_COM_ESFORCO = ("claude-opus-5", "claude-sonnet-5", "claude-haiku-5", "claude-fable-5",
                         "claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8", "claude-sonnet-4-6")

# Modelos com fallback automático no servidor: se o filtro de segurança recusar,
# a própria Anthropic tenta de novo em outro modelo, na mesma chamada.
_MODELOS_COM_FALLBACK = ("claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1")


class Claude:
    def __init__(self, modelo: str, chave: str, esforco: str = "low", cliente=None):
        self.modelo = modelo
        self.esforco = esforco
        self.cliente = cliente or anthropic.AsyncAnthropic(api_key=chave, max_retries=3, timeout=90.0)

    async def _chamar(self, **params):
        if self.modelo.startswith(_PREFIXOS_COM_ESFORCO):
            params["output_config"] = {"effort": self.esforco}
        if self.modelo in _MODELOS_COM_FALLBACK:
            return await self.cliente.beta.messages.create(
                **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        return await self.cliente.messages.create(**params)

    async def conversar(self, sistema: str, contexto: str, historico: list[dict],
                        ferramentas: list[Ferramenta], executar: Executor) -> RespostaIA:
        # O bloco fixo é marcado para cache; o contexto do lead vem depois para não quebrá-lo.
        system = [{"type": "text", "text": sistema, "cache_control": {"type": "ephemeral"}}]
        if contexto:
            system.append({"type": "text", "text": contexto})
        tools = [{"name": f.nome, "description": f.descricao, "input_schema": f.parametros, "strict": True}
                 for f in ferramentas]
        messages = [{"role": m["papel"], "content": m["texto"]} for m in historico_valido(historico)]
        if not messages:
            raise ErroIA("Histórico vazio: não há mensagem do lead para responder.")

        textos = []  # a IA pode escrever antes de chamar uma ferramenta: guardamos tudo
        for _ in range(MAX_PASSOS_FERRAMENTAS):
            params = {"model": self.modelo, "max_tokens": 16000, "system": system, "messages": messages}
            if tools:
                params["tools"] = tools
            try:
                resp = await self._chamar(**params)
            except anthropic.APIError as erro:
                raise ErroIA(f"Anthropic: {erro}") from erro

            if resp.stop_reason == "refusal":
                return RespostaIA(texto="", recusou=True)

            texto = "".join(b.text for b in resp.content if b.type == "text").strip()
            if texto:
                textos.append(texto)
            pedidos = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not pedidos:
                return RespostaIA(texto="\n\n".join(textos))

            # Devolvemos o conteúdo inteiro (inclusive blocos de raciocínio) sem alterar.
            messages.append({"role": "assistant", "content": resp.content})
            resultados = []
            for pedido in pedidos:
                try:
                    saida = await executar(pedido.name, dict(pedido.input or {}))
                    resultados.append({"type": "tool_result", "tool_use_id": pedido.id, "content": saida})
                except Exception as erro:  # a ferramenta falhou: a IA precisa saber
                    resultados.append({"type": "tool_result", "tool_use_id": pedido.id,
                                       "content": f"Erro: {erro}", "is_error": True})
            messages.append({"role": "user", "content": resultados})

        return RespostaIA(texto="\n\n".join(textos))
