import DOMPurify from "dompurify"
import { useEffect, useRef, useState } from "react"
import { api, ApiError, type Exame, type Explicacao, type GemeaT, type Questao, type ResultadoSimulado, type SimResultado, type SimRun } from "./api"
import Feedback from "./Feedback"

const LETRAS = ["A", "B", "C", "D", "E"]
const MASTERY_ROTULO: Record<string, string> = {
    NOT_TESTED: "não testado", WEAK: "fraco", UNSTABLE: "instável",
    CONSISTENT: "consistente", STRONG: "forte", CONSOLIDATED: "consolidado", FORGETTING: "esquecendo",
}
function rotuloMastery(m: string) { return MASTERY_ROTULO[m] ?? m.toLowerCase() }

export default function Caderno({ modo }: { modo: "celular" | "computador" }) {
    const [exames, setExames] = useState<Exame[] | null>(null)
    // Recolhido por padrão — nada abre sozinho, o usuário escolhe (pedido do
    // usuário: antes o primeiro caderno abria sozinho).
    const [abertos, setAbertos] = useState<Set<number>>(new Set())
    const [jaAbertos, setJaAbertos] = useState<Set<number>>(new Set())  // já montados (mantém o estado do simulado ao recolher)
    // Filtro por toggle: null = mostra todos os cadernos (recolhidos); um id =
    // mostra só aquele (e já abre, é a intenção de escolher pra estudar nele).
    const [filtroId, setFiltroId] = useState<number | null>(null)

    useEffect(() => {
        api.exames().then(setExames).catch(() => setExames([]))
    }, [])

    function alternar(id: number) {
        setAbertos((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
        setJaAbertos((s) => new Set(s).add(id))
    }

    function escolherFiltro(id: number | null) {
        setFiltroId(id)
        if (id != null) { setAbertos(new Set([id])); setJaAbertos((s) => new Set(s).add(id)) }
    }

    if (!exames) return <p className="neutro">Carregando…</p>
    if (!exames.length) return <p className="neutro">Nenhuma prova disponível ainda.</p>
    const visiveis = filtroId == null ? exames : exames.filter((e) => e.id === filtroId)
    return (
        <div>
            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
                <Feedback ferramenta="simulado" />
            </div>
            {exames.length > 1 && (
                <div className="caderno-filtro" role="group" aria-label="Filtrar caderno">
                    <button className={filtroId == null ? "sel" : ""} onClick={() => escolherFiltro(null)}>Todos</button>
                    {exames.map((e) => (
                        <button key={e.id} className={filtroId === e.id ? "sel" : ""} onClick={() => escolherFiltro(e.id)}>
                            {e.orgao} · {e.cargo}
                        </button>
                    ))}
                </div>
            )}
            {visiveis.map((ex) => (
                <div key={ex.id} className={`caderno-linha ${abertos.has(ex.id) ? "aberto" : ""}`}>
                    <div className="caderno-cab" onClick={() => alternar(ex.id)}>
                        <span className="seta">{abertos.has(ex.id) ? "▾" : "▸"}</span>
                        <strong>{ex.orgao} · {ex.cargo}</strong>
                        <span className="caderno-meta">{ex.banca}{ex.ano ? ` · ${ex.ano}` : ""} · {ex.total} questões</span>
                    </div>
                    {jaAbertos.has(ex.id) && (
                        <div hidden={!abertos.has(ex.id)} className="caderno-corpo-sim">
                            <Simulado exameId={ex.id} modo={modo} />
                        </div>
                    )}
                </div>
            ))}
        </div>
    )
}

function fmtSeg(s: number): string {
    if (s < 60) return `${s}s`
    const m = Math.floor(s / 60), r = s % 60
    return r ? `${m}min ${r}s` : `${m}min`
}

function Simulado({ exameId, modo }: { exameId: number; modo: "celular" | "computador" }) {
    const [qs, setQs] = useState<Questao[] | null>(null)
    const [marcadas, setMarcadas] = useState<Record<number, Set<string>>>({})
    const [foraDoCampo, setForaDoCampo] = useState<Record<number, boolean>>({})
    const [resultado, setResultado] = useState<SimResultado | ResultadoSimulado | null>(null)
    const [erroInicio, setErroInicio] = useState<string | null>(null)
    const [semCredito, setSemCredito] = useState<string | null>(null)

    // configurações do cartão
    const [tamanhoBolha, setTamanhoBolha] = useState(22)  // px — o usuário controla
    const [corCaneta, setCorCaneta] = useState<"#0b3d91" | "#111111">("#0b3d91")  // azul | preto

    // tempo
    const [run, setRun] = useState<SimRun | null>(null)
    const [restante, setRestante] = useState<number>(0)
    const [minutos, setMinutos] = useState(240)
    // medição de tempo por questão (proxy: 1ª marcação de cada questão, em refs p/ não re-renderizar)
    const inicioRef = useRef<number>(Date.now())
    const marcadoEm = useRef<Record<number, number>>({})

    useEffect(() => {
        api.questoes(exameId).then((d) => setQs(d.filter((q) => !q.descartada))).catch((e: unknown) => {
            if (e instanceof ApiError && e.status === 402) { setSemCredito(e.message); return }
            setQs([])
        })
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

    if (semCredito) return <p className="falha">🔒 {semCredito}</p>
    if (!qs) return <p className="neutro">Carregando questões…</p>

    function marcar(qid: number, letra: string, fora: boolean) {
        if (fora) { setForaDoCampo((f) => ({ ...f, [qid]: true })); return }
        if (!marcadoEm.current[qid]) marcadoEm.current[qid] = Date.now()  // 1ª marcação
        setMarcadas((m) => { const a = new Set(m[qid] ?? []); a.add(letra); return { ...m, [qid]: a } })
    }
    function calcularTempos(): Record<number, number> {
        // tempo por questão ≈ intervalo até a 1ª marcação, na ordem em que foram respondidas
        const entradas = Object.entries(marcadoEm.current).map(([qid, t]) => ({ qid: Number(qid), t })).sort((a, b) => a.t - b.t)
        const tempos: Record<number, number> = {}
        let prev = inicioRef.current
        for (const { qid, t } of entradas) { tempos[qid] = Math.max(1, Math.round((t - prev) / 1000)); prev = t }
        return tempos
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
        setErroInicio(null)
        try {
            const r = await api.iniciarSimulado(exameId, minutos * 60)
            setRun(r)
            setMarcadas({}); setForaDoCampo({}); setResultado(null)
            inicioRef.current = Date.now(); marcadoEm.current = {}  // zera o relógio das questões
        } catch (e) {
            setErroInicio(e instanceof Error ? e.message : "Não foi possível iniciar o simulado.")
        }
    }

    async function entregar() {
        const respostas = respostasValidas()
        const tempos = calcularTempos()
        if (run) setResultado(await api.entregarSimulado(run.simulation_id, respostas, tempos))
        else setResultado(await api.corrigir(exameId, respostas, tempos))
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
                                {(q.enunciado.trim() || (q.enunciado_col2 && q.enunciado_col2.trim())) && (
                                    q.enunciado_col2 && q.enunciado_col2.trim() ? (
                                        <div className="enun-2col">
                                            <div className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado.replace(/\n\[figura:.*\]/, "")) }} />
                                            <div className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado_col2) }} />
                                        </div>
                                    ) : (
                                        <p className="enun" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.enunciado.replace(/\n\[figura:.*\]/, "")) }} />
                                    )
                                )}
                                {q.pergunta && q.pergunta.trim() && <div className="pergunta" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(q.pergunta) }} />}
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
                                <Gemeas qid={q.id} />
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
                        {erroInicio && <p className="falha">{erroInicio}</p>}
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
                        {"tempo_por_enfase" in resultado && resultado.tempo_por_enfase && resultado.tempo_por_enfase.length > 0 && (
                            <div className="desempenho">
                                <h4>Tempo por ênfase{resultado.tempo_alvo_s ? ` · alvo ~${fmtSeg(resultado.tempo_alvo_s)}/questão` : ""}</h4>
                                {resultado.tempo_por_enfase.map((t) => (
                                    <div key={t.enfase} className="linha-tempo">
                                        <span className="enf-nome">{t.enfase}</span>
                                        <span className="enf-tempo">mediana {fmtSeg(t.mediana_s)} · média {fmtSeg(t.media_s)} · P75 {fmtSeg(t.p75_s)}</span>
                                        {resultado.tempo_alvo_s != null && (
                                            <span className={`delta ${t.mediana_s > resultado.tempo_alvo_s ? "lento" : "ok"}`}>
                                                {t.mediana_s > resultado.tempo_alvo_s ? "acima do alvo" : "no alvo"}
                                            </span>
                                        )}
                                    </div>
                                ))}
                                <p className="dica">Tempo aproximado (intervalo entre marcações).</p>
                            </div>
                        )}
                        {"classificacao" in resultado && resultado.classificacao && (
                            <div className={`classificacao ${resultado.classificacao.eliminado ? "elim" : "ok"}`}>
                                <h4>Classificação (edital)</h4>
                                <p className="veredito">
                                    {resultado.classificacao.eliminado ? "✕ ELIMINADO" : "✓ CLASSIFICADO"}
                                    {" · nota "}<strong>{resultado.classificacao.nota_ponderada}</strong>
                                    {resultado.classificacao.nota_corte != null && ` / corte ${resultado.classificacao.nota_corte}`}
                                </p>
                                {resultado.classificacao.por_fase?.length > 0 && (
                                    <ul className="fases-res">
                                        {resultado.classificacao.por_fase.map((f) => (
                                            <li key={f.fase} className={f.minimo_pct != null && f.percentual < f.minimo_pct ? "abaixo" : "ok"}>
                                                {f.fase}: {f.percentual}%{f.minimo_pct != null && ` (mín. ${f.minimo_pct}%)`}
                                            </li>
                                        ))}
                                    </ul>
                                )}
                                {resultado.classificacao.motivos.length > 0 && (
                                    <ul className="motivos">{resultado.classificacao.motivos.map((m, i) => <li key={i}>{m}</li>)}</ul>
                                )}
                                {resultado.classificacao.ranking?.status === "OK" && (
                                    <div className="ranking">
                                        <b>Ranking estimado</b> <span className="conf-tag">{resultado.classificacao.ranking.confianca}</span>
                                        <p>Você {resultado.classificacao.ranking.candidato_pct}% · média pública {resultado.classificacao.ranking.publico_pct}% (Δ {(resultado.classificacao.ranking.delta_pp ?? 0) > 0 ? "+" : ""}{resultado.classificacao.ranking.delta_pp}pp)</p>
                                        <p>Percentil ~{resultado.classificacao.ranking.percentil_estimado}%
                                            {resultado.classificacao.ranking.posicao_estimada != null && ` · posição ~${resultado.classificacao.ranking.posicao_estimada}/${resultado.classificacao.ranking.total_inscritos}`}
                                        </p>
                                        {resultado.classificacao.ranking.situacao && <p className="situacao">{resultado.classificacao.ranking.situacao}</p>}
                                    </div>
                                )}
                                {resultado.classificacao.ranking?.status === "PUBLIC_DATA_NOT_FOUND" && (
                                    <p className="dica">Ranking: {resultado.classificacao.ranking.observacao}</p>
                                )}
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


// Questões gêmeas: a IA gera 2 questões do mesmo conceito para praticar.
function Gemeas({ qid }: { qid: number }) {
    const [gemeas, setGemeas] = useState<GemeaT[] | null>(null)
    const [carregando, setCarregando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [respostas, setRespostas] = useState<Record<number, { escolha: string; acertou: boolean; gabarito: string }>>({})

    async function gerar() {
        setCarregando(true); setErro(null)
        try { setGemeas(await api.gerarGemeas(qid)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha na IA") }
        finally { setCarregando(false) }
    }
    async function responder(tw: GemeaT, letra: string) {
        const r = await api.responderGemea(tw.id, letra)
        setRespostas((m) => ({ ...m, [tw.id]: { escolha: letra, acertou: r.acertou, gabarito: r.gabarito } }))
    }

    if (!gemeas) {
        return (
            <div style={{ marginTop: 6 }}>
                <button className="ia" disabled={carregando} onClick={gerar}>{carregando ? "IA gerando…" : "👯 Questões gêmeas"}</button>
                {erro && <span className="falha"> {erro}</span>}
            </div>
        )
    }
    return (
        <div className="gemeas">
            {gemeas.map((tw, i) => {
                const r = respostas[tw.id]
                return (
                    <div key={tw.id} className="gemea">
                        <p><b>Gêmea {i + 1}</b></p>
                        <p className="enun">{tw.enunciado}</p>
                        <ol className="alts-prova">
                            {Object.entries(tw.alternativas).map(([L, t]) => <li key={L}><b>{L})</b> {t}</li>)}
                        </ol>
                        {!r ? (
                            <div className="seletor-grande">
                                {["A", "B", "C", "D", "E"].map((L) => <button key={L} className="bolha-grande" onClick={() => responder(tw, L)}>{L}</button>)}
                            </div>
                        ) : (
                            <p className={r.acertou ? "acertou" : "errou"}>{r.acertou ? "✓ acertou" : `✕ errou — gabarito ${r.gabarito}`}</p>
                        )}
                    </div>
                )
            })}
        </div>
    )
}
