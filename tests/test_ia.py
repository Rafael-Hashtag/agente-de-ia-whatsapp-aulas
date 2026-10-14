import asyncio
import json
from types import SimpleNamespace as NS

import httpx

from app.ferramentas import FERRAMENTAS, Acoes
from app.ia.claude import Claude
from app.ia.openai_compativel import URL_GEMINI, OpenAICompativel

HISTORICO = [{"papel": "assistant", "texto": "msg antiga do robô"}, {"papel": "user", "texto": "quero comprar"}]


class MensagensFalsas:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    async def create(self, **params):
        self.pedidos.append({**params, "messages": list(params["messages"])})  # foto do momento da chamada
        return self.respostas.pop(0)


def cliente_anthropic_falso(respostas):
    mensagens = MensagensFalsas(respostas)
    return NS(messages=mensagens, beta=NS(messages=mensagens)), mensagens


def test_claude_ciclo_de_ferramentas():
    pede = NS(stop_reason="tool_use", content=[
        NS(type="thinking", thinking=""),
        NS(type="tool_use", id="tu1", name="enviar_link_checkout", input={"lead_pediu_explicitamente": False}),
    ])
    final = NS(stop_reason="end_turn", content=[NS(type="text", text="Vou te mandar o link!")])
    cliente, mensagens = cliente_anthropic_falso([pede, final])
    ia = Claude("claude-opus-5-5", "chave", cliente=cliente)
    acoes = Acoes(lead={}, tem_link=True)

    resposta = asyncio.run(ia.conversar("SISTEMA", "FICHA", HISTORICO, FERRAMENTAS, acoes.executar))

    assert resposta.texto == "Vou te mandar o link!" and acoes.enviar_checkout
    primeiro, segundo = mensagens.pedidos
    assert primeiro["messages"] == [{"role": "user", "content": "quero comprar"}]  # começa no lead
    assert primeiro["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert primeiro["system"][1]["text"] == "FICHA"
    assert primeiro["output_config"] == {"effort": "low"}
    assert primeiro["fallbacks"] == "default" and primeiro["betas"] == ["server-side-fallback-2026-07-01"]
    assert all(t["strict"] for t in primeiro["tools"])
    # o conteúdo do assistente volta inalterado, seguido do resultado da ferramenta
    assert segundo["messages"][1] == {"role": "assistant", "content": pede.content}
    assert segundo["messages"][2]["content"][0]["tool_use_id"] == "tu1"


def test_claude_texto_antes_da_ferramenta_nao_se_perde():
    pede = NS(stop_reason="tool_use", content=[
        NS(type="text", text="Que legal, Ana! Me conta mais."),
        NS(type="tool_use", id="tu1", name="registrar_qualificacao", input={"necessidade": "x"}),
    ])
    final = NS(stop_reason="end_turn", content=[])
    cliente, _ = cliente_anthropic_falso([pede, final])
    resposta = asyncio.run(Claude("claude-opus-5-5", "k", cliente=cliente).conversar(
        "S", "", HISTORICO, FERRAMENTAS, Acoes({}, True).executar))
    assert resposta.texto == "Que legal, Ana! Me conta mais."


def test_claude_recusa_e_modelo_antigo_sem_parametros_novos():
    cliente, mensagens = cliente_anthropic_falso([NS(stop_reason="refusal", content=[])])
    ia = Claude("claude-haiku-4-5", "chave", cliente=cliente)
    resposta = asyncio.run(ia.conversar("S", "", HISTORICO, [], Acoes({}, True).executar))
    assert resposta.recusou
    pedido = mensagens.pedidos[0]
    assert "output_config" not in pedido and "fallbacks" not in pedido and "tools" not in pedido


def test_openai_compativel_ciclo_de_ferramentas():
    pedidos = []
    respostas = [
        {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "chamar_humano",
                                                          "arguments": json.dumps({"motivo": "reembolso"})}}]}}]},
        {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": "Já chamo alguém."}}]},
    ]

    def responder(request: httpx.Request):
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, json=respostas.pop(0))

    cliente = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    ia = OpenAICompativel(URL_GEMINI, "chave", "gemini-2.5-flash", cliente=cliente)
    acoes = Acoes(lead={}, tem_link=True)
    resposta = asyncio.run(ia.conversar("S", "F", HISTORICO, FERRAMENTAS, acoes.executar))

    assert resposta.texto == "Já chamo alguém." and acoes.chamar_humano == "reembolso"
    assert pedidos[0]["messages"][0] == {"role": "system", "content": "S\n\nF"}
    assert "additionalProperties" not in pedidos[0]["tools"][0]["function"]["parameters"]
    assert pedidos[1]["messages"][-1] == {"role": "tool", "tool_call_id": "c1",
                                          "content": pedidos[1]["messages"][-1]["content"]}


def test_openai_compativel_nao_insiste_em_chave_invalida():
    chamadas = []

    def responder(request):
        chamadas.append(1)
        return httpx.Response(401, json={"error": "invalid key"})

    ia = OpenAICompativel("https://x", "ruim", "m", cliente=httpx.AsyncClient(transport=httpx.MockTransport(responder)))
    try:
        asyncio.run(ia.conversar("S", "", HISTORICO, [], Acoes({}, True).executar))
    except Exception as erro:
        assert "401" in str(erro)
    assert len(chamadas) == 1
