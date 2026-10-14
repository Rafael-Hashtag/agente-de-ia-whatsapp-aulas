"""Diagnóstico rápido: configuração, IA respondendo e WhatsApp conectado.

    docker compose exec agente python -m scripts.checar
"""

import asyncio
import sys

import httpx

from app.config import Config, carregar_arquivo_env
from app.ia.fabrica import criar_ia
from app.prompts import montar_sistema


async def testar_ia(cfg: Config) -> str:
    ia = criar_ia(cfg)

    async def nada(nome, args):
        return "ok"

    resposta = await ia.conversar("Responda apenas: tudo certo.", "", [{"papel": "user", "texto": "teste"}],
                                  [], nada)
    return resposta.texto


def main() -> int:
    carregar_arquivo_env()
    cfg = Config.do_ambiente()
    ok = True

    print("Configuração:")
    for problema in cfg.problemas():
        print(f"  ❌ {problema}")
        ok = False
    if ok:
        print("  ✅ .env completo")

    try:
        montar_sistema(cfg.pasta_config)
        print("  ✅ config/negocio.md encontrado")
    except FileNotFoundError as erro:
        print(f"  ❌ {erro}")
        ok = False

    print(f"IA ({cfg.ia_provedor}/{cfg.ia_modelo}):")
    try:
        print(f"  ✅ respondeu: {asyncio.run(testar_ia(cfg))[:80]!r}")
    except Exception as erro:
        print(f"  ❌ {erro}")
        ok = False

    if cfg.canal == "evolution":
        print("WhatsApp (Evolution GO):")
        try:
            resp = httpx.get(f"{cfg.evolution_url}/instance/status",
                             headers={"apikey": cfg.evolution_token_instancia}, timeout=10)
            if resp.status_code == 503:
                print("  ❌ Evolution GO sem licença ativada (rode scripts.conectar_whatsapp para ver como ativar)")
                ok = False
            else:
                dados = resp.json().get("data") or {}
                if dados.get("LoggedIn"):
                    print("  ✅ conectado")
                else:
                    print("  ❌ não conectado — rode: docker compose exec agente python -m scripts.conectar_whatsapp")
                    ok = False
        except (httpx.HTTPError, ValueError) as erro:
            print(f"  ❌ Evolution GO não respondeu ({erro})")
            ok = False

    print("\nTudo certo! ✅" if ok else "\nCorrija os itens com ❌ e rode de novo.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
