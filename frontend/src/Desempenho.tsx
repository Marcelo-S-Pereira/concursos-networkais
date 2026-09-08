import { useEffect, useState } from "react"
import { api, type DesempenhoResumo } from "./api"

const ROTULO_MASTERY: Record<string, string> = {
    STRONG: "forte", CONSISTENT: "consistente", UNSTABLE: "instável",
    WEAK: "fraco", NOT_TESTED: "sem dados",
}

export default function Desempenho() {
    const [d, setD] = useState<DesempenhoResumo | null>(null)
    const [erro, setErro] = useState<string | null>(null)

    useEffect(() => { api.desempenho().then(setD).catch((e) => setErro(e instanceof Error ? e.message : "Falha")) }, [])

    if (erro) return <p className="falha">{erro}</p>
    if (!d) return <p className="neutro">Carregando…</p>

    const g = d.gamificacao
    const pctNivel = g.xp_para_proximo ? Math.round((g.xp_no_nivel / g.xp_para_proximo) * 100) : 0
    const semDados = d.mastery.length === 0

    return (
        <div>
            <p className="explica">
                Seu progresso consolidado, somando todos os simulados e revisões. Tudo vem dos seus dados —
                nada é inventado.
            </p>

            <div className="cartao gamif">
                <div className="gamif-topo">
                    <div className="gamif-nivel"><span className="nv">Nível {g.nivel}</span><span className="xp">{g.xp} XP</span></div>
                    <div className="gamif-streak">🔥 {g.streak_dias} {g.streak_dias === 1 ? "dia" : "dias"} seguidos</div>
                </div>
                <div className="barra"><div className="preenche" style={{ width: `${pctNivel}%` }} /></div>
                <p className="dica">{g.xp_no_nivel}/{g.xp_para_proximo} XP para o próximo nível · {g.acertos} acertos · {g.simulados} simulados · {g.revisoes} revisões</p>
            </div>

            {semDados ? (
                <p className="neutro">Faça um simulado por tempo para começar a registrar seu desempenho consolidado.</p>
            ) : (
                <>
                    <div className="desempenho">
                        <h4>Mastery consolidado por disciplina</h4>
                        {d.mastery.map((e) => (
                            <div key={e.enfase} className="linha-enfase">
                                <span className="enf-nome">{e.enfase}</span>
                                <span className="enf-num">{e.acertos}/{e.total}</span>
                                <div className="barra"><div className="preenche" style={{ width: `${e.percentual}%` }} /></div>
                                <span className="enf-pct">{e.percentual}%</span>
                                <span className={`mastery ${e.mastery.toLowerCase()}`}>{ROTULO_MASTERY[e.mastery] ?? e.mastery}</span>
                            </div>
                        ))}
                    </div>

                    <div className="desempenho">
                        <h4>Dificuldade por disciplina <span className="dica">(quanto você erra)</span></h4>
                        {d.dificuldade.map((x) => (
                            <div key={x.enfase} className="linha-tempo">
                                <span className="enf-nome">{x.enfase}</span>
                                <span className="enf-tempo">{x.erro_pct}% de erro · {x.tentativas} tentativas</span>
                                <span className={`dif dif-${x.dificuldade === "difícil" ? "alta" : x.dificuldade === "média" ? "media" : "baixa"}`}>{x.dificuldade}</span>
                            </div>
                        ))}
                    </div>
                </>
            )}

            <div className="cartao">
                <h4 style={{ margin: "0 0 6px" }}>Eficácia do macete</h4>
                {d.macete.acerto_pos_macete_pct != null ? (
                    <p><strong>{d.macete.acerto_pos_macete_pct}%</strong> de acerto nas revisões das {d.macete.com_macete} questões em que você recebeu macete ({d.macete.revisoes_avaliadas} revisões avaliadas).</p>
                ) : (
                    <p className="neutro">{d.macete.observacao}</p>
                )}
            </div>
        </div>
    )
}
