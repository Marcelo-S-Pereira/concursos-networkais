from fastapi.testclient import TestClient

from app.core.validadores import cpf_valido, telefone_valido
from app.main import app

CPF_VALIDO = "[CPF_TESTE_REMOVIDO]"  # dígitos verificadores corretos, pessoa inexistente


def test_cpf_rejeita_digito_errado_e_repetido():
    assert cpf_valido(CPF_VALIDO)
    assert not cpf_valido("[CPF_INVALIDO_EXEMPLO]")
    assert not cpf_valido("[CPF_INVALIDO_EXEMPLO]")


def test_telefone_exige_ddd_e_nono_digito():
    assert telefone_valido("(11) 98765-4321")
    assert telefone_valido("[TELEFONE_TESTE_REMOVIDO]")
    assert not telefone_valido("11987654")
    assert not telefone_valido("(11) 88765-4321")  # celular sem o 9


def test_rota_protegida_exige_sessao():
    with TestClient(app) as client:
        assert client.get("/api/v1/auth/me").status_code == 401


def test_cadastro_recusa_cpf_invalido():
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/cadastro",
            json={
                "nome": "Fulano de Tal",
                "email": "naoexiste@exemplo.com",
                "cpf": "[CPF_INVALIDO_EXEMPLO]",
                "telefone": "[TELEFONE_TESTE_REMOVIDO]",
            },
        )
        assert res.status_code == 422


def test_codigo_errado_nao_entra():
    with TestClient(app) as client:
        res = client.post("/api/v1/auth/login/verificar", json={"email": "ninguem@exemplo.com", "codigo": "000000"})
        assert res.status_code == 401
        assert res.json()["detail"] == "Código inválido ou expirado."


def test_cpf_vai_cifrado_e_volta_mascarado():
    from app.core.crypto import cifrar, decifrar
    from app.core.validadores import mascarar_cpf

    cifrado = cifrar("[CPF_TESTE_REMOVIDO]")
    assert "[CPF_TESTE_REMOVIDO]" not in cifrado          # não dá para ler no banco
    assert decifrar(cifrado) == "[CPF_TESTE_REMOVIDO]"    # mas o sistema recupera
    assert mascarar_cpf("[CPF_TESTE_REMOVIDO]") == "***.***.777-35"


def test_cpf_do_dono_pode_abrir_varias_contas_mas_de_terceiro_continua_unico():
    """[102]: exceção só para o CPF do próprio superadmin (teste), não para
    CPF alheio — a unicidade normal continua valendo para todo o resto."""
    from app.core.crypto import cifrar, indice_deterministico
    from app.db.models import User
    from app.db.session import SessionLocal

    CPF_DONO = "[CPF_TESTE_REMOVIDO]"
    CPF_TERCEIRO = "[CPF_TESTE_REMOVIDO]"
    db = SessionLocal()
    dono = User(
        nome="Dono Teste",
        email="dono_teste_102@example.com",
        cpf_cifrado=cifrar(CPF_DONO),
        cpf_indice=indice_deterministico(CPF_DONO, "cpf"),
        telefone="[TELEFONE_TESTE_REMOVIDO]",
        role="superadmin",
    )
    terceiro = User(
        nome="Terceiro Teste",
        email="terceiro_teste_102@example.com",
        cpf_cifrado=cifrar(CPF_TERCEIRO),
        cpf_indice=indice_deterministico(CPF_TERCEIRO, "cpf"),
        telefone="[TELEFONE_TESTE_REMOVIDO]",
        role="aluno",
    )
    db.add_all([dono, terceiro])
    db.commit()
    dono_id, terceiro_id = dono.id, terceiro.id

    try:
        with TestClient(app) as client:
            # o próprio CPF do dono, e-mail diferente: permitido (conta de teste)
            r1 = client.post(
                "/api/v1/auth/cadastro",
                json={
                    "nome": "Conta de Teste do Dono",
                    "email": "conta_teste_dono_102@example.com",
                    "cpf": CPF_DONO,
                    "telefone": "[TELEFONE_TESTE_REMOVIDO]",
                },
            )
            assert r1.status_code == 201, r1.text

            # o CPF de um terceiro (não-superadmin) continua único
            r2 = client.post(
                "/api/v1/auth/cadastro",
                json={
                    "nome": "Outra Pessoa",
                    "email": "outra_pessoa_102@example.com",
                    "cpf": CPF_TERCEIRO,
                    "telefone": "[TELEFONE_TESTE_REMOVIDO]",
                },
            )
            assert r2.status_code == 409, r2.text
    finally:
        db.query(User).filter(
            User.id.in_(
                [dono_id, terceiro_id]
                + [
                    u.id
                    for u in db.query(User)
                    .filter(User.email == "conta_teste_dono_102@example.com")
                    .all()
                ]
            )
        ).delete(synchronize_session=False)
        db.commit()
        db.close()
