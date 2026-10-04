from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import usuario_atual
from app.core.validadores import cpf_valido, telefone_valido
from app.db.models import User
from app.db.session import SessionLocal, get_db
from app.main import app

CPF_VALIDO = "111" + "444" + "777" + "35"  # dígitos verificadores corretos, pessoa inexistente
CPF_VALIDO_FORMATADO = "111." + "444." + "777-" + "35"
CPF_INVALIDO = "123" + "456" + "789" + "00"
CPF_REPETIDO = "111" + "111" + "111" + "11"
CPF_DONO_TESTE = "529" + "982" + "247" + "25"
CPF_TERCEIRO_TESTE = "390" + "533" + "447" + "05"
TELEFONE_TESTE = "11" + "98765" + "4321"
TELEFONE_TESTE_2 = "11" + "98765" + "4322"
TELEFONE_TESTE_3 = "11" + "98765" + "4323"
TELEFONE_TESTE_4 = "11" + "98765" + "4324"
TELEFONE_FIXO_TESTE = "11" + "3333" + "4444"


def test_cpf_rejeita_digito_errado_e_repetido():
    assert cpf_valido(CPF_VALIDO)
    assert not cpf_valido(CPF_INVALIDO)
    assert not cpf_valido(CPF_REPETIDO)


def test_telefone_exige_ddd_e_nono_digito():
    assert telefone_valido("(11) " + "98765-" + "4321")
    assert telefone_valido(TELEFONE_FIXO_TESTE)
    assert not telefone_valido("11" + "987654")
    assert not telefone_valido("(11) " + "88765-" + "4321")  # celular sem o 9


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
                "cpf": CPF_INVALIDO,
                "telefone": TELEFONE_TESTE,
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

    cifrado = cifrar(CPF_VALIDO)
    assert CPF_VALIDO not in cifrado          # não dá para ler no banco
    assert decifrar(cifrado) == CPF_VALIDO    # mas o sistema recupera
    assert mascarar_cpf(CPF_VALIDO) == "***.***.777-35"


def test_cpf_do_dono_pode_abrir_varias_contas_mas_de_terceiro_continua_unico():
    """[102]: exceção só para o CPF do próprio superadmin (teste), não para
    CPF alheio — a unicidade normal continua valendo para todo o resto."""
    from app.core.crypto import cifrar, indice_deterministico
    from app.db.models import User
    from app.db.session import SessionLocal

    CPF_DONO = CPF_DONO_TESTE
    CPF_TERCEIRO = CPF_TERCEIRO_TESTE
    db = SessionLocal()
    dono = User(
        nome="Dono Teste",
        email="dono_teste_102@example.com",
        cpf_cifrado=cifrar(CPF_DONO),
        cpf_indice=indice_deterministico(CPF_DONO, "cpf"),
        telefone=TELEFONE_TESTE,
        role="superadmin",
    )
    terceiro = User(
        nome="Terceiro Teste",
        email="terceiro_teste_102@example.com",
        cpf_cifrado=cifrar(CPF_TERCEIRO),
        cpf_indice=indice_deterministico(CPF_TERCEIRO, "cpf"),
        telefone=TELEFONE_TESTE_2,
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
                    "telefone": TELEFONE_TESTE_3,
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
                    "telefone": TELEFONE_TESTE_4,
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


# --- [118]: login por senha, opcional, ao lado do código por e-mail ---

def _usuario_118(sufixo: str) -> User:
    from app.core.crypto import cifrar, indice_deterministico

    db = SessionLocal()
    u = User(nome="Teste 118", email=f"t118_{sufixo}@testelocal.dev", cpf_cifrado=cifrar("[CPF_TESTE_REMOVIDO]"),
             cpf_indice=indice_deterministico(f"[CPF_TESTE_REMOVIDO]{sufixo}", "cpf"), telefone="x", role="aluno")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.close()
    return u


def _limpar_118(uid: int) -> None:
    db = SessionLocal()
    db.query(User).filter(User.id == uid).delete()
    db.commit()
    db.close()


def _override_logado(uid: int):
    """Mesmo padrão de `usuario_atual`, mas sem exigir sessão real — E
    compartilhando a MESMA sessão do `db: Session = Depends(get_db)` da
    rota (senão `db.commit()`/`db.refresh(user)` da rota quebram, porque
    `user` e `db` seriam de sessões diferentes — achado ao testar de
    verdade, não é bug da rota, é exigência de como o override precisa
    ser montado)."""
    def _fake(db: Session = Depends(get_db)) -> User:
        return db.get(User, uid)
    return _fake


def test_login_senha_sem_senha_cadastrada_da_401():
    u = _usuario_118("sem_senha")
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "qualquer123"})
        assert r.status_code == 401
        assert "não tem senha" in r.json()["detail"]
    finally:
        _limpar_118(u.id)


def test_cadastrar_senha_curta_da_422():
    u = _usuario_118("curta")
    app.dependency_overrides[usuario_atual] = _override_logado(u.id)
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/auth/senha/cadastrar", json={"senha": "123"})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_118(u.id)


def test_ciclo_completo_cadastrar_logar_desligar_religar():
    u = _usuario_118("ciclo")
    app.dependency_overrides[usuario_atual] = _override_logado(u.id)
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/auth/senha/cadastrar", json={"senha": "MinhaSenhaForte123"})
            assert r.status_code == 200, r.text
            assert r.json()["tem_senha"] is True
            assert r.json()["senha_habilitada"] is True

            r = client.post("/api/v1/auth/senha/alternar", json={"habilitada": False})
            assert r.json()["senha_habilitada"] is False

            r = client.post("/api/v1/auth/senha/alternar", json={"habilitada": True})
            assert r.json()["senha_habilitada"] is True

            r = client.post("/api/v1/auth/senha/dispensar-prompt")
            assert r.json()["senha_prompt_dispensado"] is True
        app.dependency_overrides.pop(usuario_atual, None)

        # login por senha de verdade — rota pública, sem override
        with TestClient(app) as client:
            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "MinhaSenhaForte123"})
            assert r.status_code == 200, r.text
            assert r.json()["email"] == u.email

            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "errada"})
            assert r.status_code == 401
            assert r.json()["detail"] == "E-mail ou senha incorretos."
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_118(u.id)


def test_alternar_liga_sem_senha_cadastrada_da_422():
    u = _usuario_118("liga_sem_senha")
    app.dependency_overrides[usuario_atual] = _override_logado(u.id)
    try:
        with TestClient(app) as client:
            r = client.post("/api/v1/auth/senha/alternar", json={"habilitada": True})
        assert r.status_code == 422
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_118(u.id)


def test_desligar_senha_impede_login_por_senha_mas_mantem_o_hash():
    u = _usuario_118("desliga_bloqueia")
    app.dependency_overrides[usuario_atual] = _override_logado(u.id)
    try:
        with TestClient(app) as client:
            client.post("/api/v1/auth/senha/cadastrar", json={"senha": "MinhaSenhaForte123"})
            client.post("/api/v1/auth/senha/alternar", json={"habilitada": False})
        app.dependency_overrides.pop(usuario_atual, None)

        with TestClient(app) as client:
            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "MinhaSenhaForte123"})
        assert r.status_code == 401
        assert "não tem senha" in r.json()["detail"]

        # religando (sem recadastrar), a MESMA senha antiga volta a funcionar —
        # prova que o hash não foi apagado ao desligar
        app.dependency_overrides[usuario_atual] = _override_logado(u.id)
        with TestClient(app) as client:
            client.post("/api/v1/auth/senha/alternar", json={"habilitada": True})
        app.dependency_overrides.pop(usuario_atual, None)

        with TestClient(app) as client:
            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "MinhaSenhaForte123"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_118(u.id)


def test_cinco_senhas_erradas_bloqueia_temporariamente():
    u = _usuario_118("lockout")
    app.dependency_overrides[usuario_atual] = _override_logado(u.id)
    try:
        with TestClient(app) as client:
            client.post("/api/v1/auth/senha/cadastrar", json={"senha": "MinhaSenhaForte123"})
        app.dependency_overrides.pop(usuario_atual, None)

        with TestClient(app) as client:
            for _ in range(5):
                r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "errada"})
            assert r.status_code == 401  # a 5ª ainda é "senha incorreta"

            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "errada"})
            assert r.status_code == 429  # a 6ª já está bloqueada

            # nem a senha CERTA entra enquanto bloqueado — força esperar/usar código
            r = client.post("/api/v1/auth/login/senha", json={"email": u.email, "senha": "MinhaSenhaForte123"})
            assert r.status_code == 429
    finally:
        app.dependency_overrides.pop(usuario_atual, None)
        _limpar_118(u.id)
