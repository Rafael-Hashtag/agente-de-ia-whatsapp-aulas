# Planilha de leads no Google Sheets

O agente envia a ficha do lead a cada resposta. Um pequeno script dentro da planilha recebe
os dados e atualiza a linha daquele telefone (ou cria uma nova). Não precisa de conta de
serviço nem de configurar OAuth.

## Passo a passo

1. Crie uma planilha nova no Google Sheets.
2. Menu **Extensões → Apps Script**. Apague o que estiver lá e cole o código abaixo.
3. Clique em **Implantar → Nova implantação** → tipo **App da Web**:
   - Executar como: **Eu**
   - Quem pode acessar: **Qualquer pessoa**
4. Autorize o acesso quando o Google pedir e copie a **URL do app da Web**
   (termina em `/exec`).
5. Coloque essa URL em `SHEETS_WEBHOOK_URL` no `.env` (ou rode o configurador de novo) e
   aplique com `docker compose up -d`.

A partir daí, cada conversa atualiza a aba **Leads**.

```javascript
const ABA = 'Leads';

function doPost(e) {
  const dados = JSON.parse(e.postData.contents);
  const planilha = SpreadsheetApp.getActiveSpreadsheet();
  let aba = planilha.getSheetByName(ABA);
  if (!aba) {
    aba = planilha.insertSheet(ABA);
    aba.appendRow(Object.keys(dados));
    aba.getRange('A:A').setNumberFormat('@'); // telefone como texto
    aba.setFrozenRows(1);
  }
  const cabecalho = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0];
  const linha = cabecalho.map(coluna => dados[coluna] ?? '');
  const total = aba.getLastRow() - 1;
  const telefones = total > 0 ? aba.getRange(2, 1, total, 1).getValues().map(r => String(r[0])) : [];
  const posicao = telefones.indexOf(String(dados.telefone));
  if (posicao >= 0) {
    aba.getRange(posicao + 2, 1, 1, linha.length).setValues([linha]);
  } else {
    aba.appendRow(linha);
  }
  return ContentService.createTextOutput('ok');
}
```

## Observações

- Trate a URL `/exec` como senha: quem tiver a URL consegue escrever na planilha.
- Se você mudar o código do script, faça **Implantar → Gerenciar implantações → Editar →
  Nova versão**, ou a mudança não entra no ar.
- Prefere não usar o Google? Baixe o CSV a qualquer momento em
  `/leads.csv?token=SEU_PAINEL_TOKEN` (veja o README).
