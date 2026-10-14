import time

import pytest

from app.agente import Agente
from app.canais.base import MensagemRecebida
from app.config import Config
from app.db import Banco
from app.ia.base import RespostaIA


class CanalFalso:
    nome = "falso"

    def __init__(self):
        self.enviadas: list[tuple[str, str]] = []
        self.lidas: list[str] = []
        self.falhar = False

    async def enviar_texto(self, destino, texto, digitando_ms=0):
        if self.falhar:
            raise RuntimeError("canal fora do ar")
        self.enviadas.append((destino, texto))
        return f"enviada-{len(self.enviadas)}"

    async def marcar_lida(self, msg):
        self.lidas.append(msg.id)

    async def baixar_audio(self, msg):
        return msg.audio

    def textos(self, destino=None):
        return [t for d, t in self.enviadas if destino is None or d == destino]


class IAFalsa:
    """Responde com um roteiro: cada item é um texto ou uma função async(executar) -> texto."""

    def __init__(self, *roteiro):
        self.roteiro = list(roteiro)
        self.chamadas: list[dict] = []

    async def conversar(self, sistema, contexto, historico, ferramentas, executar):
        self.chamadas.append({"sistema": sistema, "contexto": contexto, "historico": list(historico),
                              "ferramentas": [f.nome for f in ferramentas]})
        passo = self.roteiro.pop(0) if self.roteiro else "ok"
        if isinstance(passo, Exception):
            raise passo
        if isinstance(passo, RespostaIA):
            return passo
        if callable(passo):
            return RespostaIA(texto=await passo(executar))
        return RespostaIA(texto=passo)


@pytest.fixture
def cfg(tmp_path):
    (tmp_path / "negocio.md").write_text("Produto: Curso X por R$ 100", encoding="utf-8")
    (tmp_path / "instrucoes.md").write_text("Você é um vendedor.", encoding="utf-8")
    return Config(
        canal="evolution", anthropic_api_key="x", evolution_token_instancia="t", webhook_segredo="s",
        link_checkout="https://pagar.exemplo/curso", dono_telefone="5511900000000",
        debounce_segundos=0, pasta_config=tmp_path, pasta_dados=tmp_path,
        horario_inicio=0, horario_fim=24,
    )


@pytest.fixture
def banco():
    return Banco(":memory:")


@pytest.fixture
def canal():
    return CanalFalso()


@pytest.fixture
def montar(cfg, banco, canal):
    def _montar(ia):
        agente = Agente(cfg, banco, canal, ia)
        agente.espera_nova_tentativa = 0  # nos testes, nada de esperar 60s
        return agente
    return _montar


_contador = {"n": 0}


def msg(texto="oi", telefone="5511988887777", **extra):
    _contador["n"] += 1
    dados = dict(id=f"m{_contador['n']}", telefone=telefone, destino=telefone, nome="Fulano",
                 texto=texto, timestamp=time.time())
    dados.update(extra)
    return MensagemRecebida(**dados)
