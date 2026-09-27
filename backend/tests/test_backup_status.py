"""[176]: o alarme do backup. O que importa: backup velho, backup que falhou e backup
que nunca rodou precisam gerar aviso; backup em dia não pode gerar ruído."""

from datetime import UTC, datetime, timedelta

from app.core import monitor
from app.core.monitor import problema_de_backup

AGORA = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def _status(tmp_path, texto: str):
    f = tmp_path / "status"
    f.write_text(texto)
    return f


def test_backup_recente_nao_gera_aviso(tmp_path):
    f = _status(tmp_path, f"OK {(AGORA - timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%SZ')} dump=28421639\n")
    assert problema_de_backup(f, AGORA) is None


def test_backup_velho_gera_aviso_com_a_idade(tmp_path):
    f = _status(tmp_path, f"OK {(AGORA - timedelta(hours=30)).strftime('%Y-%m-%dT%H:%M:%SZ')} dump=1\n")
    assert "30 h" in problema_de_backup(f, AGORA)


def test_falha_do_script_gera_aviso_com_o_motivo(tmp_path):
    f = _status(tmp_path, "FALHA 2026-09-27T03:45:10Z pg_dump falhou\n")
    aviso = problema_de_backup(f, AGORA)
    assert "FALHOU" in aviso and "pg_dump falhou" in aviso


def test_sem_registro_ou_ilegivel_gera_aviso(tmp_path):
    assert "nenhum backup" in problema_de_backup(tmp_path / "nao_existe", AGORA)
    assert "nenhum backup" in problema_de_backup(_status(tmp_path, ""), AGORA)
    assert "ilegível" in problema_de_backup(_status(tmp_path, "OK ontem dump=1\n"), AGORA)


def test_monitor_manda_um_email_e_nao_repete_dentro_do_intervalo(tmp_path, monkeypatch):
    f = _status(tmp_path, "FALHA 2026-09-27T03:45:10Z pg_dump falhou\n")
    monkeypatch.setattr(monitor, "STATUS_BACKUP", f)
    # o valor padrão do argumento foi fixado na definição: o monitor precisa ler o caminho atual
    monkeypatch.setattr(monitor, "problema_de_backup", lambda: problema_de_backup(f, AGORA))
    enviados: list[str] = []
    monkeypatch.setattr(monitor, "enviar_email", lambda para, assunto, corpo: enviados.append(assunto))
    monkeypatch.setattr(monitor, "_ultimo_alerta_backup", 0.0)

    class _Db:
        def execute(self, *_a, **_k):
            class _R:
                def scalars(self):
                    class _S:
                        def all(self_inner):
                            class _U:
                                email = "dono@teste.local"
                            return [_U()]
                    return _S()
            return _R()

    monitor._verificar_backup(_Db())
    monitor._verificar_backup(_Db())  # dentro do intervalo: não repete
    assert enviados == ["⚠ Backup do ConcurseiroIA com problema"]
