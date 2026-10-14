"""Converse com o agente no terminal, como se você fosse um lead. Nada vai para o WhatsApp.

    docker compose exec agente python -m scripts.simular
    (ou, fora do Docker: python -m scripts.simular)

Usa a IA de verdade e o seu config/negocio.md, então é o melhor jeito de testar o
prompt antes de colocar no ar. Comandos: /ficha, /reiniciar, /sair.
"""

import asyncio
import tempfile
from pathlib import Path

from app.agente import Agente
from app.canais.base import MensagemRecebida
from app.config import Config, carregar_arquivo_env
from app.db import Banco
from app.ia.fabrica import criar_ia

TELEFONE = "5500000000001"
CINZA, VERDE, AMARELO, FIM = "\033[90m", "\033[92m", "\033[93m", "\033[0m"


class CanalTerminal:
    nome = "terminal"

    async def enviar_texto(self, destino, texto, digitando_ms=0):
        if destino == TELEFONE:
            print(f"{VERDE}Agente:{FIM} {texto}")
        else:
            print(f"{AMARELO}[aviso para o dono]{FIM} {texto}")
        return None

    async def marcar_lida(self, msg):
        pass

    async def baixar_audio(self, msg):
        return None


def novo_agente(cfg: Config) -> Agente:
    return Agente(cfg, Banco(":memory:"), CanalTerminal(), criar_ia(cfg))


async def principal() -> None:
    carregar_arquivo_env()
    cfg = Config.do_ambiente()
    cfg.debounce_segundos = 0
    cfg.modo_atendimento = "todos"
    cfg.pasta_dados = Path(tempfile.mkdtemp())
    if cfg.dono_telefone == TELEFONE:
        cfg.dono_telefone = ""
    faltando = [p for p in cfg.problemas() if "EVOLUTION" not in p and "META" not in p]
    if faltando:
        print("Antes de simular, resolva:\n- " + "\n- ".join(faltando))
        return

    agente = novo_agente(cfg)
    print(f"{CINZA}Simulador — IA {cfg.ia_provedor}/{cfg.ia_modelo}. Você é o lead. "
          f"Comandos: /ficha /reiniciar /sair{FIM}\n")
    contador = 0
    while True:
        try:
            texto = await asyncio.to_thread(input, "Você: ")
        except (EOFError, KeyboardInterrupt):
            break
        texto = texto.strip()
        if not texto:
            continue
        if texto == "/sair":
            break
        if texto == "/reiniciar":
            agente = novo_agente(cfg)
            print(f"{CINZA}Conversa zerada.{FIM}")
            continue
        if texto == "/ficha":
            lead = agente.banco.lead(TELEFONE) or {}
            campos = ("status", "necessidade", "autoridade", "orcamento", "prazo", "temperatura", "resumo",
                      "checkout_enviado_em", "pausado_ate")
            print(CINZA + "\n".join(f"  {c}: {lead.get(c)}" for c in campos) + FIM)
            continue
        contador += 1
        await agente.receber(MensagemRecebida(id=f"sim-{contador}", telefone=TELEFONE, destino=TELEFONE,
                                              nome="Lead de Teste", texto=texto))
        await agente.aguardar_tarefas()
        if agente._pausado(agente.banco.lead(TELEFONE) or {}):
            print(f"{CINZA}(robô pausado — um humano assumiria aqui. Use /reiniciar para recomeçar.){FIM}")


if __name__ == "__main__":
    asyncio.run(principal())
