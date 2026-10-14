"""Exporta os leads: CSV (abre no Excel/Sheets) e sincronização com Google Sheets.

A sincronização usa um Web App do Google Apps Script (código em docs/google-sheets.md):
o agente envia a ficha do lead por POST e o script atualiza a linha daquele telefone.
Não precisa de conta de serviço nem OAuth.
"""

import csv
import io
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger(__name__)

COLUNAS = ["telefone", "nome", "status", "resultado", "temperatura", "necessidade", "autoridade",
           "orcamento", "prazo", "resumo", "checkout_enviado_em", "criado_em", "ultima_msg_lead_em",
           "pausado_ate"]
COLUNAS_DATA = {"checkout_enviado_em", "criado_em", "ultima_msg_lead_em", "pausado_ate"}


def linha(lead: dict, fuso: str) -> dict:
    saida = {}
    for coluna in COLUNAS:
        valor = lead.get(coluna)
        if coluna in COLUNAS_DATA:
            valor = datetime.fromtimestamp(valor, ZoneInfo(fuso)).strftime("%d/%m/%Y %H:%M") if valor else ""
        saida[coluna] = "" if valor is None else valor
    return saida


def gerar_csv(leads: list[dict], fuso: str) -> str:
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=COLUNAS, delimiter=";")
    escritor.writeheader()
    for lead in leads:
        escritor.writerow(linha(lead, fuso))
    return "﻿" + buffer.getvalue()  # BOM: o Excel abre os acentos certinho


class Planilha:
    def __init__(self, url: str, fuso: str, cliente: httpx.AsyncClient | None = None):
        self.url = url
        self.fuso = fuso
        self.cliente = cliente or httpx.AsyncClient(timeout=20, follow_redirects=True)

    async def sincronizar(self, lead: dict) -> None:
        if not self.url or not lead:
            return
        try:
            resp = await self.cliente.post(self.url, json=linha(lead, self.fuso))
            resp.raise_for_status()
        except httpx.HTTPError as erro:
            log.warning("Não consegui atualizar a planilha: %s", erro)
