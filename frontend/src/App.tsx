import { useEffect, useState } from "react"
import Cadastro from "./Cadastro"
import Caderno from "./Caderno"
import ConexoesIA from "./ConexoesIA"
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

type Aba = "caderno" | "cadastro" | "ia"

function Painel({ usuario, aoSair }: { usuario: Usuario; aoSair: () => void }) {
    const [aba, setAba] = useState<Aba>("caderno")
    const admin = usuario.role === "superadmin"

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
                <button className={aba === "caderno" ? "ativa" : ""} onClick={() => setAba("caderno")}>Caderno de questões</button>
                {admin && <button className={aba === "cadastro" ? "ativa" : ""} onClick={() => setAba("cadastro")}>Cadastro de questões</button>}
                {admin && <button className={aba === "ia" ? "ativa" : ""} onClick={() => setAba("ia")}>Cadastro de IA</button>}
            </nav>

            {aba === "caderno" && <Caderno />}
            {aba === "cadastro" && admin && <Cadastro />}
            {aba === "ia" && admin && <ConexoesIA />}
        </main>
    )
}
