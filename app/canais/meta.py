"""Canal API oficial do WhatsApp (WhatsApp Cloud API, da Meta).

Diferenças importantes em relação ao Evolution GO:
- A Meta exige um endereço HTTPS público para o webhook (o Caddy cuida disso).
- Mensagem livre só pode ser enviada até 24h depois da última mensagem do lead.
  Depois disso, só com template aprovado — por isso o follow-up respeita essa janela.
"""

import asyncio
import hashlib
import hmac
import logging

import httpx

from app.canais.base import MensagemRecebida

log = logging.getLogger(__name__)


def assinatura_valida(corpo: bytes, cabecalho: str, app_secret: str) -> bool:
    """Confere o header X-Hub-Signature-256 (prova de que o webhook veio da Meta)."""
    if not app_secret:
        return False  # sem App Secret qualquer um poderia forjar mensagens: recusamos tudo
    esperado = "sha256=" + hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, cabecalho or "")


def _tipo_e_texto(msg: dict) -> tuple[str, str, str]:
    """Devolve (tipo, texto, id_da_midia)."""
    tipo = msg.get("type")
    if tipo == "text":
        return "texto", (msg.get("text") or {}).get("body", ""), ""
    if tipo == "audio":
        return "audio", "", (msg.get("audio") or {}).get("id", "")
    if tipo == "image":
        imagem = msg.get("image") or {}
        return "imagem", imagem.get("caption", ""), imagem.get("id", "")
    if tipo == "button":
        return "texto", (msg.get("button") or {}).get("text", ""), ""
    if tipo == "interactive":
        inter = msg.get("interactive") or {}
        resposta = inter.get("button_reply") or inter.get("list_reply") or {}
        return "texto", resposta.get("title", ""), ""
    return "outro", "", ""


def interpretar_webhook(payload: dict, phone_number_id: str = "") -> list[MensagemRecebida]:
    mensagens = []
    for entrada in payload.get("entry") or []:
        for mudanca in entrada.get("changes") or []:
            valor = mudanca.get("value") or {}
            if phone_number_id and (valor.get("metadata") or {}).get("phone_number_id") != phone_number_id:
                continue
            nomes = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in valor.get("contacts") or []}
            for msg in valor.get("messages") or []:
                tipo, texto, midia = _tipo_e_texto(msg)
                remetente = str(msg.get("from", ""))
                try:
                    ts = float(msg.get("timestamp"))
                except (TypeError, ValueError):
                    ts = None
                mensagem = MensagemRecebida(
                    id=str(msg.get("id", "")),
                    telefone=remetente,
                    destino=remetente,
                    nome=nomes.get(remetente, ""),
                    texto=(texto or "").strip(),
                    tipo=tipo,
                    midia_id=midia,
                )
                if ts:
                    mensagem.timestamp = ts
                mensagens.append(mensagem)
    return mensagens


class MetaCloud:
    nome = "meta"

    def __init__(self, token: str, phone_number_id: str, versao: str = "v23.0",
                 cliente: httpx.AsyncClient | None = None):
        self.base = f"https://graph.facebook.com/{versao}"
        self.phone_number_id = phone_number_id
        self.cliente = cliente or httpx.AsyncClient(timeout=30)
        self.headers = {"Authorization": f"Bearer {token}"}
        self._ultima_recebida: dict[str, str] = {}  # destino -> id (usado no "digitando...")

    async def _post(self, corpo: dict) -> dict:
        resp = await self.cliente.post(f"{self.base}/{self.phone_number_id}/messages",
                                       headers=self.headers, json=corpo)
        if resp.status_code >= 400:
            log.error("Meta recusou o envio (%s): %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        return resp.json()

    async def enviar_texto(self, destino: str, texto: str, digitando_ms: int = 0) -> str | None:
        ultima = self._ultima_recebida.get(destino)
        if digitando_ms and ultima:
            try:
                await self._post({"messaging_product": "whatsapp", "status": "read", "message_id": ultima,
                                  "typing_indicator": {"type": "text"}})
            except httpx.HTTPError:
                pass  # "digitando..." é só cosmético
            await asyncio.sleep(digitando_ms / 1000)
        dados = await self._post({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": destino,
            "type": "text",
            "text": {"preview_url": True, "body": texto},
        })
        return ((dados.get("messages") or [{}])[0]).get("id")

    async def marcar_lida(self, msg: MensagemRecebida) -> None:
        if not msg.id:
            return
        self._ultima_recebida[msg.destino] = msg.id
        try:
            await self._post({"messaging_product": "whatsapp", "status": "read", "message_id": msg.id})
        except httpx.HTTPError as erro:
            log.info("Não consegui marcar como lida (%s).", erro)

    async def baixar_audio(self, msg: MensagemRecebida) -> bytes | None:
        if not msg.midia_id:
            return None
        info = await self.cliente.get(f"{self.base}/{msg.midia_id}", headers=self.headers)
        info.raise_for_status()
        arquivo = await self.cliente.get(info.json()["url"], headers=self.headers)
        arquivo.raise_for_status()
        return arquivo.content
