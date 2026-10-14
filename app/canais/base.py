"""O que todo canal de WhatsApp precisa oferecer ao agente.

O agente não sabe se está falando pelo Evolution GO ou pela API oficial da Meta:
ele só recebe `MensagemRecebida` e chama os métodos de `Canal`.
"""

import time
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class MensagemRecebida:
    id: str
    telefone: str          # só dígitos; identifica o lead
    destino: str           # para onde responder (número ou JID, depende do canal)
    nome: str = ""
    texto: str = ""
    tipo: str = "texto"    # texto | audio | imagem | outro
    audio: bytes | None = None
    midia_id: str = ""     # referência para baixar a mídia depois (API da Meta)
    de_mim: bool = False   # enviada pelo número do agente (ex.: dono respondendo pelo celular)
    timestamp: float = field(default_factory=time.time)


class Canal(Protocol):
    nome: str

    async def enviar_texto(self, destino: str, texto: str, digitando_ms: int = 0) -> str | None:
        """Envia a mensagem e devolve o id dela (ou None se não souber)."""

    async def marcar_lida(self, msg: MensagemRecebida) -> None:
        """Marca a mensagem do lead como lida (os dois tracinhos azuis)."""

    async def baixar_audio(self, msg: MensagemRecebida) -> bytes | None:
        """Bytes do áudio, quando o webhook não trouxe junto."""
