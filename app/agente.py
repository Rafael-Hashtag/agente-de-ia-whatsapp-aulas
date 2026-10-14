"""O agente de vendas: decide quando e como responder cada lead.

Fluxo de uma mensagem:
  webhook -> receber() -> salva no banco -> espera alguns segundos (o lead costuma
  mandar várias mensagens picadas) -> responder() -> IA -> envia em partes curtas
  -> aplica o que a IA pediu (link de compra, chamar humano, ficha do lead).
"""

import asyncio
import logging
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.canais.base import Canal, MensagemRecebida
from app.config import Config, so_digitos
from app.db import CAMPOS_QUALIFICACAO, Banco
from app.ferramentas import FERRAMENTAS, Acoes
from app.ia.base import ProvedorIA
from app.planilha import Planilha
from app.prompts import montar_contexto, montar_sistema

log = logging.getLogger(__name__)

PAUSA_INDEFINIDA = 32503680000  # ano 3000: só volta com #retomar
MSG_AGUARDE = "Oi! Recebi sua mensagem 🙂 Já já alguém da equipe te responde por aqui."
MSG_HUMANO = "Vou chamar alguém da equipe para continuar com você por aqui. Só um instante! 🙂"
INSTRUCAO_FOLLOWUP = (
    "(Mensagem interna do sistema — não é o lead falando.) O lead não responde há cerca de {horas} horas. "
    "Escreva UMA mensagem curta de follow-up (máximo 2 frases), natural e sem pressão, retomando o ponto "
    "em que a conversa parou. Este é o follow-up número {numero} de {maximo}"
    "{ultimo}. Não repita mensagens anteriores e não envie link."
)
AJUDA_DONO = (
    "Comandos do agente:\n"
    "#status — resumo dos leads\n"
    "#lead 11999999999 — ficha de um lead\n"
    "#pausar 11999999999 — o robô para de responder esse lead\n"
    "#retomar 11999999999 — o robô volta a responder\n"
    "#comprou 11999999999 — marca venda e encerra os follow-ups"
)


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def mesmo_numero(a: str, b: str) -> bool:
    """Compara pelos últimos 8 dígitos (o WhatsApp às vezes omite o 9 dos celulares do Brasil)."""
    return bool(a and b) and so_digitos(a)[-8:] == so_digitos(b)[-8:]


def dividir_em_mensagens(texto: str, maximo: int = 3) -> list[str]:
    """Quebra a resposta nos parágrafos, como uma pessoa faria no WhatsApp."""
    partes = [p.strip() for p in re.split(r"\n\s*\n", texto.strip()) if p.strip()]
    while len(partes) > maximo:
        # junta os dois parágrafos vizinhos mais curtos
        i = min(range(len(partes) - 1), key=lambda k: len(partes[k]) + len(partes[k + 1]))
        partes[i:i + 2] = [partes[i] + "\n\n" + partes[i + 1]]
    return partes


def tempo_digitando_ms(texto: str) -> int:
    return min(1200 + len(texto) * 30, 8000)


class Agente:
    def __init__(self, cfg: Config, banco: Banco, canal: Canal, ia: ProvedorIA,
                 transcritor=None, planilha: Planilha | None = None):
        self.cfg = cfg
        self.banco = banco
        self.canal = canal
        self.ia = ia
        self.transcritor = transcritor
        self.planilha = planilha
        self._timers: dict[str, asyncio.Task] = {}
        self._travas: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._falhas: dict[str, int] = defaultdict(int)
        self._tarefas: set[asyncio.Task] = set()
        self.espera_nova_tentativa = 60  # segundos até tentar de novo quando a IA falha

    # ── utilidades ────────────────────────────────────────────────────────────

    def _rodar(self, coro) -> asyncio.Task:
        tarefa = asyncio.create_task(coro)
        self._tarefas.add(tarefa)
        tarefa.add_done_callback(self._tarefas.discard)
        return tarefa

    async def aguardar_tarefas(self) -> None:
        """Espera tudo que está em andamento (usado nos testes e no simulador)."""
        while self._tarefas or any(not t.done() for t in self._timers.values()):
            await asyncio.gather(*self._tarefas, *self._timers.values(), return_exceptions=True)
            await asyncio.sleep(0)

    def _pausado(self, lead: dict) -> bool:
        return (lead.get("pausado_ate") or 0) > time.time()

    def _eh_dono(self, telefone: str) -> bool:
        return mesmo_numero(telefone, self.cfg.dono_telefone)

    def _ignorado(self, telefone: str) -> bool:
        return any(mesmo_numero(telefone, n) for n in self.cfg.numeros_ignorados)

    async def _sincronizar(self, telefone: str) -> None:
        if self.planilha:
            await self.planilha.sincronizar(self.banco.lead(telefone))

    async def _avisar_dono(self, texto: str) -> None:
        if not self.cfg.dono_telefone:
            log.warning("Sem DONO_TELEFONE configurado. Aviso não enviado: %s", texto)
            return
        try:
            msg_id = await self.canal.enviar_texto(self.cfg.dono_telefone, texto)
            self.banco.registrar_enviado(msg_id, self.cfg.dono_telefone, texto)
        except Exception as erro:
            log.error("Não consegui avisar o dono (%s): %s", erro, texto)

    # ── entrada ───────────────────────────────────────────────────────────────

    async def receber(self, msg: MensagemRecebida) -> None:
        if not msg.telefone or not self.banco.registrar_evento(msg.id):
            return
        if msg.de_mim:
            await self._mensagem_do_proprio_numero(msg)
            return
        if self._eh_dono(msg.telefone):
            # O dono nunca vira lead: um "ok" em resposta a um aviso não pode virar conversa de venda.
            if msg.texto.startswith("#"):
                await self._comando_do_dono(msg)
            return
        if self._ignorado(msg.telefone):
            return
        atraso = time.time() - msg.timestamp
        if atraso > self.cfg.atraso_maximo_minutos * 60:
            log.info("Ignorando mensagem antiga de %s (%.0f min de atraso).", msg.telefone, atraso / 60)
            return

        texto = await self._texto_da_mensagem(msg)
        if not texto:
            return

        lead = self.banco.lead(msg.telefone)
        if lead is None:
            if self.cfg.modo_atendimento == "gatilho" and normalizar(self.cfg.frase_gatilho) not in normalizar(texto):
                return  # contato que não veio pelo link de divulgação: o robô não entra
            lead = self.banco.criar_lead(msg.telefone, msg.destino, msg.nome)
            log.info("Novo lead: %s (%s)", msg.nome, msg.telefone)
        else:
            mudancas = {}
            if msg.destino != lead["destino"]:
                mudancas["destino"] = msg.destino
            if msg.nome and not lead.get("nome"):
                mudancas["nome"] = msg.nome
            if lead.get("resultado") in ("sem_interesse", "pediu_para_parar"):
                # O lead voltou a falar por conta própria: a conversa reabre.
                mudancas.update(resultado="", status="conversando")
            self.banco.atualizar_lead(msg.telefone, **mudancas)
            lead = self.banco.lead(msg.telefone)

        self.banco.salvar_mensagem(msg.telefone, "user", texto, respondida=False)
        if self._pausado(lead):
            return  # um humano está cuidando dessa conversa
        try:
            await self.canal.marcar_lida(msg)
        except Exception as erro:
            log.info("Falha ao marcar como lida: %s", erro)
        self._agendar(msg.telefone, self.cfg.debounce_segundos)

    async def _texto_da_mensagem(self, msg: MensagemRecebida) -> str:
        if msg.tipo == "texto":
            return msg.texto
        if msg.tipo == "audio":
            audio = msg.audio
            if audio is None:
                try:
                    audio = await self.canal.baixar_audio(msg)
                except Exception as erro:
                    log.error("Não consegui baixar o áudio: %s", erro)
            if audio and self.transcritor:
                transcricao = await self.transcritor.transcrever(audio)
                if transcricao:
                    return f"[áudio transcrito] {transcricao}"
            return "[O lead enviou um áudio que não pôde ser ouvido. Peça com gentileza para ele escrever.]"
        if msg.tipo == "imagem":
            legenda = f" com a legenda: {msg.texto}" if msg.texto else ""
            return f"[O lead enviou uma imagem{legenda}. Você não consegue ver imagens.]"
        if msg.texto:  # vídeo ou documento com legenda
            return f"[O lead enviou um arquivo com a legenda: {msg.texto}]"
        return ""  # figurinha, reação etc.: não exige resposta

    async def _mensagem_do_proprio_numero(self, msg: MensagemRecebida) -> None:
        """Mensagem que saiu do número do agente sem ser pelo robô: é o dono respondendo pelo celular."""
        if self._eh_dono(msg.telefone) or not msg.texto:
            return
        if self.banco.foi_enviado_pelo_agente(msg.id, msg.telefone, msg.texto):
            return
        lead = self.banco.lead(msg.telefone)
        if lead is None:
            # Conversa iniciada pelo dono: o robô não se mete.
            self.banco.criar_lead(msg.telefone, msg.destino, "")
            self.banco.atualizar_lead(msg.telefone, pausado_ate=PAUSA_INDEFINIDA, status="humano")
            return
        self.banco.salvar_mensagem(msg.telefone, "assistant", msg.texto)
        self.banco.marcar_respondidas(msg.telefone, 10**12)
        if not self._pausado(lead):
            ate = int(time.time()) + self.cfg.pausa_humano_horas * 3600
            self.banco.atualizar_lead(msg.telefone, pausado_ate=ate)
            log.info("Dono assumiu a conversa com %s; robô pausado por %sh.", msg.telefone, self.cfg.pausa_humano_horas)

    # ── comandos do dono ──────────────────────────────────────────────────────

    def _achar_lead(self, numero: str) -> tuple[dict | None, str]:
        encontrados = self.banco.buscar_lead_por_final(so_digitos(numero))
        if not encontrados:
            return None, f"Não achei lead com o número {numero}."
        if len(encontrados) > 1:
            return None, "Mais de um lead com esse final: " + ", ".join(l["telefone"] for l in encontrados)
        return encontrados[0], ""

    async def _comando_do_dono(self, msg: MensagemRecebida) -> None:
        partes = msg.texto.split(maxsplit=1)
        comando, argumento = partes[0].lower(), (partes[1].strip() if len(partes) > 1 else "")
        resposta = await self._executar_comando(comando, argumento)
        msg_id = await self.canal.enviar_texto(msg.destino, resposta)
        self.banco.registrar_enviado(msg_id, msg.telefone, resposta)

    async def _executar_comando(self, comando: str, argumento: str) -> str:
        if comando == "#status":
            contagem = self.banco.contagem_por_status()
            pausados = sum(1 for l in self.banco.todos_leads() if self._pausado(l))
            linhas = [f"{status}: {n}" for status, n in sorted(contagem.items())] or ["nenhum lead ainda"]
            return "📊 Leads por etapa\n" + "\n".join(linhas) + f"\n\nPausados (com humano): {pausados}"
        if comando not in ("#lead", "#pausar", "#retomar", "#comprou"):
            return AJUDA_DONO
        if not argumento:
            return f"Faltou o número. Exemplo: {comando} 11999999999"
        lead, erro = self._achar_lead(argumento)
        if not lead:
            return erro
        tel = lead["telefone"]
        if comando == "#lead":
            ficha = [f"{c}: {lead[c]}" for c in CAMPOS_QUALIFICACAO if lead.get(c)]
            situacao = "pausado (humano)" if self._pausado(lead) else "robô ativo"
            return (f"👤 {lead.get('nome') or 'sem nome'} ({tel})\nEtapa: {lead['status']} — {situacao}\n"
                    + ("\n".join(ficha) or "Ainda sem qualificação."))
        if comando == "#pausar":
            self.banco.atualizar_lead(tel, pausado_ate=PAUSA_INDEFINIDA)
            return f"⏸️ Robô pausado para {tel}. Use #retomar {tel} para devolver."
        if comando == "#retomar":
            self.banco.atualizar_lead(tel, pausado_ate=0, status="conversando" if lead["status"] == "humano" else lead["status"])
            if self.banco.pendentes(tel):
                self._agendar(tel, 2)
            return f"▶️ Robô de volta na conversa com {tel}."
        self.banco.atualizar_lead(tel, resultado="comprou", status="comprou")
        await self._sincronizar(tel)
        return f"🎉 Venda registrada para {tel}. Follow-ups encerrados."

    # ── resposta ──────────────────────────────────────────────────────────────

    def _agendar(self, telefone: str, atraso: float) -> None:
        anterior = self._timers.get(telefone)
        if anterior and not anterior.done():
            anterior.cancel()  # chegou mensagem nova: recomeça a espera
        self._timers[telefone] = asyncio.create_task(self._esperar_e_responder(telefone, atraso))

    async def _esperar_e_responder(self, telefone: str, atraso: float) -> None:
        try:
            await asyncio.sleep(atraso)
        except asyncio.CancelledError:
            return
        # A resposta roda em outra tarefa para não ser cancelada no meio por mensagem nova.
        self._rodar(self.responder(telefone))

    async def responder(self, telefone: str) -> None:
        async with self._travas[telefone]:
            pendentes = self.banco.pendentes(telefone)
            lead = self.banco.lead(telefone)
            if not pendentes or not lead or self._pausado(lead):
                self._falhas.pop(telefone, None)  # nada a responder: uma falha antiga não conta mais
                return
            ultimo_id = pendentes[-1]["id"]
            acoes = Acoes(lead=lead, tem_link=bool(self.cfg.link_checkout))
            try:
                resposta = await self.ia.conversar(
                    montar_sistema(self.cfg.pasta_config),
                    montar_contexto(lead, self.cfg.fuso, bool(self.cfg.link_checkout)),
                    self.banco.historico_para_ia(telefone, self.cfg.historico_max_mensagens),
                    FERRAMENTAS,
                    acoes.executar,
                )
            except Exception as erro:
                log.exception("Falha da IA ao responder %s", telefone)
                await self._falhou(lead, erro)
                return

            if resposta.recusou and not acoes.chamar_humano:
                acoes.chamar_humano = "A IA não pôde responder (filtro de segurança do provedor)."
            texto = resposta.texto or (MSG_HUMANO if acoes.chamar_humano else "")
            if not texto and not acoes.enviar_checkout and not acoes.encerrar:
                await self._falhou(lead, RuntimeError("a IA devolveu uma resposta vazia"))
                return
            if self._pausado(self.banco.lead(telefone) or {}):
                return  # o dono assumiu enquanto a IA pensava: a resposta não sai
            try:
                if texto:
                    await self._enviar(lead, texto)
                if acoes.enviar_checkout:
                    await self._enviar(lead, self.cfg.link_checkout)
            except Exception as erro:
                log.exception("Falha ao enviar mensagem para %s", telefone)
                await self._falhou(lead, erro)
                return
            self.banco.marcar_respondidas(telefone, ultimo_id)
            self._falhas.pop(telefone, None)
            await self._aplicar(telefone, acoes)

    async def _enviar(self, lead: dict, texto: str) -> None:
        enviadas = []
        try:
            for parte in dividir_em_mensagens(texto):
                msg_id = await self.canal.enviar_texto(lead["destino"], parte, tempo_digitando_ms(parte))
                self.banco.registrar_enviado(msg_id, lead["telefone"], parte)
                enviadas.append(parte)
        finally:
            # Guarda no histórico só o que o lead realmente recebeu (mesmo se o envio caiu no meio).
            if enviadas:
                self.banco.salvar_mensagem(lead["telefone"], "assistant", "\n\n".join(enviadas))

    async def _aplicar(self, tel: str, acoes: Acoes) -> None:
        lead = self.banco.lead(tel)  # relê: o dono pode ter mudado algo (#comprou) enquanto a IA pensava
        mudancas = dict(acoes.qualificacao)
        status = lead["status"]
        if status == "novo":
            status = "conversando"
        if acoes.qualificacao.get("temperatura") == "quente" and status == "conversando":
            status = "qualificado"
        if acoes.enviar_checkout:
            mudancas["checkout_enviado_em"] = int(time.time())
            if status in ("conversando", "qualificado"):
                status = "checkout_enviado"
        if lead.get("resultado") == "comprou":
            status = "comprou"  # venda registrada pelo dono vale mais que a leitura da IA
        elif acoes.encerrar:
            mudancas["resultado"] = acoes.encerrar
            status = "comprou" if acoes.encerrar == "comprou" else "perdido"
        if acoes.chamar_humano:
            mudancas["pausado_ate"] = PAUSA_INDEFINIDA
        mudancas["status"] = status
        self.banco.atualizar_lead(tel, **mudancas)

        if acoes.chamar_humano:
            atual = self.banco.lead(tel)
            await self._avisar_dono(
                f"🙋 {atual.get('nome') or 'Lead'} ({tel}) precisa de atendimento humano.\n"
                f"Motivo: {acoes.chamar_humano}\n"
                + (f"Resumo: {atual['resumo']}\n" if atual.get("resumo") else "")
                + f"\nResponda pelo WhatsApp normalmente. Para devolver ao robô: #retomar {tel}"
            )
        await self._sincronizar(tel)

    async def _falhou(self, lead: dict, erro: Exception) -> None:
        tel = lead["telefone"]
        self._falhas[tel] += 1
        if self._falhas[tel] == 1:
            self._agendar(tel, self.espera_nova_tentativa)
            return
        # Segunda falha seguida: o lead não pode ficar sem resposta.
        self._falhas.pop(tel, None)
        try:
            await self._enviar(lead, MSG_AGUARDE)
        except Exception:
            log.exception("Também não consegui enviar a mensagem de espera para %s", tel)
        self.banco.marcar_respondidas(tel, 10**12)
        self.banco.atualizar_lead(tel, pausado_ate=PAUSA_INDEFINIDA)
        await self._avisar_dono(
            f"⚠️ A IA falhou duas vezes ao responder {lead.get('nome') or 'um lead'} ({tel}).\n"
            f"Erro: {str(erro)[:300]}\n\nO lead recebeu uma mensagem de espera e o robô foi pausado "
            f"nessa conversa. Responda pelo WhatsApp e depois use #retomar {tel}."
        )

    def retomar_pendentes(self) -> None:
        """Ao reiniciar, responde quem ficou sem resposta nos últimos minutos."""
        desde = int(time.time()) - self.cfg.atraso_maximo_minutos * 60
        for telefone in self.banco.telefones_com_pendentes(desde):
            self._agendar(telefone, 3)

    # ── follow-up ─────────────────────────────────────────────────────────────

    def _em_horario_comercial(self) -> bool:
        hora = datetime.now(ZoneInfo(self.cfg.fuso)).hour
        return self.cfg.horario_inicio <= hora < self.cfg.horario_fim

    async def fazer_followups(self) -> int:
        if not self.cfg.followup_ativo or not self._em_horario_comercial():
            return 0
        enviados = 0
        agora = int(time.time())
        for lead in self.banco.leads_para_followup(agora, self.cfg.followup_horas, self.cfg.followup_max):
            if self.cfg.canal == "meta" and agora - (lead.get("ultima_msg_lead_em") or 0) > 23 * 3600:
                continue  # fora da janela de 24h da Meta: só com template aprovado
            if await self._followup(lead["telefone"]):
                enviados += 1
        return enviados

    async def _followup(self, telefone: str) -> bool:
        async with self._travas[telefone]:
            lead = self.banco.lead(telefone)
            if not lead or self._pausado(lead) or lead.get("resultado") or self.banco.pendentes(telefone):
                return False
            numero = (lead.get("followups_enviados") or 0) + 1
            horas = max(1, (int(time.time()) - (lead.get("ultima_msg_bot_em") or 0)) // 3600)
            instrucao = INSTRUCAO_FOLLOWUP.format(
                horas=horas, numero=numero, maximo=self.cfg.followup_max,
                ultimo=" (o último: se não houver resposta, a conversa será encerrada)" if numero == self.cfg.followup_max else "",
            )
            historico = self.banco.historico_para_ia(telefone, self.cfg.historico_max_mensagens)
            historico.append({"papel": "user", "texto": instrucao})

            async def sem_ferramentas(nome: str, args: dict) -> str:
                return "Ferramentas indisponíveis no follow-up."

            try:
                resposta = await self.ia.conversar(
                    montar_sistema(self.cfg.pasta_config),
                    montar_contexto(lead, self.cfg.fuso, bool(self.cfg.link_checkout)),
                    historico, [], sem_ferramentas,
                )
                if not resposta.texto:
                    return False
                await self._enviar(lead, resposta.texto)
            except Exception:
                log.exception("Falha no follow-up de %s", telefone)
                return False
            self.banco.atualizar_lead(telefone, followups_enviados=numero)
            log.info("Follow-up %s enviado para %s", numero, telefone)
            return True
