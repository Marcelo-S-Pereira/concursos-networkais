import { useEffect, useRef, useState } from "react"
import { api, type RagDoc } from "./api"

export default function Biblioteca() {
    const [docs, setDocs] = useState<RagDoc[] | null>(null)
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

            <div className="topo-cadernos">
                <input ref={inputRef} type="file" accept="application/pdf" hidden onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])} />
                <button className="add" disabled={enviando} onClick={() => inputRef.current?.click()}>{enviando ? "Importando…" : "+ Importar PDF"}</button>
            </div>
            {erro && <p className="falha">{erro}</p>}

            <table className="tabela-estat">
                <thead><tr><th>Documento</th><th>Coleção</th><th>Trechos</th><th>Indexado</th><th></th></tr></thead>
                <tbody>
                    {docs.map((d) => (
                        <tr key={d.id}>
                            <td>{d.titulo}</td><td>{d.colecao}</td><td>{d.chunk_count}</td>
                            <td>{d.indexado ? "✓" : (d.erro ? "pendente" : "não")}</td>
                            <td>
                                {!d.indexado && <button className="link" onClick={async () => { try { await api.ragReindexar(d.id); recarregar() } catch (e) { setErro(e instanceof Error ? e.message : "?") } }}>reindexar</button>}
                                {" "}<button className="link" onClick={async () => { if (confirm("Apagar?")) { await api.ragApagar(d.id); recarregar() } }}>apagar</button>
                            </td>
                        </tr>
                    ))}
                    {!docs.length && <tr><td colSpan={5} className="neutro">Nenhum documento ainda.</td></tr>}
                </tbody>
            </table>

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
