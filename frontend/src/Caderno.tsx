import DOMPurify from "dompurify"
import { useEffect, useRef, useState } from "react"
import { api, type Exame, type Explicacao, type Questao, type ResultadoSimulado, type SimResultado, type SimRun } from "./api"

const LETRAS = ["A", "B", "C", "D", "E"]
const MASTERY_ROTULO: Record<string, string> = {
    NOT_TESTED: "não testado", WEAK: "fraco", UNSTABLE: "instável",
    CONSISTENT: "consistente", STRONG: "forte", CONSOLIDATED: "consolidado", FORGETTING: "esquecendo",
}
function rotuloMastery(m: string) { return MASTERY_ROTULO[m] ?? m.toLowerCase() }

export default function Caderno({ modo }: { modo: "celular" | "computador" }) {
    const [exames, setExames] = useState<Exame[] | null>(null)
    const [exameId, setExameId] = useState<number | null>(null)

    useEffect(() => {
        api.exames().then((e) => { setExames(e); if (e.length) setExameId(e[0].id) }).catch(() => setExames([]))
    }, [])

    if (!exames) return <p className="neutro">Carregando…</p>
    if (!exames.length) return <p className="neutro">Nenhuma prova disponível ainda.</p>
    return (
        <div>
            <div className="seletor-exame">
                {exames.map((e) => (
                    <button key={e.id} className={e.id === exameId ? "ativa" : ""} onClick={() => setExameId(e.id)}>
                        {e.orgao} · {e.cargo}
                    </button>
                ))}
            </div>
            {exameId && <Simulado key={exameId} exameId={exameId} modo={modo} />}
        </div>
    )
}

function Simulado({ exameId, modo }: { exameId: number; modo: "celular" | "computador" }) {
    const [qs, setQs] = useState<Questao[] | null>(null)
    const [marcadas, setMarcadas] = useState<Record<number, Set<string>>>({})
    const [foraDoCampo, setForaDoCampo] = useState<Record<number, boolean>>({})
    const [resultado, setResultado] = useState<SimResultado | ResultadoSimulado | null>(null)

    // configurações do cartão
    const [tamanhoBolha, setTamanhoBolha] = useState(22)  // px — o usuário controla
    const [corCaneta, setCorCaneta] = useState<"#0b3d91" | "#111111">("#0b3d91")  // azul | preto

    // tempo
    const [run, setRun] = useState<SimRun | null>(null)
    const [restante, setRestante] = useState<number>(0)
    const [minutos, setMinutos] = useState(240)

    useEffect(() => {
        api.questoes(exameId).then((d) => setQs(d.filter((q) => !q.descartada))).catch(() => setQs([]))
    }, [exameId])

    // cronômetro do simulado por tempo
    useEffect(() => {
        if (!run || resultado) return
        const fim = new Date(run.deadline_at).getTime()
        const t = setInterval(() => {
            const s = Math.max(0, Math.round((fim - Date.now()) / 1000))
            setRestante(s)
            if (s <= 0) { clearInterval(t); entregar() }
        }, 250)
        return () => clearInterval(t)
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [run, resultado])

    if (!qs) return <p className="neutro">Carregando questões…</p>

    function marcar(qid: number, letra: string, fora: boolean) {
        if (fora) { setForaDoCampo((f) => ({ ...f, [qid]: true })); return }
        setMarcadas((m) => { const a = new Set(m[qid] ?? []); a.add(letra); return { ...m, [qid]: a } })
    }
    function limpar(qid: number) {
        setMarcadas((m) => { const c = { ...m }; delete c[qid]; return c })
        setForaDoCampo((f) => { const c = { ...f }; delete c[qid]; return c })
    }

    function respostasValidas(): Record<number, string> {
        // 1 marcação, dentro do campo. Fora do campo ou dupla marcação = não conta (errada).
        const r: Record<number, string> = {}
        for (const q of qs!) {
            const set = marcadas[q.id]
            if (set && set.size === 1 && !foraDoCampo[q.id]) r[q.id] = [...set][0]
        }
        return r
    }

    async function iniciarComTempo() {
        const r = await api.iniciarSimulado(exameId, minutos * 60)
        setRun(r)
        setMarcadas({}); setForaDoCampo({}); setResultado(null)
    }

    async function entregar() {
        const respostas = respostasValidas()
        if (run) setResultado(await api.entregarSimulado(run.simulation_id, respostas))
        else setResultado(await api.corrigir(exameId, respostas))
    }

    const anuladas = qs.filter((q) => (marcadas[q.id]?.size ?? 0) > 1 || foraDoCampo[q.id]).length
    const mm = String(Math.floor(restante / 60)).padStart(2, "0")
    const ss = String(restante % 60).padStart(2, "0")

    return (
        <div className="simulado">
            {run && !resultado && (
                <div className={`relogio-fixo ${restante < 60 ? "urgente" : ""}`}>
                    ⏱ {mm}:{ss}
                    <button className="entregar-mini" onClick={entregar}>Entregar</button>
                </div>
            )}
            <div className="coluna-questoes">
                {qs.map((q) => (
                    <article key={q.id} className="q-prova">
                        <header><strong>{q.numero}</strong> <span className="disc">{q.disciplina}</span></header>
                        {q.modo_exibicao === "imagem" && q.tem_figura ? (
                            <img className="figura questao-img" src={api.figuraUrl(q.id)} alt={`questão ${q.numero}`} />
                        ) : (
                            <>
                                {q.enunciado_col2 && q.enunciado_col2.trim() ? (
                                    <div className="enun-2col">
                                        <div className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado.replace(/\n\[figura:.*\]/, "")) }} />
                                        <div className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado_col2) }} />
                                    </div>
                                ) : (
                                    <p className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado.replace(/\n\[figura:.*\]/, "")) }} />
                                )}
                                {q.tem_figura && <img className="figura" src={api.figuraUrl(q.id)} alt="figura" />}
                                <ol className="alts-prova">
                                    {q.alternativas.map((a) => (
                                        <li key={a.letra}><b>{a.letra})</b> <span dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(a.texto) }} /></li>
                                    ))}
                                </ol>
                            </>
                        )}
                        {modo === "celular" && !resultado && (
                            <SeletorGrande cor={corCaneta}
                                marcada={[...(marcadas[q.id] ?? [])][0]}
                                aoMarcar={(L) => setMarcadas((m) => ({ ...m, [q.id]: new Set([L]) }))} />
                        )}
                        <Rascunho cor={corCaneta} />
                        {resultado && (
                            <div className="pos-resultado">
                                <p className={resultado.resultado[q.id] ? "acertou" : "errou"}>
                                    {resultado.resultado[q.id] ? "✓ acertou" : "✕ errou"}
                                    {" · "}<button className="link" onClick={() => alert(`Gabarito da questão ${q.numero}: ${q.gabarito}`)}>ver gabarito</button>
                                </p>
                                <Explicar qid={q.id} respostaAluno={[...(marcadas[q.id] ?? [])][0] ?? null} />
                            </div>
                        )}
                    </article>
                ))}
            </div>

            <aside className="cartao-resposta">
                {!run && !resultado && (
                    <div className="config-teste">
                        <h3>Iniciar teste</h3>
                        <label className="cfg">Tempo (min)
                            <input type="number" min={1} value={minutos} onChange={(e) => setMinutos(Number(e.target.value))} />
                        </label>
                        <button className="entregar" onClick={iniciarComTempo}>▶ Iniciar simulado por tempo</button>
                        <p className="regra">Ou preencha e entregue sem tempo, treinando.</p>
                    </div>
                )}

                {run && !resultado && (
                    <div className={`relogio ${restante < 60 ? "urgente" : ""}`}>⏱ {mm}:{ss}</div>
                )}

                <h3>Cartão-resposta</h3>
                <div className="cfg-cartao">
                    <label className="cfg">Tamanho do campo
                        <input type="range" min={12} max={34} value={tamanhoBolha} onChange={(e) => setTamanhoBolha(Number(e.target.value))} />
                        <span>{tamanhoBolha}px</span>
                    </label>
                    <div className="cfg-cor">
                        Caneta:
                        <button className={corCaneta === "#0b3d91" ? "sel" : ""} style={{ background: "#0b3d91" }} onClick={() => setCorCaneta("#0b3d91")} title="azul" />
                        <button className={corCaneta === "#111111" ? "sel" : ""} style={{ background: "#111111" }} onClick={() => setCorCaneta("#111111")} title="preto" />
                    </div>
                </div>
                <p className="regra">Preencha o círculo <b>inteiro</b> com a caneta. Marcar fora do campo, em branco ou dupla marcação = questão errada.</p>

                <div className="folha">
                    {qs.map((q) => {
                        const set = marcadas[q.id] ?? new Set()
                        const problema = set.size > 1 || foraDoCampo[q.id]
                        return (
                            <div key={q.id} className={`linha-cartao ${problema ? "anulada" : ""}`}>
                                <span className="num">{q.numero}</span>
                                {LETRAS.map((L) => (
                                    <Bolha key={L} tamanho={tamanhoBolha} cor={corCaneta} marcada={set.has(L)}
                                           bloqueado={!!resultado} aoMarcar={(fora) => marcar(q.id, L, fora)} />
                                ))}
                                {(set.size > 0 || foraDoCampo[q.id]) && !resultado &&
                                    <button className="limpa" onClick={() => limpar(q.id)} title="riscar/limpar">↺</button>}
                            </div>
                        )
                    })}
                </div>

                {!resultado ? (
                    <>
                        {anuladas > 0 && <p className="aviso">⚠ {anuladas} questão(ões) inválidas (fora do campo/dupla).</p>}
                        <button className="entregar" onClick={entregar}>Entregar cartão</button>
                    </>
                ) : (
                    <div>
                        <div className="placar">
                            <strong>{resultado.acertos}/{resultado.total}</strong> acertos
                            <span>({resultado.respondidas} respondidas · {resultado.percentual_bruto}%)</span>
                            {"encerrado_no_prazo" in resultado && !resultado.encerrado_no_prazo && <span className="aviso">entregue após o prazo</span>}
                        </div>
                        {"por_enfase" in resultado && (
                            <div className="desempenho">
                                <h4>Desempenho por ênfase</h4>
                                {resultado.por_enfase.map((e) => (
                                    <div key={e.enfase} className="linha-enfase">
                                        <span className="enf-nome">{e.enfase}</span>
                                        <span className="enf-num">{e.acertos}/{e.total}</span>
                                        <div className="barra"><div className="preenche" style={{ width: `${e.percentual}%` }} /></div>
                                        <span className="enf-pct">{e.percentual}%</span>
                                        <span className={`mastery ${e.mastery.toLowerCase()}`}>{rotuloMastery(e.mastery)}</span>
                                        {e.historico_pct != null && e.delta != null && (
                                            <span className="delta" title={`Histórico: ${e.historico_pct}% (N=${e.amostra_historico ?? "?"})`}>
                                                vs {e.historico_pct}% · {e.delta > 0 ? "+" : ""}{e.delta}pp {e.delta_rotulo}
                                            </span>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </aside>
        </div>
    )
}

// Rascunho por questão: papel para rabiscar com a caneta (mesa digitalizadora/mouse).
function Rascunho({ cor }: { cor: string }) {
    const ref = useRef<HTMLCanvasElement>(null)
    const desenhando = useRef(false)
    const [aberto, setAberto] = useState(false)

    function ponto(e: React.PointerEvent) {
        const c = ref.current!; const r = c.getBoundingClientRect()
        return { x: e.clientX - r.left, y: e.clientY - r.top }
    }
    function down(e: React.PointerEvent) {
        desenhando.current = true; (e.target as HTMLElement).setPointerCapture(e.pointerId)
        const ctx = ref.current!.getContext("2d")!; const p = ponto(e)
        ctx.strokeStyle = cor; ctx.lineWidth = 2; ctx.lineCap = "round"
        ctx.beginPath(); ctx.moveTo(p.x, p.y)
    }
    function move(e: React.PointerEvent) {
        if (!desenhando.current) return
        const ctx = ref.current!.getContext("2d")!; const p = ponto(e)
        ctx.lineTo(p.x, p.y); ctx.stroke()
    }
    function limpar() {
        const c = ref.current!; c.getContext("2d")!.clearRect(0, 0, c.width, c.height)
    }

    return (
        <div className="rascunho">
            <button className="link" onClick={() => setAberto((v) => !v)}>{aberto ? "▾ fechar rascunho" : "✏ rascunho"}</button>
            {aberto && (
                <div>
                    <canvas ref={ref} width={520} height={180} className="papel"
                        onPointerDown={down} onPointerMove={move} onPointerUp={() => (desenhando.current = false)} />
                    <button className="link" onClick={limpar}>limpar rascunho</button>
                </div>
            )}
        </div>
    )
}

// Bolha preenchível à caneta, com tamanho configurável. Detecta pintura FORA do
// círculo pequeno (marca inválida). Só conta como marcada com preenchimento real.
function Bolha({ tamanho, cor, marcada, bloqueado, aoMarcar }: {
    tamanho: number; cor: string; marcada: boolean; bloqueado: boolean; aoMarcar: (fora: boolean) => void
}) {
    const ref = useRef<HTMLCanvasElement>(null)
    const desenhando = useRef(false)
    const raio = tamanho / 2 - 1

    useEffect(() => {
        const c = ref.current!; const ctx = c.getContext("2d")!
        ctx.clearRect(0, 0, tamanho, tamanho)
        if (marcada) { ctx.fillStyle = cor; ctx.beginPath(); ctx.arc(tamanho / 2, tamanho / 2, raio, 0, Math.PI * 2); ctx.fill() }
    }, [marcada, tamanho, cor, raio])

    function pintar(e: React.PointerEvent) {
        if (bloqueado || marcada) return
        const c = ref.current!; const r = c.getBoundingClientRect()
        const x = e.clientX - r.left, y = e.clientY - r.top
        const ctx = c.getContext("2d")!
        ctx.fillStyle = cor; ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill()
        // distância ao centro: pintou fora do círculo pequeno?
        const dist = Math.hypot(x - tamanho / 2, y - tamanho / 2)
        if (dist > raio + 2) { aoMarcar(true); return }  // marca fora = inválida
        // quanto do círculo foi pintado
        const img = ctx.getImageData(0, 0, tamanho, tamanho).data
        let pint = 0, area = 0
        for (let i = 0; i < tamanho * tamanho; i++) {
            const px = i % tamanho, py = Math.floor(i / tamanho)
            if (Math.hypot(px - tamanho / 2, py - tamanho / 2) <= raio) { area++; if (img[i * 4 + 3] > 0) pint++ }
        }
        if (area && pint / area > 0.6) aoMarcar(false)
    }

    return (
        <canvas ref={ref} width={tamanho} height={tamanho} className="bolha"
            style={{ width: tamanho, height: tamanho }}
            onPointerDown={(e) => { desenhando.current = true; (e.target as HTMLElement).setPointerCapture(e.pointerId); pintar(e) }}
            onPointerMove={(e) => desenhando.current && pintar(e)}
            onPointerUp={() => (desenhando.current = false)} />
    )
}


// Celular: alternativas grandes na frente da questão, para preencher com o dedo.
function SeletorGrande({ cor, marcada, aoMarcar }: { cor: string; marcada: string | undefined; aoMarcar: (letra: string) => void }) {
    return (
        <div className="seletor-grande">
            {["A", "B", "C", "D", "E"].map((L) => (
                <button
                    key={L}
                    className={`bolha-grande ${marcada === L ? "cheia" : ""}`}
                    style={marcada === L ? { background: cor, borderColor: cor } : undefined}
                    onClick={() => aoMarcar(L)}
                >
                    {L}
                </button>
            ))}
        </div>
    )
}


// Tutor IA: gera diagnóstico, mini-aula e macete para a questão (sob demanda).
function Explicar({ qid, respostaAluno }: { qid: number; respostaAluno: string | null }) {
    const [exp, setExp] = useState<Explicacao | null>(null)
    const [carregando, setCarregando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function pedir() {
        setCarregando(true); setErro(null)
        try { setExp(await api.explicarIA(qid, respostaAluno)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha na IA") }
        finally { setCarregando(false) }
    }

    if (exp) {
        const t = exp.memory_trick
        return (
            <div className="explicacao">
                {exp.diagnosis && <p><b>Diagnóstico</b> <span className="tag-erro">{exp.error_type}</span><br />{exp.diagnosis}</p>}
                {exp.mini_lesson && <p><b>Mini-aula</b><br />{exp.mini_lesson}</p>}
                {(t.rapid_rule || t.steps.length > 0) && (
                    <div className="macete">
                        <b>Macete</b>
                        {t.memory_hook && <p>🧠 {t.memory_hook}</p>}
                        {t.rapid_rule && <p>⚡ {t.rapid_rule}</p>}
                        {t.steps.length > 0 && <ol>{t.steps.map((p, i) => <li key={i}>{p}</li>)}</ol>}
                        {t.applies_when && <p className="dica">Usar quando: {t.applies_when}</p>}
                        {t.warning && <p className="dica">Cuidado: {t.warning}</p>}
                    </div>
                )}
                {exp.review_recommendation && <p className="dica">Revisar: {exp.review_recommendation}</p>}
            </div>
        )
    }
    return (
        <div>
            <button className="ia" disabled={carregando} onClick={pedir}>{carregando ? "IA explicando…" : "✨ Explicar com IA"}</button>
            {erro && <span className="falha"> {erro}</span>}
        </div>
    )
}
