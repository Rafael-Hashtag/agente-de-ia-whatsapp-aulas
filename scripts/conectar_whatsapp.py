"""Conecta o número de WhatsApp ao Evolution GO e liga o webhook do agente.

Rode dentro do container do agente:
    docker compose exec agente python -m scripts.conectar_whatsapp
    docker compose exec agente python -m scripts.conectar_whatsapp --codigo 5511999999999

Sem argumento, mostra um QR Code no terminal. Com --codigo, gera um código de
8 letras para digitar no celular (útil quando o QR não aparece bem no terminal).
"""

import argparse
import base64
import sys
import time

import httpx
import qrcode

from app.config import Config, so_digitos

TEMPO_LIMITE = 180  # segundos esperando o celular conectar


class Evolution:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = httpx.Client(base_url=cfg.evolution_url, timeout=30)

    def _pedir(self, metodo: str, rota: str, chave: str, **kw) -> dict:
        resp = self.http.request(metodo, rota, headers={"apikey": chave}, **kw)
        if resp.status_code == 503 and "LICENSE" in resp.text:
            raise LicencaPendente()
        resp.raise_for_status()
        return resp.json() if resp.content else {}

    def global_(self, metodo, rota, **kw):
        return self._pedir(metodo, rota, self.cfg.evolution_api_key_global, **kw)

    def instancia(self, metodo, rota, **kw):
        return self._pedir(metodo, rota, self.cfg.evolution_token_instancia, **kw)


class LicencaPendente(Exception):
    pass


def explicar_licenca(cfg: Config) -> None:
    print("""
🔑 O Evolution GO precisa ser ativado uma única vez, pelo painel dele.

  1) No SEU computador (não na VPS), abra um terminal e crie um túnel seguro:
       ssh -L 4000:localhost:4000 root@IP_DA_SUA_VPS
     (deixe esse terminal aberto)
  2) No navegador, abra:  http://localhost:4000/manager
  3) No login, use a URL  http://localhost:4000  e a chave global, que você vê na VPS com:
       grep EVOLUTION_API_KEY_GLOBAL .env
  4) Siga o cadastro da licença na tela.

Depois rode este comando de novo. Dica: preencha EVOLUTION_EMAIL_LICENCA no .env com o
e-mail usado no cadastro para o Evolution GO se reativar sozinho no futuro.""")


def mostrar_qr(dados: dict) -> None:
    codigo = dados.get("code")
    imagem = dados.get("qrcode", "")
    if imagem:
        try:
            caminho = Config.do_ambiente().pasta_dados / "qrcode.png"
            caminho.write_bytes(base64.b64decode(imagem.split(",")[-1]))
            print(f"(O QR também foi salvo em dados/{caminho.name}, caso prefira abrir a imagem.)")
        except (ValueError, OSError):
            pass
    if codigo:
        qr = qrcode.QRCode(border=2)
        qr.add_data(codigo)
        qr.print_ascii(invert=True)
    print("\n📱 No celular: WhatsApp → Configurações → Aparelhos conectados → Conectar um aparelho.")
    print("   Se o QR aparecer torto, diminua o zoom do terminal (Ctrl -) ou use --codigo SEU_NUMERO.\n")


def conectado(evo: Evolution) -> bool:
    dados = evo.instancia("GET", "/instance/status").get("data") or {}
    return bool(dados.get("LoggedIn") or dados.get("loggedIn") or dados.get("status") == "open")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codigo", metavar="NUMERO", help="conectar por código em vez de QR (número com DDI e DDD)")
    parser.add_argument("--recriar", action="store_true",
                        help="apaga a instância existente se o token não bater com o .env")
    args = parser.parse_args()

    cfg = Config.do_ambiente()
    if cfg.canal != "evolution":
        print("Este passo é só para o canal Evolution GO (CANAL=evolution no .env).")
        return 1
    evo = Evolution(cfg)

    print("1/4 Verificando o Evolution GO...")
    try:
        evo.http.get("/server/ok").raise_for_status()
    except httpx.HTTPError:
        print(f"❌ Não encontrei o Evolution GO em {cfg.evolution_url}. Ele está rodando?")
        print("   Veja com: docker compose ps   e   docker compose logs evolution-go --tail 50")
        return 1

    try:
        print("2/4 Preparando a instância...")
        existentes = evo.global_("GET", "/instance/all").get("data") or []
        atual = next((i for i in existentes if isinstance(i, dict) and i.get("name") == cfg.evolution_instancia), None)
        if atual and atual.get("token") and atual["token"] != cfg.evolution_token_instancia:
            # O .env foi gerado de novo, mas a instância antiga continua lá com o token anterior.
            if not args.recriar:
                print(f"❌ A instância '{cfg.evolution_instancia}' já existe com outro token (o .env foi recriado?).")
                print("   Rode de novo com --recriar para apagá-la e criar outra. Você vai precisar escanear o QR de novo.")
                return 1
            evo.global_("DELETE", f"/instance/delete/{atual['id']}")
            print("   🗑️  Instância antiga removida.")
            atual = None
        if not atual:
            evo.global_("POST", "/instance/create",
                        json={"name": cfg.evolution_instancia, "token": cfg.evolution_token_instancia})
            print(f"   ✅ Instância '{cfg.evolution_instancia}' criada.")

        print("3/4 Ligando o webhook do agente...")
        webhook = f"{cfg.url_interna_agente}/webhook/evolution/{cfg.webhook_segredo}"
        evo.instancia("POST", "/instance/connect", json={"webhookUrl": webhook, "subscribe": ["MESSAGE"]})

        if conectado(evo):
            print("✅ Este WhatsApp já está conectado e o webhook foi atualizado. Tudo pronto!")
            return 0

        print("4/4 Conectando o WhatsApp...")
        if args.codigo:
            dados = evo.instancia("POST", "/instance/pair", json={"phone": so_digitos(args.codigo)}).get("data") or {}
            codigo = dados.get("PairingCode") or dados.get("pairingCode")
            print(f"\n🔢 Código: {codigo}")
            print("📱 No celular: Aparelhos conectados → Conectar um aparelho → Conectar com número de telefone.\n")
        ultimo_qr, inicio = None, time.monotonic()
        while time.monotonic() - inicio < TEMPO_LIMITE:
            if conectado(evo):
                print("\n✅ WhatsApp conectado! Mande uma mensagem de outro número para testar.")
                return 0
            if not args.codigo:
                try:
                    dados = evo.instancia("GET", "/instance/qr").get("data") or {}
                except httpx.HTTPError:
                    dados = {}
                if dados.get("code") and dados.get("code") != ultimo_qr:
                    ultimo_qr = dados["code"]
                    mostrar_qr(dados)
            time.sleep(3)
    except LicencaPendente:
        explicar_licenca(cfg)
        return 1
    except httpx.HTTPStatusError as erro:
        print(f"❌ O Evolution GO respondeu {erro.response.status_code}: {erro.response.text[:300]}")
        return 1

    print("⌛ O tempo acabou sem conexão. Rode o comando de novo para gerar um QR novo.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
