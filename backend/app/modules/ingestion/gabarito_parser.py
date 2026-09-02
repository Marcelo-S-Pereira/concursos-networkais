"""Parser do gabarito da Cesgranrio/PCI, que traz VÁRIAS provas em colunas.

A extração de texto do PDF intercala as colunas: cada linha vira uma sequência
de pares "NN - X" de provas diferentes. Este parser agrupa por número de questão
e, para cada questão, coleta TODAS as respostas que aparecem — depois o chamador
escolhe a coluna certa pela posição.

Como as colunas 1-20 (Conhecimentos Básicos) são comuns a todas as provas, elas
aparecem uma vez; as 21-60 aparecem uma vez POR prova. A prova alvo é escolhida
pelo índice da coluna (0 = primeira prova específica listada).
"""

import re

PAR = re.compile(r"(\d{1,2})\s*-\s*([A-E])")


def parse_respostas(texto: str, coluna_alvo: int = 0) -> dict[int, str]:
    """Devolve {numero_questao: alternativa}. `coluna_alvo` seleciona qual prova
    específica usar quando o mesmo número aparece em várias colunas (0 = a 1ª)."""
    # coleta, na ordem de leitura, todas as ocorrências (numero, letra)
    ocorrencias = [(int(n), letra) for n, letra in PAR.findall(texto)]

    # agrupa por número preservando ordem de aparição
    por_numero: dict[int, list[str]] = {}
    for numero, letra in ocorrencias:
        por_numero.setdefault(numero, []).append(letra)

    respostas: dict[int, str] = {}
    for numero, letras in por_numero.items():
        if len(letras) == 1:
            respostas[numero] = letras[0]  # questão comum (1-20)
        else:
            idx = min(coluna_alvo, len(letras) - 1)
            respostas[numero] = letras[idx]  # questão específica: pega a coluna alvo
    return respostas
