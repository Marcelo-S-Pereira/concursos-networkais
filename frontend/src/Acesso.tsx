import { useState, type FormEvent } from "react"
import { api, type Usuario } from "./api"
import { mascararCpf, mascararTelefone } from "./formatos"

type Aba = "entrar" | "cadastrar"
type Etapa = "email" | "codigo"

export default function Acesso({ aoEntrar }: { aoEntrar: (u: Usuario) => void }) {
    const [aba, setAba] = useState<Aba>("entrar")

    return (
        <main className="tela tela-acesso">
            <h1>APP Concursos</h1>

            <div className="abas" role="tablist">
                <button role="tab" aria-selected={aba === "entrar"} className={aba === "entrar" ? "ativa" : ""} onClick={() => setAba("entrar")}>
                    Entrar
                </button>
                <button role="tab" aria-selected={aba === "cadastrar"} className={aba === "cadastrar" ? "ativa" : ""} onClick={() => setAba("cadastrar")}>
                    Criar conta
                </button>
            </div>

            {aba === "entrar" ? <Entrar aoEntrar={aoEntrar} /> : <Cadastrar aoConcluir={() => setAba("entrar")} />}
        </main>
    )
}

function Entrar({ aoEntrar }: { aoEntrar: (u: Usuario) => void }) {
    const [etapa, setEtapa] = useState<Etapa>("email")
    const [email, setEmail] = useState("")
    const [codigo, setCodigo] = useState("")
    const [aviso, setAviso] = useState<string | null>(null)
    const [erro, setErro] = useState<string | null>(null)
    const [enviando, setEnviando] = useState(false)

    async function pedirCodigo(e: FormEvent) {
        e.preventDefault()
        setErro(null)
        setEnviando(true)
        try {
            const r = await api.solicitarCodigo(email)
            setAviso(r.mensagem)
            setEtapa("codigo")
        } catch (err) {
            setErro(err instanceof Error ? err.message : "Não foi possível enviar o código.")
        } finally {
            setEnviando(false)
        }
    }

    async function confirmar(e: FormEvent) {
        e.preventDefault()
        setErro(null)
        setEnviando(true)
        try {
            aoEntrar(await api.verificarCodigo(email, codigo))
        } catch (err) {
            setErro(err instanceof Error ? err.message : "Código inválido.")
        } finally {
            setEnviando(false)
        }
    }

    if (etapa === "email") {
        return (
            <form className="cartao" onSubmit={pedirCodigo}>
                <p className="explica">Digite seu e-mail. Enviamos um código de acesso — não existe senha.</p>
                <label>
                    E-mail
                    <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" required autoFocus />
                </label>
                {erro && <p className="falha">{erro}</p>}
                <button type="submit" disabled={enviando}>{enviando ? "Enviando…" : "Enviar código"}</button>
            </form>
        )
    }

    return (
        <form className="cartao" onSubmit={confirmar}>
            {aviso && <p className="explica">{aviso}</p>}
            <label>
                Código de 6 dígitos
                <input
                    className="codigo"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    value={codigo}
                    onChange={(e) => setCodigo(e.target.value.replace(/\D/g, ""))}
                    autoComplete="one-time-code"
                    required
                    autoFocus
                />
            </label>
            {erro && <p className="falha">{erro}</p>}
            <button type="submit" disabled={enviando || codigo.length !== 6}>{enviando ? "Verificando…" : "Entrar"}</button>
            <button type="button" className="secundario" onClick={() => { setEtapa("email"); setCodigo(""); setErro(null) }}>
                Usar outro e-mail
            </button>
        </form>
    )
}

function Cadastrar({ aoConcluir }: { aoConcluir: () => void }) {
    const [form, setForm] = useState({ nome: "", email: "", cpf: "", telefone: "" })
    const [erro, setErro] = useState<string | null>(null)
    const [ok, setOk] = useState<string | null>(null)
    const [enviando, setEnviando] = useState(false)

    function campo(nome: keyof typeof form) {
        return (valor: string) => setForm((f) => ({ ...f, [nome]: valor }))
    }

    async function enviar(e: FormEvent) {
        e.preventDefault()
        setErro(null)
        setEnviando(true)
        try {
            const r = await api.cadastrar(form)
            setOk(r.mensagem)
            setTimeout(aoConcluir, 1800)
        } catch (err) {
            setErro(err instanceof Error ? err.message : "Não foi possível cadastrar.")
        } finally {
            setEnviando(false)
        }
    }

    if (ok) return <div className="cartao"><p className="sucesso">{ok}</p></div>

    return (
        <form className="cartao" onSubmit={enviar}>
            <label>
                Nome completo
                <input value={form.nome} onChange={(e) => campo("nome")(e.target.value)} autoComplete="name" required autoFocus />
            </label>
            <label>
                E-mail
                <input type="email" value={form.email} onChange={(e) => campo("email")(e.target.value)} autoComplete="email" required />
            </label>
            <label>
                CPF
                <input inputMode="numeric" value={form.cpf} onChange={(e) => campo("cpf")(mascararCpf(e.target.value))} required />
            </label>
            <label>
                Telefone
                <input inputMode="tel" value={form.telefone} onChange={(e) => campo("telefone")(mascararTelefone(e.target.value))} autoComplete="tel" required />
            </label>
            {erro && <p className="falha">{erro}</p>}
            <button type="submit" disabled={enviando}>{enviando ? "Cadastrando…" : "Criar conta"}</button>
        </form>
    )
}
