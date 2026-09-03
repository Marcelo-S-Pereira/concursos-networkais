import { useEffect, useState } from "react"
import { api, type StatEnfase, type StatEnfaseInput } from "./api"

const VAZIO: StatEnfaseInput = {
    banca: "", orgao: "", cargo: "", ano: null, enfase: "",
    amostra: null, acerto_pct: null, fonte: "", tipo_fonte: "", status: "OK",
}

export default function Estatisticas() {
    const [lista, setLista] = useState<StatEnfase[] | null>(null)
    const [novo, setNovo] = useState<StatEnfaseInput>(VAZIO)
    const [salvando, setSalvando] = useState(false)

    async function recarregar() { setLista(await api.estatEnfase()) }
    useEffect(() => { recarregar().catch(() => setLista([])) }, [])

    async function adicionar() {
        if (!novo.enfase.trim()) return
        setSalvando(true)
        try { await api.criarEstat(novo); setNovo(VAZIO); await recarregar() }
        finally { setSalvando(false) }
    }

    if (!lista) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Estatística pública de acerto por ênfase (o quanto os candidatos acertam), para comparar
                com o seu desempenho. Preencha aqui o que vier do web scraping. Sem dado, deixe em branco —
                o sistema nunca inventa.
            </p>

            <div className="cartao form-estat">
                <h3>Adicionar estatística</h3>
                <div className="grade-estat">
                    <label>Ênfase/disciplina<input value={novo.enfase} onChange={(e) => setNovo({ ...novo, enfase: e.target.value })} placeholder="ex: Matemática" /></label>
                    <label>% que acertam<input type="number" step="0.1" value={novo.acerto_pct ?? ""} onChange={(e) => setNovo({ ...novo, acerto_pct: e.target.value ? Number(e.target.value) : null })} placeholder="45.0" /></label>
                    <label>Amostra (N)<input type="number" value={novo.amostra ?? ""} onChange={(e) => setNovo({ ...novo, amostra: e.target.value ? Number(e.target.value) : null })} placeholder="12540" /></label>
                    <label>Banca<input value={novo.banca} onChange={(e) => setNovo({ ...novo, banca: e.target.value })} placeholder="Cesgranrio" /></label>
                    <label>Cargo<input value={novo.cargo} onChange={(e) => setNovo({ ...novo, cargo: e.target.value })} placeholder="Dutos e Terminais" /></label>
                    <label>Ano<input type="number" value={novo.ano ?? ""} onChange={(e) => setNovo({ ...novo, ano: e.target.value ? Number(e.target.value) : null })} placeholder="2023" /></label>
                    <label>Fonte<input value={novo.fonte} onChange={(e) => setNovo({ ...novo, fonte: e.target.value })} placeholder="URL/origem" /></label>
                </div>
                <button disabled={salvando} onClick={adicionar}>{salvando ? "Salvando…" : "Adicionar"}</button>
            </div>

            <table className="tabela-estat">
                <thead><tr><th>Ênfase</th><th>% acerto</th><th>N</th><th>Banca/Cargo</th><th>Ano</th><th></th></tr></thead>
                <tbody>
                    {lista.map((s) => (
                        <tr key={s.id}>
                            <td>{s.enfase}</td>
                            <td>{s.acerto_pct ?? "—"}%</td>
                            <td>{s.amostra ?? "—"}</td>
                            <td>{[s.banca, s.cargo].filter(Boolean).join(" · ") || "—"}</td>
                            <td>{s.ano ?? "—"}</td>
                            <td><button className="link" onClick={async () => { if (confirm("Apagar?")) { await api.apagarEstat(s.id); recarregar() } }}>apagar</button></td>
                        </tr>
                    ))}
                    {!lista.length && <tr><td colSpan={6} className="neutro">Nenhuma estatística ainda.</td></tr>}
                </tbody>
            </table>
        </div>
    )
}
