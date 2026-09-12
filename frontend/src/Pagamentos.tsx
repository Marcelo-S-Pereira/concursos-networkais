import { useEffect, useState } from "react"
import { api, type ConfigPagamento, type PlataformaPagamento, type PlataformaPagamentoInput } from "./api"
import CampoSecreto from "./CampoSecreto"

const PROVEDORES = [
    { v: "mercadopago", nome: "Mercado Pago" },
    { v: "stripe", nome: "Stripe" },
    { v: "efi", nome: "Efí (Gerencianet)" },
    { v: "asaas", nome: "Asaas" },
    { v: "outro", nome: "Outro" },
]
const nomeProvedor = (v: string) => PROVEDORES.find((p) => p.v === v)?.nome ?? v

export default function Pagamentos() {
    const [plats, setPlats] = useState<PlataformaPagamento[] | null>(null)
    const [config, setConfig] = useState<ConfigPagamento | null>(null)
    const [adicionando, setAdicionando] = useState(false)

    async function recarregar() {
        setPlats(await api.pagPlataformas())
        setConfig(await api.pagConfig())
    }
    useEffect(() => { recarregar().catch(() => setPlats([])) }, [])

    if (!plats) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Cadastre o provedor de pagamento e o <strong>valor fixo</strong>. Modelo simples: um preço único que dá
                créditos, e cada simulado consome créditos. Só você (admin) vê esta aba.
            </p>

            {config && <ConfigValor inicial={config} aoSalvar={recarregar} />}

            <div className="topo-cadernos" style={{ marginTop: 18 }}>
                <h3 style={{ margin: 0 }}>Provedores de pagamento</h3>
                <button className="add" onClick={() => setAdicionando((v) => !v)}>{adicionando ? "Cancelar" : "+ Adicionar provedor"}</button>
            </div>
            {adicionando && <FormProvedor aoConcluir={async () => { setAdicionando(false); await recarregar() }} />}
            {plats.map((p) => <CardProvedor key={p.id} p={p} aoMudar={recarregar} />)}
            {!plats.length && !adicionando && <p className="neutro">Nenhum provedor cadastrado ainda.</p>}

            <Instrucoes />
        </div>
    )
}

/** Custo do dia de hoje só pra mostrar ao admin — mesma conta do backend
 *  (`acesso_diario.custo_do_dia`), aproximado; o valor que vale é sempre o
 *  do servidor. */
function custoDoDiaHoje(poolMensal: number): number {
    const hoje = new Date()
    const diasNoMes = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0).getDate()
    return Math.max(1, Math.round(poolMensal / diasNoMes))
}

function ConfigValor({ inicial, aoSalvar }: { inicial: ConfigPagamento; aoSalvar: () => Promise<void> }) {
    const [f, setF] = useState<ConfigPagamento>(inicial)
    const [salvando, setSalvando] = useState(false)
    const [salvo, setSalvo] = useState(false)
    const custoHoje = custoDoDiaHoje(f.creditos_por_compra)

    async function salvar() {
        setSalvando(true)
        try { await api.salvarPagConfig(f); setSalvo(true); await aoSalvar() }
        finally { setSalvando(false) }
    }

    return (
        <div className="cartao">
            <h3 style={{ margin: "0 0 8px" }}>Valor fixo — pool mensal</h3>
            <div className="grade-estat">
                <label>Preço (R$)<input type="number" step="0.01" value={f.preco_reais}
                    onChange={(e) => { setF({ ...f, preco_reais: Number(e.target.value) }); setSalvo(false) }} /></label>
                <label>Créditos por mês<input type="number" value={f.creditos_por_compra}
                    onChange={(e) => { setF({ ...f, creditos_por_compra: Number(e.target.value) }); setSalvo(false) }} /></label>
            </div>
            <p className="dica">
                Cada compra dá <b>{f.creditos_por_compra}</b> créditos por <b>R$ {f.preco_reais.toFixed(2)}</b>, válidos
                até o fim do mês (não acumulam). Simulado, chat de estudo e tutor ficam atrás de uma <b>porta de acesso
                diária</b>: o primeiro uso do dia já abre, sem botão — custa <b>{f.creditos_por_compra} ÷ dias do mês</b>,
                hoje seria <b>~{custoHoje} créditos</b>. O aluno nunca vê esse número — só um gráfico de atividade da
                semana. Admin, moderador (quando existir) e vitalício não pagam nada disso.
            </p>
            <button disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar valor"}</button>
            {salvo && <span className="dica"> ✓ salvo</span>}
        </div>
    )
}

const VAZIO: PlataformaPagamentoInput = { titulo: "", provedor: "mercadopago", access_token: "", public_key: "" }

function FormProvedor({ aoConcluir }: { aoConcluir: () => void }) {
    const [f, setF] = useState<PlataformaPagamentoInput>({ ...VAZIO, titulo: "Mercado Pago" })
    const [erro, setErro] = useState<string | null>(null)
    const [salvando, setSalvando] = useState(false)

    async function salvar() {
        setSalvando(true); setErro(null)
        try { await api.criarPagPlataforma(f); aoConcluir() }
        catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar") }
        finally { setSalvando(false) }
    }

    return (
        <div className="cartao form-ia">
            <h4 style={{ margin: "0 0 6px" }}>Novo provedor</h4>
            <label>Provedor
                <select value={f.provedor} onChange={(e) => setF({ ...f, provedor: e.target.value, titulo: nomeProvedor(e.target.value) })}>
                    {PROVEDORES.map((p) => <option key={p.v} value={p.v}>{p.nome}</option>)}
                </select>
            </label>
            <label>Apelido<input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} /></label>
            <label>Access token (chave secreta)
                <CampoSecreto valor={f.access_token} aoMudar={(v) => setF({ ...f, access_token: v })} placeholder="APP_USR-… (produção)" />
            </label>
            <label>Public key (não secreta)<input value={f.public_key} onChange={(e) => setF({ ...f, public_key: e.target.value })} placeholder="opcional" /></label>
            {erro && <p className="falha">{erro}</p>}
            <div className="linha-acoes"><button disabled={salvando} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button></div>
        </div>
    )
}

function CardProvedor({ p, aoMudar }: { p: PlataformaPagamento; aoMudar: () => Promise<void> }) {
    const [aberto, setAberto] = useState(false)
    const [f, setF] = useState<PlataformaPagamentoInput>({ titulo: p.titulo, provedor: p.provedor, access_token: "", public_key: p.public_key })
    const [teste, setTeste] = useState<string | null>(null)
    const [salvando, setSalvando] = useState(false)

    async function salvar() {
        setSalvando(true)
        try { await api.editarPagPlataforma(p.id, f); await aoMudar() }
        finally { setSalvando(false) }
    }
    async function testar() {
        setTeste("testando…")
        const r = await api.testarPagPlataforma(p.id).catch((e) => ({ ok: false, mensagem: e instanceof Error ? e.message : "erro" }))
        setTeste(r.mensagem)
    }

    return (
        <div className={`card-modelo ${p.ativa ? "ativa" : ""}`}>
            <div className="modelo-topo" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <span className="modelo">{p.titulo} <span className="dica">({nomeProvedor(p.provedor)})</span></span>
                <span className="chave">{p.token_mascarado || "sem chave"}</span>
                {p.ativa ? <span className="tag-ativa">ativo</span> : <span className="tag-fb">—</span>}
            </div>
            {aberto && (
                <div className="modelo-corpo form-ia">
                    <label>Apelido<input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} /></label>
                    <label>Access token (deixe em branco para manter)
                        <CampoSecreto valor={f.access_token} aoMudar={(v) => setF({ ...f, access_token: v })}
                            placeholder="•••• (mantém a atual)" aoRevelar={async () => (await api.revelarPagToken(p.id)).access_token} />
                    </label>
                    <label>Public key<input value={f.public_key} onChange={(e) => setF({ ...f, public_key: e.target.value })} /></label>
                    <div className="linha-acoes">
                        <button disabled={salvando} onClick={salvar}>Salvar</button>
                        {!p.ativa && <button onClick={async () => { await api.ativarPagPlataforma(p.id); await aoMudar() }}>Tornar ativo</button>}
                        <button className="secundario" onClick={testar}>Testar</button>
                        {teste && <span className="teste-res">{teste}</span>}
                        <button className="perigo" onClick={async () => { if (confirm(`Apagar "${p.titulo}"?`)) { await api.apagarPagPlataforma(p.id); await aoMudar() } }}>Apagar</button>
                    </div>
                </div>
            )}
        </div>
    )
}

function Instrucoes() {
    return (
        <div className="cartao" style={{ marginTop: 16 }}>
            <h3 style={{ margin: "0 0 6px" }}>Como conectar o Mercado Pago</h3>
            <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, fontSize: ".9rem" }}>
                <li>Entre na sua conta do <b>Mercado Pago</b> → <b>Suas integrações</b> (developers) → crie uma <b>aplicação</b>.</li>
                <li>Em <b>Credenciais de produção</b>, copie o <b>Access Token</b> e a <b>Public Key</b>.</li>
                <li>Aqui em <b>“+ Adicionar provedor”</b>, escolha Mercado Pago, cole o Access Token (e a Public Key) e salve.</li>
                <li>Clique em <b>Testar</b> — deve dizer “Conectado ao Mercado Pago: …”. Depois, <b>Tornar ativo</b>.</li>
                <li>No seu negócio no MP, configure o <b>nome/logo da loja</b> (é o que o comprador vê ao pagar).</li>
                <li>Pronto para o próximo passo: o checkout de <b>{"{"}preço{"}"} = créditos</b> vai usar o provedor ativo (eu construo em seguida).</li>
            </ol>
        </div>
    )
}
