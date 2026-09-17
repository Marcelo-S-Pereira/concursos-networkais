import DOMPurify from "dompurify"
import { useEffect, useState } from "react"
import { api, type QuestaoRevisao } from "./api"

const LETRAS = ["A", "B", "C", "D", "E"]

export default function Revisao() {
    const [devidas, setDevidas] = useState<QuestaoRevisao[] | null>(null)
    const [i, setI] = useState(0)
    const [resultado, setResultado] = useState<boolean | null>(null)

    useEffect(() => { api.revisaoDevidas().then(setDevidas).catch(() => setDevidas([])) }, [])

    if (!devidas) return <p className="neutro">Carregando revisão…</p>
    if (!devidas.length) return <p className="sucesso">Nada para revisar agora. 🎉 As questões que você errar entram aqui.</p>
    if (i >= devidas.length) return <p className="sucesso">Revisão concluída! Volte amanhã. 🎉</p>

    const q = devidas[i]

    async function responder(letra: string) {
        const r = await api.responderRevisao(q.id, letra)
        setResultado(r.acertou)
    }
    function proxima() { setResultado(null); setI((n) => n + 1) }

    return (
        <div className="revisao-view">
            <p className="sub">Revisão espaçada · {i + 1} de {devidas.length}</p>
            <article className="q-prova">
                <header>
                    <strong>Questão {q.numero}</strong> <span className="disc">{q.disciplina}</span>
                    {q.origem === "chat" && <span className="badge-origem">Chat IA</span>}
                </header>
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

                {resultado === null ? (
                    <div className="seletor-grande">
                        {LETRAS.map((L) => <button key={L} className="bolha-grande" onClick={() => responder(L)}>{L}</button>)}
                    </div>
                ) : (
                    <div className="pos-resultado">
                        <p className={resultado ? "acertou" : "errou"}>{resultado ? "✓ acertou — intervalo aumentou" : "✕ errou — volta para amanhã"}</p>
                        <button onClick={proxima}>Próxima</button>
                    </div>
                )}
            </article>
        </div>
    )
}
