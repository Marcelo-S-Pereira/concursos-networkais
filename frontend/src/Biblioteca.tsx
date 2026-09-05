import { useEffect, useRef, useState } from "react"
import { api, type RagDoc } from "./api"

export default function Biblioteca() {
    const [docs, setDocs] = useState<RagDoc[] | null>(null)
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [consulta, setConsulta] = useState("")
    const [resultados, setResultados] = useState<{ titulo: string; chunk: number; conteudo: string }[] | null>(null)
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

    if (!docs) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Biblioteca RAG no PostgreSQL/pgvector. Os documentos viram trechos com embedding e o tutor
                consulta por similaridade. A busca precisa de uma conexão de IA de <strong>embeddings</strong>
                (cadastre em Cadastro de IA); sem ela, os trechos ficam salvos e você reindexa depois.
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
                <h3 style={{ margin: "0 0 8px", fontSize: ".95rem" }}>Buscar na biblioteca</h3>
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
