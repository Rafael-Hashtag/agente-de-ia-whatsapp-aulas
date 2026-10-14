"""Configuração do agente.

Tudo que é segredo ou ajuste técnico vem do arquivo .env (o docker compose
injeta como variável de ambiente). O conteúdo do negócio — produto, preço,
objeções, tom de voz — fica em config/*.md, que você edita sem mexer em código.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def carregar_arquivo_env(caminho: Path = RAIZ / ".env") -> None:
    """Para rodar os scripts fora do Docker: lê o .env sem sobrescrever o que já existe."""
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


def so_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def _texto(nome: str, padrao: str = "") -> str:
    # "CHAVE=" vazio no .env conta como não preenchido e cai no padrão.
    return (os.getenv(nome) or "").strip() or padrao


def _int(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, padrao))
    except ValueError:
        return padrao


def _bool(nome: str, padrao: bool) -> bool:
    valor = os.getenv(nome)
    if valor is None or not valor.strip():
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "s", "yes")


def _telefones(nome: str) -> list[str]:
    return [so_digitos(n) for n in re.split(r"[,;\s]+", os.getenv(nome, "")) if so_digitos(n)]


@dataclass
class Config:
    # Canal de WhatsApp: "evolution" (Evolution GO, QR Code) ou "meta" (API oficial)
    canal: str = "evolution"

    # IA que conversa com os leads
    ia_provedor: str = "anthropic"  # anthropic | openai | gemini
    ia_modelo: str = "claude-opus-5-5"
    ia_esforco: str = "low"  # quanto a IA "pensa" antes de responder: low | medium | high
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""

    # Transcrição de áudio
    transcricao_provedor: str = "nenhum"  # openai | groq | nenhum
    groq_api_key: str = ""

    # Evolution GO
    evolution_url: str = "http://evolution-go:4000"
    evolution_api_key_global: str = ""
    evolution_instancia: str = "agente-vendas"
    evolution_token_instancia: str = ""
    webhook_segredo: str = ""
    url_interna_agente: str = "http://agente:8000"

    # API oficial da Meta
    meta_token: str = ""
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""
    meta_app_secret: str = ""
    meta_api_versao: str = "v23.0"

    # Comportamento
    dono_telefone: str = ""
    numeros_ignorados: list[str] = field(default_factory=list)
    modo_atendimento: str = "todos"  # todos | gatilho
    frase_gatilho: str = ""
    link_checkout: str = ""
    debounce_segundos: int = 8
    historico_max_mensagens: int = 40
    pausa_humano_horas: int = 12
    atraso_maximo_minutos: int = 30

    # Follow-up
    followup_ativo: bool = True
    followup_horas: int = 20
    followup_max: int = 2
    horario_inicio: int = 9
    horario_fim: int = 20
    fuso: str = "America/Sao_Paulo"

    # Planilha / painel
    sheets_webhook_url: str = ""
    painel_token: str = ""

    # Pastas
    pasta_config: Path = RAIZ / "config"
    pasta_dados: Path = RAIZ / "dados"

    @classmethod
    def do_ambiente(cls) -> "Config":
        return cls(
            canal=_texto("CANAL", "evolution").lower(),
            ia_provedor=_texto("IA_PROVEDOR", "anthropic").lower(),
            ia_modelo=_texto("IA_MODELO", "claude-opus-5-5"),
            ia_esforco=_texto("IA_ESFORCO", "low").lower(),
            anthropic_api_key=_texto("ANTHROPIC_API_KEY"),
            openai_api_key=_texto("OPENAI_API_KEY"),
            gemini_api_key=_texto("GEMINI_API_KEY"),
            transcricao_provedor=_texto("TRANSCRICAO_PROVEDOR", "nenhum").lower(),
            groq_api_key=_texto("GROQ_API_KEY"),
            evolution_url=_texto("EVOLUTION_URL", "http://evolution-go:4000").rstrip("/"),
            evolution_api_key_global=_texto("EVOLUTION_API_KEY_GLOBAL"),
            evolution_instancia=_texto("EVOLUTION_INSTANCIA", "agente-vendas"),
            evolution_token_instancia=_texto("EVOLUTION_TOKEN_INSTANCIA"),
            webhook_segredo=_texto("WEBHOOK_SEGREDO"),
            url_interna_agente=_texto("URL_INTERNA_AGENTE", "http://agente:8000").rstrip("/"),
            meta_token=_texto("META_TOKEN"),
            meta_phone_number_id=_texto("META_PHONE_NUMBER_ID"),
            meta_verify_token=_texto("META_VERIFY_TOKEN"),
            meta_app_secret=_texto("META_APP_SECRET"),
            meta_api_versao=_texto("META_API_VERSAO", "v23.0"),
            dono_telefone=so_digitos(_texto("DONO_TELEFONE")),
            numeros_ignorados=_telefones("NUMEROS_IGNORADOS"),
            modo_atendimento=_texto("MODO_ATENDIMENTO", "todos").lower(),
            frase_gatilho=_texto("FRASE_GATILHO"),
            link_checkout=_texto("LINK_CHECKOUT"),
            debounce_segundos=_int("DEBOUNCE_SEGUNDOS", 8),
            historico_max_mensagens=_int("HISTORICO_MAX_MENSAGENS", 40),
            pausa_humano_horas=_int("PAUSA_HUMANO_HORAS", 12),
            atraso_maximo_minutos=_int("ATRASO_MAXIMO_MINUTOS", 30),
            followup_ativo=_bool("FOLLOWUP_ATIVO", True),
            followup_horas=_int("FOLLOWUP_HORAS", 20),
            followup_max=_int("FOLLOWUP_MAX", 2),
            horario_inicio=_int("HORARIO_INICIO", 9),
            horario_fim=_int("HORARIO_FIM", 20),
            fuso=_texto("FUSO", "America/Sao_Paulo"),
            sheets_webhook_url=_texto("SHEETS_WEBHOOK_URL"),
            painel_token=_texto("PAINEL_TOKEN"),
            pasta_config=Path(_texto("PASTA_CONFIG") or RAIZ / "config"),
            pasta_dados=Path(_texto("PASTA_DADOS") or RAIZ / "dados"),
        )

    def problemas(self) -> list[str]:
        """Lista o que está faltando para o agente funcionar."""
        erros = []
        if self.canal not in ("evolution", "meta"):
            erros.append("CANAL deve ser 'evolution' ou 'meta'.")
        chave = {"anthropic": self.anthropic_api_key, "openai": self.openai_api_key,
                 "gemini": self.gemini_api_key}.get(self.ia_provedor)
        if chave is None:
            erros.append("IA_PROVEDOR deve ser 'anthropic', 'openai' ou 'gemini'.")
        elif not chave:
            erros.append(f"Falta a chave da IA ({self.ia_provedor.upper()}_API_KEY).")
        if self.canal == "evolution" and not (self.evolution_token_instancia and self.webhook_segredo):
            erros.append("Faltam EVOLUTION_TOKEN_INSTANCIA e WEBHOOK_SEGREDO (rode scripts/configurar.py).")
        if self.canal == "meta" and not (self.meta_token and self.meta_phone_number_id and self.meta_verify_token
                                         and self.meta_app_secret):
            erros.append("Faltam META_TOKEN, META_PHONE_NUMBER_ID, META_VERIFY_TOKEN e META_APP_SECRET.")
        if self.modo_atendimento == "gatilho" and not self.frase_gatilho:
            erros.append("MODO_ATENDIMENTO=gatilho exige FRASE_GATILHO.")
        if not self.link_checkout:
            erros.append("Falta LINK_CHECKOUT.")
        return erros
