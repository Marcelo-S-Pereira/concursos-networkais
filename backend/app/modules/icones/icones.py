"""[128]: escolha do admin de qual ícone usar em cada slot — biblioteca
curada (nome de um ícone gerado em `iconesBiblioteca.tsx`, sem verificação
aqui contra a lista real do front — front ignora nome desconhecido e cai
no texto padrão, nunca quebra) ou upload de arquivo próprio
(`uploads/icones/`, fora do git). Sem linha em `component_icons` pra um
slot = usa o texto padrão (comportamento de hoje, inalterado)."""

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ComponentIcon
from app.modules.icones.catalogo import SLOTS

UPLOADS_DIR = Path(__file__).resolve().parents[3].parent / "uploads" / "icones"

EXTENSOES_PERMITIDAS = {"png", "svg", "jpg", "jpeg", "webp"}
TAMANHO_MAX_BYTES = 1_000_000  # 1MB — é ícone, não precisa de mais


def estado(db: Session) -> dict[str, dict]:
    """slot -> {tipo, valor} para todos que têm escolha feita — é o que
    todo usuário (não só admin) consulta pra saber o que renderizar."""
    linhas = db.execute(select(ComponentIcon)).scalars().all()
    return {r.slot: {"tipo": r.tipo, "valor": r.valor} for r in linhas}


def catalogo_com_estado(db: Session) -> list[dict]:
    """Para o admin: os slots do catálogo + o que está escolhido (ou None)."""
    atuais = estado(db)
    return [{"slot": slot, **info, "atual": atuais.get(slot)} for slot, info in SLOTS.items()]


def _apagar_arquivo_antigo(db: Session, slot: str) -> None:
    linha = db.get(ComponentIcon, slot)
    if linha and linha.tipo == "upload":
        (UPLOADS_DIR / linha.valor).unlink(missing_ok=True)


def definir_biblioteca(db: Session, slot: str, nome_icone: str) -> None:
    if slot not in SLOTS:
        raise ValueError(f"Slot desconhecido: {slot!r}")
    if not nome_icone.strip():
        raise ValueError("Escolha um ícone da biblioteca.")
    _apagar_arquivo_antigo(db, slot)
    linha = db.get(ComponentIcon, slot)
    if linha:
        linha.tipo, linha.valor = "biblioteca", nome_icone.strip()
    else:
        db.add(ComponentIcon(slot=slot, tipo="biblioteca", valor=nome_icone.strip()))
    db.commit()


def definir_upload(db: Session, slot: str, nome_arquivo: str, dados: bytes) -> str:
    if slot not in SLOTS:
        raise ValueError(f"Slot desconhecido: {slot!r}")
    ext = nome_arquivo.rsplit(".", 1)[-1].lower() if "." in nome_arquivo else ""
    if ext not in EXTENSOES_PERMITIDAS:
        raise ValueError(f"Formato não suportado — use um de {sorted(EXTENSOES_PERMITIDAS)}.")
    if not dados:
        raise ValueError("Arquivo vazio.")
    if len(dados) > TAMANHO_MAX_BYTES:
        raise ValueError("Arquivo grande demais (máx. 1MB — é só um ícone).")
    _apagar_arquivo_antigo(db, slot)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    nome_salvo = f"{slot.replace('.', '_')}.{ext}"
    (UPLOADS_DIR / nome_salvo).write_bytes(dados)
    linha = db.get(ComponentIcon, slot)
    if linha:
        linha.tipo, linha.valor = "upload", nome_salvo
    else:
        db.add(ComponentIcon(slot=slot, tipo="upload", valor=nome_salvo))
    db.commit()
    return nome_salvo


def remover(db: Session, slot: str) -> None:
    _apagar_arquivo_antigo(db, slot)
    linha = db.get(ComponentIcon, slot)
    if linha:
        db.delete(linha)
        db.commit()


def caminho_upload(nome_arquivo: str) -> Path:
    return UPLOADS_DIR / nome_arquivo
