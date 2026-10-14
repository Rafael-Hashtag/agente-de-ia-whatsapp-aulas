"""Banco de dados local (SQLite) com leads, mensagens e controle de duplicidade.

Datas são guardadas como timestamp Unix (segundos), o que simplifica as contas
de "há quantas horas o lead não responde".
"""

import sqlite3
import time
from pathlib import Path

STATUS_ATIVOS = ("novo", "conversando", "qualificado", "checkout_enviado")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS leads (
    telefone TEXT PRIMARY KEY,
    destino TEXT NOT NULL,
    nome TEXT,
    status TEXT NOT NULL DEFAULT 'novo',
    criado_em INTEGER NOT NULL,
    atualizado_em INTEGER NOT NULL,
    ultima_msg_lead_em INTEGER,
    ultima_msg_bot_em INTEGER,
    pausado_ate INTEGER DEFAULT 0,
    checkout_enviado_em INTEGER,
    followups_enviados INTEGER DEFAULT 0,
    necessidade TEXT DEFAULT '',
    autoridade TEXT DEFAULT '',
    orcamento TEXT DEFAULT '',
    prazo TEXT DEFAULT '',
    temperatura TEXT DEFAULT '',
    resumo TEXT DEFAULT '',
    resultado TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telefone TEXT NOT NULL,
    papel TEXT NOT NULL,           -- user | assistant
    texto TEXT NOT NULL,
    criado_em INTEGER NOT NULL,
    respondida INTEGER DEFAULT 1   -- 0 = mensagem do lead ainda sem resposta
);
CREATE INDEX IF NOT EXISTS idx_mensagens_telefone ON mensagens(telefone, id);
CREATE TABLE IF NOT EXISTS eventos (
    id TEXT PRIMARY KEY,           -- id da mensagem no WhatsApp (evita processar duas vezes)
    criado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS enviados (
    id TEXT PRIMARY KEY,           -- id das mensagens que o próprio agente enviou
    telefone TEXT,
    texto TEXT,
    criado_em INTEGER NOT NULL
);
"""

CAMPOS_QUALIFICACAO = ("necessidade", "autoridade", "orcamento", "prazo", "temperatura", "resumo")


class Banco:
    def __init__(self, caminho: Path | str):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(caminho), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(ESQUEMA)
        self.con.commit()

    # ── Duplicidade ──────────────────────────────────────────────────────────

    def registrar_evento(self, msg_id: str) -> bool:
        """True se o id é novo. O webhook pode chegar repetido; só processamos uma vez."""
        if not msg_id:
            return True
        cur = self.con.execute(
            "INSERT OR IGNORE INTO eventos (id, criado_em) VALUES (?, ?)", (msg_id, int(time.time()))
        )
        self.con.commit()
        return cur.rowcount == 1

    def registrar_enviado(self, msg_id: str | None, telefone: str, texto: str) -> None:
        self.con.execute(
            "INSERT OR IGNORE INTO enviados (id, telefone, texto, criado_em) VALUES (?, ?, ?, ?)",
            (msg_id or f"sem-id-{time.time_ns()}", telefone, texto, int(time.time())),
        )
        self.con.commit()

    def foi_enviado_pelo_agente(self, msg_id: str, telefone: str, texto: str) -> bool:
        """Mensagem 'minha' que o próprio agente mandou (e não o dono pelo celular)?"""
        if msg_id and self.con.execute("SELECT 1 FROM enviados WHERE id = ?", (msg_id,)).fetchone():
            return True
        # O webhook às vezes chega antes de sabermos o id: comparamos o texto recente.
        recente = int(time.time()) - 120
        return bool(self.con.execute(
            "SELECT 1 FROM enviados WHERE telefone = ? AND texto = ? AND criado_em >= ?",
            (telefone, texto.strip(), recente),
        ).fetchone())

    # ── Leads ────────────────────────────────────────────────────────────────

    def lead(self, telefone: str) -> dict | None:
        row = self.con.execute("SELECT * FROM leads WHERE telefone = ?", (telefone,)).fetchone()
        return dict(row) if row else None

    def criar_lead(self, telefone: str, destino: str, nome: str) -> dict:
        agora = int(time.time())
        self.con.execute(
            "INSERT OR IGNORE INTO leads (telefone, destino, nome, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?)",
            (telefone, destino, nome, agora, agora),
        )
        self.con.commit()
        return self.lead(telefone)

    def atualizar_lead(self, telefone: str, **campos) -> None:
        if not campos:
            return
        campos["atualizado_em"] = int(time.time())
        colunas = ", ".join(f"{c} = ?" for c in campos)
        self.con.execute(f"UPDATE leads SET {colunas} WHERE telefone = ?", (*campos.values(), telefone))
        self.con.commit()

    def buscar_lead_por_final(self, numero: str) -> list[dict]:
        """Acha leads pelos últimos 8 dígitos (o WhatsApp às vezes omite o 9 do celular)."""
        final = numero[-8:]
        if len(final) < 8:
            return []
        rows = self.con.execute("SELECT * FROM leads WHERE telefone LIKE ?", (f"%{final}",)).fetchall()
        return [dict(r) for r in rows]

    def todos_leads(self) -> list[dict]:
        return [dict(r) for r in self.con.execute("SELECT * FROM leads ORDER BY atualizado_em DESC")]

    def leads_para_followup(self, agora: int, horas: int, maximo: int) -> list[dict]:
        """Leads ativos em que o agente falou por último e o lead sumiu há `horas`."""
        limite = agora - horas * 3600
        rows = self.con.execute(
            f"""
            SELECT * FROM leads
            WHERE status IN ({",".join("?" * len(STATUS_ATIVOS))})
              AND resultado = ''
              AND COALESCE(pausado_ate, 0) < ?
              AND followups_enviados < ?
              AND ultima_msg_bot_em IS NOT NULL
              AND ultima_msg_bot_em >= COALESCE(ultima_msg_lead_em, 0)
              AND ultima_msg_bot_em <= ?
            """,
            (*STATUS_ATIVOS, agora, maximo, limite),
        ).fetchall()
        return [dict(r) for r in rows]

    def contagem_por_status(self) -> dict[str, int]:
        rows = self.con.execute("SELECT status, COUNT(*) AS n FROM leads GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}

    # ── Mensagens ────────────────────────────────────────────────────────────

    def salvar_mensagem(self, telefone: str, papel: str, texto: str, respondida: bool = True) -> int:
        agora = int(time.time())
        cur = self.con.execute(
            "INSERT INTO mensagens (telefone, papel, texto, criado_em, respondida) VALUES (?, ?, ?, ?, ?)",
            (telefone, papel, texto, agora, 1 if respondida else 0),
        )
        coluna = "ultima_msg_lead_em" if papel == "user" else "ultima_msg_bot_em"
        self.con.execute(f"UPDATE leads SET {coluna} = ?, atualizado_em = ? WHERE telefone = ?", (agora, agora, telefone))
        if papel == "user":
            # Lead respondeu: zera a contagem de follow-ups.
            self.con.execute("UPDATE leads SET followups_enviados = 0 WHERE telefone = ?", (telefone,))
        self.con.commit()
        return cur.lastrowid

    def pendentes(self, telefone: str) -> list[dict]:
        rows = self.con.execute(
            "SELECT * FROM mensagens WHERE telefone = ? AND papel = 'user' AND respondida = 0 ORDER BY id",
            (telefone,),
        ).fetchall()
        return [dict(r) for r in rows]

    def marcar_respondidas(self, telefone: str, ate_id: int) -> None:
        self.con.execute(
            "UPDATE mensagens SET respondida = 1 WHERE telefone = ? AND id <= ? AND papel = 'user'",
            (telefone, ate_id),
        )
        self.con.commit()

    def telefones_com_pendentes(self, desde: int) -> list[str]:
        rows = self.con.execute(
            "SELECT DISTINCT telefone FROM mensagens WHERE respondida = 0 AND papel = 'user' AND criado_em >= ?",
            (desde,),
        ).fetchall()
        return [r["telefone"] for r in rows]

    def historico(self, telefone: str, limite: int) -> list[dict]:
        """Últimas mensagens em ordem cronológica, já no formato papel/texto."""
        rows = self.con.execute(
            "SELECT papel, texto FROM mensagens WHERE telefone = ? ORDER BY id DESC LIMIT ?",
            (telefone, limite),
        ).fetchall()
        return [{"papel": r["papel"], "texto": r["texto"]} for r in reversed(rows)]

    def historico_para_ia(self, telefone: str, limite: int) -> list[dict]:
        """Como `historico`, mas com as mensagens do lead ainda sem resposta no fim.

        Se o lead escreve enquanto a IA está gerando, a mensagem nova fica gravada antes da
        resposta do robô. Sem esta reordenação, a conversa enviada à IA terminaria numa fala
        do próprio robô, e ela não responderia a mensagem nova.
        """
        rows = self.con.execute(
            """
            SELECT papel, texto FROM (
                SELECT id, papel, texto, respondida FROM mensagens WHERE telefone = ? ORDER BY id DESC LIMIT ?
            ) ORDER BY (papel = 'user' AND respondida = 0), id
            """,
            (telefone, limite),
        ).fetchall()
        return [{"papel": r["papel"], "texto": r["texto"]} for r in rows]
