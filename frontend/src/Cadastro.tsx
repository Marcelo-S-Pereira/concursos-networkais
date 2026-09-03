import { useEffect, useRef, useState } from "react"
import { api, type Exame, type Questao } from "./api"

export default function Cadastro() {
    const [exames, setExames] = useState<Exame[] | null>(null)
    const [exameId, setExameId] = useState<number | null>(null)

    useEffect(() => {
        api.exames().then((e) => { setExames(e); if (e.length) setExameId(e[0].id) }).catch(() => setExames([]))
    }, [])

    if (!exames) return <p className="neutro">Carregando…</p>
    if (!exames.length) return <p className="neutro">Nenhuma prova importada. (importação por PDF: próxima etapa)</p>

    return (
        <div>
            <p className="explica">
                Aqui você confere a transcrição das questões e recorta as figuras.
                O <strong>gabarito fica escondido</strong> — ele já está na base e o backend corrige por ele.
            </p>
            <div className="seletor-exame">
                {exames.map((e) => (
                    <button key={e.id} className={e.id === exameId ? "ativa" : ""} onClick={() => setExameId(e.id)}>
                        {e.orgao} · {e.cargo}
                    </button>
                ))}
            </div>
            {exameId && <Lista exameId={exameId} />}
        </div>
    )
}

function Lista({ exameId }: { exameId: number }) {
    const [qs, setQs] = useState<Questao[] | null>(null)
    useEffect(() => { api.questoes(exameId).then(setQs).catch(() => setQs([])) }, [exameId])
    if (!qs) return <p className="neutro">Carregando questões…</p>
    const atualizar = (q: Questao) => setQs((l) => l!.map((x) => (x.id === q.id ? q : x)))
    return <div>{qs.filter((q) => !q.descartada).map((q) => <CartaoCadastro key={q.id} q={q} aoMudar={atualizar} />)}</div>
}

function CartaoCadastro({ q, aoMudar }: { q: Questao; aoMudar: (q: Questao) => void }) {
    const [enunciado, setEnunciado] = useState(q.enunciado)
    const [alts, setAlts] = useState<Record<string, string>>(Object.fromEntries(q.alternativas.map((a) => [a.letra, a.texto])))
    const [verGabarito, setVerGabarito] = useState(false)
    const [recortando, setRecortando] = useState(false)
    const [salvando, setSalvando] = useState(false)

    async function salvar(extra?: { revisada?: boolean }) {
        setSalvando(true)
        try { aoMudar(await api.editarQuestao(q.id, { enunciado, alternativas: alts, ...extra })) }
        finally { setSalvando(false) }
    }

    const badge = q.confianca >= 1 ? "ok" : q.confianca >= 0.6 ? "medio" : "baixo"

    return (
        <article className="questao">
            <header>
                <strong>Questão {q.numero}</strong>
                <span className="disc">{q.disciplina}</span>
                <span className={`conf ${badge}`}>{Math.round(q.confianca * 100)}%</span>
                {q.revisada && <span className="revisada">✓ conferida</span>}
            </header>
            {q.aviso && <p className="aviso">⚠ {q.aviso}</p>}

            {q.tem_figura && (
                <div className="figura-bloco">
                    <button className="secundario" onClick={() => setRecortando((v) => !v)}>
                        {recortando ? "Fechar recorte" : "✂ Recortar figura da página"}
                    </button>
                    {recortando
                        ? <Recortador qid={q.id} aoConcluir={() => { setRecortando(false); aoMudar({ ...q }) }} />
                        : <img className="figura" src={`${api.figuraUrl(q.id)}?t=${Date.now()}`} alt={`figura q${q.numero}`} />}
                </div>
            )}

            <label className="campo">Enunciado
                <textarea value={enunciado} onChange={(e) => setEnunciado(e.target.value)} rows={3} />
            </label>
            <div className="alternativas-edit">
                {["A", "B", "C", "D", "E"].map((L) => (
                    <label key={L} className="alt">
                        <span className="marca">{L}</span>
                        <input value={alts[L] ?? ""} onChange={(e) => setAlts({ ...alts, [L]: e.target.value })} placeholder={`alternativa ${L}`} />
                    </label>
                ))}
            </div>

            <div className="acoes">
                <button disabled={salvando} onClick={() => salvar()}>Salvar</button>
                <button disabled={salvando} onClick={() => salvar({ revisada: true })}>Salvar e conferida</button>
                <button className="secundario" onClick={() => setVerGabarito((v) => !v)}>
                    {verGabarito ? `Gabarito: ${q.gabarito ?? "—"} (ocultar)` : "Ver gabarito (evite)"}
                </button>
            </div>
        </article>
    )
}

// Ferramenta de recorte: arrasta um retângulo sobre a página; ao soltar, corta e envia.
function Recortador({ qid, aoConcluir }: { qid: number; aoConcluir: () => void }) {
    const imgRef = useRef<HTMLImageElement>(null)
    const [sel, setSel] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
    const arrasto = useRef<{ x0: number; y0: number } | null>(null)
    const [salvando, setSalvando] = useState(false)

    function pos(e: React.PointerEvent) {
        const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
        return { x: e.clientX - r.left, y: e.clientY - r.top }
    }
    function down(e: React.PointerEvent) {
        const p = pos(e); arrasto.current = { x0: p.x, y0: p.y }; setSel({ x: p.x, y: p.y, w: 0, h: 0 })
        ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
    }
    function move(e: React.PointerEvent) {
        if (!arrasto.current) return
        const p = pos(e); const a = arrasto.current
        setSel({ x: Math.min(a.x0, p.x), y: Math.min(a.y0, p.y), w: Math.abs(p.x - a.x0), h: Math.abs(p.y - a.y0) })
    }
    function up() { arrasto.current = null }

    async function recortar() {
        const img = imgRef.current
        if (!img || !sel || sel.w < 8 || sel.h < 8) return
        setSalvando(true)
        try {
            const escala = img.naturalWidth / img.clientWidth
            const canvas = document.createElement("canvas")
            canvas.width = sel.w * escala; canvas.height = sel.h * escala
            const ctx = canvas.getContext("2d")!
            ctx.drawImage(img, sel.x * escala, sel.y * escala, sel.w * escala, sel.h * escala, 0, 0, canvas.width, canvas.height)
            const blob: Blob = await new Promise((res) => canvas.toBlob((b) => res(b!), "image/png"))
            await api.salvarFigura(qid, blob)
            aoConcluir()
        } finally { setSalvando(false) }
    }

    return (
        <div className="recortador">
            <p className="dica">Arraste sobre a figura para selecionar; depois clique em Recortar.</p>
            <div className="area-recorte" onPointerDown={down} onPointerMove={move} onPointerUp={up}>
                <img ref={imgRef} src={`${api.figuraUrl(qid)}?t=${Date.now()}`} alt="página" draggable={false} />
                {sel && <div className="selecao" style={{ left: sel.x, top: sel.y, width: sel.w, height: sel.h }} />}
            </div>
            <button disabled={salvando || !sel} onClick={recortar}>{salvando ? "Recortando…" : "Recortar e integrar"}</button>
        </div>
    )
}
