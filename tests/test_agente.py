import asyncio
import time

from app.agente import MSG_AGUARDE, PAUSA_INDEFINIDA, dividir_em_mensagens
from app.ia.base import RespostaIA
from tests.conftest import IAFalsa, msg

LEAD = "5511988887777"


async def entregar(agente, *mensagens):
    for m in mensagens:
        await agente.receber(m)
    await agente.aguardar_tarefas()


def test_conversa_continua_depois_da_primeira_mensagem(montar, canal):
    """O agente original ignorava toda mensagem sem a frase-gatilho, então a conversa morria."""
    ia = IAFalsa("Oi! Como posso ajudar?", "Perfeito, e quando você precisa resolver isso?")
    agente = montar(ia)
    asyncio.run(entregar(agente, msg("oi")))
    asyncio.run(entregar(agente, msg("sou eu que decido")))
    assert canal.textos(LEAD) == ["Oi! Como posso ajudar?", "Perfeito, e quando você precisa resolver isso?"]
    assert [m["texto"] for m in ia.chamadas[1]["historico"]] == ["oi", "Oi! Como posso ajudar?", "sou eu que decido"]


def test_mensagens_picadas_geram_uma_resposta(montar, canal, cfg):
    cfg.debounce_segundos = 0.2
    ia = IAFalsa("Resposta única")
    agente = montar(ia)

    async def cenario():
        for texto in ("oi", "tudo bem?", "queria saber do curso"):
            await agente.receber(msg(texto))
            await asyncio.sleep(0.05)
        await agente.aguardar_tarefas()

    asyncio.run(cenario())
    assert len(ia.chamadas) == 1
    assert [m["texto"] for m in ia.chamadas[0]["historico"]] == ["oi", "tudo bem?", "queria saber do curso"]
    assert canal.textos(LEAD) == ["Resposta única"]


def test_link_de_checkout_enviado_uma_vez(montar, canal, banco):
    async def pede_link(executar):
        retorno = await executar("enviar_link_checkout", {"lead_pediu_explicitamente": False})
        return "Vou te mandar o link!" if "será enviado" in retorno else "O link está logo acima."

    agente = montar(IAFalsa(pede_link, pede_link))
    asyncio.run(entregar(agente, msg("quero comprar")))
    asyncio.run(entregar(agente, msg("beleza")))
    textos = canal.textos(LEAD)
    assert textos.count("https://pagar.exemplo/curso") == 1
    assert textos[-1] == "O link está logo acima."
    assert banco.lead(LEAD)["status"] == "checkout_enviado"


def test_lead_pede_link_de_novo(montar, canal):
    async def pede_link(executar):
        await executar("enviar_link_checkout", {"lead_pediu_explicitamente": True})
        return "Aqui está!"

    agente = montar(IAFalsa(pede_link, pede_link))
    asyncio.run(entregar(agente, msg("manda o link")))
    asyncio.run(entregar(agente, msg("perdi o link, manda de novo")))
    assert canal.textos(LEAD).count("https://pagar.exemplo/curso") == 2


def test_modo_gatilho_so_atende_quem_veio_pelo_link(montar, canal, cfg, banco):
    cfg.modo_atendimento = "gatilho"
    cfg.frase_gatilho = "Quero saber mais sobre o Curso"
    agente = montar(IAFalsa("Oi!"))
    asyncio.run(entregar(agente, msg("e aí, vamos no jogo hoje?", telefone="5511911112222")))
    assert canal.enviadas == [] and banco.lead("5511911112222") is None

    asyncio.run(entregar(agente, msg("Olá! quero saber mais sobre o CURSO")))
    assert canal.textos(LEAD) == ["Oi!"]


def test_chamar_humano_pausa_e_avisa_o_dono(montar, canal, banco, cfg):
    async def humano(executar):
        await executar("chamar_humano", {"motivo": "pediu reembolso"})
        return "Vou chamar alguém da equipe."

    agente = montar(IAFalsa(humano, "voltei"))
    asyncio.run(entregar(agente, msg("quero reembolso")))
    assert banco.lead(LEAD)["pausado_ate"] == PAUSA_INDEFINIDA
    aviso = canal.textos(cfg.dono_telefone)[0]
    assert "pediu reembolso" in aviso and "#retomar" in aviso

    asyncio.run(entregar(agente, msg("alô?")))
    assert canal.textos(LEAD) == ["Vou chamar alguém da equipe."]  # robô calado

    asyncio.run(entregar(agente, msg("#retomar 11988887777", telefone=cfg.dono_telefone)))
    assert "de volta" in canal.textos(cfg.dono_telefone)[-1]
    assert canal.textos(LEAD)[-1] == "voltei"  # respondeu o "alô?" pendente


def test_dono_respondendo_pelo_celular_pausa_o_robo(montar, canal, banco):
    agente = montar(IAFalsa("Oi! Tudo bem?"))
    asyncio.run(entregar(agente, msg("oi")))

    # Eco da mensagem que o próprio robô enviou: não é o dono, não pausa.
    asyncio.run(entregar(agente, msg("Oi! Tudo bem?", de_mim=True, id="enviada-1")))
    assert (banco.lead(LEAD)["pausado_ate"] or 0) < time.time()

    asyncio.run(entregar(agente, msg("Fala, aqui é o João, dono da escola!", de_mim=True)))
    assert banco.lead(LEAD)["pausado_ate"] > time.time()
    assert banco.historico(LEAD, 10)[-1] == {"papel": "assistant", "texto": "Fala, aqui é o João, dono da escola!"}


def test_conversa_iniciada_pelo_dono_nao_vira_lead_do_robo(montar, canal, banco):
    agente = montar(IAFalsa("não deveria responder"))
    asyncio.run(entregar(agente, msg("Oi mãe, chego às 8", de_mim=True, telefone="5511933334444")))
    asyncio.run(entregar(agente, msg("ok filho", telefone="5511933334444")))
    assert canal.enviadas == []


def test_falha_da_ia_nunca_envia_erro_ao_lead(montar, canal, banco, cfg):
    agente = montar(IAFalsa(RuntimeError("401 chave inválida"), RuntimeError("401 chave inválida")))
    agente.espera_nova_tentativa = 0
    asyncio.run(entregar(agente, msg("oi")))
    assert canal.textos(LEAD) == [MSG_AGUARDE]
    assert "401" in canal.textos(cfg.dono_telefone)[0]
    assert banco.lead(LEAD)["pausado_ate"] == PAUSA_INDEFINIDA


def test_ia_se_recupera_na_segunda_tentativa(montar, canal):
    agente = montar(IAFalsa(RuntimeError("timeout"), "Oi!"))
    agente.espera_nova_tentativa = 0
    asyncio.run(entregar(agente, msg("oi")))
    assert canal.textos(LEAD) == ["Oi!"]


def test_resposta_vazia_tenta_de_novo(montar, canal):
    agente = montar(IAFalsa("", "Oi!"))
    asyncio.run(entregar(agente, msg("oi")))
    assert canal.textos(LEAD) == ["Oi!"]


def test_recusa_da_ia_vira_atendimento_humano(montar, canal, banco, cfg):
    agente = montar(IAFalsa(RespostaIA(texto="", recusou=True)))
    asyncio.run(entregar(agente, msg("...")))
    assert "alguém da equipe" in canal.textos(LEAD)[0]
    assert canal.textos(cfg.dono_telefone)
    assert banco.lead(LEAD)["pausado_ate"] == PAUSA_INDEFINIDA


def test_webhook_repetido_e_mensagem_antiga_sao_ignorados(montar, canal):
    agente = montar(IAFalsa("Oi!", "não deveria"))
    m = msg("oi")
    asyncio.run(entregar(agente, m, m))
    asyncio.run(entregar(agente, msg("mensagem de ontem", timestamp=time.time() - 86400)))
    assert canal.textos(LEAD) == ["Oi!"]


def test_numero_ignorado(montar, canal, cfg):
    cfg.numeros_ignorados = ["11977776666"]
    agente = montar(IAFalsa("Oi!"))
    asyncio.run(entregar(agente, msg("oi", telefone="5511977776666")))
    assert canal.enviadas == []


def test_qualificacao_atualiza_ficha_e_etapa(montar, banco):
    async def qualifica(executar):
        await executar("registrar_qualificacao", {"necessidade": "automatizar relatórios", "autoridade": "ele mesmo",
                                                  "orcamento": "", "prazo": "este mês", "temperatura": "quente",
                                                  "resumo": "analista com pressa"})
        return "Entendi!"

    agente = montar(IAFalsa(qualifica))
    asyncio.run(entregar(agente, msg("preciso automatizar relatórios este mês")))
    lead = banco.lead(LEAD)
    assert lead["necessidade"] == "automatizar relatórios"
    assert lead["status"] == "qualificado"


def test_encerrar_para_followups(montar, banco):
    async def encerra(executar):
        await executar("encerrar_conversa", {"resultado": "sem_interesse"})
        return "Tudo bem, obrigado!"

    agente = montar(IAFalsa(encerra))
    asyncio.run(entregar(agente, msg("não tenho interesse")))
    banco.atualizar_lead(LEAD, ultima_msg_bot_em=int(time.time()) - 30 * 3600)
    assert banco.leads_para_followup(int(time.time()), 20, 2) == []


def test_audio_e_transcrito(montar, canal):
    class Transcritor:
        async def transcrever(self, audio):
            return "quanto custa o curso?"

    ia = IAFalsa("Custa R$ 100.")
    agente = montar(ia)
    agente.transcritor = Transcritor()
    asyncio.run(entregar(agente, msg("", tipo="audio", audio=b"OggS...")))
    assert ia.chamadas[0]["historico"][-1]["texto"] == "[áudio transcrito] quanto custa o curso?"


def test_audio_sem_transcricao_pede_para_escrever(montar):
    ia = IAFalsa("Pode me escrever?")
    agente = montar(ia)
    asyncio.run(entregar(agente, msg("", tipo="audio", audio=b"OggS...")))
    assert "não pôde ser ouvido" in ia.chamadas[0]["historico"][-1]["texto"]


def test_followup_respeita_intervalo_e_limite(montar, canal, banco, cfg):
    ia = IAFalsa("Oi!", "E aí, conseguiu pensar?", "Último toque!", "não deveria")
    agente = montar(ia)
    asyncio.run(entregar(agente, msg("oi")))

    assert asyncio.run(agente.fazer_followups()) == 0  # acabou de responder

    def passar_21_horas():
        agora = int(time.time())
        banco.atualizar_lead(LEAD, ultima_msg_lead_em=agora - 22 * 3600, ultima_msg_bot_em=agora - 21 * 3600)

    passar_21_horas()
    assert asyncio.run(agente.fazer_followups()) == 1
    assert "Mensagem interna do sistema" in ia.chamadas[1]["historico"][-1]["texto"]
    assert ia.chamadas[1]["ferramentas"] == []

    passar_21_horas()
    assert asyncio.run(agente.fazer_followups()) == 1
    passar_21_horas()
    assert asyncio.run(agente.fazer_followups()) == 0  # FOLLOWUP_MAX = 2
    assert canal.textos(LEAD) == ["Oi!", "E aí, conseguiu pensar?", "Último toque!"]


def test_followup_fora_da_janela_da_meta(montar, banco, cfg):
    cfg.canal = "meta"
    agente = montar(IAFalsa("Oi!", "follow"))
    asyncio.run(entregar(agente, msg("oi")))
    passado = int(time.time()) - 25 * 3600
    banco.atualizar_lead(LEAD, ultima_msg_bot_em=passado, ultima_msg_lead_em=passado - 60)
    assert asyncio.run(agente.fazer_followups()) == 0


def test_comandos_do_dono(montar, canal, cfg):
    agente = montar(IAFalsa("Oi!"))
    asyncio.run(entregar(agente, msg("oi")))
    asyncio.run(entregar(agente, msg("#status", telefone=cfg.dono_telefone)))
    assert "conversando: 1" in canal.textos(cfg.dono_telefone)[-1]
    asyncio.run(entregar(agente, msg("#comprou 988887777", telefone=cfg.dono_telefone)))
    assert "Venda registrada" in canal.textos(cfg.dono_telefone)[-1]
    asyncio.run(entregar(agente, msg("#qualquercoisa", telefone=cfg.dono_telefone)))
    assert "#retomar" in canal.textos(cfg.dono_telefone)[-1]


def test_dono_nunca_vira_lead(montar, canal, cfg, banco):
    """Um "ok" do dono em resposta a um aviso não pode virar conversa de venda."""
    agente = montar(IAFalsa("Oi, quer conhecer o curso?"))
    asyncio.run(entregar(agente, msg("ok, vou ver", telefone=cfg.dono_telefone)))
    assert canal.enviadas == [] and banco.lead(cfg.dono_telefone) is None


def test_lead_escreve_enquanto_a_ia_gera(montar, canal, banco):
    """A mensagem nova precisa ser a última da conversa enviada à IA na resposta seguinte."""
    agente = montar(None)

    async def lenta(executar):
        await agente.receber(msg("e tem certificado?"))  # chega no meio da geração
        return "O curso custa R$ 100."

    agente.ia = IAFalsa(lenta, "Tem sim!")
    asyncio.run(entregar(agente, msg("quanto custa?")))
    assert canal.textos(LEAD) == ["O curso custa R$ 100.", "Tem sim!"]
    segunda = [m["texto"] for m in agente.ia.chamadas[1]["historico"]]
    assert segunda == ["quanto custa?", "O curso custa R$ 100.", "e tem certificado?"]


def test_dono_assume_enquanto_a_ia_gera(montar, canal, banco):
    agente = montar(None)

    async def lenta(executar):
        await agente.receber(msg("Deixa que eu respondo, Maria!", de_mim=True))
        return "resposta que não deve sair"

    agente.ia = IAFalsa(lenta)
    asyncio.run(entregar(agente, msg("oi")))
    assert canal.enviadas == []


def test_falha_no_envio_tenta_de_novo(montar, canal):
    agente = montar(IAFalsa("Oi!", "Oi de novo!"))
    agente.espera_nova_tentativa = 0.2
    canal.falhar = True

    async def cenario():
        await agente.receber(msg("oi"))
        await asyncio.sleep(0.05)
        canal.falhar = False  # o WhatsApp voltou
        await agente.aguardar_tarefas()

    asyncio.run(cenario())
    assert canal.textos(LEAD) == ["Oi de novo!"]


def test_comprou_durante_a_geracao_nao_e_sobrescrito(montar, banco, cfg):
    agente = montar(None)

    async def lenta(executar):
        await agente.receber(msg("#comprou 11988887777", telefone=cfg.dono_telefone))
        return "Que ótimo!"

    agente.ia = IAFalsa(lenta)
    asyncio.run(entregar(agente, msg("já paguei")))
    assert banco.lead(LEAD)["status"] == "comprou"


def test_dividir_em_mensagens():
    texto = "Um.\n\nDois.\n\nTrês.\n\nQuatro com mais texto."
    partes = dividir_em_mensagens(texto)
    assert len(partes) == 3
    assert "\n\n".join(partes).replace("\n\n", "|") == "Um.|Dois.|Três.|Quatro com mais texto."
    assert dividir_em_mensagens("Só uma.") == ["Só uma."]
