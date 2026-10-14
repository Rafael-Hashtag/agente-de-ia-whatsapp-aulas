# Problemas comuns

Comece sempre por:

```bash
docker compose ps                                     # todos os serviços "running"/"healthy"?
docker compose exec agente python -m scripts.checar   # diagnóstico do agente
docker compose logs agente --tail 100                 # o que o agente fez por último
docker compose logs evolution-go --tail 100           # o que o Evolution GO fez por último
```

| Sintoma | Causa provável | Como resolver |
|---|---|---|
| `docker: command not found` | Docker não instalado | `curl -fsSL https://get.docker.com \| sh` |
| `docker compose` não existe, só `docker-compose` | Compose antigo (v1) | Instale o plugin v2: `apt-get install docker-compose-plugin` (repositório oficial do Docker) |
| `env file .env not found` | Configurador não rodou | `python3 scripts/configurar.py` |
| `conectar_whatsapp` fala de licença | Evolution GO ainda não ativado | Siga as instruções que o script mostra (túnel SSH + painel `/manager`). É uma vez só |
| QR Code torto ou ilegível | Fonte/zoom do terminal | Diminua o zoom (Ctrl -), use outro terminal, ou `--codigo 55DDDNUMERO` |
| `conectar_whatsapp`: "já existe com outro token" | O `.env` foi gerado de novo depois da primeira instalação | `docker compose exec agente python -m scripts.conectar_whatsapp --recriar` (vai pedir o QR de novo) |
| QR escaneado mas `checar` diz "não conectado" | Conexão caiu ou celular sem internet | Rode `scripts.conectar_whatsapp` de novo |
| Lead manda mensagem e nada acontece | Webhook não chega no agente | `docker compose logs agente` deve mostrar a mensagem. Se não mostrar, rode `scripts.conectar_whatsapp` (ele religa o webhook) |
| Nada acontece com `MODO_ATENDIMENTO=gatilho` | A mensagem não contém a `FRASE_GATILHO` | Confira a frase do link wa.me (maiúsculas e acentos não importam) |
| Dono recebe "⚠️ A IA falhou duas vezes" | Chave sem crédito, chave inválida ou modelo errado | `scripts.checar` mostra o erro do provedor. Corrija o `.env` e rode `docker compose up -d`. Depois `#retomar NUMERO` para cada lead pausado |
| `checar` diz que a chave não tem acesso ao modelo | Nome do modelo errado ou conta sem acesso | Rode o configurador de novo: ele lista os modelos disponíveis para a sua chave |
| O robô parou de responder um lead | Lead pausado (pediu humano, você respondeu pelo celular, ou falha da IA) | `#lead NUMERO` mostra se está pausado; `#retomar NUMERO` devolve ao robô |
| Áudio: "não pôde ser ouvido" | Transcrição desligada ou chave da Groq/OpenAI inválida | Configure `TRANSCRICAO_PROVEDOR` e a chave; `docker compose up -d` |
| Respostas inventam preço ou condição | Faltou informação no `config/negocio.md` | Complete o arquivo. As instruções mandam chamar humano quando a informação não existe; se ainda assim inventar, troque para um modelo mais capaz |
| Meta: "não foi possível validar a URL de callback" | HTTPS ainda não emitido ou token diferente | `curl https://SEU_DOMINIO/saude` deve funcionar; confira `META_VERIFY_TOKEN`. Portas 80 e 443 precisam estar liberadas no firewall da VPS |
| Meta: mensagens chegam mas o envio falha | Token temporário expirou ou falta permissão | Gere o token permanente do usuário do sistema (veja `docs/meta.md`) |
| Porta 80/443/4000/8000 ocupada | Outro serviço na VPS | Pare o outro serviço ou ajuste a porta no `docker-compose.yml` |

## Backup

Os leads e conversas ficam em `dados/agente.sqlite3`. A sessão do WhatsApp fica no volume
`evolution_dados`. Para backup do agente:

```bash
docker compose stop agente && cp dados/agente.sqlite3 ~/backup-agente-$(date +%F).sqlite3 && docker compose start agente
```
