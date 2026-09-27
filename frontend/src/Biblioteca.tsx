import { useEffect, useRef, useState } from "react"
import { api, type RagDoc } from "./api"

/** [108]: editar nome + descrição ("memória de conhecimento") de um documento. */
function EditarMeta({ doc, aoSalvar }: { doc: RagDoc; aoSalvar: (titulo: string, descricao: string) => Promise<void> }) {
    const [titulo, setTitulo] = useState(doc.titulo)
    const [descricao, setDescricao] = useState(doc.descricao)
    const [salvando, setSalvando] = useState(false)
    return (
        <div style={{ marginBottom: 10 }}>
            <label>Nome<input value={titulo} onChange={(e) => setTitulo(e.target.value)} /></label>
            <label>Descrição (do que trata o conteúdo — memória de conhecimento)
                <textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} rows={2} maxLength={500} />
            </label>
            <button disabled={salvando} onClick={async () => { setSalvando(true); try { await aoSalvar(titulo, descricao) } finally { setSalvando(false) } }}>
                {salvando ? "Salvando…" : "Salvar nome/descrição"}
            </button>
        </div>
    )
}

export default function Biblioteca() {
    const [docs, setDocs] = useState<RagDoc[] | null>(null)
    const [abertos, setAbertos] = useState<Set<number>>(new Set())
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [consulta, setConsulta] = useState("")
    const [resultados, setResultados] = useState<{ titulo: string; chunk: number; conteudo: string }[] | null>(null)
    const [pergunta, setPergunta] = useState("")
    const [resposta, setResposta] = useState<{ resposta: string; trechos: { titulo: string; chunk: number; conteudo: string }[] } | null>(null)
    const [perguntando, setPerguntando] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)

    async function recarregar() { setDocs(await api.ragDocs()) }
    useEffect(() => { recarregar().catch(() => setDocs([])) }, [])

    async function importar(file: File) {
        setEnviando(true); setErro(null)
        try {
            const fd = new FormData(); fd.append("arquivo", file); fd.append("colecao", "oficial")
            await api.ragImportar(fd); await recarregar()
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha") }
        finally { setEnviando(false) }
    }
    function alternarAberto(id: number) {
        setAbertos((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
    }
    async function alternarUso(d: RagDoc, campo: "uso_chat" | "uso_tutor" | "uso_simulado") {
        setErro(null)
        try {
            const atualizado = await api.ragClassificar(
                d.id,
                campo === "uso_chat" ? !d.uso_chat : d.uso_chat,
                campo === "uso_tutor" ? !d.uso_tutor : d.uso_tutor,
                campo === "uso_simulado" ? !d.uso_simulado : d.uso_simulado,
            )
            setDocs((ds) => ds?.map((x) => (x.id === d.id ? atualizado : x)) ?? ds)
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao classificar") }
    }
    async function salvarMeta(id: number, titulo: string, descricao: string) {
        setErro(null)
        try {
            const atualizado = await api.ragEditarMeta(id, titulo, descricao)
            setDocs((ds) => ds?.map((x) => (x.id === id ? atualizado : x)) ?? ds)
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao salvar") }
    }
    async function buscar() {
        setErro(null)
        try { setResultados((await api.ragBuscar(consulta)).resultados) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha na busca") }
    }
    async function perguntar() {
        if (!pergunta.trim()) return
        setPerguntando(true); setErro(null); setResposta(null)
        try { setResposta(await api.ragPerguntar(pergunta)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao perguntar") }
        finally { setPerguntando(false) }
    }

    if (!docs) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Biblioteca RAG no PostgreSQL/pgvector. Os documentos viram trechos com embedding e você pode
                <strong> perguntar ao edital</strong> (resposta ancorada nos trechos, com citação — nunca inventa).
                Precisa de uma conexão de IA de <strong>embeddings</strong> (cadastre em Cadastro de IA); sem ela,
                os trechos ficam salvos e você reindexa depois.
            </p>
            <p className="explica">
                Cada documento tem uma <strong>classificação de uso</strong>: em quais ferramentas ele pode ser
                consultado — Chat de estudos, Tutor IA, Simulado/Caderno de questões. Marcar só "Tutor IA" faz esse
                documento entrar só ali. <strong>Chat de estudos e Tutor IA já consultam</strong> os documentos
                classificados pra cada um (usa e cita só se ajudar; senão ignora); em cada conversa do Tutor IA o
                usuário escolhe quais documentos valem. Simulado ainda não consulta. Edite o <strong>nome e a
                descrição</strong> de cada documento (resumo do conteúdo, gerado como rascunho na importação)
                clicando pra expandir.
            </p>

            <div className="topo-cadernos">
                <input ref={inputRef} type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])} />
                <button className="add" disabled={enviando} onClick={() => inputRef.current?.click()}>{enviando ? "Importando…" : "+ Importar PDF"}</button>
            </div>
            {erro && <p className="falha">{erro}</p>}

            {!docs.length && <p className="neutro">Nenhum documento ainda.</p>}
            {docs.map((d) => {
                const aberto = abertos.has(d.id)
                return (
                    <div key={d.id} className={`caderno-linha ${aberto ? "aberto" : ""}`}>
                        <div className="caderno-cab" onClick={() => alternarAberto(d.id)}>
                            <span className="seta">{aberto ? "▾" : "▸"}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <strong style={{ display: "block", overflowWrap: "anywhere" }}>{d.titulo}</strong>
                                <span className="caderno-meta">
                                    {d.colecao} · {d.chunk_count} trechos · {d.chunks_prontos >= d.chunk_count
                                        ? "indexado"
                                        : d.erro ? `pausado: ${d.erro.slice(0, 60)}` : `indexando ${d.chunks_prontos}/${d.chunk_count}`}
                                    {d.enviado_por && <> · enviado por {d.enviado_por}</>}
                                </span>
                                {d.descricao && <span className="caderno-meta" style={{ display: "block" }}>{d.descricao}</span>}
                            </div>
                        </div>
                        {aberto && (
                            <div className="caderno-corpo-sim">
                                <EditarMeta doc={d} aoSalvar={(titulo, descricao) => salvarMeta(d.id, titulo, descricao)} />
                                <p className="dica" style={{ margin: "0 0 4px" }}>Usar em:</p>
                                <div className="rag-uso">
                                    <label><input type="checkbox" checked={d.uso_chat} onChange={() => alternarUso(d, "uso_chat")} /> Chat de estudos</label>
                                    <label><input type="checkbox" checked={d.uso_tutor} onChange={() => alternarUso(d, "uso_tutor")} /> Tutor IA</label>
                                    <label><input type="checkbox" checked={d.uso_simulado} onChange={() => alternarUso(d, "uso_simulado")} /> Simulado/Caderno de questões</label>
                                </div>
                                <div className="linha-acoes" style={{ marginTop: 10 }}>
                                    {!d.indexado && (
                                        <>
                                            <span className="dica">🕓 em análise ({d.tentativas_indexacao} tentativa{d.tentativas_indexacao === 1 ? "" : "s"}) </span>
                                            <button className="link" onClick={async () => { try { await api.ragReindexar(d.id); recarregar() } catch (e) { setErro(e instanceof Error ? e.message : "?") } }}>reindexar</button>
                                        </>
                                    )}
                                    <button className="link" onClick={async () => { if (confirm("Apagar?")) { await api.ragApagar(d.id); recarregar() } }}>apagar</button>
                                </div>
                            </div>
                        )}
                    </div>
                )
            })}

            <div className="cartao" style={{ marginTop: 16 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: ".95rem" }}>Perguntar ao edital</h3>
                <div className="regras-linha">
                    <input value={pergunta} onChange={(e) => setPergunta(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && perguntar()}
                        placeholder="ex: quem é eliminado? quantas vagas? qual a idade mínima?" style={{ flex: 1 }} />
                    <button disabled={perguntando} onClick={perguntar}>{perguntando ? "Consultando…" : "Perguntar"}</button>
                </div>
                {resposta && (
                    <div style={{ marginTop: 10 }}>
                        <p style={{ whiteSpace: "pre-wrap" }}>{resposta.resposta}</p>
                        {resposta.trechos.length > 0 && (
                            <details className="uso-erros" style={{ marginTop: 6 }}>
                                <summary>trechos do edital citados ({resposta.trechos.length})</summary>
                                {resposta.trechos.map((t, i) => (
                                    <div key={i} className="gemea" style={{ marginTop: 6 }}>
                                        <p className="dica">{t.titulo} · trecho {t.chunk}</p>
                                        <p>{t.conteudo.slice(0, 300)}…</p>
                                    </div>
                                ))}
                            </details>
                        )}
                    </div>
                )}
            </div>

            <div className="cartao" style={{ marginTop: 16 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: ".95rem" }}>Buscar trechos (avançado)</h3>
                <div className="regras-linha">
                    <input value={consulta} onChange={(e) => setConsulta(e.target.value)} placeholder="ex: nota de corte, eliminação" style={{ flex: 1 }} />
                    <button onClick={buscar}>Buscar</button>
                </div>
                {resultados && resultados.map((r, i) => (
                    <div key={i} className="gemea" style={{ marginTop: 8 }}>
                        <p className="dica">{r.titulo} · trecho {r.chunk}</p>
                        <p>{r.conteudo.slice(0, 400)}…</p>
                    </div>
                ))}
                {resultados && !resultados.length && <p className="neutro">Nenhum trecho (indexe os documentos primeiro).</p>}
            </div>
        </div>
    )
}
