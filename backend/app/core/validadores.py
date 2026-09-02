"""Validação de CPF e telefone. Erra cedo, com mensagem que a pessoa entende."""

import re


def normalizar_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf: str) -> bool:
    """Dígito verificador oficial. Rejeita também os repetidos ([CPF_INVALIDO_EXEMPLO]),
    que passam na conta mas não são CPF de ninguém."""
    numeros = normalizar_digitos(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False

    for tamanho in (9, 10):
        soma = sum(int(numeros[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(numeros[tamanho]):
            return False
    return True


def telefone_valido(telefone: str) -> bool:
    """Fixo (10) ou celular (11) com DDD. O celular tem 9 na frente do número."""
    numeros = normalizar_digitos(telefone)
    if len(numeros) not in (10, 11):
        return False
    if not 11 <= int(numeros[:2]) <= 99:  # DDD brasileiro válido
        return False
    return not (len(numeros) == 11 and numeros[2] != "9")


def formatar_cpf(cpf: str) -> str:
    n = normalizar_digitos(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else cpf


def mascarar_cpf(cpf: str) -> str:
    """Só os 3 últimos dígitos. É o que a tela mostra - CPF inteiro na interface
    é vazamento por cima do ombro."""
    n = normalizar_digitos(cpf)
    return f"***.***.{n[6:9]}-{n[9:]}" if len(n) == 11 else "***"
