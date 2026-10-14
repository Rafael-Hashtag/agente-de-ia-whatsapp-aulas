"""Tipos comuns a todos os provedores de IA.

Cada provedor implementa `conversar()`: recebe o prompt, o histórico e as
ferramentas, roda o ciclo "IA pede ferramenta -> executamos -> IA continua"
e devolve o texto final para o lead.
"""

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

MAX_PASSOS_FERRAMENTAS = 5


@dataclass
class Ferramenta:
    nome: str
    descricao: str
    parametros: dict  # JSON Schema de um objeto (additionalProperties: false)


@dataclass
class RespostaIA:
    texto: str
    recusou: bool = False  # a IA se recusou a responder (filtro de segurança do provedor)


Executor = Callable[[str, dict], Awaitable[str]]


class ErroIA(Exception):
    """Falha ao falar com o provedor de IA (chave inválida, fora do ar, limite...)."""


class ProvedorIA(Protocol):
    async def conversar(self, sistema: str, contexto: str, historico: list[dict],
                        ferramentas: list[Ferramenta], executar: Executor) -> RespostaIA:
        """`sistema` é fixo (vai para o cache); `contexto` muda a cada resposta."""


def historico_valido(historico: list[dict]) -> list[dict]:
    """A conversa enviada à IA precisa começar com uma mensagem do lead."""
    inicio = 0
    while inicio < len(historico) and historico[inicio]["papel"] != "user":
        inicio += 1
    return [m for m in historico[inicio:] if m["texto"].strip()]
