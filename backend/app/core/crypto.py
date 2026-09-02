"""Cifra simétrica (AES-256-GCM) e índice determinístico.

Duas chaves distintas, por propósito:
- DATA_ENCRYPTION_KEY  → dado pessoal (CPF).
- AI_MASTER_ENCRYPTION_KEY → chave de API das conexões de IA.
Separar limita o estrago se uma vazar, e permite girar uma sem tocar na outra.

AES-GCM usa nonce novo a cada cifragem: o mesmo texto vira saída diferente toda
vez. Por isso, quando é preciso UNIQUE/busca (ex.: CPF), há o
`indice_deterministico` — um HMAC estável — em vez de guardar o valor em claro.
"""

import hashlib
import hmac
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

NONCE_BYTES = 12


def _chave(hex_key: str, nome: str) -> bytes:
    if not hex_key:
        raise ValueError(f"{nome} não definida no ambiente.")
    b = bytes.fromhex(hex_key)
    if len(b) != 32:
        raise ValueError(f"{nome} precisa ter 32 bytes (64 caracteres hex).")
    return b


def _chave_dados() -> bytes:
    return _chave(get_settings().data_encryption_key, "DATA_ENCRYPTION_KEY")


def _chave_ia() -> bytes:
    return _chave(get_settings().ai_master_encryption_key, "AI_MASTER_ENCRYPTION_KEY")


def _cifrar(texto: str, chave: bytes) -> str:
    if texto == "":
        return ""
    nonce = os.urandom(NONCE_BYTES)
    dado = AESGCM(chave).encrypt(nonce, texto.encode(), None)
    return (nonce + dado).hex()


def _decifrar(cifrado: str, chave: bytes) -> str:
    if cifrado == "":
        return ""
    bruto = bytes.fromhex(cifrado)
    return AESGCM(chave).decrypt(bruto[:NONCE_BYTES], bruto[NONCE_BYTES:], None).decode()


# --- Dado pessoal (CPF) ---
def cifrar(texto: str) -> str:
    return _cifrar(texto, _chave_dados())


def decifrar(cifrado: str) -> str:
    return _decifrar(cifrado, _chave_dados())


def indice_deterministico(valor: str, rotulo: str) -> str:
    chave = hashlib.sha256(_chave_dados() + rotulo.encode()).digest()
    return hmac.new(chave, valor.encode(), hashlib.sha256).hexdigest()


# --- Chave de API das conexões de IA ---
def cifrar_ia(texto: str) -> str:
    return _cifrar(texto, _chave_ia())


def decifrar_ia(cifrado: str) -> str:
    return _decifrar(cifrado, _chave_ia())


def mascarar_chave(plain: str) -> str:
    """Só os 4 últimos. É o que a API/tela mostram — chave inteira nunca aparece."""
    return f"****{plain[-4:]}" if len(plain) >= 4 else ""
