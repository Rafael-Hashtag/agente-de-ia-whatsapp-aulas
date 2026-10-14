"""Servidor web do agente: recebe os webhooks do WhatsApp e roda o follow-up.

Rotas:
  POST /webhook/evolution/{segredo}  ← Evolution GO (rede interna do Docker)
  GET|POST /webhook/meta             ← API oficial da Meta (precisa de HTTPS)
  GET  /leads.csv?token=...          ← planilha com todos os leads
  GET  /saude                        ← diz se está tudo configurado
"""

import asyncio
import hmac
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.agente import Agente
from app.canais import evolution_go, meta
from app.config import Config
from app.db import Banco
from app.ia.fabrica import criar_ia, criar_transcritor
from app.planilha import Planilha, gerar_csv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("agente")

INTERVALO_FOLLOWUP = 300  # segundos


def criar_agente(cfg: Config) -> Agente:
    if cfg.canal == "meta":
        canal = meta.MetaCloud(cfg.meta_token, cfg.meta_phone_number_id, cfg.meta_api_versao)
    else:
        canal = evolution_go.EvolutionGO(cfg.evolution_url, cfg.evolution_token_instancia)
    return Agente(
        cfg=cfg,
        banco=Banco(cfg.pasta_dados / "agente.sqlite3"),
        canal=canal,
        ia=criar_ia(cfg),
        transcritor=criar_transcritor(cfg),
        planilha=Planilha(cfg.sheets_webhook_url, cfg.fuso) if cfg.sheets_webhook_url else None,
    )


async def _laco_followup(agente: Agente) -> None:
    while True:
        await asyncio.sleep(INTERVALO_FOLLOWUP)
        try:
            await agente.fazer_followups()
        except Exception:
            log.exception("Erro no ciclo de follow-up")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    cfg = Config.do_ambiente()
    problemas = cfg.problemas()
    for problema in problemas:
        log.error("CONFIGURAÇÃO: %s", problema)
    app.state.cfg = cfg
    app.state.problemas = problemas
    app.state.agente = criar_agente(cfg)
    app.state.agente.retomar_pendentes()
    tarefa = asyncio.create_task(_laco_followup(app.state.agente))
    log.info("Agente no ar — canal %s, IA %s (%s).", cfg.canal, cfg.ia_provedor, cfg.ia_modelo)
    yield
    tarefa.cancel()


app = FastAPI(title="Agente de Vendas WhatsApp", lifespan=ciclo_de_vida)


def _distribuir(request: Request, mensagens) -> None:
    agente: Agente = request.app.state.agente
    for msg in mensagens:
        agente._rodar(agente.receber(msg))  # responde rápido ao webhook; processa em segundo plano


@app.post("/webhook/evolution/{segredo}")
async def webhook_evolution(segredo: str, request: Request):
    cfg: Config = request.app.state.cfg
    if not cfg.webhook_segredo or not hmac.compare_digest(segredo, cfg.webhook_segredo):
        raise HTTPException(status_code=403)
    payload = await request.json()
    token = payload.get("instanceToken")
    if token and cfg.evolution_token_instancia and token != cfg.evolution_token_instancia:
        raise HTTPException(status_code=403)
    _distribuir(request, evolution_go.interpretar_webhook(payload))
    return {"ok": True}


@app.get("/webhook/meta")
async def verificar_webhook_meta(request: Request):
    """A Meta chama esta rota uma vez, ao cadastrar o webhook, para confirmar que somos nós."""
    cfg: Config = request.app.state.cfg
    params = request.query_params
    if params.get("hub.mode") == "subscribe" and cfg.meta_verify_token and \
            hmac.compare_digest(params.get("hub.verify_token", ""), cfg.meta_verify_token):
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403)


@app.post("/webhook/meta")
async def webhook_meta(request: Request):
    cfg: Config = request.app.state.cfg
    corpo = await request.body()
    if not meta.assinatura_valida(corpo, request.headers.get("x-hub-signature-256", ""), cfg.meta_app_secret):
        raise HTTPException(status_code=403)
    _distribuir(request, meta.interpretar_webhook(json.loads(corpo or b"{}"), cfg.meta_phone_number_id))
    return {"ok": True}


@app.get("/leads.csv")
async def leads_csv(request: Request, token: str = ""):
    cfg: Config = request.app.state.cfg
    if not cfg.painel_token or not hmac.compare_digest(token, cfg.painel_token):
        raise HTTPException(status_code=403)
    conteudo = gerar_csv(request.app.state.agente.banco.todos_leads(), cfg.fuso)
    return Response(conteudo, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="leads.csv"'})


@app.get("/saude")
async def saude(request: Request):
    cfg: Config = request.app.state.cfg
    return {
        "ok": not request.app.state.problemas,
        "problemas": request.app.state.problemas,
        "canal": cfg.canal,
        "ia": f"{cfg.ia_provedor}/{cfg.ia_modelo}",
        "transcricao": cfg.transcricao_provedor,
        "creditos": "Conexão WhatsApp via Evolution GO (evolution-foundation/evolution-go)" if cfg.canal == "evolution" else "",
    }
