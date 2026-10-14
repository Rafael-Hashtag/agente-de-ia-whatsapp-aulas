import base64
import hashlib
import hmac
from datetime import datetime, timezone

from app.canais import evolution_go, meta


def payload_evolution(**info_extra):
    info = {"ID": "3EB0AA", "Chat": "5511988887777@s.whatsapp.net", "Sender": "5511988887777@s.whatsapp.net",
            "IsFromMe": False, "IsGroup": False, "PushName": "Maria", "Timestamp": "2026-10-14T10:00:00-03:00"}
    info.update(info_extra)
    return {"event": "Message", "instanceToken": "tok", "instanceName": "agente",
            "data": {"Info": info, "Message": {"conversation": "Oi, quero saber do curso"}}}


def test_evolution_texto():
    [m] = evolution_go.interpretar_webhook(payload_evolution())
    assert (m.id, m.telefone, m.destino, m.nome, m.texto, m.tipo, m.de_mim) == (
        "3EB0AA", "5511988887777", "5511988887777", "Maria", "Oi, quero saber do curso", "texto", False)
    assert m.timestamp == datetime(2026, 10, 14, 13, 0, tzinfo=timezone.utc).timestamp()


def test_evolution_texto_estendido_e_audio():
    p = payload_evolution()
    p["data"]["Message"] = {"extendedTextMessage": {"text": "respondendo você"}}
    assert evolution_go.interpretar_webhook(p)[0].texto == "respondendo você"

    p["data"]["Message"] = {"audioMessage": {"seconds": 4}, "base64": base64.b64encode(b"OggS123").decode()}
    m = evolution_go.interpretar_webhook(p)[0]
    assert (m.tipo, m.audio) == ("audio", b"OggS123")


def test_evolution_ignora_grupo_status_e_outros_eventos():
    assert evolution_go.interpretar_webhook(payload_evolution(Chat="123-456@g.us")) == []
    assert evolution_go.interpretar_webhook(payload_evolution(Chat="status@broadcast")) == []
    assert evolution_go.interpretar_webhook({"event": "Receipt", "data": {}}) == []


def test_evolution_formato_lid():
    p = payload_evolution(Chat="99887766@lid", SenderAlt="5511988887777@s.whatsapp.net")
    assert evolution_go.interpretar_webhook(p)[0].destino == "5511988887777"
    p = payload_evolution(Chat="99887766@lid", SenderAlt="")
    m = evolution_go.interpretar_webhook(p)[0]
    assert (m.telefone, m.destino) == ("99887766", "99887766@lid")


def test_evolution_mensagem_do_proprio_numero():
    m = evolution_go.interpretar_webhook(payload_evolution(IsFromMe=True))[0]
    assert m.de_mim and m.telefone == "5511988887777"


def test_evolution_mensagem_do_proprio_numero_em_chat_lid():
    """Em mensagem nossa, o SenderAlt somos nós; o lead está em RecipientAlt."""
    p = payload_evolution(IsFromMe=True, Chat="99887766@lid", Sender="5511900000000@s.whatsapp.net",
                          SenderAlt="11112222@lid", RecipientAlt="5511988887777@s.whatsapp.net")
    assert evolution_go.interpretar_webhook(p)[0].telefone == "5511988887777"


def test_meta_texto_audio_e_nome():
    payload = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "PN1"},
        "contacts": [{"wa_id": "5511988887777", "profile": {"name": "Maria"}}],
        "messages": [
            {"from": "5511988887777", "id": "wamid.1", "timestamp": "1792069200", "type": "text",
             "text": {"body": "Oi"}},
            {"from": "5511988887777", "id": "wamid.2", "timestamp": "1792069201", "type": "audio",
             "audio": {"id": "MEDIA1", "mime_type": "audio/ogg"}},
        ]}}]}]}
    texto, audio = meta.interpretar_webhook(payload, "PN1")
    assert (texto.nome, texto.texto, texto.timestamp) == ("Maria", "Oi", 1792069200.0)
    assert (audio.tipo, audio.midia_id) == ("audio", "MEDIA1")
    assert meta.interpretar_webhook(payload, "OUTRO_NUMERO") == []


def test_meta_status_de_entrega_nao_vira_mensagem():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.1", "status": "read"}]}}]}]}
    assert meta.interpretar_webhook(payload) == []


def test_meta_assinatura():
    corpo = b'{"entry": []}'
    assinatura = "sha256=" + hmac.new(b"segredo", corpo, hashlib.sha256).hexdigest()
    assert meta.assinatura_valida(corpo, assinatura, "segredo")
    assert not meta.assinatura_valida(corpo, "sha256=errada", "segredo")
    assert not meta.assinatura_valida(b"adulterado", assinatura, "segredo")
    assert not meta.assinatura_valida(corpo, assinatura, "")  # sem App Secret, nada entra
