"""Ingere a prova Transpetro Dutos e Terminais 2023.

Uso: ./.venv/bin/python scripts_ingerir_prova.py
"""

from app.db.models import Exam
from app.db.session import SessionLocal
from app.modules.ingestion.servico import ingerir

PASTA = "../provas_pdf_gabarito"

# 1-10 Português, 11-20 Matemática, 21-60 Específicos (Dutos e Terminais)
DISCIPLINAS = {}
for n in range(1, 11):
    DISCIPLINAS[n] = "Língua Portuguesa"
for n in range(11, 21):
    DISCIPLINAS[n] = "Matemática"
for n in range(21, 61):
    DISCIPLINAS[n] = "Conhecimentos Específicos"


def main() -> None:
    with SessionLocal() as db:
        # evita duplicar se rodar de novo
        ja = db.query(Exam).filter(Exam.orgao == "Transpetro", Exam.cargo.like("%Dutos%")).first()
        if ja:
            print(f"Prova já ingerida (exam id={ja.id}). Apague antes se quiser reimportar.")
            return
        exam = ingerir(
            db,
            caminho_prova=f"{PASTA}/dutos_e_terminais.pdf",
            caminho_gabarito=f"{PASTA}/gabarito.pdf",
            banca="Cesgranrio",
            orgao="Transpetro",
            cargo="Dutos e Terminais",
            ano=2023,
            coluna_gabarito=0,
            disciplinas=DISCIPLINAS,
        )
        n = len(exam.questoes)
        com_gab = len([q for q in exam.questoes if q.gabarito])
        rev = len([q for q in exam.questoes if q.confianca < 1.0])
        print(f"Prova ingerida: exam id={exam.id}, {n} questões, {com_gab} com gabarito, {rev} para revisar.")


if __name__ == "__main__":
    main()
