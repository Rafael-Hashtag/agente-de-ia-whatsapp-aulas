import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

ENV = {
    "CANAL": "evolution", "IA_PROVEDOR": "anthropic", "ANTHROPIC_API_KEY": "x",
    "EVOLUTION_TOKEN_INSTANCIA": "tok", "WEBHOOK_SEGREDO": "seg", "LINK_CHECKOUT": "https://pagar",
    "META_VERIFY_TOKEN": "verifica", "META_APP_SECRET": "app-secret", "PAINEL_TOKEN": "painel",
}


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    for chave, valor in ENV.items():
        monkeypatch.setenv(chave, valor)
    monkeypatch.setenv("PASTA_DADOS", str(tmp_path))
    from app.main import app
    with TestClient(app) as c:
        recebidas = []

        async def receber(msg):
            recebidas.append(msg)

        app.state.agente.receber = receber
        c.recebidas = recebidas
        yield c


def test_saude(cliente):
    dados = cliente.get("/saude").json()
    assert dados["ok"] and "Evolution GO" in dados["creditos"]


def test_webhook_evolution_exige_segredo_e_token(cliente):
    corpo = {"event": "Message", "instanceToken": "tok", "data": {
        "Info": {"ID": "1", "Chat": "5511988887777@s.whatsapp.net", "Timestamp": "2026-10-14T10:00:00Z"},
        "Message": {"conversation": "oi"}}}
    assert cliente.post("/webhook/evolution/errado", json=corpo).status_code == 403
    assert cliente.post("/webhook/evolution/seg", json={**corpo, "instanceToken": "outro"}).status_code == 403
    assert cliente.post("/webhook/evolution/seg", json=corpo).status_code == 200
    assert [m.texto for m in cliente.recebidas] == ["oi"]


def test_webhook_meta_verificacao_e_assinatura(cliente):
    params = {"hub.mode": "subscribe", "hub.verify_token": "verifica", "hub.challenge": "123"}
    assert cliente.get("/webhook/meta", params=params).text == "123"
    assert cliente.get("/webhook/meta", params={**params, "hub.verify_token": "x"}).status_code == 403

    corpo = json.dumps({"entry": [{"changes": [{"value": {"messages": [
        {"from": "5511988887777", "id": "w1", "timestamp": "1792069200", "type": "text", "text": {"body": "oi"}}]}}]}]}).encode()
    assinatura = "sha256=" + hmac.new(b"app-secret", corpo, hashlib.sha256).hexdigest()
    assert cliente.post("/webhook/meta", content=corpo, headers={"x-hub-signature-256": "sha256=x"}).status_code == 403
    assert cliente.post("/webhook/meta", content=corpo, headers={"x-hub-signature-256": assinatura}).status_code == 200
    assert cliente.recebidas[-1].texto == "oi"


def test_csv_protegido(cliente):
    assert cliente.get("/leads.csv").status_code == 403
    resp = cliente.get("/leads.csv", params={"token": "painel"})
    assert resp.status_code == 200 and "telefone;nome;status" in resp.text
