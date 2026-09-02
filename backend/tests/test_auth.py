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
