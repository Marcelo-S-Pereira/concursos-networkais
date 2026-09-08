import { useEffect, useState } from "react"
import { api, type EstruturaEstat, type Exame, type StatEnfaseInput, type TemaComStat } from "./api"

export default function Estatisticas() {
    const [cadernos, setCadernos] = useState<Exame[] | null>(null)
    const [examId, setExameId] = useState<number | null>(null)
    const [estrutura, setEstrutura] = useState<EstruturaEstat | null>(null)
    const [extraindo, setExtraindo] = useState(false)
    const [msg, setMsg] = useState<string | null>(null)

    useEffect(() => {
        api.exames().then((c) => { setCadernos(c); if (c.length) setExameId(c[0].id) }).catch(() => setCadernos([]))
    }, [])
    async function carregar(id: number) { setEstrutura(await api.estatEstrutura(id).catch(() => null)) }
    useEffect(() => { if (examId) void carregar(examId) }, [examId])

    async function extrair() {
        if (!examId) return
        setExtraindo(true); setMsg(null)
        try {
            const r = await api.estatExtrairTemas(examId)
            setMsg(`✓ ${r.criados} subtemas extraídos do edital (${r.disciplinas.join(", ")})`)
            await carregar(examId)
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha ao extrair") }
        finally { setExtraindo(false) }
    }

    if (!cadernos) return <p className="neutro">Carregando…</p>
    if (!cadernos.length) return <p className="neutro">Importe um caderno primeiro (aba Cadastro de questões).</p>
    const caderno = cadernos.find((c) => c.id === examId)

    return (
        <div>
            <p className="explica">
                Estatística pública de acerto por <strong>subtema</strong> do edital, <strong>por caderno</strong>. Os
                subtemas vêm do conteúdo programático — extraia com a IA e preencha o % que os candidatos acertam em cada
                um. Sem dado, deixe em branco: o sistema nunca inventa.
            </p>

            <div className="regras-linha">
                <label>Caderno
                    <select value={examId ?? ""} onChange={(e) => setExameId(Number(e.target.value))}>
                        {cadernos.map((c) => <option key={c.id} value={c.id}>{c.orgao} · {c.cargo}</option>)}
                    </select>
                </label>
                <button className="secundario" disabled={extraindo} onClick={extrair}>
                    {extraindo ? "extraindo…" : "✨ Extrair subtemas do edital (IA)"}
                </button>
            </div>
            {msg && <p className="dica">{msg}</p>}

            {estrutura && estrutura.disciplinas.length === 0 && (
                <p className="neutro">Nenhum subtema ainda. Clique em “Extrair subtemas do edital (IA)” — ou adicione manualmente após extrair.</p>
            )}
            {estrutura?.disciplinas.map((d) => (
                <DisciplinaBloco key={d.disciplina} examId={estrutura.exam_id} caderno={caderno}
                    disciplina={d.disciplina} temas={d.temas} aoMudar={() => examId && carregar(examId)} />
            ))}
        </div>
    )
}

function DisciplinaBloco({
    examId, caderno, disciplina, temas, aoMudar,
}: {
    examId: number; caderno: Exame | undefined; disciplina: string; temas: TemaComStat[]; aoMudar: () => void
}) {
    const [aberto, setAberto] = useState(true)
    const [novo, setNovo] = useState("")
    const preenchidos = temas.filter((t) => t.stat && t.stat.acerto_pct != null).length

    async function adicionar() {
        if (!novo.trim()) return
        await api.estatAddTema(examId, disciplina, novo.trim()); setNovo(""); aoMudar()
    }

    return (
        <div className={`caderno-linha ${aberto ? "aberto" : ""}`}>
            <div className="caderno-cab" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <strong>{disciplina}</strong>
                <span className="caderno-meta">{temas.length} subtemas · {preenchidos} preenchido(s)</span>
            </div>
            {aberto && (
                <div style={{ padding: "0 12px 12px" }}>
                    {temas.map((t) => <CardTema key={t.id} examId={examId} caderno={caderno} disciplina={disciplina} tema={t} aoMudar={aoMudar} />)}
                    <div className="regras-linha" style={{ marginTop: 8 }}>
                        <input value={novo} onChange={(e) => setNovo(e.target.value)} placeholder="+ adicionar subtema" style={{ flex: 1 }} />
                        <button className="secundario" onClick={adicionar}>Adicionar</button>
                    </div>
                </div>
            )}
        </div>
    )
}

function CardTema({
    examId, caderno, disciplina, tema, aoMudar,
}: {
    examId: number; caderno: Exame | undefined; disciplina: string; tema: TemaComStat; aoMudar: () => void
}) {
    const s = tema.stat
    const [aberto, setAberto] = useState(false)
    const [f, setF] = useState<StatEnfaseInput>({
        exam_id: examId, disciplina, enfase: tema.nome,
        banca: s?.banca ?? caderno?.banca ?? "", orgao: s?.orgao ?? caderno?.orgao ?? "",
        cargo: s?.cargo ?? caderno?.cargo ?? "", ano: s?.ano ?? caderno?.ano ?? null,
        amostra: s?.amostra ?? null, acerto_pct: s?.acerto_pct ?? null,
        fonte: s?.fonte ?? "", tipo_fonte: "", status: "OK",
    })
    const [salvando, setSalvando] = useState(false)
    const [salvo, setSalvo] = useState(false)
    const preenchido = s && s.acerto_pct != null

    function up<K extends keyof StatEnfaseInput>(k: K, v: StatEnfaseInput[K]) { setF((x) => ({ ...x, [k]: v })); setSalvo(false) }
    async function salvar() {
        setSalvando(true)
        try { await api.upsertEstatTema({ ...f, exam_id: examId, disciplina, enfase: tema.nome }); setSalvo(true); aoMudar() }
        finally { setSalvando(false) }
    }

    return (
        <div className={`caderno-linha ${aberto ? "aberto" : ""}`} style={{ marginTop: 6 }}>
            <div className="caderno-cab" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <strong>{tema.nome}</strong>
                <span className="caderno-meta">{preenchido ? `${s!.acerto_pct}% acertam${s!.amostra ? ` · N=${s!.amostra}` : ""}` : "não preenchido"}</span>
                {preenchido && <span className="badge">✓</span>}
                <button className="link apagar-caderno" onClick={async (e) => { e.stopPropagation(); if (confirm(`Remover o subtema "${tema.nome}"?`)) { await api.estatDelTema(tema.id); aoMudar() } }}>remover</button>
            </div>
            {aberto && (
                <div style={{ padding: "0 14px 12px" }}>
                    <div className="grade-estat">
                        <label>% que acertam<input type="number" step="0.1" value={f.acerto_pct ?? ""} placeholder="45.0"
                            onChange={(e) => up("acerto_pct", e.target.value ? Number(e.target.value) : null)} /></label>
                        <label>Nº de candidatos (N)<input type="number" value={f.amostra ?? ""} placeholder="12540"
                            onChange={(e) => up("amostra", e.target.value ? Number(e.target.value) : null)} /></label>
                        <label>Banca<input value={f.banca} onChange={(e) => up("banca", e.target.value)} /></label>
                        <label>Cargo<input value={f.cargo} onChange={(e) => up("cargo", e.target.value)} /></label>
                        <label>Ano<input type="number" value={f.ano ?? ""} onChange={(e) => up("ano", e.target.value ? Number(e.target.value) : null)} /></label>
                        <label>Fonte<input value={f.fonte} onChange={(e) => up("fonte", e.target.value)} placeholder="URL/origem" /></label>
                    </div>
                    <button disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
                    {salvo && <span className="dica"> ✓ salvo</span>}
                </div>
            )}
        </div>
    )
}
