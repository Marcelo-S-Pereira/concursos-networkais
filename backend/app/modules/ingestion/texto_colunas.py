"""Extrai o texto de uma página respeitando as 2 colunas da prova.

A extração linear do PDF intercala as colunas. Aqui a posição x de cada trecho
decide a coluna (antes/depois do meio da página); dentro de cada coluna, ordena
por y (de cima para baixo) e agrupa por linha. Devolve as duas colunas separadas
para o usuário copiar uma ou outra sem bagunça.
"""

from pypdf import PdfReader


def _linhas_da_coluna(trechos: list[tuple[float, float, str]]) -> str:
    # trechos: (x, y, texto). Agrupa por linha (y próximo), ordena por x.
    trechos = sorted(trechos, key=lambda t: (-t[1], t[0]))
    linhas: list[list[tuple[float, str]]] = []
    y_atual: float | None = None
    for x, y, texto in trechos:
        if y_atual is None or abs(y - y_atual) > 4:
            linhas.append([])
            y_atual = y
        linhas[-1].append((x, texto))
    saida = []
    for linha in linhas:
        saida.append(" ".join(t for _, t in sorted(linha, key=lambda p: p[0])).strip())
    return "\n".join(ln for ln in saida if ln)


def texto_por_colunas(caminho_pdf: str, indice_pagina: int) -> str:
    reader = PdfReader(caminho_pdf)
    page = reader.pages[indice_pagina]
    meio = float(page.mediabox.width) / 2

    trechos: list[tuple[float, float, str]] = []

    def visit(text, cm, tm, font, size):  # noqa: ANN001 - assinatura do pypdf
        if text.strip() and "pcimarkpci" not in text and "pciconcursos" not in text:
            trechos.append((tm[4], tm[5], text.strip()))

    page.extract_text(visitor_text=visit)
    esq = [t for t in trechos if t[0] < meio]
    dir_ = [t for t in trechos if t[0] >= meio]

    partes = []
    if esq:
        partes.append("── COLUNA ESQUERDA ──\n" + _linhas_da_coluna(esq))
    if dir_:
        partes.append("── COLUNA DIREITA ──\n" + _linhas_da_coluna(dir_))
    return "\n\n".join(partes)
