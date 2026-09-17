import { useEffect, useRef, useState } from "react"
import { api, type AdminOverview, type CreditosResumo, type EstadoHoje, type FilaEstado, type FilaHistoricoLinha, type LimitesConfig, type Orcamento, type RecursoCatalogo, type ResumoSemana, type SaudeVPS, type Usuario, type UsuarioAdmin } from "./api"
import CampoSecreto from "./CampoSecreto"

const HIERARQUIA: Record<string, string> = {
    superadmin: "Administrador mestre",
    aluno: "Aluno",
}
const STATUS_ROTULO: Record<string, string> = { ok: "tudo bem", atencao: "atenção", critico: "crítico" }
const TIPO_ROTULO: Record<string, string> = {
    compra: "compra", bonus: "bônus", ajuste: "ajuste", acesso_diario: "acesso do dia",
    gasto_simulado: "simulado", gasto_chat_texto: "chat (texto)", gasto_chat_voz: "chat (voz)",
}

/** Barra de HOJE: contagem regressiva de verdade (não "% usado" — o uso é
 *  ilimitado uma vez aberta a porta). Ancorada no momento em que abriu, não na
 *  meia-noite — senão quem abre às 23h veria a barra quase cheia sem ter usado
 *  nada. Tica sozinha, mesmo padrão `setInterval` do cronômetro do simulado
 *  em Caderno.tsx. */
function BarraHoje({ hoje }: { hoje: EstadoHoje }) {
    const [estado, setEstado] = useState({ pct: 0, restanteMin: 0 })
    const abriuMs = useRef(hoje.abriu_em ? new Date(hoje.abriu_em).getTime() : 0)
    const fechaMs = useRef(hoje.fecha_em ? new Date(hoje.fecha_em).getTime() : 0)

    useEffect(() => {
        if (!hoje.aberto) return
        const calcular = () => {
            const total = fechaMs.current - abriuMs.current
            const decorrido = Date.now() - abriuMs.current
            setEstado({
                pct: Math.max(0, Math.min(100, total > 0 ? (decorrido / total) * 100 : 100)),
                restanteMin: Math.max(0, Math.round((fechaMs.current - Date.now()) / 60000)),
            })
        }
        calcular()
        const t = setInterval(calcular, 15000)
        return () => clearInterval(t)
    }, [hoje.aberto])

    if (!hoje.aberto) return <p className="dica" style={{ margin: "0 0 4px" }}>Hoje: acesso ainda não aberto.</p>
    return (
        <div style={{ marginBottom: 10 }}>
            <p className="dica" style={{ margin: "0 0 4px" }}>Hoje — fecha em {estado.restanteMin} min</p>
            <div className="barra-uso"><div className="barra-uso-fill" style={{ width: `${estado.pct}%` }} /></div>
        </div>
    )
}

/** Barra da SEMANA: créditos gastos na semana corrente ÷ alvo semanal
 *  (7 × custo do dia) — mesma dupla hoje/semana do plataforma de estudo de verdade.
 *  Só leitura da mesma CreditTransaction da porta diária; reseta sozinha na
 *  virada da semana, sem dedução própria. */
function BarraSemana({ semana }: { semana: ResumoSemana }) {
    const pct = semana.alvo > 0 ? Math.min(100, (semana.usado / semana.alvo) * 100) : 0
    return (
        <div>
            <p className="dica" style={{ margin: "0 0 4px" }}>Esta semana</p>
            <div className="barra-uso"><div className="barra-uso-fill" style={{ width: `${pct}%` }} /></div>
        </div>
    )
}

export default function Perfil({
    usuario, creditos, aoRecarregarCreditos, aoAtualizarUsuario,
}: {
    usuario: Usuario
    creditos: CreditosResumo | null
    aoRecarregarCreditos: () => Promise<void>
    aoAtualizarUsuario: (u: Usuario) => void
}) {
    const admin = usuario.role === "superadmin"
    const [ov, setOv] = useState<AdminOverview | null>(null)
    const [saude, setSaude] = useState<SaudeVPS | null>(null)
    const [porta, setPorta] = useState<{ hoje: EstadoHoje; semana: ResumoSemana } | null>(null)

    async function carregarSaude() { setSaude(await api.adminSaude().catch(() => null)) }
    useEffect(() => {
        if (admin) { api.adminOverview().then(setOv).catch(() => setOv(null)); void carregarSaude() }
        else { api.minhaPorta().then(setPorta).catch(() => setPorta(null)) }
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

            <CardSenha usuario={usuario} aoAtualizarUsuario={aoAtualizarUsuario} />

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
                            <p className="dica">
                                Simulado, chat de estudo e tutor abrem sozinhos no primeiro uso do dia.
                            </p>
                            <ComprarCreditos />
                            {porta && (
                                <div style={{ marginTop: 10 }}>
                                    <BarraHoje hoje={porta.hoje} />
                                    <BarraSemana semana={porta.semana} />
                                </div>
                            )}
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
                    <CardFila />
                    <ConcederCredito aoConcluir={aoRecarregarCreditos} />
                    <Campanhas aoConcluir={aoRecarregarCreditos} />
                </div>
            )}
        </div>
    )
}

/** [118]: senha de acesso — opcional, ao lado do código por e-mail (que
 * continua sempre disponível como recuperação, sem rota própria). Serve pro
 * admin e pro aluno, sem distinção de papel. */
function CardSenha({ usuario, aoAtualizarUsuario }: { usuario: Usuario; aoAtualizarUsuario: (u: Usuario) => void }) {
    const [aberto, setAberto] = useState(false)
    const [senha, setSenha] = useState("")
    const [confirmar, setConfirmar] = useState("")
    const [erro, setErro] = useState<string | null>(null)
    const [ok, setOk] = useState<string | null>(null)
    const [enviando, setEnviando] = useState(false)

    async function salvar() {
        setErro(null); setOk(null)
        if (senha.length < 8) { setErro("A senha precisa ter pelo menos 8 caracteres."); return }
        if (senha !== confirmar) { setErro("As senhas não coincidem."); return }
        setEnviando(true)
        try {
            const u = await api.cadastrarSenha(senha)
            aoAtualizarUsuario(u)
            setSenha(""); setConfirmar(""); setAberto(false)
            setOk(usuario.tem_senha ? "Senha trocada." : "Senha cadastrada — já pode entrar com ela.")
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível salvar a senha.")
        } finally { setEnviando(false) }
    }

    async function alternar(habilitada: boolean) {
        setErro(null)
        try { aoAtualizarUsuario(await api.alternarSenha(habilitada)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Não foi possível mudar isso agora.") }
    }

    return (
        <div className="cartao">
            <h3 style={{ margin: "0 0 8px" }}>Senha de acesso</h3>
            <p className="dica">
                Opcional, ao lado do código por e-mail (que continua sempre funcionando — inclusive pra
                recuperar o acesso se você esquecer a senha).
            </p>
            {usuario.tem_senha && (
                <label className="bloq-cadastros" style={{ margin: "6px 0" }}>
                    <input type="checkbox" checked={usuario.senha_habilitada} onChange={(e) => alternar(e.target.checked)} />
                    <span>Entrar com senha {usuario.senha_habilitada ? "— ligado ✓" : "— desligado"}</span>
                </label>
            )}
            {!aberto ? (
                <button className="secundario" onClick={() => setAberto(true)}>
                    {usuario.tem_senha ? "Trocar senha" : "Cadastrar senha"}
                </button>
            ) : (
                <div style={{ marginTop: 6 }}>
                    <label>Nova senha (mín. 8 caracteres)
                        <CampoSecreto valor={senha} aoMudar={setSenha} placeholder="••••••••" />
                    </label>
                    <label>Confirmar
                        <CampoSecreto valor={confirmar} aoMudar={setConfirmar} placeholder="••••••••" />
                    </label>
                    {erro && <p className="falha" style={{ margin: "4px 0" }}>{erro}</p>}
                    <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
                        <button disabled={enviando} onClick={salvar}>{enviando ? "Salvando…" : "Salvar"}</button>
                        <button className="secundario" onClick={() => { setAberto(false); setSenha(""); setConfirmar(""); setErro(null) }}>Cancelar</button>
                    </div>
                </div>
            )}
            {ok && <p className="dica" style={{ color: "var(--ok)", marginTop: 6 }}>{ok}</p>}
        </div>
    )
}

/** [112]: botão real de compra — cria a preferência no Mercado Pago e abre o
 * checkout numa aba nova. Erro claro (ex: sem plataforma cadastrada) em vez
 * de fingir que funciona. */
function ComprarCreditos() {
    const [carregando, setCarregando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function comprar() {
        setCarregando(true); setErro(null)
        try {
            const r = await api.creditosComprar()
            window.open(r.init_point, "_blank", "noopener")
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível iniciar a compra.")
        } finally { setCarregando(false) }
    }

    return (
        <div style={{ marginTop: 4 }}>
            <button disabled={carregando} onClick={comprar}>
                {carregando ? "Abrindo pagamento…" : "Comprar créditos (Mercado Pago)"}
            </button>
            {erro && <p className="falha" style={{ margin: "4px 0 0" }}>{erro}</p>}
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

/** [126]: fila de admissão para chamadas de IA — teto de concorrência
 * editável (padrão 5, "sai 1 entra mais 1") + gate por CPU/memória/disco
 * (padrão 78% os três, editáveis separadamente). Vale pra API do admin hoje
 * e, quando a API compartilhada da comunidade ([119]) existir, pro mesmo
 * ponto — sem precisar mexer aqui de novo. */
function CardFila() {
    const [f, setF] = useState<FilaEstado | null>(null)
    const [historico, setHistorico] = useState<FilaHistoricoLinha[] | null>(null)
    const [campos, setCampos] = useState({ max_concorrente: "", cpu_pct_max: "", mem_pct_max: "", disco_pct_max: "", timeout_espera_s: "" })
    const [msg, setMsg] = useState("")

    async function carregar() {
        const r = await api.adminFila().catch(() => null)
        setF(r)
        if (r) {
            setCampos({
                max_concorrente: String(r.max_concorrente), cpu_pct_max: String(r.cpu_pct_max),
                mem_pct_max: String(r.mem_pct_max), disco_pct_max: String(r.disco_pct_max),
                timeout_espera_s: String(r.timeout_espera_s),
            })
        }
    }
    async function carregarHistorico() { setHistorico(await api.adminFilaHistorico(7).catch(() => null)) }
    useEffect(() => { void carregar(); void carregarHistorico() }, [])

    async function salvar() {
        setMsg("")
        try {
            const r = await api.salvarFila({
                max_concorrente: Number(campos.max_concorrente) || 1,
                cpu_pct_max: Number(campos.cpu_pct_max) || 78,
                mem_pct_max: Number(campos.mem_pct_max) || 78,
                disco_pct_max: Number(campos.disco_pct_max) || 78,
                timeout_espera_s: Number(campos.timeout_espera_s) || 60,
            })
            setF(r); setMsg("Salvo.")
        } catch (e) { setMsg(e instanceof Error ? e.message : "Falha ao salvar.") }
    }

    if (!f) return null
    return (
        <div className="cartao">
            <div className="saude-cab">
                <strong>Fila de chamadas de IA</strong>
                <button className="link" onClick={() => { carregar(); carregarHistorico() }} title="Atualizar">↻</button>
            </div>
            <p className="dica">
                Limita quantas chamadas de IA ficam em andamento ao mesmo tempo — protege o servidor de
                colapsar. Sai uma, entra mais uma. Também segura novas admissões se CPU, memória ou disco da
                ambiente de execucao estiverem acima do limiar. Vale pra sua própria API e, no futuro, pra API que outros
                usuários compartilharem em troca de créditos.
            </p>
            <div className="uso-grade">
                <div className="uso-item destaque"><span className="uso-num">{f.em_voo}/{f.max_concorrente}</span><span className="uso-rot">em andamento</span></div>
                <div className="uso-item"><span className="uso-num">{f.esperando}</span><span className="uso-rot">esperando vaga</span></div>
                <div className="uso-item"><span className="uso-num">{f.cpu_pct}%</span><span className="uso-rot">CPU (teto {f.cpu_pct_max}%)</span></div>
                <div className="uso-item"><span className="uso-num">{f.memoria_pct ?? "—"}%</span><span className="uso-rot">memória (teto {f.mem_pct_max}%)</span></div>
                <div className="uso-item"><span className="uso-num">{f.disco_pct ?? "—"}%</span><span className="uso-rot">disco (teto {f.disco_pct_max}%)</span></div>
            </div>
            <div className="grade-estat">
                <label>Requisições simultâneas<input value={campos.max_concorrente} onChange={(e) => setCampos({ ...campos, max_concorrente: e.target.value })} inputMode="numeric" /></label>
                <label>Teto de CPU (%)<input value={campos.cpu_pct_max} onChange={(e) => setCampos({ ...campos, cpu_pct_max: e.target.value })} inputMode="decimal" /></label>
                <label>Teto de memória (%)<input value={campos.mem_pct_max} onChange={(e) => setCampos({ ...campos, mem_pct_max: e.target.value })} inputMode="decimal" /></label>
                <label>Teto de disco (%)<input value={campos.disco_pct_max} onChange={(e) => setCampos({ ...campos, disco_pct_max: e.target.value })} inputMode="decimal" /></label>
                <label>Espera máxima na fila (s)<input value={campos.timeout_espera_s} onChange={(e) => setCampos({ ...campos, timeout_espera_s: e.target.value })} inputMode="numeric" /></label>
            </div>
            <div className="linha-acoes"><button onClick={salvar}>Salvar</button>{msg && <span className="dica">{msg}</span>}</div>

            {historico && historico.length > 0 && (
                <details className="uso-erros">
                    <summary>Histórico dos últimos 7 dias (amostra a cada 3 min) — {historico.length} pontos</summary>
                    <ul>
                        {historico.slice(-20).reverse().map((h, i) => (
                            <li key={i}>
                                <span className="uso-erro-quando">{new Date(h.quando).toLocaleString("pt-BR")}</span>
                                <span className="uso-erro-origem">CPU {h.cpu_pct ?? "—"}% · mem {h.memoria_pct ?? "—"}% · disco {h.disco_pct ?? "—"}%</span>
                                <span className="uso-erro-msg">
                                    {h.admitidas} admitida(s){h.rejeitadas > 0 ? ` · ${h.rejeitadas} rejeitada(s)` : ""}
                                    {h.espera_media_ms !== null ? ` · espera média ${h.espera_media_ms}ms` : ""}
                                </span>
                            </li>
                        ))}
                    </ul>
                </details>
            )}
        </div>
    )
}

/** Contorno por categoria ([105]) — precedência: CPF do dono (contas de
 *  teste, [102]) > moderador (papel ainda não existe no sistema, fica
 *  pronto pra quando existir) > vitalício > usuário normal (padrão). */
function categoriaUsuario(u: UsuarioAdmin): "verde" | "azul" | "cinza" | "vermelho" {
    if (u.mesmo_cpf_dono) return "verde"
    if (u.role === "moderador") return "azul"
    if (u.vitalicio) return "cinza"
    return "vermelho"
}
/** 👑 pagante que virou vitalício · 💳 pagante normal (paga por crédito) ·
 *  🎁 vitalício doado (nunca comprou) — hoje só o 🎁 pode aparecer de
 *  verdade, porque o checkout do Mercado Pago ([075]) nunca foi concluído. */
function iconePagamento(u: UsuarioAdmin): string {
    if (u.vitalicio) return u.comprado > 0 ? "👑" : "🎁"
    return u.comprado > 0 ? "💳" : ""
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
            <p className="dica" style={{ margin: "0 0 6px" }}>
                🟢 CPF do dono (teste) · 🔵 moderador · ⚪ vitalício · 🔴 usuário normal —
                👑 pagante vitalício · 💳 pagante · 🎁 vitalício doado
            </p>
            <div className="lista-usuarios" role="listbox" aria-label="Selecione o usuário">
                {usuarios.map((u) => (
                    <button key={u.id} type="button" role="option" aria-selected={email === u.email}
                        className={`usuario-linha ${categoriaUsuario(u)} ${email === u.email ? "sel" : ""}`}
                        onClick={() => setEmail(u.email)}>
                        {iconePagamento(u) && <span className="usuario-icone">{iconePagamento(u)}</span>}
                        <span className="usuario-nome-email">
                            <span className="usuario-nome">{u.nome}</span>
                            <span className="usuario-email">{u.email}</span>
                        </span>
                        <span className="usuario-valores">comprou {u.comprado} · doado {u.doado}</span>
                    </button>
                ))}
                {!usuarios.length && <p className="dica">Nenhum usuário ainda.</p>}
            </div>
            <div className="grade-estat">
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
