# Agente de Vendas no WhatsApp

Um vendedor com IA que atende seus leads no WhatsApp 24 horas por dia: entende o que a
pessoa precisa, responde dúvidas e objeções com as informações do **seu** produto, qualifica
o lead (BANT) e envia o link de compra na hora certa. Quando o assunto foge do que ele sabe,
passa a conversa para você.

## O que ele faz

| | |
|---|---|
| 💬 **Conversa de verdade** | Mantém o contexto da conversa inteira, não só da primeira mensagem |
| ⏳ **Espera o lead terminar de digitar** | Junta "oi" + "tudo bem?" + "queria saber do curso" numa resposta só |
| ✍️ **Parece gente** | Mostra "digitando...", quebra respostas longas em mensagens curtas |
| 🎙️ **Entende áudio** | Transcreve os áudios do lead (OpenAI ou Groq) |
| 🔗 **Link de compra na hora certa** | A IA decide quando o lead está pronto, e o link sai uma vez só |
| 🙋 **Passa para humano** | Se o lead pedir uma pessoa, reclamar ou perguntar algo fora do roteiro, o robô pausa e te avisa no seu WhatsApp |
| 🤝 **Você assume quando quiser** | Respondeu um lead pelo celular? O robô sai da conversa sozinho |
| 🔁 **Follow-up** | Retoma leads que sumiram (até 2 vezes, só em horário comercial) |
| 📊 **Planilha de leads** | Ficha de cada lead (necessidade, decisor, orçamento, prazo, temperatura) em CSV ou Google Sheets |
| 🛡️ **Nunca manda erro para o cliente** | Se a IA cair, tenta de novo; se não der, manda uma mensagem de espera e te avisa |

Funciona com **Evolution GO** (conecta qualquer número por QR Code) ou com a **API oficial da
Meta**, e com IA da **Anthropic (Claude)**, **OpenAI** ou **Google (Gemini)**.

## Como funciona

```
Lead manda mensagem
      │
      ▼
WhatsApp ──► Evolution GO  ou  API da Meta ──webhook──► Agente (este projeto)
                                                          │  espera o lead terminar
                                                          │  lê a ficha + histórico
                                                          │  IA responde e usa ferramentas:
                                                          │   • registrar_qualificacao
                                                          │   • enviar_link_checkout
                                                          │   • chamar_humano
                                                          │   • encerrar_conversa
                                                          ▼
                                   resposta em partes curtas, com "digitando..."
```

Tudo roda em containers Docker numa VPS: o agente, o Evolution GO com o banco dele, e
(para a API da Meta) o Caddy, que cuida do HTTPS.

## Do que você precisa

- **Uma VPS** com Ubuntu 22.04 ou 24.04 e pelo menos 2 GB de RAM (Hostinger, Contabo, DigitalOcean, Hetzner...).
- **Uma chave de API** da Anthropic, da OpenAI ou do Google AI Studio. É crédito de API, separado
  de assinaturas como Claude Pro ou ChatGPT Plus.
- **Um número de WhatsApp dedicado às vendas.** Não use seu número pessoal: o robô responde
  quem mandar mensagem para ele.
- **Seu WhatsApp pessoal** (outro número), para receber os avisos e mandar comandos.

## Instalação

### Com uma IA te guiando (recomendado)

Na VPS, dentro da pasta do projeto, abra o Claude Code (ou o Codex) e digite `INICIAR SETUP`.
A IA conduz cada passo, explica o que está acontecendo e te ajuda a escrever o arquivo do
seu produto. As chaves de API você digita direto no configurador, nunca no chat.

### Na mão (5 comandos)

```bash
git clone https://github.com/Rafael-Hashtag/agente-de-ia-whatsapp-aulas.git
cd agente-de-ia-whatsapp-aulas
bash instalar.sh
```

O `instalar.sh` instala o Docker se faltar, roda o configurador (que faz as perguntas e testa
suas chaves) e sobe tudo. Depois:

```bash
nano config/negocio.md                                          # descreva seu produto
docker compose exec agente python -m scripts.simular            # converse com o agente no terminal
docker compose exec agente python -m scripts.conectar_whatsapp  # conecte o número (QR Code)
docker compose exec agente python -m scripts.checar             # confere se está tudo certo
```

**Primeira vez com Evolution GO:** ele pede uma ativação de licença única, pelo painel web
dele. O `conectar_whatsapp` detecta isso e mostra o passo a passo.

**API oficial da Meta:** veja [docs/meta.md](docs/meta.md).

## Ensinando o agente sobre o seu produto

Tudo que a IA sabe sobre o negócio está em **`config/negocio.md`**: produto, preço, formas de
pagamento, garantia, bônus, perguntas frequentes, objeções e quando chamar um humano. Use o
[exemplo](config/negocio.exemplo.md) como modelo.

- Editou? Vale na próxima mensagem, sem reiniciar nada.
- O que não estiver nesse arquivo, a IA não inventa: ela chama você.
- Teste cada mudança no simulador (`scripts.simular`) antes de deixar os leads verem.

As regras gerais de comportamento (tom de WhatsApp, método BANT, quando mandar o link) ficam
em [config/instrucoes.md](config/instrucoes.md). Você pode ajustar, mas raramente precisa.

## No dia a dia

**Comandos** — mande do seu WhatsApp pessoal (`DONO_TELEFONE`) para o número do agente:

| Comando | O que faz |
|---|---|
| `#status` | Quantos leads em cada etapa e quantos estão com humano |
| `#lead 11999999999` | Ficha do lead |
| `#pausar 11999999999` | O robô para de responder esse lead |
| `#retomar 11999999999` | O robô volta (e responde o que ficou pendente) |
| `#comprou 11999999999` | Registra a venda e encerra os follow-ups |

Mensagens suas **sem** `#` são ignoradas: o robô nunca tenta vender para você. Para testar o
atendimento como cliente, use o simulador ou mande mensagem de um terceiro número.

**Assumir uma conversa:** com Evolution GO, basta responder o lead pelo WhatsApp do número
de vendas (celular ou WhatsApp Web). O robô fica quieto naquela conversa por 12 horas
(`PAUSA_HUMANO_HORAS`). Conversas que **você** começa nunca são assumidas pelo robô.

**Planilha:** `https://SEU_DOMINIO/leads.csv?token=SEU_PAINEL_TOKEN` baixa todos os leads
(o token está no `.env`). Para uma planilha do Google atualizada sozinha, veja
[docs/google-sheets.md](docs/google-sheets.md). Sem domínio configurado, use um túnel SSH:
`ssh -L 8000:localhost:8000 root@IP_DA_VPS` e abra `http://localhost:8000/leads.csv?token=...`.

**Atualizar:** `git pull && docker compose up -d --build`.

**Ver o que está acontecendo:** `docker compose logs -f agente`.

## Divulgando

Use um link que já abre a conversa com uma frase pronta:

```
https://wa.me/5511999999999?text=Quero%20saber%20mais%20sobre%20o%20curso
```

Se o número também recebe outros contatos, configure `MODO_ATENDIMENTO=gatilho` com essa
frase em `FRASE_GATILHO`: o robô só entra nas conversas que começam por ela.

## Custos

- **VPS**: a partir de uns R$ 30/mês.
- **IA**: depende do modelo e do volume. Numa estimativa grosseira, uma conversa de vendas de
  uns 20 turnos sai por volta de US$ 0,02 com o Claude Haiku 5.5 e de US$ 0,50 com o Opus 5.5
  (padrão, mais capaz). Teste a qualidade dos dois no simulador antes de escolher: troque
  `IA_MODELO` no `.env` e rode `docker compose up -d`.
- **Transcrição de áudio**: a Groq tem uso gratuito; na OpenAI são frações de centavo por minuto.
- **API oficial da Meta**: a Meta cobra por conversa iniciada pela empresa; responder o lead
  dentro de 24h costuma ser gratuito. Confira a tabela atual da Meta.

## Riscos e boas práticas

- O **Evolution GO** usa o WhatsApp Web, que **não é oficial**. Contas que mandam muitas
  mensagens não solicitadas podem ser banidas. Use para **responder** quem te procurou, não
  para disparar mensagens em massa. Se o volume crescer, migre para a API oficial (`CANAL=meta`).
- O agente guarda nome, telefone e conversas dos leads (`dados/agente.sqlite3`). Informe isso
  na sua política de privacidade (LGPD) e faça backup da pasta `dados/`.
- Quando o lead pede para parar, o agente encerra a conversa e não manda mais follow-up.

## Para desenvolvedores

```
app/
  main.py            servidor (webhooks, CSV, saúde)
  agente.py          regras do atendimento: fila, pausa, comandos, follow-up
  ferramentas.py     ferramentas que a IA pode usar
  prompts.py         monta o prompt (instruções + negócio + ficha do lead)
  db.py              SQLite
  canais/            evolution_go.py, meta.py
  ia/                claude.py (SDK da Anthropic), openai_compativel.py (OpenAI/Gemini), transcricao.py
scripts/             configurar, conectar_whatsapp, simular, checar
tests/               testes automatizados (sem WhatsApp nem IA de verdade)
```

```bash
pip install -r requirements-dev.txt
pytest
```

## Créditos

A conexão com o WhatsApp não oficial usa o [Evolution GO](https://github.com/evolution-foundation/evolution-go),
da Evolution Foundation (licença Apache 2.0 com condições adicionais — veja a licença do projeto).
