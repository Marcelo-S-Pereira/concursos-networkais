import { useEffect, useState } from "react"
import Cadastro from "./Cadastro"
import Caderno from "./Caderno"
import ConexoesIA from "./ConexoesIA"
import Estatisticas from "./Estatisticas"
import Biblioteca from "./Biblioteca"
import Revisao from "./Revisao"
import Desempenho from "./Desempenho"
import Perfil from "./Perfil"
import Pagamentos from "./Pagamentos"
import Acesso from "./Acesso"
import { api, type CreditosResumo, type Usuario } from "./api"

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

type Aba = "caderno" | "revisao" | "desempenho" | "perfil" | "cadastro" | "ia" | "estat" | "rag" | "pagamentos"

const MENU: { aba: Aba; label: string; admin: boolean }[] = [
    { aba: "caderno", label: "Caderno de questões", admin: false },
    { aba: "revisao", label: "Revisão", admin: false },
    { aba: "desempenho", label: "Desempenho", admin: false },
    { aba: "cadastro", label: "Cadastro de questões", admin: true },
    { aba: "ia", label: "Cadastro de IA", admin: true },
    { aba: "estat", label: "Estatísticas", admin: true },
    { aba: "rag", label: "Biblioteca", admin: true },
    { aba: "pagamentos", label: "Pagamentos", admin: true },
]

function Painel({ usuario, aoSair }: { usuario: Usuario; aoSair: () => void }) {
    const [aba, setAba] = useState<Aba>("caderno")
    const [menuAberto, setMenuAberto] = useState(false)
    const admin = usuario.role === "superadmin"
    function ir(a: Aba) { setAba(a); setMenuAberto(false) }
    const [creditos, setCreditos] = useState<CreditosResumo | null>(null)
    async function recarregarCreditos() { setCreditos(await api.meusCreditos().catch(() => null)) }
    useEffect(() => { void recarregarCreditos() }, [])
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
                <div className="topo-esq">
                    <button className="hamburguer" aria-label="Abrir menu" onClick={() => setMenuAberto(true)}>☰</button>
                    <div>
                        <h1>Simulado - Transpetro e Petrobrás</h1>
                        <p className="sub">Simulados reais, tutor de IA e desempenho por questão — sua preparação inteligente para a aprovação.</p>
                    </div>
                </div>
                <div className="topo-acoes">
                    <div className="chave-modo" role="group" aria-label="Modo de tela">
                        <button className={modo === "celular" ? "on" : ""} onClick={() => trocarModo("celular")} title="Celular">📱</button>
                        <button className={modo === "computador" ? "on" : ""} onClick={() => trocarModo("computador")} title="Computador/Tablet">🖥</button>
                    </div>
                    {creditos && (
                        <button className="chip-creditos" onClick={() => ir("perfil")} title="Ver extrato no Perfil">
                            💰 {creditos.acesso_livre
                                ? "acesso livre"
                                : <>{creditos.saldo} cr <span className="cr-det">· ganho {creditos.total_ganho} · gasto {creditos.total_gasto}</span></>}
                        </button>
                    )}
                    <button className={`secundario ${aba === "perfil" ? "on" : ""}`} onClick={() => ir("perfil")} title="Perfil">👤 Perfil</button>
                    <button className="secundario" onClick={sair}>Sair</button>
                </div>
            </header>

            {menuAberto && <div className="menu-backdrop" onClick={() => setMenuAberto(false)} />}
            <aside className={`menu-lateral ${menuAberto ? "aberto" : ""}`} aria-hidden={!menuAberto}>
                <div className="menu-cab">
                    <strong>Menu</strong>
                    <button className="link" aria-label="Fechar menu" onClick={() => setMenuAberto(false)}>✕</button>
                </div>
                <nav className="menu-itens">
                    {MENU.filter((m) => !m.admin || admin).map((m) => (
                        <button key={m.aba} className={aba === m.aba ? "ativa" : ""} onClick={() => ir(m.aba)}>{m.label}</button>
                    ))}
                    <button className={aba === "perfil" ? "ativa" : ""} onClick={() => ir("perfil")}>👤 Perfil</button>
                </nav>
            </aside>

            {aba === "caderno" && <Caderno modo={modo} />}
            {aba === "revisao" && <Revisao />}
            {aba === "desempenho" && <Desempenho />}
            {aba === "perfil" && <Perfil usuario={usuario} creditos={creditos} aoRecarregarCreditos={recarregarCreditos} />}
            {aba === "cadastro" && admin && <Cadastro />}
            {aba === "ia" && admin && <ConexoesIA />}
            {aba === "estat" && admin && <Estatisticas />}
            {aba === "rag" && admin && <Biblioteca />}
            {aba === "pagamentos" && admin && <Pagamentos />}
        </main>
    )
}
