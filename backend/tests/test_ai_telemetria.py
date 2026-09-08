"""Telemetria por conexão: agrega tokens/requisições/erros/tempo e deriva custo.

A cotação USD→BRL é monkeypatchada (o código real busca na rede; o teste não
deve depender de internet). Cria plataforma+conexão+logs no banco de teste e
limpa pelo id.
"""

from app.db.models import AiCallLog, AiConnection, AiPlatform
from app.db.session import SessionLocal
from app.modules.ai_registry import telemetria


def test_resumo_por_conexao_agrega_e_deriva_custo(monkeypatch):
    monkeypatch.setattr(telemetria, "usd_brl", lambda: (5.0, "teste"))
    # preço vem do "provedor" (API), não de campo — aqui monkeypatchado
    monkeypatch.setattr(
        telemetria, "precos_da_plataforma",
        lambda plat: {"m": {"input": 0.5, "output": 1.0, "por_minuto": None, "type": "chat"}},
    )

    db = SessionLocal()
    plat = AiPlatform(titulo="__t_tele__", endpoint="https://x/v1", api_key_cifrada="x")
    db.add(plat)
    db.commit()
    db.refresh(plat)
    conn = AiConnection(
        platform_id=plat.id, nome="__modelo_tele__", modelo="m", categoria="texto",
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    cid = conn.id

    def _log(sucesso, pt, ct, erro=None):
        return AiCallLog(
            connection_id=cid, categoria="texto", origem="teste", modelo="m",
            sucesso=sucesso, latencia_ms=100,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=(pt + ct) if pt else None,
            erro=erro,
        )

    db.add_all([
        _log(True, 1000, 500),
        _log(True, 1000, 500),
        _log(False, None, None, erro="429 Too Many Requests"),
    ])
    db.commit()
    db.close()

    try:
        db = SessionLocal()
        res = telemetria.resumo_por_conexao(db)
        db.close()

        assert res["cotacao_usd_brl"] == 5.0
        linha = next(x for x in res["por_conexao"] if x["connection_id"] == cid)
        assert linha["requisicoes"] == 3
        assert linha["erros"] == 1
        assert linha["prompt_tokens"] == 2000
        assert linha["completion_tokens"] == 1000
        # custo: 2000/1e6*0.5 + 1000/1e6*1.0 = 0.002 USD; BRL = *5
        assert abs(linha["custo_usd"] - 0.002) < 1e-9
        assert abs(linha["custo_brl"] - 0.01) < 1e-9
        assert linha["tem_preco"] is True
        assert linha["preco"]["input"] == 0.5 and linha["preco"]["output"] == 1.0
        # gasto por hora/minuto de uso (seg=0.3): 0.002/(0.3/3600)=24 USD/h; /(0.3/60)=0.4 USD/min
        assert abs(linha["gasto_hora_usd"] - 24.0) < 1e-6
        assert abs(linha["gasto_min_usd"] - 0.4) < 1e-6
        # projeção: dia = hora×24, mês = hora×24×30
        assert abs(linha["gasto_dia_usd"] - 576.0) < 1e-6
        assert abs(linha["gasto_mes_usd"] - 17280.0) < 1e-6
        assert abs(linha["gasto_mes_brl"] - 17280.0 * 5.0) < 1e-6
        assert linha["ultimos_erros"] and linha["ultimos_erros"][0]["erro"].startswith("429")
        assert linha["segundos_uso"] == 0.3
    finally:
        db = SessionLocal()
        db.query(AiCallLog).filter(AiCallLog.connection_id == cid).delete()
        obj = db.get(AiPlatform, plat.id)  # cascata apaga a conexão
        if obj:
            db.delete(obj)
        db.commit()
        db.close()
