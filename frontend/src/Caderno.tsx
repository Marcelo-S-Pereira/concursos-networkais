import { useEffect, useRef, useState } from "react"
import { api, type Exame, type Questao, type ResultadoSimulado } from "./api"

const LETRAS = ["A", "B", "C", "D", "E"]

export default function Caderno() {
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
            {exameId && <Simulado exameId={exameId} />}
        </div>
    )
}

function Simulado({ exameId }: { exameId: number }) {
    const [qs, setQs] = useState<Questao[] | null>(null)
    // marcadas[qid] = conjunto de letras preenchidas (2+ = dupla marcação = anula)
    const [marcadas, setMarcadas] = useState<Record<number, Set<string>>>({})
    const [resultado, setResultado] = useState<ResultadoSimulado | null>(null)

    useEffect(() => {
        api.questoes(exameId).then((d) => setQs(d.filter((q) => !q.descartada))).catch(() => setQs([]))
    }, [exameId])

    if (!qs) return <p className="neutro">Carregando questões…</p>

    function preencher(qid: number, letra: string) {
        setMarcadas((m) => {
            const atual = new Set(m[qid] ?? [])
            atual.add(letra)  // uma vez preenchida, some só ao "limpar" — mudar = dupla marcação
            return { ...m, [qid]: atual }
        })
    }
    function limpar(qid: number) {
        setMarcadas((m) => { const c = { ...m }; delete c[qid]; return c })
    }

    async function entregar() {
        // envia só as questões com UMA marcação (dupla marcação = anulada, não conta)
        const respostas: Record<number, string> = {}
        for (const q of qs!) {
            const set = marcadas[q.id]
            if (set && set.size === 1) respostas[q.id] = [...set][0]
        }
        setResultado(await api.corrigir(exameId, respostas))
    }

    const anuladas = qs.filter((q) => (marcadas[q.id]?.size ?? 0) > 1).length

    return (
        <div className="simulado">
            <div className="coluna-questoes">
                {qs.map((q) => (
                    <article key={q.id} className="q-prova">
                        <header><strong>{q.numero}</strong> <span className="disc">{q.disciplina}</span></header>
                        <p className="enun">{q.enunciado.replace(/\n\[figura:.*\]/, "")}</p>
                        {q.tem_figura && <img className="figura" src={api.figuraUrl(q.id)} alt="figura" />}
                        <ol className="alts-prova">
                            {q.alternativas.map((a) => (
                                <li key={a.letra}><b>{a.letra})</b> {a.texto}</li>
                            ))}
                        </ol>
                        {resultado && (
                            <p className={resultado.resultado[q.id] ? "acertou" : "errou"}>
                                {resultado.resultado[q.id] ? "✓ acertou" : "✕ errou"}
                                {" · "}<button className="link" onClick={() => alert(`Gabarito da questão ${q.numero}: ${q.gabarito}`)}>ver gabarito</button>
                            </p>
                        )}
                    </article>
                ))}
            </div>

            <aside className="cartao-resposta">
                <h3>Cartão-resposta</h3>
                <p className="regra">Preencha o círculo <b>inteiro</b> com a caneta. Uma alternativa por questão. Dupla marcação anula.</p>
                <div className="folha">
                    {qs.map((q) => {
                        const set = marcadas[q.id] ?? new Set()
                        const dupla = set.size > 1
                        return (
                            <div key={q.id} className={`linha-cartao ${dupla ? "anulada" : ""}`}>
                                <span className="num">{q.numero}</span>
                                {LETRAS.map((L) => (
                                    <Bolha key={L} marcada={set.has(L)} aoPreencher={() => preencher(q.id, L)} bloqueado={!!resultado} />
                                ))}
                                {set.size > 0 && !resultado && <button className="limpa" onClick={() => limpar(q.id)} title="limpar">↺</button>}
                            </div>
                        )
                    })}
                </div>
                {!resultado ? (
                    <>
                        {anuladas > 0 && <p className="aviso">⚠ {anuladas} questão(ões) com dupla marcação serão anuladas.</p>}
                        <button className="entregar" onClick={entregar}>Entregar cartão</button>
                    </>
                ) : (
                    <div className="placar">
                        <strong>{resultado.acertos}/{resultado.total}</strong> acertos
                        <span>({resultado.respondidas} respondidas)</span>
                    </div>
                )}
            </aside>
        </div>
    )
}

// Bolha preenchível à caneta: o traço pinta o círculo; só conta como marcada
// quando preenchida o bastante (regra do cartão-resposta: preencher todo o círculo).
function Bolha({ marcada, aoPreencher, bloqueado }: { marcada: boolean; aoPreencher: () => void; bloqueado: boolean }) {
    const ref = useRef<HTMLCanvasElement>(null)
    const pintando = useRef(false)

    useEffect(() => {
        if (marcada && ref.current) {
            const ctx = ref.current.getContext("2d")!
            ctx.fillStyle = "#16181d"
            ctx.beginPath(); ctx.arc(14, 14, 12, 0, Math.PI * 2); ctx.fill()
        }
    }, [marcada])

    function pintar(e: React.PointerEvent) {
        if (bloqueado || marcada) return
        const c = ref.current!; const r = c.getBoundingClientRect()
        const ctx = c.getContext("2d")!
        ctx.fillStyle = "#16181d"
        ctx.beginPath(); ctx.arc(e.clientX - r.left, e.clientY - r.top, 5, 0, Math.PI * 2); ctx.fill()
        // mede quanto do círculo foi pintado
        const img = ctx.getImageData(0, 0, 28, 28).data
        let pint = 0
        for (let i = 3; i < img.length; i += 4) if (img[i] > 0) pint++
        if (pint / (28 * 28) > 0.5) aoPreencher()
    }

    return (
        <canvas
            ref={ref} width={28} height={28} className={`bolha ${marcada ? "cheia" : ""}`}
            onPointerDown={(e) => { pintando.current = true; (e.target as HTMLElement).setPointerCapture(e.pointerId); pintar(e) }}
            onPointerMove={(e) => pintando.current && pintar(e)}
            onPointerUp={() => (pintando.current = false)}
        />
    )
}
