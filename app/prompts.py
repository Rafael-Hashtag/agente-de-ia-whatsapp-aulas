"""Monta o que a IA lê antes de responder.

- `sistema`: config/instrucoes.md + config/negocio.md. É lido do disco a cada
  resposta, então editar esses arquivos vale na hora, sem reiniciar nada.
- `contexto`: a ficha do lead (nome, o que já se sabe, se o link já foi enviado).
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def _ler(caminho: Path) -> str:
    try:
        return caminho.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def montar_sistema(pasta_config: Path) -> str:
    instrucoes = _ler(pasta_config / "instrucoes.md")
    negocio = _ler(pasta_config / "negocio.md")
    if not negocio:
        raise FileNotFoundError(f"Não encontrei {pasta_config / 'negocio.md'} — é ali que vai a descrição do produto.")
    return f"{instrucoes}\n\n---\n\n# O NEGÓCIO (fonte única de verdade sobre produto, preço e condições)\n\n{negocio}"


def _data(ts: int | None, fuso: str) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, ZoneInfo(fuso)).strftime("%d/%m às %H:%M")


def montar_contexto(lead: dict, fuso: str, tem_link: bool, extra: str = "") -> str:
    agora = datetime.now(ZoneInfo(fuso))
    linhas = [
        "# FICHA DESTE LEAD (atualizada pelo sistema agora)",
        f"- Agora: {DIAS[agora.weekday()]}, {agora.strftime('%d/%m/%Y %H:%M')}",
        f"- Nome no WhatsApp: {lead.get('nome') or 'não informado'}",
        f"- Etapa: {lead.get('status', 'novo')}",
    ]
    conhecidos = [(c, lead.get(c)) for c in ("necessidade", "autoridade", "orcamento", "prazo", "temperatura", "resumo")]
    conhecidos = [f"{c}: {v}" for c, v in conhecidos if v]
    linhas.append("- Já sabemos: " + ("; ".join(conhecidos) if conhecidos else "nada ainda"))
    if not tem_link:
        linhas.append("- Link de compra: não configurado — se o lead quiser comprar, chame um humano.")
    elif lead.get("checkout_enviado_em"):
        linhas.append(f"- Link de compra: JÁ ENVIADO em {_data(lead['checkout_enviado_em'], fuso)}. "
                      "Não envie de novo, a menos que o lead peça o link explicitamente.")
    else:
        linhas.append("- Link de compra: ainda não enviado.")
    if extra:
        linhas.append(f"\n{extra}")
    return "\n".join(linhas)
