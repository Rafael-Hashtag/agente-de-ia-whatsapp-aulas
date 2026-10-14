"""Canal Evolution GO (WhatsApp Web, conectado por QR Code).

O Evolution GO avisa cada mensagem nova por webhook, no formato do whatsmeow:
    {"event": "Message",
     "data": {"Info": {"ID", "Chat", "Sender", "IsFromMe", "PushName", "Timestamp", ...},
              "Message": {"conversation": "...", "audioMessage": {...}, "base64": "..."}},
     "instanceToken": "...", "instanceName": "..."}
Cada instância tem um token próprio, enviado no header `apikey`.
"""

import base64
import logging
import re
from datetime import datetime

import httpx

from app.canais.base import MensagemRecebida

log = logging.getLogger(__name__)

SUFIXOS_IGNORADOS = ("@g.us", "@broadcast", "@newsletter")


def _limpar_jid(jid: str) -> str:
    """'5511999999999:12@s.whatsapp.net' -> '5511999999999@s.whatsapp.net'"""
    return re.sub(r":\d+(?=@)", "", jid or "")


def _timestamp(valor) -> float | None:
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str) and valor:
        try:
            return datetime.fromisoformat(valor.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _texto_da_mensagem(msg: dict) -> tuple[str, str]:
    """Devolve (tipo, texto) a partir do campo Message do whatsmeow."""
    if msg.get("conversation"):
        return "texto", msg["conversation"]
    ext = msg.get("extendedTextMessage") or {}
    if ext.get("text"):
        return "texto", ext["text"]
    if msg.get("audioMessage"):
        return "audio", ""
    if msg.get("imageMessage"):
        return "imagem", (msg["imageMessage"] or {}).get("caption", "")
    if msg.get("videoMessage"):
        return "outro", (msg["videoMessage"] or {}).get("caption", "")
    if msg.get("documentMessage"):
        return "outro", (msg["documentMessage"] or {}).get("caption", "")
    for chave in ("buttonsResponseMessage", "templateButtonReplyMessage", "listResponseMessage"):
        resp = msg.get(chave) or {}
        texto = resp.get("selectedDisplayText") or resp.get("title")
        if texto:
            return "texto", texto
    return "outro", ""


def interpretar_webhook(payload: dict) -> list[MensagemRecebida]:
    """Transforma o webhook do Evolution GO em mensagens. Ignora o que não for conversa 1:1."""
    if payload.get("event") != "Message":
        return []
    dados = payload.get("data") or {}
    info = dados.get("Info") or {}
    conteudo = dados.get("Message") or {}

    chat = _limpar_jid(str(info.get("Chat", "")))
    if not chat or chat.endswith(SUFIXOS_IGNORADOS) or info.get("IsGroup"):
        return []

    # Quando o chat vem no formato novo (@lid), buscamos o número real do lead no campo "Alt".
    # Em mensagem enviada por nós, o Sender somos nós: o lead está em RecipientAlt.
    if chat.endswith("@lid"):
        campo = "RecipientAlt" if info.get("IsFromMe") else "SenderAlt"
        alt = _limpar_jid(str(info.get(campo, "")))
        if alt.endswith("@s.whatsapp.net"):
            chat = alt
    telefone = re.sub(r"\D", "", chat.split("@")[0])
    destino = telefone if chat.endswith("@s.whatsapp.net") else chat

    tipo, texto = _texto_da_mensagem(conteudo)
    audio = None
    if tipo == "audio" and conteudo.get("base64"):
        try:
            audio = base64.b64decode(conteudo["base64"])
        except ValueError:
            log.warning("Áudio em base64 inválido na mensagem %s", info.get("ID"))

    return [MensagemRecebida(
        id=str(info.get("ID", "")),
        telefone=telefone,
        destino=destino,
        nome=str(info.get("PushName") or ""),
        texto=(texto or "").strip(),
        tipo=tipo,
        audio=audio,
        de_mim=bool(info.get("IsFromMe")),
        timestamp=_timestamp(info.get("Timestamp")) or datetime.now().timestamp(),
    )]


def _id_enviado(resposta: dict) -> str | None:
    dados = resposta.get("data") or {}
    if isinstance(dados, dict):
        info = dados.get("Info") or {}
        return info.get("ID") or dados.get("messageId") or dados.get("ID") or (dados.get("key") or {}).get("id")
    return None


class EvolutionGO:
    nome = "evolution"

    def __init__(self, url: str, token_instancia: str, cliente: httpx.AsyncClient | None = None):
        self.url = url.rstrip("/")
        self.cliente = cliente or httpx.AsyncClient(timeout=30)
        self.headers = {"apikey": token_instancia}

    async def enviar_texto(self, destino: str, texto: str, digitando_ms: int = 0) -> str | None:
        # `delay` faz o Evolution GO mostrar "digitando..." antes de enviar.
        resp = await self.cliente.post(
            f"{self.url}/send/text",
            headers=self.headers,
            json={"number": destino, "text": texto, "delay": max(0, int(digitando_ms))},
            timeout=30 + digitando_ms / 1000,
        )
        resp.raise_for_status()
        return _id_enviado(resp.json())

    async def marcar_lida(self, msg: MensagemRecebida) -> None:
        if not msg.id:
            return
        try:
            resp = await self.cliente.post(
                f"{self.url}/message/markread",
                headers=self.headers,
                json={"id": [msg.id], "number": msg.destino},
            )
            resp.raise_for_status()
        except httpx.HTTPError as erro:
            log.info("Não consegui marcar como lida (%s) — seguindo mesmo assim.", erro)

    async def baixar_audio(self, msg: MensagemRecebida) -> bytes | None:
        # Com WEBHOOK_FILES=true (padrão do docker-compose) o áudio já chega no webhook.
        return msg.audio
