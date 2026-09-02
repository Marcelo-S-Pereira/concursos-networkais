"""Parser da prova objetiva (padrão Cesgranrio/PCI, texto nativo).

Estrutura observada em dutos_e_terminais.pdf:
- número da questão sozinho numa linha (ex.: "32");
- enunciado em seguida;
- 5 alternativas iniciando a linha com "(A) ", "(B) " ... "(E) ".

Ruído a remover: marca d'água (pcimarkpci/pciconcursos) e cabeçalhos de página
("PROVA 2 - DUTOS E TERMINAIS", "TERRA", "TRANSPETRO", número de página solto).

Questões com figura ("Figura", "figura abaixo") ficam marcadas para revisão —
o texto sozinho não basta e a imagem entra depois (modelo de visão).
"""

import re
from dataclasses import dataclass, field

RUIDO = re.compile(r"pcimarkpci|pciconcursos|^\s*TERRA\s*$|^\s*TRANSPETRO\s*$|PROVA\s+\d+\s*-", re.I)
ALT = re.compile(r"^\s*\(([A-E])\)\s*(.*)$")
NUM_SOZINHO = re.compile(r"^\s*(\d{1,2})\s*$")
TEM_FIGURA = re.compile(r"figura|gráfico|imagem|tabela abaixo|esquema abaixo", re.I)


@dataclass
class QuestaoExtraida:
    numero: int
    enunciado: str
    pagina: int = 0
    alternativas: dict[str, str] = field(default_factory=dict)
    tem_figura: bool = False
    confianca: float = 1.0
    aviso: str = ""


def _dehifenizar(texto: str) -> str:
    """Junta palavra cortada por hífen na quebra de linha ("utiliza- ção" →
    "utilização"). Só quando é minúscula-hífen-espaço-minúscula, para não comer
    hífens legítimos ("primeiro-ministro") nem intervalos ("21- A")."""
    return re.sub(r"([a-zà-ú])-\s+([a-zà-ú])", r"\1\2", texto)


def parse_prova(paginas: list[str], primeira: int = 1, ultima: int = 60) -> list[QuestaoExtraida]:
    # numera cada linha com a página de origem, para saber onde renderizar figura
    linhas_pag: list[tuple[str, int]] = []
    for i, txt in enumerate(paginas):
        for linha in txt.split("\n"):
            linhas_pag.append((linha, i))
    linhas = [(ln, pg) for (ln, pg) in linhas_pag if not RUIDO.search(ln)]
    questoes: list[QuestaoExtraida] = []
    atual: QuestaoExtraida | None = None
    letra_corrente: str | None = None

    def fechar(q: QuestaoExtraida | None) -> None:
        if q is None:
            return
        q.enunciado = _dehifenizar(re.sub(r"[ \t]+", " ", q.enunciado)).strip()
        q.alternativas = {
            k: _dehifenizar(v) for k, v in q.alternativas.items()
        }
        # avalia confiança: precisa das 5 alternativas e de enunciado não-vazio
        faltando = [x for x in "ABCDE" if x not in q.alternativas]
        if faltando:
            q.confianca = 0.4
            q.aviso = f"faltam alternativas: {', '.join(faltando)}"
        elif len(q.enunciado) < 15:
            q.confianca = 0.5
            q.aviso = "enunciado muito curto"
        if q.tem_figura and not q.aviso:
            q.confianca = min(q.confianca, 0.7)
            q.aviso = "contém figura — confira com a imagem"
        questoes.append(q)

    for linha, pagina in linhas:
        linha = linha.rstrip()
        m_num = NUM_SOZINHO.match(linha)
        # um número sozinho DENTRO da faixa esperada e maior/igual ao próximo esperado inicia questão
        if m_num and primeira <= int(m_num.group(1)) <= ultima:
            numero = int(m_num.group(1))
            esperado = (atual.numero + 1) if atual else primeira
            # só é nova questão se for o próximo número esperado E a questão
            # atual já tiver alternativas (evita que numeração de linha do texto
            # de leitura — 5, 10, 15 — abra questões vazias).
            atual_pronta = atual is None or len(atual.alternativas) >= 1
            if numero == esperado and atual_pronta:
                fechar(atual)
                atual = QuestaoExtraida(numero=numero, enunciado="", pagina=pagina)
                letra_corrente = None
                continue

        if atual is None:
            continue

        m_alt = ALT.match(linha)
        if m_alt:
            letra_corrente = m_alt.group(1)
            atual.alternativas[letra_corrente] = m_alt.group(2).strip()
        elif letra_corrente:
            # continuação de uma alternativa que quebrou linha
            atual.alternativas[letra_corrente] += " " + linha.strip()
        else:
            atual.enunciado += " " + linha
            if TEM_FIGURA.search(linha):
                atual.tem_figura = True

    fechar(atual)
    return questoes
