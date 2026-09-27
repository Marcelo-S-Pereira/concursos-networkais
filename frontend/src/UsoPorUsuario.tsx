import { useEffect, useState } from "react"
import { api, type Dinheiro, type ConsumoResumo, type UsoTotais } from "./api"

/** [170] Consumo de IA por ferramenta e por usuário, na unidade da API. Serve para
 *  DEFINIR limites com dado real (nada aqui aplica limite). O custo vem do uso ×
 *  preço da API no momento da leitura. */

const ROTULO: Record<string, string> = {
    chat_estudo: "Chat de estudo",
    tutor_ia: "Tutor IA",
    tutor_ia_tempo_real: "Tutor IA · Tempo real",
    simulado_tutor: "Explicar (simulado)",
    gemeas: "Questões gêmeas",
    passo_a_passo: "Passo a passo",
    admin: "Admin / biblioteca",
    sem_ferramenta: "Histórico (antes do registro)",
}
const rotulo = (f: string) => ROTULO[f] ?? f

const num = (v: number) => v.toLocaleString("pt-BR")

/** Custos por mensagem são frações de centavo: 2 casas esconderiam tudo. */
function brl(v: number) {
    const casas = v >= 1 ? 2 : v >= 0.1 ? 3 : 4
    return `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas })}`
}
const dinheiro = (d: Dinheiro | null | undefined) => (d ? brl(d.brl) : "—")

function unidades(t: UsoTotais) {
    const partes: string[] = []
    if (t.tokens_in || t.tokens_out) partes.push(`${num(t.tokens_in)} / ${num(t.tokens_out)} tokens`)
    if (t.stt_seg) partes.push(`${num(t.stt_seg)} s de voz ouvida`)
    if (t.tts_chars) partes.push(`${num(t.tts_chars)} caracteres falados`)
    return partes.join(" · ") || "—"
}

export default function CardUso() {
    const [dias, setDias] = useState(7)
    const [r, setR] = useState<ConsumoResumo | null>(null)
    const [erro, setErro] = useState("")

    async function carregar(d = dias) {
        setErro("")
        try { setR(await api.adminUsoResumo(d)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao carregar o uso.") }
    }
    useEffect(() => { void carregar() }, [dias]) // eslint-disable-line react-hooks/exhaustive-deps

    const dist = r?.distribuicao_clientes
    const semDados = !dist || dist.custo_por_usuario_dia.n === 0

    return (
        <div className="cartao">
            <div className="saude-cab">
                <strong>Uso de IA por usuário e ferramenta</strong>
                <button className="link" onClick={() => carregar()} title="Atualizar">↻</button>
            </div>
            <div className="uso-filtro">
                <span className="dica">Período:</span>
                {[7, 14, 30, 90].map((d) => (
                    <button key={d} className={d === dias ? "" : "secundario"} onClick={() => setDias(d)}>{d} dias</button>
                ))}
            </div>
            {erro && <p className="erro">{erro}</p>}
            {!r && !erro && <p className="dica">Carregando…</p>}

            {r && (
                <>
                    <div className="uso-grade">
                        <div className="uso-item destaque">
                            <span className="uso-num">{brl(r.total.brl)}</span>
                            <span className="uso-rot">gasto no período (US$ {r.total.usd.toFixed(2)})</span>
                        </div>
                        <div className="uso-item">
                            <span className="uso-num">{semDados ? "—" : dinheiro(dist!.custo_por_usuario_dia.p50)}</span>
                            <span className="uso-rot">cliente típico, por dia (mediana)</span>
                        </div>
                        <div className="uso-item">
                            <span className="uso-num">{semDados ? "—" : dinheiro(dist!.custo_por_usuario_dia.p90)}</span>
                            <span className="uso-rot">os 10% que mais usam, por dia (p90)</span>
                        </div>
                        <div className="uso-item">
                            <span className="uso-num">{dist?.acoes_por_usuario_dia.p50 == null ? "—" : Math.round(dist.acoes_por_usuario_dia.p50)}</span>
                            <span className="uso-rot">ações por cliente por dia (mediana)</span>
                        </div>
                    </div>
                    <p className="dica">
                        {semDados
                            ? "Ainda não há uso de clientes com registro por ação. Os números do cliente típico aparecem conforme as pessoas usam (dono e vitalício ficam de fora da conta)."
                            : `Base: ${dist!.custo_por_usuario_dia.n} dia(s) de uso de ${dist!.usuarios_com_uso} cliente(s). Amostra pequena mostra tendência, não regra.`}
                    </p>

                    <h4 style={{ margin: "8px 0 2px" }}>Por ferramenta</h4>
                    <div className="tabela-uso-rolagem">
                        <table className="tabela-uso">
                            <thead>
                                <tr>
                                    <th>Ferramenta</th><th>Ações</th><th>Chamadas</th><th>Custo</th>
                                    <th>Custo/ação (mediana)</th><th>Custo/ação (p90)</th><th className="col-uso">Uso na unidade da API</th>
                                </tr>
                            </thead>
                            <tbody>
                                {r.ferramentas.map((f) => (
                                    <tr key={f.ferramenta}>
                                        <td>{rotulo(f.ferramenta)}</td>
                                        <td>{f.ferramenta === "sem_ferramenta" ? "—" : `${f.acoes}${f.acoes_falhas ? ` (+${f.acoes_falhas} sem resposta)` : ""}`}</td>
                                        <td>{f.chamadas}{f.falhas ? ` (${f.falhas} falhas)` : ""}</td>
                                        <td>{brl(f.custo.brl)}</td>
                                        <td>{dinheiro(f.custo_por_acao_clientes.p50)}</td>
                                        <td>{dinheiro(f.custo_por_acao_clientes.p90)}</td>
                                        <td className="col-uso">{unidades(f)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <h4 style={{ margin: "10px 0 2px" }}>Por usuário</h4>
                    <div style={{ display: "grid", gap: 6, gridTemplateColumns: "minmax(0, 1fr)" }}>
                        {r.usuarios.map((u) => (
                            <details key={u.user_id ?? "sem"} className="uso-usuario">
                                <summary>
                                    <span className="uso-quem">{u.nome}</span>
                                    {u.sem_limites && <span className="selo-livre" title="Dono ou vitalício: fora das distribuições">livre</span>}
                                    <span className="uso-soma">{brl(u.total.custo.brl)} · {u.total.chamadas} chamadas</span>
                                </summary>
                                <div className="tabela-uso-rolagem">
                                    <table className="tabela-uso">
                                        <thead><tr><th>Ferramenta</th><th>Ações</th><th>Custo</th><th className="col-uso">Uso na unidade da API</th></tr></thead>
                                        <tbody>
                                            {u.por_ferramenta.map((f) => (
                                                <tr key={f.ferramenta}>
                                                    <td>{rotulo(f.ferramenta)}</td>
                                                    <td>{f.ferramenta === "sem_ferramenta" ? "—" : f.acoes}</td>
                                                    <td>{brl(f.custo.brl)}</td>
                                                    <td className="col-uso">{unidades(f)}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                                {u.email && <p className="dica" style={{ margin: "4px 0 0" }}>{u.email} · {u.dias_ativos} dia(s) ativo(s)</p>}
                            </details>
                        ))}
                    </div>

                    <p className="dica">
                        Câmbio: US$ 1 = R$ {r.cotacao.usd_brl.toFixed(2)} ({r.cotacao.fonte}).
                        {" "}{r.notas.join(" ")}
                    </p>
                </>
            )}
        </div>
    )
}
