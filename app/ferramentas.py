"""Ferramentas que a IA pode usar durante a conversa.

A IA não executa nada diretamente: ela *pede* a ferramenta, o código abaixo
registra o pedido e o agente aplica os efeitos depois de enviar a resposta
(ex.: o link de compra sai numa mensagem separada, logo após o texto da IA).
"""

from dataclasses import dataclass, field

from app.ia.base import Ferramenta


def _objeto(propriedades: dict) -> dict:
    return {"type": "object", "properties": propriedades,
            "required": list(propriedades), "additionalProperties": False}


_TEXTO = {"type": "string"}

FERRAMENTAS = [
    Ferramenta(
        nome="registrar_qualificacao",
        descricao=(
            "Atualiza a ficha do lead com o que você descobriu na conversa (método BANT). "
            "Use sempre que aprender algo novo. Preencha com string vazia o que ainda não sabe."
        ),
        parametros=_objeto({
            "necessidade": {**_TEXTO, "description": "Dor ou objetivo do lead, nas palavras dele."},
            "autoridade": {**_TEXTO, "description": "Quem decide a compra (ele mesmo, sócio, cônjuge...)."},
            "orcamento": {**_TEXTO, "description": "O que ele disse sobre investimento/preço."},
            "prazo": {**_TEXTO, "description": "Quando ele precisa resolver."},
            "temperatura": {"type": "string", "enum": ["fria", "morna", "quente", ""],
                            "description": "Chance de compra: fria, morna ou quente."},
            "resumo": {**_TEXTO, "description": "Uma frase resumindo o lead até agora."},
        }),
    ),
    Ferramenta(
        nome="enviar_link_checkout",
        descricao=(
            "Envia o link de compra numa mensagem separada, logo depois da sua resposta. "
            "Use quando o lead estiver qualificado e demonstrar intenção de comprar, ou quando pedir o link. "
            "NUNCA escreva o link você mesmo: o sistema envia. O link é enviado no máximo uma vez, "
            "a não ser que o lead peça de novo."
        ),
        parametros=_objeto({
            "lead_pediu_explicitamente": {"type": "boolean",
                                          "description": "true se o lead pediu o link com essas palavras."},
        }),
    ),
    Ferramenta(
        nome="chamar_humano",
        descricao=(
            "Passa a conversa para uma pessoa da equipe e pausa o atendimento automático deste lead. "
            "Use quando: o lead pedir para falar com uma pessoa; você não souber responder com base nas "
            "informações do negócio; houver reclamação, pedido de reembolso, negociação fora das condições "
            "oferecidas ou assunto sensível. Depois de chamar, avise o lead que alguém vai responder em breve."
        ),
        parametros=_objeto({"motivo": {**_TEXTO, "description": "Por que precisa de um humano (curto)."}}),
    ),
    Ferramenta(
        nome="encerrar_conversa",
        descricao=(
            "Marca o resultado final da conversa e para os follow-ups automáticos. Use quando o lead disser que "
            "já comprou, que não tem interesse, ou pedir para não receber mais mensagens."
        ),
        parametros=_objeto({
            "resultado": {"type": "string", "enum": ["comprou", "sem_interesse", "pediu_para_parar"]},
        }),
    ),
]


@dataclass
class Acoes:
    """Pedidos que a IA fez numa resposta. O agente aplica depois de enviar o texto."""

    lead: dict
    tem_link: bool
    qualificacao: dict = field(default_factory=dict)
    enviar_checkout: bool = False
    chamar_humano: str = ""
    encerrar: str = ""

    async def executar(self, nome: str, args: dict) -> str:
        if nome == "registrar_qualificacao":
            self.qualificacao = {k: str(v).strip() for k, v in args.items() if str(v).strip()}
            return "Ficha atualizada."
        if nome == "enviar_link_checkout":
            if not self.tem_link:
                return "Não há link de compra configurado. Use chamar_humano para fechar a venda."
            if self.lead.get("checkout_enviado_em") and not args.get("lead_pediu_explicitamente"):
                return "O link já foi enviado antes. Não reenviei. Relembre o lead de que ele está acima na conversa."
            self.enviar_checkout = True
            return "Combinado: o link será enviado logo depois da sua mensagem. Não escreva o link no texto."
        if nome == "chamar_humano":
            self.chamar_humano = str(args.get("motivo") or "sem motivo informado")
            return "Equipe avisada e atendimento automático pausado. Diga ao lead que alguém responde em breve."
        if nome == "encerrar_conversa":
            self.encerrar = str(args.get("resultado") or "")
            return "Conversa encerrada. Despeça-se de forma breve e cordial."
        return f"Ferramenta desconhecida: {nome}"
