import { useState } from "react"
import { api } from "./api"

/** [153]: widget de feedback — estrelas (pequeno) + texto, por ferramenta.
 * Reusado no Chat de estudo, Tutor IA e Simulado. Discreto por padrão
 * (recolhido), abre só quando o usuário clica. */
export default function Feedback({ ferramenta }: { ferramenta: "chat" | "tutor_ia" | "simulado" }) {
    const [aberto, setAberto] = useState(false)
    const [estrelas, setEstrelas] = useState(0)
    const [texto, setTexto] = useState("")
    const [enviando, setEnviando] = useState(false)
    const [enviado, setEnviado] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function enviar() {
        if (!estrelas && !texto.trim()) { setErro("Dê uma nota ou escreva algo."); return }
        setEnviando(true); setErro(null)
        try {
            await api.enviarFeedback(ferramenta, estrelas || null, texto.trim() || null)
            setEnviado(true)
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao enviar.") }
        finally { setEnviando(false) }
    }

    if (!aberto) {
        return <button className="feedback-abrir" onClick={() => setAberto(true)} title="Deixar feedback">💬 Feedback</button>
    }
    if (enviado) {
        return <p className="feedback-obrigado">Obrigado pelo feedback! 🙏</p>
    }
    return (
        <div className="feedback-caixa">
            <div className="feedback-estrelas">
                {[1, 2, 3, 4, 5].map((n) => (
                    <button key={n} className={n <= estrelas ? "on" : ""} onClick={() => setEstrelas(n)} aria-label={`${n} estrelas`}>★</button>
                ))}
            </div>
            <textarea value={texto} onChange={(e) => setTexto(e.target.value)} placeholder="O que achou? (opcional)" rows={2} />
            {erro && <p className="falha">{erro}</p>}
            <div className="feedback-botoes">
                <button className="secundario" onClick={() => setAberto(false)}>cancelar</button>
                <button disabled={enviando} onClick={enviar}>{enviando ? "Enviando…" : "Enviar"}</button>
            </div>
        </div>
    )
}
