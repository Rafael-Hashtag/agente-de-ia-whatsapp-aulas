# Usando a API oficial do WhatsApp (Meta)

A API oficial não corre risco de banimento por automação e é o caminho para volume alto.
Em troca, exige uma conta Business verificada, um endereço HTTPS público e segue as regras
de cobrança e de janela de 24 horas da Meta.

> As telas da Meta mudam com frequência. Os nomes abaixo podem variar um pouco; o que
> importa são os quatro dados que você precisa copiar.

## 1. Criar o app

1. Acesse [developers.facebook.com](https://developers.facebook.com) → **Meus apps** → **Criar app**.
2. Escolha o caso de uso de **WhatsApp** (ou tipo "Empresa") e vincule ao seu Business Manager.
3. No painel do app, abra **WhatsApp → Configuração da API**.
4. Adicione e verifique o número que será usado pelo agente. Ele não pode estar ativo no
   aplicativo WhatsApp comum ao mesmo tempo, a não ser que você use a modalidade de
   coexistência oferecida pela Meta.

## 2. Copiar os dados

| Dado | Onde fica | Vai para |
|---|---|---|
| **Phone number ID** | WhatsApp → Configuração da API (abaixo do número) | `META_PHONE_NUMBER_ID` |
| **Token permanente** | Business Manager → Usuários do sistema → crie um usuário admin → Gerar token, com as permissões `whatsapp_business_messaging` e `whatsapp_business_management` | `META_TOKEN` |
| **App Secret** | Configurações do app → Básico → Chave secreta do app | `META_APP_SECRET` |

O token temporário que aparece na tela de teste expira em 24 horas: use o do usuário do sistema.

Rode `python3 scripts/configurar.py`, escolha **API oficial da Meta** e cole esses dados.
Quando ele perguntar o domínio, informe o domínio apontado para a VPS ou, se não tiver um,
o **IP da VPS** — o configurador monta um endereço `IP.sslip.io` com HTTPS automático.

## 3. Subir e cadastrar o webhook

```bash
docker compose up -d --build
curl https://SEU_DOMINIO/saude      # deve responder {"ok": true, ...}
```

No painel do app: **WhatsApp → Configuração → Webhook → Editar**:

- **URL de callback:** `https://SEU_DOMINIO/webhook/meta`
- **Token de verificação:** o valor de `META_VERIFY_TOKEN` (o configurador mostrou no final;
  ou rode `grep META_VERIFY_TOKEN .env`)

Clique em **Verificar e salvar** e depois **assine o campo `messages`**.

## 4. Testar

Mande uma mensagem para o número e acompanhe: `docker compose logs -f agente`.

## Regras da Meta que afetam o agente

- **Janela de 24 horas:** a empresa só pode mandar mensagem livre até 24h depois da última
  mensagem do lead. Por isso o follow-up só sai dentro dessa janela (o primeiro, por padrão,
  20h depois). Mensagens fora da janela exigem template aprovado, o que este projeto ainda
  não faz.
- **Avisos para você:** os avisos de "chamar humano" chegam no seu `DONO_TELEFONE` pelo próprio
  número do agente, então também dependem da janela de 24h. Mande um `#status` para o número
  do agente de vez em quando (ou todo dia de manhã) para mantê-la aberta.
- **Assumir conversa:** com a API oficial, respostas que você dá por outro sistema não chegam
  ao agente. Use `#pausar NUMERO` antes de atender o lead por fora e `#retomar NUMERO` depois.
- **Custos:** a Meta cobra por conversa conforme a categoria e o país. Confira a tabela atual
  no site da Meta.
