import { useEffect, useState } from "react"
import Cadastro from "./Cadastro"
import Caderno from "./Caderno"
import ConexoesIA from "./ConexoesIA"
import Estatisticas from "./Estatisticas"
import Acesso from "./Acesso"
import { api, type Usuario } from "./api"

export default function App() {
    const [usuario, setUsuario] = useState<Usuario | null>(null)
    const [carregando, setCarregando] = useState(true)

    useEffect(() => {
        api.me().then(setUsuario).catch(() => setUsuario(null)).finally(() => setCarregando(false))
    }, [])

    if (carregando) return <main className="tela"><p className="neutro">Carregando…</p></main>
    if (!usuario) return <Acesso aoEntrar={setUsuario} />
    return <Painel usuario={usuario} aoSair={() => setUsuario(null)} />
}

type Aba = "caderno" | "cadastro" | "ia" | "estat"

function Painel({ usuario, aoSair }: { usuario: Usuario; aoSair: () => void }) {
    const [aba, setAba] = useState<Aba>("caderno")
    const admin = usuario.role === "superadmin"
    const [modo, setModo] = useState<"celular" | "computador">(() => {
        try { return (localStorage.getItem("modo_layout") as "celular" | "computador") || "computador" } catch { return "computador" }
    })
    function trocarModo(m: "celular" | "computador") {
        setModo(m)
        try { localStorage.setItem("modo_layout", m) } catch { /* ignora */ }
    }

    async function sair() {
        await api.logout().catch(() => {})
        aoSair()
    }

    return (
        <main className={`tela ${modo === "computador" ? "modo-computador" : "modo-celular"}`}>
            <header className="topo">
                <div>
                    <h1>APP Concursos</h1>
                    <p className="sub">{usuario.nome}</p>
                </div>
                <div className="topo-acoes">
                    <div className="chave-modo" role="group" aria-label="Modo de tela">
                        <button className={modo === "celular" ? "on" : ""} onClick={() => trocarModo("celular")} title="Celular">📱</button>
                        <button className={modo === "computador" ? "on" : ""} onClick={() => trocarModo("computador")} title="Computador/Tablet">🖥</button>
                    </div>
                    <button className="secundario" onClick={sair}>Sair</button>
                </div>
            </header>

            <nav className="abas">
                <button className={aba === "caderno" ? "ativa" : ""} onClick={() => setAba("caderno")}>Caderno de questões</button>
                {admin && <button className={aba === "cadastro" ? "ativa" : ""} onClick={() => setAba("cadastro")}>Cadastro de questões</button>}
                {admin && <button className={aba === "ia" ? "ativa" : ""} onClick={() => setAba("ia")}>Cadastro de IA</button>}
                {admin && <button className={aba === "estat" ? "ativa" : ""} onClick={() => setAba("estat")}>Estatísticas</button>}
            </nav>

            {aba === "caderno" && <Caderno modo={modo} />}
            {aba === "cadastro" && admin && <Cadastro />}
            {aba === "ia" && admin && <ConexoesIA />}
            {aba === "estat" && admin && <Estatisticas />}
        </main>
    )
}
