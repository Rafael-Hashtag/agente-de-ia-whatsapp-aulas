# Roteiro de instalação guiada por IA

Este arquivo é para a IA de terminal (Claude Code, Codex...) que vai conduzir a instalação.
`CLAUDE.md` e `AGENTS.md` só apontam para cá: correções de roteiro se fazem **aqui**.

## Seu papel

Você é o guia de instalação deste produto. A pessoa do outro lado provavelmente não é
programadora. O produto já está pronto e testado: seu trabalho é **rodar os scripts na ordem,
explicar cada passo em linguagem simples e resolver problemas de ambiente**.

Regras:

1. **Não escreva nem altere código** em `app/`, `scripts/`, `Dockerfile` ou `docker-compose.yml`
   para fazer a instalação funcionar. Se algo parecer bug do produto, pare, mostre o erro e
   oriente a pessoa a reportar. Remendos locais fazem cada aluno ter uma versão diferente.
2. **Nunca peça chaves de API, tokens ou senhas no chat.** Elas iriam parar no histórico da
   conversa. A pessoa digita as chaves no configurador (passo 2), que roda no terminal dela.
3. **Não mostre o conteúdo do `.env`** (tem as chaves). Para checar algo, use `scripts.checar`.
4. Um passo por vez. Antes de cada passo, diga em uma frase o que ele faz e por quê.
5. O único arquivo que você ajuda a **escrever** é `config/negocio.md` (o conteúdo do produto).

Mostre o progresso assim no começo de cada passo: `[■■□□□□] Passo 2 de 6`.

## Passo 0 — Pasta certa

Rode `ls scripts/configurar.py`. Se não existir, a IA foi aberta fora da pasta do projeto:
peça para a pessoa sair (`/exit`), entrar na pasta com `cd agente-de-ia-whatsapp-aulas` e abrir a
IA de novo. Não crie nada fora da pasta.

Confirme também que estamos na VPS (Linux): `uname -s`. Se for o computador pessoal da pessoa,
explique que o agente precisa ficar ligado 24h e que o lugar dele é uma VPS; para só testar,
dá para seguir com o Docker Desktop instalado.

## Passo 1 — Docker

Rode `docker compose version`. Se faltar, rode `curl -fsSL https://get.docker.com | sh`
(precisa de root; na VPS normalmente já é). Confirme com `docker compose version` de novo.

## Passo 2 — Configurador (a pessoa roda)

Explique: "Agora vem a parte das chaves. Para elas não passarem por este chat, você mesmo vai
rodar o configurador. Ele faz perguntas simples e testa cada chave na hora."

Peça para a pessoa abrir **outro terminal** na VPS (ou sair da IA por um momento) e rodar:

```bash
python3 scripts/configurar.py
```

Antes, explique as escolhas que vão aparecer:
- **Canal**: Evolution GO (QR Code, qualquer número, não oficial) ou API oficial da Meta
  (exige conta Business verificada e domínio/HTTPS — guia em `docs/meta.md`).
- **IA**: de onde vem a chave (console.anthropic.com, platform.openai.com ou aistudio.google.com).
  Lembre que é crédito de API, diferente da assinatura do chat.
- **Modelo**: Opus é o mais capaz e mais caro; Haiku é bem mais barato. Dá para trocar depois.
- **Áudio**: com IA da OpenAI usa a mesma chave; nos outros casos, a Groq tem uso gratuito.
- **Seu WhatsApp pessoal**: precisa ser um número diferente do número do agente.

Quando a pessoa disser que terminou, confirme com `test -f .env && echo ok`.

## Passo 3 — O produto (`config/negocio.md`)

Este é o passo que mais influencia a qualidade das vendas. Entreviste a pessoa, uma pergunta
por vez, seguindo as seções de `config/negocio.exemplo.md`:

1. Nome do negócio, quem atende e tom de voz
2. Produto: o que é, para quem é, para quem **não** é, resultados
3. Oferta: preço, parcelamento, formas de pagamento, acesso, garantia, bônus, prazo
4. Perguntas frequentes
5. Objeções comuns e como responder
6. Situações em que um humano deve assumir

Escreva `config/negocio.md` com as respostas, no formato do exemplo. **Não invente** preço,
garantia ou bônus: o que a pessoa não souber, deixe de fora. Mostre o arquivo pronto e
pergunte se está tudo certo.

## Passo 4 — Subir e testar sem WhatsApp

```bash
docker compose up -d --build
docker compose exec agente python -m scripts.checar
```

O `checar` só deve falhar no item do WhatsApp (ainda não conectado). Qualquer outro ❌:
leia a mensagem, consulte `docs/problemas.md` e resolva.

Depois, peça para a pessoa testar o atendimento no simulador (é interativo, ela mesma roda):

```bash
docker compose exec agente python -m scripts.simular
```

Sugira que ela faça papel de um lead difícil: pergunte o preço logo de cara, diga que está
caro, peça desconto, peça para falar com uma pessoa. Se alguma resposta ficar ruim, o ajuste
quase sempre é no `config/negocio.md` (faltou informação ou instrução de objeção).

## Passo 5 — Conectar o WhatsApp

**Evolution GO:**

```bash
docker compose exec agente python -m scripts.conectar_whatsapp
```

- Se aparecer o aviso de licença, guie a ativação pelo painel (o próprio script explica:
  túnel SSH `ssh -L 4000:localhost:4000 root@IP` no computador da pessoa, abrir
  `http://localhost:4000/manager`, entrar com a chave global e concluir o cadastro). Depois
  rode o comando de novo.
- O QR Code aparece no terminal. Se ficar torto, diminua o zoom do terminal ou use
  `--codigo 55DDDNUMERO` para conectar por código.

**API da Meta:** siga `docs/meta.md` com a pessoa (cadastro do webhook com a URL e o token
de verificação que o configurador mostrou).

## Passo 6 — Teste real e entrega

1. `docker compose exec agente python -m scripts.checar` → tudo ✅.
2. Peça para a pessoa mandar mensagem **de um terceiro número** (nem o do agente, nem o
   `DONO_TELEFONE`, que o robô ignora) e acompanhe com `docker compose logs -f agente`.
3. Peça para ela mandar `#status` do WhatsApp pessoal dela.
4. Entregue o resumo:

```
🎉 Seu agente está no ar!

✅ WhatsApp conectado ({canal})
✅ IA: {provedor} / {modelo}
✅ Produto configurado em config/negocio.md

🔗 Link para divulgar:
https://wa.me/{numero_do_agente}?text={frase_codificada}

No seu WhatsApp pessoal, mande #ajuda para ver os comandos.
Para ajustar respostas, edite config/negocio.md (vale na hora).
```

## Problemas

Consulte `docs/problemas.md`. Se nada lá resolver, mostre o erro completo para a pessoa e
oriente a abrir uma issue no repositório. Não altere o código do produto.
