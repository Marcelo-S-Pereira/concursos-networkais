import { useEffect, useState } from "react"
import Acesso from "./Acesso"
import Revisao from "./Revisao"
import { api, type Health, type Usuario } from "./api"

export default function App() {
    const [usuario, setUsuario] = useState<Usuario | null>(null)
    const [carregando, setCarregando] = useState(true)

    // Ao abrir, pergunta ao backend se o cookie de sessão ainda vale.
    // Quem decide se está autenticado é o servidor, nunca o front.
    useEffect(() => {
        api.me()
            .then(setUsuario)
            .catch(() => setUsuario(null))
            .finally(() => setCarregando(false))
    }, [])

    if (carregando) return <main className="tela"><p className="neutro">Carregando…</p></main>
    if (!usuario) return <Acesso aoEntrar={setUsuario} />
    return <Painel usuario={usuario} aoSair={() => setUsuario(null)} />
}

function Painel({ usuario, aoSair }: { usuario: Usuario; aoSair: () => void }) {
    const [aba, setAba] = useState<"revisao" | "estado">("revisao")

    async function sair() {
        await api.logout().catch(() => {})
        aoSair()
    }

    return (
        <main className="tela larga">
            <header className="topo">
                <div>
                    <h1>APP Concursos</h1>
                    <p className="sub">{usuario.nome}</p>
                </div>
                <button className="secundario" onClick={sair}>Sair</button>
            </header>

            <nav className="abas">
                <button className={aba === "revisao" ? "ativa" : ""} onClick={() => setAba("revisao")}>Revisão de questões</button>
                <button className={aba === "estado" ? "ativa" : ""} onClick={() => setAba("estado")}>Estado</button>
            </nav>

            {aba === "revisao" ? <Revisao /> : <Estado />}
        </main>
    )
}

function Estado() {
    const [health, setHealth] = useState<Health | null>(null)
    useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)) }, [])
    return (
        <section className="cartao">
            <h2>Estado do sistema</h2>
            {!health && <p className="neutro">Consultando…</p>}
            {health && (
                <ul className="lista">
                    <Linha rotulo="API" ok valor="respondendo" />
                    <Linha rotulo="PostgreSQL" ok={!!health.database} valor={health.database ? "conectado" : "fora"} />
                    <Linha rotulo="pgvector" ok={!!health.pgvector} valor={health.pgvector ?? "ausente"} />
                </ul>
            )}
        </section>
    )
}

function Linha({ rotulo, ok, valor }: { rotulo: string; ok: boolean; valor: string }) {
    return (
        <li>
            <span className={ok ? "selo ok" : "selo falha"}>{ok ? "✓" : "✕"}</span>
            <strong>{rotulo}</strong>
            <span className="valor">{valor}</span>
        </li>
    )
}
