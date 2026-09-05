import { useEffect, useRef, useState } from "react"
import RichText from "./RichText"
import { api, type Exame, type Questao } from "./api"

export default function Cadastro() {
    const [exames, setExames] = useState<Exame[] | null>(null)
    const [abertos, setAbertos] = useState<Set<number>>(new Set())
    const [adicionando, setAdicionando] = useState(false)

    async function recarregar() { setExames(await api.exames()) }
    useEffect(() => { recarregar().catch(() => setExames([])) }, [])

    function alternar(id: number) {
        setAbertos((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
    }

    if (!exames) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <div className="topo-cadernos">
                <p className="explica">Confira a transcrição e recorte figuras. O gabarito fica escondido (o backend corrige por ele).</p>
                <button className="add" onClick={() => setAdicionando((v) => !v)}>{adicionando ? "Cancelar" : "+ Adicionar caderno"}</button>
            </div>

            {adicionando && <FormCaderno aoConcluir={async () => { setAdicionando(false); await recarregar() }} />}

            {!exames.length && !adicionando && <p className="neutro">Nenhum caderno ainda. Clique em “Adicionar caderno”.</p>}

            {exames.map((ex) => (
                <div key={ex.id} className={`caderno-linha ${abertos.has(ex.id) ? "aberto" : ""}`}>
                    <div className="caderno-cab" onClick={() => alternar(ex.id)}>
                        <span className="seta">{abertos.has(ex.id) ? "▾" : "▸"}</span>
                        <strong>{ex.orgao} · {ex.cargo}</strong>
                        <span className="caderno-meta">{ex.banca}{ex.ano ? ` · ${ex.ano}` : ""} · {ex.total} questões</span>
                        {ex.revisar > 0 && <span className="badge">{ex.revisar} p/ revisar</span>}
                        <button className="link apagar-caderno" onClick={async (e) => { e.stopPropagation(); if (confirm(`Apagar o caderno "${ex.cargo}" e todas as questões?`)) { await api.apagarCaderno(ex.id); await recarregar() } }}>apagar</button>
                    </div>
                    {abertos.has(ex.id) && <Lista exameId={ex.id} />}
                </div>
            ))}
        </div>
    )
}

function Dropzone({ rotulo, arquivo, aoSelecionar }: { rotulo: string; arquivo: File | null; aoSelecionar: (f: File | null) => void }) {
    const [sobre, setSobre] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)

    function pegarPdf(files: FileList | null) {
        const f = files?.[0]
        if (f && f.type === "application/pdf") aoSelecionar(f)
    }

    return (
        <div
            className={`dropzone ${sobre ? "sobre" : ""} ${arquivo ? "ok" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setSobre(true) }}
            onDragLeave={() => setSobre(false)}
            onDrop={(e) => { e.preventDefault(); setSobre(false); pegarPdf(e.dataTransfer.files) }}
        >
            <input ref={inputRef} type="file" accept="application/pdf" hidden onChange={(e) => pegarPdf(e.target.files)} />
            <strong>{rotulo}</strong>
            <span>{arquivo ? `✓ ${arquivo.name}` : "arraste o PDF aqui ou clique para selecionar"}</span>
        </div>
    )
}

function FormCaderno({ aoConcluir }: { aoConcluir: () => void }) {
    const [prova, setProva] = useState<File | null>(null)
    const [gabarito, setGabarito] = useState<File | null>(null)
    const [meta, setMeta] = useState({ banca: "", orgao: "", cargo: "", ano: "", coluna_gabarito: "0" })
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function enviar() {
        if (!prova || !gabarito) { setErro("Selecione o PDF da prova e o do gabarito."); return }
        setEnviando(true); setErro(null)
        try {
            const fd = new FormData()
            fd.append("prova", prova); fd.append("gabarito", gabarito)
            fd.append("banca", meta.banca); fd.append("orgao", meta.orgao); fd.append("cargo", meta.cargo)
            if (meta.ano) fd.append("ano", meta.ano)
            fd.append("coluna_gabarito", meta.coluna_gabarito)
            await api.importarCaderno(fd)
            aoConcluir()
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao importar") }
        finally { setEnviando(false) }
    }

    return (
        <div className="cartao form-caderno">
            <h3>Novo caderno</h3>
            <div className="grade-estat">
                <Dropzone rotulo="PDF da prova (caderno)" arquivo={prova} aoSelecionar={setProva} />
                <Dropzone rotulo="PDF do gabarito" arquivo={gabarito} aoSelecionar={setGabarito} />
                <label>Banca<input value={meta.banca} onChange={(e) => setMeta({ ...meta, banca: e.target.value })} placeholder="Cesgranrio" /></label>
                <label>Órgão<input value={meta.orgao} onChange={(e) => setMeta({ ...meta, orgao: e.target.value })} placeholder="Transpetro" /></label>
                <label>Cargo/ênfase<input value={meta.cargo} onChange={(e) => setMeta({ ...meta, cargo: e.target.value })} placeholder="Dutos e Terminais" /></label>
                <label>Ano<input value={meta.ano} onChange={(e) => setMeta({ ...meta, ano: e.target.value })} placeholder="2023" /></label>
                <label>Coluna do gabarito<input value={meta.coluna_gabarito} onChange={(e) => setMeta({ ...meta, coluna_gabarito: e.target.value })} placeholder="0 = 1ª prova" /></label>
            </div>
            {erro && <p className="falha">{erro}</p>}
            <button disabled={enviando} onClick={enviar}>{enviando ? "Importando…" : "Importar caderno"}</button>
        </div>
    )
}

function Lista({ exameId }: { exameId: number }) {
    const [qs, setQs] = useState<Questao[] | null>(null)
    useEffect(() => { api.questoes(exameId).then(setQs).catch(() => setQs([])) }, [exameId])
    if (!qs) return <p className="neutro">Carregando questões…</p>
    const atualizar = (q: Questao) => setQs((l) => l!.map((x) => (x.id === q.id ? q : x)))
    const disciplinas = [...new Set(qs.map((q) => q.disciplina).filter(Boolean))]
    return (
        <div>
            <RegrasEdital examId={exameId} disciplinas={disciplinas} />
            {qs.filter((q) => !q.descartada).map((q) => <CartaoCadastro key={q.id} examId={exameId} q={q} aoMudar={atualizar} />)}
        </div>
    )
}

function RegrasEdital({ examId, disciplinas }: { examId: number; disciplinas: string[] }) {
    const [aberto, setAberto] = useState(false)
    const [pesos, setPesos] = useState<Record<string, string>>({})
    const [minimos, setMinimos] = useState<Record<string, string>>({})
    const [corte, setCorte] = useState("")
    const [vagas, setVagas] = useState("")
    const [inscritos, setInscritos] = useState("")
    const [afericao, setAfericao] = useState<string | null>(null)
    const [salvo, setSalvo] = useState(false)
    const [carregada, setCarregada] = useState<import("./api").RegrasEditalT | null>(null)

    async function abrir() {
        const a = !aberto; setAberto(a)
        if (a) {
            const r = await api.obterRegras(examId)
            setCarregada(r)
            if (r) {
                setPesos(Object.fromEntries(Object.entries(r.pesos).map(([k, v]) => [k, String(v)])))
                setMinimos(Object.fromEntries(Object.entries(r.minimos).map(([k, v]) => [k, String(v)])))
                setCorte(r.nota_corte != null ? String(r.nota_corte) : "")
                setVagas(r.vagas != null ? String(r.vagas) : "")
                setInscritos(r.total_inscritos != null ? String(r.total_inscritos) : "")
            }
        }
    }
    async function salvar() {
        const pnum: Record<string, number> = {}; for (const d of disciplinas) if (pesos[d]) pnum[d] = Number(pesos[d])
        const mnum: Record<string, number> = {}; for (const d of disciplinas) if (minimos[d]) mnum[d] = Number(minimos[d])
        await api.gravarRegras(examId, {
            pesos: pnum, minimos: mnum, nota_corte: corte ? Number(corte) : null, vagas: vagas ? Number(vagas) : null,
            total_inscritos: inscritos ? Number(inscritos) : null,
            fases: carregada?.fases ?? {}, minimo_pct_fase: carregada?.minimo_pct_fase ?? {}, materias_sem_zero: carregada?.materias_sem_zero ?? [],
        })
        setSalvo(true); setTimeout(() => setSalvo(false), 1500)
    }

    return (
        <div className="regras-edital">
            <button className="link" onClick={abrir}>{aberto ? "▾ ocultar regras do edital" : "▸ regras do edital (pesos, mínimos, nota de corte)"}</button>
            {aberto && (
                <div className="regras-form">
                    <table className="tabela-regras">
                        <thead><tr><th>Disciplina</th><th>Peso/questão</th><th>Mínimo de acertos</th></tr></thead>
                        <tbody>
                            {disciplinas.map((d) => (
                                <tr key={d}>
                                    <td>{d}</td>
                                    <td><input type="number" step="0.1" value={pesos[d] ?? ""} onChange={(e) => setPesos({ ...pesos, [d]: e.target.value })} placeholder="1" /></td>
                                    <td><input type="number" value={minimos[d] ?? ""} onChange={(e) => setMinimos({ ...minimos, [d]: e.target.value })} placeholder="—" /></td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="regras-linha">
                        <label>Nota de corte<input type="number" step="0.1" value={corte} onChange={(e) => setCorte(e.target.value)} placeholder="opcional" /></label>
                        <label>Vagas<input type="number" value={vagas} onChange={(e) => setVagas(e.target.value)} placeholder="opcional" /></label>
                        <label>Total de inscritos<input type="number" value={inscritos} onChange={(e) => setInscritos(e.target.value)} placeholder="opcional" /></label>
                        <button onClick={salvar}>{salvo ? "✓ salvo" : "Salvar regras"}</button>
                        <button className="ia" onClick={async () => {
                            setAfericao("aferindo…")
                            try { const r = await api.aferirLLM(examId); setAfericao(`Semelhança do LLM com a lógica: ${r.similaridade_pct}% — ${r.veredito}`) }
                            catch (e) { setAfericao(e instanceof Error ? e.message : "falha") }
                        }}>Aferir LLM</button>
                    </div>
                    {afericao && <p className="afericao-res">{afericao}</p>}
                    {carregada?.minimo_pct_fase && Object.keys(carregada.minimo_pct_fase).length > 0 && (
                        <div className="dica">
                            <b>Regra por fase (do edital):</b>
                            <ul>{Object.entries(carregada.minimo_pct_fase).map(([f, p]) => <li key={f}>{f}: mínimo {p}%</li>)}</ul>
                            {carregada.materias_sem_zero && carregada.materias_sem_zero.length > 0 && <div>Não pode zerar: {carregada.materias_sem_zero.join(", ")}</div>}
                        </div>
                    )}
                    <p className="dica">Abaixo do mínimo por fase, zerar matéria proibida, ou nota abaixo do corte = eliminado.</p>
                </div>
            )}
        </div>
    )
}

function CartaoCadastro({ examId, q, aoMudar }: { examId: number; q: Questao; aoMudar: (q: Questao) => void }) {
    const [enunciado, setEnunciado] = useState(q.enunciado)
    const [enunciadoCol2, setEnunciadoCol2] = useState(q.enunciado_col2)
    const [alts, setAlts] = useState<Record<string, string>>(Object.fromEntries(q.alternativas.map((a) => [a.letra, a.texto])))
    const [verGabarito, setVerGabarito] = useState(false)
    const [recortando, setRecortando] = useState(false)
    const [versaoImg, setVersaoImg] = useState(Date.now())
    const [verPagina, setVerPagina] = useState(false)
    const [textoPag, setTextoPag] = useState<string>("")
    const [modoExib, setModoExib] = useState(q.modo_exibicao)
    const [origemVista, setOrigemVista] = useState<"texto" | "imagem">("texto")

    // divide o texto da página nas duas colunas (esquerda/direita) para edição
    const [colEsq, colDir] = (() => {
        const t = textoPag
        const iDir = t.indexOf("── COLUNA DIREITA ──")
        if (iDir >= 0) return [t.slice(0, iDir).replace("── COLUNA ESQUERDA ──", "").trim(), t.slice(iDir).replace("── COLUNA DIREITA ──", "").trim()]
        return [t.replace("── COLUNA ESQUERDA ──", "").trim(), ""]
    })()

    async function alternarPagina() {
        const abrir = !verPagina
        setVerPagina(abrir)
        if (abrir && !textoPag) setTextoPag(await api.paginaTexto(examId, q.pagina))
    }
    const [salvando, setSalvando] = useState(false)
    const [transcrevendo, setTranscrevendo] = useState(false)
    const [erroIA, setErroIA] = useState<string | null>(null)

    async function corrigirComIA() {
        setTranscrevendo(true)
        setErroIA(null)
        try {
            const r = await api.transcreverIA(q.id)
            setEnunciado(r.enunciado)
            setAlts({ ...alts, ...r.alternativas })
        } catch (e) {
            setErroIA(e instanceof Error ? e.message : "Falha na IA")
        } finally {
            setTranscrevendo(false)
        }
    }

    async function salvar(extra?: { revisada?: boolean }) {
        setSalvando(true)
        try { aoMudar(await api.editarQuestao(q.id, { enunciado, enunciado_col2: enunciadoCol2, alternativas: alts, modo_exibicao: modoExib, ...extra })) }
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

            <div className="origem">
                <button className="link" onClick={alternarPagina}>
                    {verPagina ? "▾ ocultar texto da página" : `▸ ver texto da página de origem (pág. ${q.pagina + 1})`}
                </button>
                {verPagina && (
                    <div className="origem-conteudo-texto">
                        <div className="toggle-origem">
                            <button className={origemVista === "texto" ? "on" : ""} onClick={() => setOrigemVista("texto")}>Texto p/ copiar (2 colunas)</button>
                            <button className={origemVista === "imagem" ? "on" : ""} onClick={() => setOrigemVista("imagem")}>Print do PDF</button>
                        </div>
                        {origemVista === "texto" ? (
                            <div className="duas-colunas">
                                <textarea className="texto-origem" value={colEsq} readOnly rows={12} onFocus={(e) => e.target.select()} />
                                <textarea className="texto-origem" value={colDir} readOnly rows={12} onFocus={(e) => e.target.select()} />
                            </div>
                        ) : (
                            <div>
                                <button className="secundario" onClick={() => setRecortando((v) => !v)}>
                                    {recortando ? "Fechar recorte" : "✂ Recortar print da questão (para exibir no simulado)"}
                                </button>
                                {recortando
                                    ? <RecortadorPagina examId={examId} pagina={q.pagina} qid={q.id} aoConcluir={() => { setRecortando(false); setVersaoImg(Date.now()); setModoExib("imagem") }} />
                                    : <img className="figura" src={`${api.paginaImagemUrl(examId, q.pagina)}?t=${versaoImg}`} alt={`página ${q.pagina + 1}`} />}
                            </div>
                        )}
                        <p className="dica">Referência do PDF: copie o texto para o enunciado (2 colunas) e as alternativas. No modo Print, recorte a questão para o simulado.</p>
                    </div>
                )}
            </div>

            {q.tem_figura && (
                <div className="figura-bloco">
                    <p className="dica">Esta questão tem figura. A imagem abaixo é só para recortar a figura.</p>
                    <div className="linha-acoes">
                        <button className="secundario" onClick={() => setRecortando((v) => !v)}>
                            {recortando ? "Fechar recorte" : "✂ Recortar figura da página"}
                        </button>
                        <button className="secundario" onClick={async () => {
                            if (confirm("Restaurar a página original desta figura? O recorte atual será desfeito.")) {
                                await api.restaurarFigura(q.id)
                                setVersaoImg(Date.now())
                            }
                        }}>↺ Restaurar página</button>
                    </div>
                    {recortando
                        ? <Recortador qid={q.id} aoConcluir={() => { setRecortando(false); setVersaoImg(Date.now()) }} />
                        : <img className="figura" src={`${api.figuraUrl(q.id)}?t=${versaoImg}`} alt={`figura q${q.numero}`} />}
                </div>
            )}

            <div className="campo">Enunciado (duas colunas, como na prova)
                <div className="enunciado-2col">
                    <div className="col">
                        <span className="col-rot">Coluna esquerda</span>
                        <RichText valor={enunciado} aoMudar={setEnunciado} minRows={4} />
                    </div>
                    <div className="col">
                        <span className="col-rot">Coluna direita</span>
                        <RichText valor={enunciadoCol2} aoMudar={setEnunciadoCol2} minRows={4} />
                    </div>
                </div>
            </div>
            <div className="alternativas-edit">
                {["A", "B", "C", "D", "E"].map((L) => (
                    <div key={L} className="alt-rich">
                        <span className="marca">{L}</span>
                        <RichText valor={alts[L] ?? ""} aoMudar={(html) => setAlts({ ...alts, [L]: html })} minRows={1} />
                    </div>
                ))}
            </div>

            {erroIA && <p className="falha">{erroIA}</p>}
            <div className="exib-simulado">
                No simulado, mostrar:
                <button className={modoExib === "texto" ? "on" : ""} onClick={() => setModoExib("texto")}>Texto</button>
                <button className={modoExib === "imagem" ? "on" : ""} onClick={() => setModoExib("imagem")}>Print da questão</button>
                {modoExib === "imagem" && !q.tem_figura && <span className="dica">⚠ recorte o print da questão abaixo antes de salvar.</span>}
            </div>
            <div className="acoes">
                <button disabled={transcrevendo} className="ia" onClick={corrigirComIA} title="Transcreve esta questão com a IA cadastrada (revise antes de salvar)">
                    {transcrevendo ? "IA transcrevendo…" : "✨ Corrigir com IA"}
                </button>
                <button disabled={salvando} onClick={() => salvar()}>Salvar</button>
                <button disabled={salvando} onClick={() => salvar({ revisada: true })}>Salvar e conferida</button>
                <button className="secundario" onClick={() => setVerGabarito((v) => !v)}>
                    {verGabarito ? `Gabarito: ${q.gabarito ?? "—"} (ocultar)` : "Ver gabarito (evite)"}
                </button>
            </div>
        </article>
    )
}

// Recorta a partir da imagem da PÁGINA e salva como figura/print da questão.
function RecortadorPagina({ examId, pagina, qid, aoConcluir }: { examId: number; pagina: number; qid: number; aoConcluir: () => void }) {
    return <Recortador qid={qid} srcUrl={api.paginaImagemUrl(examId, pagina)} aoConcluir={aoConcluir} />
}

// Ferramenta de recorte: arrasta um retângulo sobre a página; ao soltar, corta e envia.
function Recortador({ qid, srcUrl, aoConcluir }: { qid: number; srcUrl?: string; aoConcluir: () => void }) {
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
                <img ref={imgRef} src={srcUrl ?? `${api.figuraUrl(qid)}?t=${Date.now()}`} alt="página" draggable={false} />
                {sel && <div className="selecao" style={{ left: sel.x, top: sel.y, width: sel.w, height: sel.h }} />}
            </div>
            <button disabled={salvando || !sel} onClick={recortar}>{salvando ? "Recortando…" : "Recortar e integrar"}</button>
        </div>
    )
}
