#!/usr/bin/env python3
"""Configurador do agente: faz as perguntas e gera o arquivo .env.

Rode VOCÊ MESMO no terminal (não peça para uma IA rodar por você):
    python3 scripts/configurar.py

Ele pede suas chaves de API com o texto escondido e testa cada uma na hora.
Usa só a biblioteca padrão do Python, então funciona na VPS sem instalar nada.
"""

import getpass
import json
import secrets
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_ENV = RAIZ / ".env"

MODELOS = {
    "anthropic": [
        ("claude-opus-5-5", "Claude Opus 5.5 — o mais capaz (US$ 4 / US$ 20 por milhão de tokens)"),
        ("claude-sonnet-5-5", "Claude Sonnet 5.5 — equilíbrio (US$ 2 / US$ 10 por milhão de tokens)"),
        ("claude-haiku-5-5", "Claude Haiku 5.5 — o mais barato (US$ 0,10 / US$ 0,50 por milhão de tokens)"),
    ],
    "openai": [("gpt-5.4-mini", "GPT-5.4 mini")],
    "gemini": [("gemini-2.5-flash", "Gemini 2.5 Flash")],
}
ONDE_PEGAR_CHAVE = {
    "anthropic": "console.anthropic.com → Settings → API Keys (é crédito de API, não a assinatura do Claude)",
    "openai": "platform.openai.com → API keys",
    "gemini": "aistudio.google.com/apikey → Create API key",
    "groq": "console.groq.com/keys (tem uso gratuito)",
}


# ── entrada do usuário ────────────────────────────────────────────────────────

def perguntar(texto: str, padrao: str = "", obrigatorio: bool = True) -> str:
    sufixo = f" [{padrao}]" if padrao else ""
    while True:
        resposta = input(f"{texto}{sufixo}: ").strip() or padrao
        if resposta or not obrigatorio:
            return resposta
        print("  ↳ Preciso dessa informação para continuar.")


def segredo(texto: str, atual: str = "") -> str:
    dica = " (Enter mantém a atual)" if atual else ""
    while True:
        valor = getpass.getpass(f"{texto}{dica} — o texto fica escondido: ").strip() or atual
        if valor:
            return valor
        print("  ↳ Preciso dessa chave para continuar.")


def escolher(texto: str, opcoes: list[tuple[str, str]], padrao: str = "") -> str:
    print(f"\n{texto}")
    for i, (_, descricao) in enumerate(opcoes, 1):
        print(f"  {i}) {descricao}")
    valores = [v for v, _ in opcoes]
    indice_padrao = str(valores.index(padrao) + 1) if padrao in valores else "1"
    while True:
        resposta = input(f"Escolha [{indice_padrao}]: ").strip() or indice_padrao
        if resposta.isdigit() and 1 <= int(resposta) <= len(opcoes):
            return valores[int(resposta) - 1]
        print("  ↳ Digite o número de uma das opções.")


def so_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


# ── validação das chaves ──────────────────────────────────────────────────────

def listar_modelos(provedor: str, chave: str) -> list[str]:
    """Chama a rota de modelos do provedor: valida a chave sem gastar nada."""
    urls = {
        "anthropic": "https://api.anthropic.com/v1/models?limit=1000",
        "openai": "https://api.openai.com/v1/models",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "groq": "https://api.groq.com/openai/v1/models",
    }
    headers = {"x-api-key": chave, "anthropic-version": "2023-06-01"} if provedor == "anthropic" \
        else {"Authorization": f"Bearer {chave}"}
    pedido = urllib.request.Request(urls[provedor], headers=headers)
    with urllib.request.urlopen(pedido, timeout=20) as resposta:
        dados = json.loads(resposta.read())
    return [m.get("id", "").removeprefix("models/") for m in dados.get("data", [])]


def pedir_chave(provedor: str, atual: str) -> tuple[str, list[str]]:
    print(f"\nOnde pegar: {ONDE_PEGAR_CHAVE[provedor]}")
    while True:
        chave = segredo(f"Chave da API ({provedor})", atual)
        try:
            modelos = listar_modelos(provedor, chave)
            print(f"  ✅ Chave válida (final ...{chave[-4:]}).")
            return chave, modelos
        except urllib.error.HTTPError as erro:
            print(f"  ❌ O provedor recusou a chave (HTTP {erro.code}). Confira e cole de novo.")
        except (urllib.error.URLError, TimeoutError) as erro:
            print(f"  ⚠️  Não consegui testar agora ({erro}). Vou aceitar a chave sem testar.")
            return chave, []
        atual = ""


def escolher_modelo(provedor: str, disponiveis: list[str], atual: str) -> str:
    opcoes = list(MODELOS[provedor]) + [("outro", "Outro modelo (digitar o nome)")]
    modelo = escolher("Qual modelo de IA vai conversar com os leads?", opcoes, atual or opcoes[0][0])
    if modelo == "outro":
        modelo = perguntar("Nome exato do modelo", atual)
    while disponiveis and modelo not in disponiveis:
        parecidos = [m for m in disponiveis if modelo.split("-")[0] in m][:15]
        print(f"  ⚠️  Sua chave não tem acesso a '{modelo}'. Alguns disponíveis: {', '.join(parecidos or disponiveis[:15])}")
        modelo = perguntar("Nome do modelo")
    return modelo


# ── .env ──────────────────────────────────────────────────────────────────────

def ler_env() -> dict:
    valores = {}
    if ARQUIVO_ENV.exists():
        for linha in ARQUIVO_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip()
    return valores


def escrever_env(v: dict) -> None:
    secoes = [
        ("Docker: quais serviços sobem (evolution = WhatsApp por QR Code; https = Caddy com certificado)",
         ["COMPOSE_PROFILES", "DOMINIO", "FUSO"]),
        ("Canal de WhatsApp", ["CANAL"]),
        ("IA que conversa com os leads", ["IA_PROVEDOR", "IA_MODELO", "IA_ESFORCO",
                                          "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]),
        ("Transcrição de áudio (openai | groq | nenhum)", ["TRANSCRICAO_PROVEDOR", "GROQ_API_KEY"]),
        ("Evolution GO (gerado automaticamente — não precisa mexer)",
         ["EVOLUTION_API_KEY_GLOBAL", "EVOLUTION_INSTANCIA", "EVOLUTION_TOKEN_INSTANCIA", "WEBHOOK_SEGREDO",
          "POSTGRES_SENHA", "EVOLUTION_EMAIL_LICENCA"]),
        ("API oficial da Meta", ["META_TOKEN", "META_PHONE_NUMBER_ID", "META_APP_SECRET", "META_VERIFY_TOKEN"]),
        ("Venda", ["LINK_CHECKOUT", "DONO_TELEFONE", "MODO_ATENDIMENTO", "FRASE_GATILHO", "NUMEROS_IGNORADOS"]),
        ("Follow-up automático", ["FOLLOWUP_ATIVO", "FOLLOWUP_HORAS", "FOLLOWUP_MAX", "HORARIO_INICIO", "HORARIO_FIM"]),
        ("Planilha de leads", ["SHEETS_WEBHOOK_URL", "PAINEL_TOKEN"]),
    ]
    usadas = set()
    linhas = ["# Gerado por scripts/configurar.py. Pode editar à mão; depois rode: docker compose up -d", ""]
    for titulo, chaves in secoes:
        linhas.append(f"# {titulo}")
        for chave in chaves:
            linhas.append(f"{chave}={v.get(chave, '')}")
            usadas.add(chave)
        linhas.append("")
    extras = [k for k in v if k not in usadas]
    if extras:
        linhas.append("# Outros ajustes")
        linhas += [f"{k}={v[k]}" for k in extras]
    ARQUIVO_ENV.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    try:
        ARQUIVO_ENV.chmod(0o600)  # só o seu usuário lê o arquivo com as chaves
    except OSError:
        pass


# ── fluxo ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 64)
    print("  Configurador do Agente de Vendas no WhatsApp")
    print("=" * 64)
    v = ler_env()
    if v:
        print("Encontrei um .env existente: os valores atuais aparecem entre [colchetes].")

    v["CANAL"] = escolher("Como o agente vai se conectar ao WhatsApp?", [
        ("evolution", "Evolution GO — conecta qualquer número por QR Code (gratuito, não oficial)"),
        ("meta", "API oficial da Meta — sem risco de bloqueio, exige conta Business verificada"),
    ], v.get("CANAL", "evolution"))

    v["IA_PROVEDOR"] = escolher("Qual empresa de IA vai responder os leads?", [
        ("anthropic", "Anthropic (Claude)"), ("openai", "OpenAI (GPT)"), ("gemini", "Google (Gemini)"),
    ], v.get("IA_PROVEDOR", "anthropic"))
    nome_chave = f"{v['IA_PROVEDOR'].upper()}_API_KEY"
    v[nome_chave], disponiveis = pedir_chave(v["IA_PROVEDOR"], v.get(nome_chave, ""))
    v["IA_MODELO"] = escolher_modelo(v["IA_PROVEDOR"], disponiveis, v.get("IA_MODELO", ""))
    v.setdefault("IA_ESFORCO", "low")

    print("\nÁudios: o agente pode transcrever os áudios que o lead manda.")
    if v["IA_PROVEDOR"] == "openai":
        v["TRANSCRICAO_PROVEDOR"] = "openai"
        print("  ✅ Vou usar a mesma chave da OpenAI para transcrever.")
    elif escolher("Quer transcrever áudios?", [("groq", "Sim, com a Groq (tem uso gratuito)"),
                                                ("nenhum", "Não — o agente pede para o lead escrever")],
                  v.get("TRANSCRICAO_PROVEDOR", "groq")) == "groq":
        v["TRANSCRICAO_PROVEDOR"] = "groq"
        v["GROQ_API_KEY"], _ = pedir_chave("groq", v.get("GROQ_API_KEY", ""))
    else:
        v["TRANSCRICAO_PROVEDOR"] = "nenhum"

    print()
    v["LINK_CHECKOUT"] = perguntar("Link de compra (checkout) do produto", v.get("LINK_CHECKOUT", ""))
    v["DONO_TELEFONE"] = so_digitos(perguntar(
        "Seu WhatsApp pessoal, com DDI e DDD (recebe os avisos e comandos; deve ser outro número)",
        v.get("DONO_TELEFONE", "")))
    v["MODO_ATENDIMENTO"] = escolher("Quem o agente deve atender?", [
        ("todos", "Todo mundo que mandar mensagem para o número (número dedicado a vendas)"),
        ("gatilho", "Só quem chegar com uma frase específica (ex.: vinda do link wa.me dos anúncios)"),
    ], v.get("MODO_ATENDIMENTO", "todos"))
    if v["MODO_ATENDIMENTO"] == "gatilho":
        v["FRASE_GATILHO"] = perguntar("Frase que o lead envia ao clicar no seu link", v.get("FRASE_GATILHO", ""))

    if v["CANAL"] == "evolution":
        v["COMPOSE_PROFILES"] = "evolution"
        v.setdefault("EVOLUTION_INSTANCIA", "agente-vendas")
        for chave in ("EVOLUTION_API_KEY_GLOBAL", "EVOLUTION_TOKEN_INSTANCIA", "WEBHOOK_SEGREDO", "POSTGRES_SENHA"):
            v[chave] = v.get(chave) or secrets.token_hex(24)
        v["EVOLUTION_EMAIL_LICENCA"] = perguntar(
            "E-mail para a licença do Evolution GO (opcional, reativa sozinho depois do 1º registro)",
            v.get("EVOLUTION_EMAIL_LICENCA", ""), obrigatorio=False)
    else:
        v["COMPOSE_PROFILES"] = "https"
        print("\nDados do app na Meta (passo a passo em docs/meta.md):")
        v["META_PHONE_NUMBER_ID"] = perguntar("Phone number ID", v.get("META_PHONE_NUMBER_ID", ""))
        v["META_TOKEN"] = segredo("Token de acesso permanente (usuário do sistema)", v.get("META_TOKEN", ""))
        v["META_APP_SECRET"] = segredo("App Secret (Configurações do app → Básico)", v.get("META_APP_SECRET", ""))
        v["META_VERIFY_TOKEN"] = v.get("META_VERIFY_TOKEN") or secrets.token_hex(16)

    if v["CANAL"] == "meta" or v.get("DOMINIO"):
        ip_ou_dominio = perguntar("Domínio apontado para a VPS, ou o IP dela (ex.: 203.0.113.10)",
                                  v.get("DOMINIO", ""))
        partes = ip_ou_dominio.split(".")
        eh_ip = len(partes) == 4 and all(p.isdigit() for p in partes)
        v["DOMINIO"] = f"{ip_ou_dominio.replace('.', '-')}.sslip.io" if eh_ip else ip_ou_dominio
        if v["CANAL"] == "evolution":
            v["COMPOSE_PROFILES"] = "evolution,https"  # com domínio, o Caddy sobe junto (CSV pela web)

    v["SHEETS_WEBHOOK_URL"] = perguntar(
        "URL do Google Sheets (opcional — veja docs/google-sheets.md; Enter para pular)",
        v.get("SHEETS_WEBHOOK_URL", ""), obrigatorio=False)
    v["PAINEL_TOKEN"] = v.get("PAINEL_TOKEN") or secrets.token_urlsafe(18)
    v.setdefault("FUSO", "America/Sao_Paulo")
    for chave, padrao in (("FOLLOWUP_ATIVO", "true"), ("FOLLOWUP_HORAS", "20"), ("FOLLOWUP_MAX", "2"),
                          ("HORARIO_INICIO", "9"), ("HORARIO_FIM", "20")):
        v.setdefault(chave, padrao)

    escrever_env(v)
    print(f"\n✅ Configuração salva em {ARQUIVO_ENV.name}.")

    negocio = RAIZ / "config" / "negocio.md"
    if not negocio.exists():
        shutil.copy(RAIZ / "config" / "negocio.exemplo.md", negocio)
        print("📝 Criei config/negocio.md a partir do exemplo. EDITE esse arquivo com o seu produto,")
        print("   preço, garantia, perguntas frequentes e objeções — é dele que a IA tira as respostas.")

    print("\nPróximos passos:")
    print("  1) docker compose up -d --build")
    if v["CANAL"] == "evolution":
        print("  2) docker compose exec agente python -m scripts.conectar_whatsapp")
    else:
        print(f"  2) Cadastre o webhook na Meta: https://{v['DOMINIO']}/webhook/meta")
        print(f"     Token de verificação: {v['META_VERIFY_TOKEN']}")
    print("  3) docker compose exec agente python -m scripts.simular   (conversa de teste no terminal)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Nada foi salvo.")
        sys.exit(1)
