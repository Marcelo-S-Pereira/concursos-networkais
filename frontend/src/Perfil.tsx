import { useEffect, useState } from "react"
import { api, type AdminOverview, type CreditosResumo, type LimitesConfig, type Orcamento, type RecursoCatalogo, type SaudeVPS, type Usuario, type UsuarioAdmin } from "./api"

const HIERARQUIA: Record<string, string> = {
    superadmin: "Administrador mestre",
    aluno: "Aluno",
}
const STATUS_ROTULO: Record<string, string> = { ok: "tudo bem", atencao: "atenção", critico: "crítico" }
const TIPO_ROTULO: Record<string, string> = {
    compra: "compra", bonus: "bônus", ajuste: "ajuste",
    gasto_simulado: "simulado", gasto_chat_texto: "chat (texto)", gasto_chat_voz: "chat (voz)",
}

export default function Perfil({
    usuario, creditos, aoRecarregarCreditos,
}: {
    usuario: Usuario
    creditos: CreditosResumo | null
    aoRecarregarCreditos: () => Promise<void>
}) {
    const admin = usuario.role === "superadmin"
    const [ov, setOv] = useState<AdminOverview | null>(null)
    const [saude, setSaude] = useState<SaudeVPS | null>(null)

    async function carregarSaude() { setSaude(await api.adminSaude().catch(() => null)) }
    useEffect(() => {
        if (admin) { api.adminOverview().then(setOv).catch(() => setOv(null)); void carregarSaude() }
    }, [admin])

    async function bloquear(b: boolean) {
        const r = await api.adminBloquearCadastros(b)
        setSaude((s) => (s ? { ...s, cadastros_bloqueados: r.cadastros_bloqueados } : s))
    }

    return (
        <div>
            <div className="cartao perfil-id">
                <h2 style={{ margin: "0 0 4px" }}>{usuario.nome}</h2>
                <span className={`hierarquia ${admin ? "mestre" : ""}`}>{HIERARQUIA[usuario.role] ?? usuario.role}</span>
                <div className="perfil-dados">
                    <div><span className="rot">E-mail</span> {usuario.email}</div>
                    <div><span className="rot">CPF</span> {usuario.cpf}</div>
                    <div><span className="rot">Telefone</span> {usuario.telefone}</div>
                </div>
            </div>

            {creditos && (
                <div className="cartao">
                    <h3 style={{ margin: "0 0 8px" }}>Meus créditos</h3>
                    {creditos.acesso_livre ? (
                        <p className="dica">Você tem <b>acesso livre</b> (administrador) — não consome créditos.</p>
                    ) : (
                        <>
                            <div className="uso-grade">
                                <div className="uso-item destaque"><span className="uso-num">{creditos.saldo}</span><span className="uso-rot">saldo</span></div>
                                <div className="uso-item"><span className="uso-num">{creditos.total_ganho}</span><span className="uso-rot">total ganho</span></div>
                                <div className="uso-item"><span className="uso-num">{creditos.total_gasto}</span><span className="uso-rot">total gasto</span></div>
                            </div>
                            <p className="dica">Cada simulado e o chat consomem créditos. Compre mais na aba de planos (em breve).</p>
                        </>
                    )}
                    {creditos.extrato.length > 0 && (
                        <details className="uso-erros" style={{ marginTop: 6 }}>
                            <summary>extrato detalhado ({creditos.extrato.length})</summary>
                            <table className="tabela-estat" style={{ marginTop: 6 }}>
                                <thead><tr><th>Quando</th><th>Movimento</th><th style={{ textAlign: "right" }}>Créditos</th></tr></thead>
                                <tbody>
                                    {creditos.extrato.map((t, i) => (
                                        <tr key={i}>
                                            <td>{t.quando ? new Date(t.quando).toLocaleString("pt-BR") : ""}</td>
                                            <td>{TIPO_ROTULO[t.tipo] ?? t.tipo}{t.descricao ? ` — ${t.descricao}` : ""}</td>
                                            <td style={{ textAlign: "right", color: t.delta < 0 ? "#c0392b" : "#2e7d32" }}>{t.delta > 0 ? "+" : ""}{t.delta}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </details>
                    )}
                </div>
            )}

            {admin && (
                <div className="painel-admin">
                    <h3>Painel do administrador</h3>
                    <p className="dica">Visível só para você (administrador mestre).</p>

                    {saude && (
                        <div className={`cartao saude saude-${saude.status}`}>
                            <div className="saude-cab">
                                <strong>Saúde do servidor</strong>
                                <span className={`saude-badge ${saude.status}`}>{STATUS_ROTULO[saude.status] ?? saude.status}</span>
                                <button className="link" onClick={carregarSaude} title="Atualizar">↻</button>
                            </div>
                            <div className="uso-grade">
                                <div className="uso-item"><span className="uso-num">{saude.load_por_cpu}</span><span className="uso-rot">carga / núcleo ({saude.cpus})</span></div>
                                <div className="uso-item"><span className="uso-num">{saude.memoria_pct ?? "—"}%</span><span className="uso-rot">memória</span></div>
                                <div className="uso-item"><span className="uso-num">{saude.disco_pct ?? "—"}%</span><span className="uso-rot">disco</span></div>
                                <div className="uso-item"><span className="uso-num">{saude.conexoes_db ?? "—"}</span><span className="uso-rot">conexões do banco</span></div>
                            </div>
                            {saude.motivos.length > 0 && <p className="falha">⚠ {saude.motivos.join(" · ")}</p>}
                            <label className="bloq-cadastros">
                                <input type="checkbox" checked={saude.cadastros_bloqueados} onChange={(e) => bloquear(e.target.checked)} />
                                <span>Bloquear novos cadastros {saude.cadastros_bloqueados ? "— fechado 🔒" : "— aberto 🔓"}</span>
                            </label>
                            <p className="dica">O sistema te avisa por e-mail e fecha os cadastros sozinho se a carga ficar crítica, para a ambiente de execucao não quebrar.</p>
                        </div>
                    )}

                    <div className="uso-grade">
                        <div className="uso-item"><span className="uso-num">{ov ? ov.usuarios : "…"}</span><span className="uso-rot">usuários</span></div>
                        <div className="uso-item"><span className="uso-num">{ov ? ov.simulados_feitos : "…"}</span><span className="uso-rot">simulados feitos</span></div>
                        <div className="uso-item"><span className="uso-num">{ov ? ov.cadernos : "…"}</span><span className="uso-rot">cadernos</span></div>
                        <div className="uso-item"><span className="uso-num">{ov ? ov.questoes : "…"}</span><span className="uso-rot">questões</span></div>
                    </div>

                    <CardOrcamento />
                    <CardLimites />
                    <ConcederCredito aoConcluir={aoRecarregarCreditos} />
                    <Campanhas aoConcluir={aoRecarregarCreditos} />
                </div>
            )}
        </div>
    )
}

function usd(v: number) { return `US$ ${v.toFixed(2)}` }

function CardOrcamento() {
    const [o, setO] = useState<Orcamento | null>(null)
    const [mensal, setMensal] = useState("")
    const [diario, setDiario] = useState("")
    const [msg, setMsg] = useState("")

    async function carregar() {
        const r = await api.adminOrcamento().catch(() => null)
        setO(r)
        if (r) { setMensal(String(r.orcamento_mensal_usd)); setDiario(String(r.orcamento_diario_usd)) }
    }
    useEffect(() => { void carregar() }, [])

    async function salvar() {
        setMsg("")
        try {
            const r = await api.salvarOrcamento(Number(mensal) || 0, diario ? Number(diario) : null)
            setO(r); setMsg("Salvo.")
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha ao salvar.") }
    }

    if (!o) return null
    return (
        <div className={`cartao orcamento ${o.diario_excedido ? "estourado" : ""}`}>
            <div className="saude-cab">
                <strong>Orçamento de IA (Together)</strong>
                {o.diario_excedido && <span className="saude-badge critico">teto do dia atingido</span>}
                <button className="link" onClick={carregar} title="Atualizar">↻</button>
            </div>
            <div className="uso-grade">
                <div className="uso-item destaque"><span className="uso-num">{usd(o.gasto_hoje_usd)}</span><span className="uso-rot">gasto hoje ({o.pct_dia}% do dia)</span></div>
                <div className="uso-item"><span className="uso-num">{usd(o.gasto_mes_usd)}</span><span className="uso-rot">gasto no mês ({o.pct_mes}%)</span></div>
                <div className="uso-item"><span className="uso-num">{usd(o.projecao_mes_usd)}</span><span className="uso-rot">projeção do mês</span></div>
                <div className="uso-item"><span className="uso-num">{usd(o.orcamento_diario_usd)}</span><span className="uso-rot">teto por dia</span></div>
            </div>
            <div className="grade-estat">
                <label>Teto mensal (US$)<input value={mensal} onChange={(e) => setMensal(e.target.value)} inputMode="decimal" /></label>
                <label>Teto diário (US$)<input value={diario} onChange={(e) => setDiario(e.target.value)} inputMode="decimal" placeholder="em branco = mensal ÷ 30" /></label>
            </div>
            <div className="linha-acoes"><button onClick={salvar}>Salvar</button>{msg && <span className="dica">{msg}</span>}</div>
            <p className="dica">
                Ao atingir o teto do dia, <b>as chamadas de IA pausam</b> até o dia seguinte (UTC) — vale para
                todos, inclusive você, porque o custo é o mesmo. O gasto vem do uso real × preço da API.
            </p>
        </div>
    )
}

function CardLimites() {
    const [c, setC] = useState<LimitesConfig | null>(null)
    const [sessao, setSessao] = useState("")
    const [semana, setSemana] = useState("")
    const [msg, setMsg] = useState("")

    async function carregar() {
        const r = await api.adminLimites().catch(() => null)
        setC(r)
        if (r) { setSessao(String(r.sessao_msgs)); setSemana(String(r.semana_msgs)) }
    }
    useEffect(() => { void carregar() }, [])

    async function salvar() {
        setMsg("")
        try {
            const r = await api.salvarLimites(Number(sessao) || 0, Number(semana) || 0)
            setC(r); setMsg("Salvo.")
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha ao salvar.") }
    }

    if (!c) return null
    return (
        <div className="cartao">
            <div className="saude-cab"><strong>Limites de ritmo por usuário</strong></div>
            <p className="dica">
                No modelo do plataforma de estudo: a <b>sessão de {c.janela_sessao_h}h</b> começa na primeira mensagem
                e expira {c.janela_sessao_h}h depois; a seguinte abre uma janela nova. A <b>semana</b> é
                rolante de {c.janela_semana_d} dias. Conta todas as chamadas de IA da pessoa (chat, tutor,
                gêmeas), não só o chat. <b>0 = sem limite.</b>
            </p>
            <div className="grade-estat">
                <label>Mensagens por sessão de {c.janela_sessao_h}h<input value={sessao} onChange={(e) => setSessao(e.target.value)} inputMode="numeric" /></label>
                <label>Mensagens por {c.janela_semana_d} dias<input value={semana} onChange={(e) => setSemana(e.target.value)} inputMode="numeric" /></label>
            </div>
            <div className="linha-acoes"><button onClick={salvar}>Salvar</button>{msg && <span className="dica">{msg}</span>}</div>
            <p className="dica">
                Você (administrador) não é limitado. O <b>vitalício continua sujeito</b>: ele não paga crédito,
                mas não pode queimar o orçamento sem teto — é exatamente para isso que o limite existe.
            </p>
        </div>
    )
}

function ConcederCredito({ aoConcluir }: { aoConcluir: () => Promise<void> }) {
    const [usuarios, setUsuarios] = useState<UsuarioAdmin[]>([])
    const [email, setEmail] = useState("")
    const [creditos, setCreditos] = useState("100")
    const [motivo, setMotivo] = useState("cortesia")
    const [msg, setMsg] = useState<string | null>(null)
    const [enviando, setEnviando] = useState(false)
    const [catalogo, setCatalogo] = useState<RecursoCatalogo | null>(null)
    const [recursoEscolhido, setRecursoEscolhido] = useState("")
    const [limiteRecurso, setLimiteRecurso] = useState("5")

    async function carregar() { setUsuarios(await api.adminUsuarios().catch(() => [])) }
    useEffect(() => { void carregar(); api.recursosCatalogo().then(setCatalogo).catch(() => setCatalogo(null)) }, [])
    const escolhido = usuarios.find((u) => u.email === email)
    const chavesRecurso = Object.keys(catalogo ?? {})
    useEffect(() => { if (!recursoEscolhido && chavesRecurso.length) setRecursoEscolhido(chavesRecurso[0]) }, [chavesRecurso, recursoEscolhido])

    async function doar() {
        if (!email) return
        setEnviando(true); setMsg(null)
        try {
            const r = await api.adminCreditar(email, Number(creditos), motivo)
            setMsg(`✓ ${escolhido?.nome ?? email} agora tem ${r.saldo} créditos`)
            await carregar(); await aoConcluir()
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha") }
        finally { setEnviando(false) }
    }
    async function alternarVitalicio() {
        if (!escolhido) return
        await api.adminVitalicio(escolhido.email, !escolhido.vitalicio)
        await carregar(); await aoConcluir()
    }
    async function liberarRecurso() {
        if (!escolhido || !recursoEscolhido) return
        await api.concederRecurso(escolhido.email, recursoEscolhido, Number(limiteRecurso) || 1)
        await carregar()
    }
    async function revogarRecurso(feature: string) {
        if (!escolhido) return
        await api.revogarRecurso(escolhido.email, feature)
        await carregar()
    }

    return (
        <div className="cartao">
            <h4 style={{ margin: "0 0 6px" }}>Doar créditos / acesso</h4>
            <div className="grade-estat">
                <label>Usuário
                    <select value={email} onChange={(e) => setEmail(e.target.value)}>
                        <option value="">— escolha —</option>
                        {usuarios.map((u) => (
                            <option key={u.id} value={u.email}>{u.nome} · {u.simulados} simulado(s) · {u.saldo} cr{u.vitalicio ? " · vitalício" : ""}{u.role === "superadmin" ? " (você)" : ""}</option>
                        ))}
                    </select>
                </label>
                <label>Créditos<input type="number" value={creditos} onChange={(e) => setCreditos(e.target.value)} /></label>
                <label>Motivo<input value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="cortesia" /></label>
            </div>
            {escolhido && (
                <p className="dica">
                    {escolhido.email} — saldo <b>{escolhido.saldo}</b> · acesso <b>{escolhido.vitalicio ? "vitalício (não gasta créditos)" : "por créditos"}</b>
                </p>
            )}
            <div className="linha-acoes">
                <button disabled={enviando || !email} onClick={doar}>{enviando ? "…" : "Doar créditos"}</button>
                {escolhido && escolhido.role !== "superadmin" && (
                    <button className="secundario" onClick={alternarVitalicio}>
                        {escolhido.vitalicio ? "Remover vitalício" : "Tornar vitalício ∞"}
                    </button>
                )}
            </div>
            {msg && <span className="dica"> {msg}</span>}

            {escolhido && escolhido.role !== "superadmin" && (
                <div className="recursos-bloco">
                    <p className="dica" style={{ marginBottom: 4 }}>
                        <b>Recursos restritos</b> — não é automático: cada um precisa ser liberado aqui, com um teto de
                        uso por dia. O resto da comunidade não vê nada disso até você liberar.
                    </p>
                    {escolhido.recursos.length > 0 && (
                        <ul className="lista-recursos">
                            {escolhido.recursos.map((r) => (
                                <li key={r.feature}>
                                    <span>{r.nome}</span>
                                    <span className="dica">{r.usado_hoje}/{r.limite_diario} hoje</span>
                                    <button className="link" onClick={() => revogarRecurso(r.feature)}>revogar</button>
                                </li>
                            ))}
                        </ul>
                    )}
                    {chavesRecurso.length > 0 && (
                        <div className="linha-acoes">
                            <select value={recursoEscolhido} onChange={(e) => setRecursoEscolhido(e.target.value)}>
                                {chavesRecurso.map((k) => <option key={k} value={k}>{catalogo?.[k].nome}</option>)}
                            </select>
                            <input type="number" min={1} style={{ width: 70 }} value={limiteRecurso}
                                onChange={(e) => setLimiteRecurso(e.target.value)} title="Limite por dia" />
                            <span className="dica">{catalogo?.[recursoEscolhido]?.unidade}</span>
                            <button className="secundario" onClick={liberarRecurso}>Liberar</button>
                        </div>
                    )}
                </div>
            )}
        </div>
    )
}

const ALVOS = [
    { v: "todos", nome: "Todos os usuários" },
    { v: "mais_ativos", nome: "Quem mais usa (top N)" },
    { v: "primeiros", nome: "Primeiros N cadastrados" },
]

function Campanhas({ aoConcluir }: { aoConcluir: () => Promise<void> }) {
    const [alvo, setAlvo] = useState("todos")
    const [quantidade, setQuantidade] = useState("100")
    const [limite, setLimite] = useState("100")
    const [motivo, setMotivo] = useState("campanha")
    const [previa, setPrevia] = useState<{ quantos: number; exemplos: string[] } | null>(null)
    const [msg, setMsg] = useState<string | null>(null)
    const usaLimite = alvo !== "todos"

    async function verPrevia() {
        setMsg(null)
        setPrevia(await api.campanhaPrevia(alvo, Number(limite)).catch(() => null))
    }
    async function aplicar() {
        if (!confirm(`Doar ${quantidade} créditos para ${previa?.quantos ?? "os"} usuário(s)?`)) return
        setMsg("aplicando…")
        try {
            const r = await api.aplicarCampanha(alvo, Number(quantidade), motivo, Number(limite))
            setMsg(`✓ ${r.beneficiados} usuário(s) receberam ${quantidade} créditos`)
            await aoConcluir()
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha") }
    }

    return (
        <div className="cartao">
            <h4 style={{ margin: "0 0 6px" }}>Campanhas de créditos (em lote)</h4>
            <div className="grade-estat">
                <label>Alvo
                    <select value={alvo} onChange={(e) => { setAlvo(e.target.value); setPrevia(null) }}>
                        {ALVOS.map((a) => <option key={a.v} value={a.v}>{a.nome}</option>)}
                    </select>
                </label>
                <label>Créditos (a doar)<input type="number" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} /></label>
                {usaLimite && <label>N (limite)<input type="number" value={limite} onChange={(e) => { setLimite(e.target.value); setPrevia(null) }} /></label>}
                <label>Motivo<input value={motivo} onChange={(e) => setMotivo(e.target.value)} /></label>
            </div>
            <div className="linha-acoes">
                <button className="secundario" onClick={verPrevia}>Prévia</button>
                {previa && <span className="dica">{previa.quantos} usuário(s){previa.exemplos.length ? `: ${previa.exemplos.join(", ")}…` : ""}</span>}
                <button disabled={!previa} onClick={aplicar}>Aplicar campanha</button>
            </div>
            {msg && <p className="dica">{msg}</p>}
            <p className="dica">⏳ <b>Aniversariantes</b> precisa do campo de nascimento; <b>afiliados</b> precisa do sistema de indicação — posso adicionar quando quiser.</p>
        </div>
    )
}
