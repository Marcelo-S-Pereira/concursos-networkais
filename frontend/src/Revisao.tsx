import { useEffect, useState } from "react"
import { api, type Exame, type Questao } from "./api"

export default function Revisao() {
    const [exames, setExames] = useState<Exame[] | null>(null)
    const [exameId, setExameId] = useState<number | null>(null)

    useEffect(() => {
        api.exames().then((e) => {
            setExames(e)
            if (e.length) setExameId(e[0].id)
        }).catch(() => setExames([]))
    }, [])

    if (!exames) return <p className="neutro">Carregando provas…</p>
    if (!exames.length) return <p className="neutro">Nenhuma prova importada ainda.</p>

    return (
        <div>
            <div className="seletor-exame">
                {exames.map((e) => (
                    <button key={e.id} className={e.id === exameId ? "ativa" : ""} onClick={() => setExameId(e.id)}>
                        {e.orgao} · {e.cargo} <span className="badge">{e.revisar} p/ revisar</span>
                    </button>
                ))}
            </div>
            {exameId && <ListaQuestoes exameId={exameId} />}
        </div>
    )
}

function ListaQuestoes({ exameId }: { exameId: number }) {
    const [questoes, setQuestoes] = useState<Questao[] | null>(null)
    const [soRevisar, setSoRevisar] = useState(true)

    useEffect(() => {
        api.questoes(exameId).then(setQuestoes).catch(() => setQuestoes([]))
    }, [exameId])

    if (!questoes) return <p className="neutro">Carregando questões…</p>

    function atualizar(q: Questao) {
        setQuestoes((qs) => qs!.map((x) => (x.id === q.id ? q : x)))
    }

    const lista = soRevisar
        ? questoes.filter((q) => !q.descartada && q.confianca < 1 && !q.revisada)
        : questoes.filter((q) => !q.descartada)

    return (
        <div>
            <label className="filtro">
                <input type="checkbox" checked={soRevisar} onChange={(e) => setSoRevisar(e.target.checked)} />
                Mostrar só as que precisam de revisão ({questoes.filter((q) => q.confianca < 1 && !q.revisada && !q.descartada).length})
            </label>
            {lista.map((q) => (
                <CartaoQuestao key={q.id} q={q} aoMudar={atualizar} />
            ))}
            {!lista.length && <p className="sucesso">Nada pendente de revisão nesta prova. 🎉</p>}
        </div>
    )
}

function CartaoQuestao({ q, aoMudar }: { q: Questao; aoMudar: (q: Questao) => void }) {
    const [enunciado, setEnunciado] = useState(q.enunciado)
    const [gabarito, setGabarito] = useState(q.gabarito ?? "")
    const [alts, setAlts] = useState<Record<string, string>>(
        Object.fromEntries(q.alternativas.map((a) => [a.letra, a.texto]))
    )
    const [salvando, setSalvando] = useState(false)

    async function salvar(extra?: { revisada?: boolean; descartada?: boolean }) {
        setSalvando(true)
        try {
            const nova = await api.editarQuestao(q.id, { enunciado, gabarito, alternativas: alts, ...extra })
            aoMudar(nova)
        } finally {
            setSalvando(false)
        }
    }

    const badge = q.confianca >= 1 ? "ok" : q.confianca >= 0.6 ? "medio" : "baixo"

    return (
        <article className="questao">
            <header>
                <strong>Questão {q.numero}</strong>
                <span className="disc">{q.disciplina}</span>
                <span className={`conf ${badge}`}>{Math.round(q.confianca * 100)}%</span>
                {q.revisada && <span className="revisada">✓ revisada</span>}
            </header>
            {q.aviso && <p className="aviso">⚠ {q.aviso}</p>}
            {q.tem_figura && <img className="figura" src={api.figuraUrl(q.id)} alt={`figura da questão ${q.numero}`} />}

            <label className="campo">Enunciado
                <textarea value={enunciado} onChange={(e) => setEnunciado(e.target.value)} rows={4} />
            </label>

            <div className="alternativas-edit">
                {["A", "B", "C", "D", "E"].map((L) => (
                    <label key={L} className={`alt ${gabarito === L ? "correta" : ""}`}>
                        <button type="button" className="marca" onClick={() => setGabarito(L)} title="marcar como gabarito">{L}</button>
                        <input value={alts[L] ?? ""} onChange={(e) => setAlts({ ...alts, [L]: e.target.value })} placeholder={`alternativa ${L}`} />
                    </label>
                ))}
            </div>
            <p className="gab-linha">Gabarito oficial: <strong>{gabarito || "—"}</strong></p>

            <div className="acoes">
                <button disabled={salvando} onClick={() => salvar()}>Salvar</button>
                <button disabled={salvando} onClick={() => salvar({ revisada: true })}>Salvar e marcar revisada</button>
                <button disabled={salvando} className="secundario" onClick={() => salvar({ descartada: true })}>Descartar</button>
            </div>
        </article>
    )
}
