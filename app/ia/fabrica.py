"""Monta o provedor de IA e o transcritor a partir da configuração."""

from app.config import Config
from app.ia.base import ProvedorIA
from app.ia.openai_compativel import URL_GEMINI, URL_OPENAI, OpenAICompativel
from app.ia.transcricao import Transcritor


def criar_ia(cfg: Config) -> ProvedorIA:
    if cfg.ia_provedor == "anthropic":
        from app.ia.claude import Claude
        return Claude(cfg.ia_modelo, cfg.anthropic_api_key, esforco=cfg.ia_esforco)
    if cfg.ia_provedor == "openai":
        # reasoning_effort só existe nos modelos de raciocínio (família gpt-5, o-series).
        esforco = cfg.ia_esforco if cfg.ia_modelo.startswith(("gpt-5", "o")) else ""
        return OpenAICompativel(URL_OPENAI, cfg.openai_api_key, cfg.ia_modelo, esforco=esforco)
    if cfg.ia_provedor == "gemini":
        return OpenAICompativel(URL_GEMINI, cfg.gemini_api_key, cfg.ia_modelo)
    raise ValueError(f"IA_PROVEDOR desconhecido: {cfg.ia_provedor}")


def criar_transcritor(cfg: Config) -> Transcritor | None:
    chave = {"openai": cfg.openai_api_key, "groq": cfg.groq_api_key}.get(cfg.transcricao_provedor)
    return Transcritor(cfg.transcricao_provedor, chave) if chave else None
