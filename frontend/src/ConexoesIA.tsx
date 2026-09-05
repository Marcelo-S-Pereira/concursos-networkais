import { useEffect, useState } from "react"
import { api, type ConexaoIA, type ConexaoInput, type Plataforma, type PlataformaInput } from "./api"
import CampoSecreto from "./CampoSecreto"

// As 5 categorias, separadas: LLM, VLM, STT, TTS + Embeddings (RAG).
const CATEGORIAS: { chave: string; rotulo: string; dica: string }[] = [
    { chave: "texto", rotulo: "LLM — Texto", dica: "chat/completions" },
    { chave: "visao", rotulo: "VLM — Visão", dica: "chat/completions com imagem" },
    { chave: "embeddings", rotulo: "Embeddings — RAG", dica: "a Together não oferece embeddings serverless" },
    { chave: "transcricao", rotulo: "STT — Transcrição", dica: "ainda não chamado pelo backend" },
    { chave: "voz", rotulo: "TTS — Voz", dica: "ainda não chamado pelo backend" },
]



const OUTRO = "__outro__"


export default function ConexoesIA() {
    const [plataformas, setPlataformas] = useState<Plataforma[] | null>(null)
    const [modelos, setModelos] = useState<ConexaoIA[]>([])
    const [adicionandoPlat, setAdicionandoPlat] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function recarregar() {
        try {
            const [p, m] = await Promise.all([api.plataformas(), api.conexoesIA()])
            setPlataformas(p)
            setModelos(m)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Erro ao carregar")
        }
    }

    useEffect(() => {
        void recarregar()
    }, [])

    if (erro) return <p className="falha">{erro}</p>
    if (!plataformas) return <p className="vazio">Carregando…</p>

    return (
        <div className="conexoes-ia">
            <div className="topo-plat">
                <div>
                    <h2>Plataformas de IA</h2>
                    <p className="dica">
                        Endpoint e chave ficam na plataforma, uma vez só. Os modelos são cadastrados dentro dela e herdam os dois.
                    </p>
                </div>
                {!adicionandoPlat && (
                    <button onClick={() => setAdicionandoPlat(true)}>+ Adicionar plataforma</button>
                )}
            </div>

            {adicionandoPlat && (
                <div className="card-plat nova">
                    <h3>Nova plataforma</h3>
                    <FormPlataforma
                        aoSalvar={async (d) => {
                            await api.criarPlataforma(d)
                            setAdicionandoPlat(false)
                            await recarregar()
                        }}
                        aoCancelar={() => setAdicionandoPlat(false)}
                    />
                </div>
            )}

            {plataformas.length === 0 && !adicionandoPlat && (
                <p className="vazio">Nenhuma plataforma cadastrada. Comece adicionando uma.</p>
            )}

            {plataformas.map((p) => (
                <CardPlataforma
                    key={p.id}
                    plataforma={p}
                    modelos={modelos.filter((m) => m.platform_id === p.id)}
                    recarregar={recarregar}
                />
            ))}
        </div>
    )
}

function CardPlataforma({
    plataforma, modelos, recarregar,
}: {
    plataforma: Plataforma
    modelos: ConexaoIA[]
    recarregar: () => Promise<void>
}) {
    const [aberto, setAberto] = useState(true)
    const [editando, setEditando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    return (
        <div className="card-plat">
            <div className="plat-topo" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <strong className="plat-titulo">{plataforma.titulo}</strong>
                <span className="plat-endpoint">{plataforma.endpoint}</span>
                <span className="chave">{plataforma.chave_mascarada || "sem chave"}</span>
                <span className="tag-fb">{plataforma.qtd_modelos} modelo(s)</span>
            </div>

            {aberto && (
                <div className="plat-corpo">
                    {editando ? (
                        <FormPlataforma
                            inicial={plataforma}
                            aoSalvar={async (d) => {
                                await api.editarPlataforma(plataforma.id, d)
                                setEditando(false)
                                await recarregar()
                            }}
                            aoCancelar={() => setEditando(false)}
                        />
                    ) : (
                        <div className="linha-acoes">
                            <button className="secundario" onClick={() => setEditando(true)}>
                                Editar endpoint / chave
                            </button>
                            <button
                                className="perigo"
                                onClick={async () => {
                                    if (!confirm(`Apagar a plataforma "${plataforma.titulo}"?`)) return
                                    try {
                                        await api.apagarPlataforma(plataforma.id)
                                        await recarregar()
                                    } catch (e) {
                                        setErro(e instanceof Error ? e.message : "Erro ao apagar")
                                    }
                                }}
                            >
                                Apagar plataforma
                            </button>
                            {erro && <span className="falha">{erro}</span>}
                        </div>
                    )}

                    <SincronizarModelos plataforma={plataforma} />

                    <div className="modelos-por-categoria">
                        {CATEGORIAS.map((cat) => (
                            <SecaoCategoria
                                key={cat.chave}
                                categoria={cat}
                                plataforma={plataforma}
                                modelos={modelos.filter((m) => m.categoria === cat.chave)}
                                recarregar={recarregar}
                            />
                        ))}
                    </div>
                </div>
            )}
        </div>
    )
}

function SincronizarModelos({ plataforma }: { plataforma: Plataforma }) {
    const [msg, setMsg] = useState<string | null>(null)
    const [rodando, setRodando] = useState(false)
    async function sincronizar() {
        setRodando(true); setMsg(null)
        try { const r = await api.sincronizarCatalogo(plataforma.id); setMsg(`${r.novos_no_catalogo} novos modelos (de ${r.modelos_no_provedor} no provedor) no catálogo.`) }
        catch (e) { setMsg(e instanceof Error ? e.message : "falha") }
        finally { setRodando(false) }
    }
    return (
        <div className="sinc-modelos">
            <button className="secundario" disabled={rodando} onClick={sincronizar}>{rodando ? "sincronizando…" : "⟳ Sincronizar modelos do provedor"}</button>
            {msg && <span className="dica"> {msg}</span>}
        </div>
    )
}

function SecaoCategoria({
    categoria, plataforma, modelos, recarregar,
}: {
    categoria: { chave: string; rotulo: string; dica: string }
    plataforma: Plataforma
    modelos: ConexaoIA[]
    recarregar: () => Promise<void>
}) {
    const [adicionando, setAdicionando] = useState(false)

    return (
        <section className="sec-cat">
            <header>
                <h4>
                    {categoria.rotulo} <span className="dica">{categoria.dica}</span>
                </h4>
                {!adicionando && (
                    <button className="secundario" onClick={() => setAdicionando(true)}>+ modelo</button>
                )}
            </header>

            {modelos.map((m) => (
                <CardModelo key={m.id} modelo={m} plataforma={plataforma} recarregar={recarregar} />
            ))}

            {adicionando && (
                <div className="card-modelo novo">
                    <FormModelo
                        plataforma={plataforma}
                        categoria={categoria.chave}
                        aoSalvar={async (d) => {
                            await api.criarConexao(d)
                            setAdicionando(false)
                            await recarregar()
                        }}
                        aoCancelar={() => setAdicionando(false)}
                    />
                </div>
            )}

            {modelos.length === 0 && !adicionando && <p className="vazio-cat">nenhum modelo</p>}
        </section>
    )
}

function CardModelo({
    modelo, plataforma, recarregar,
}: {
    modelo: ConexaoIA
    plataforma: Plataforma
    recarregar: () => Promise<void>
}) {
    const [aberto, setAberto] = useState(false)
    const [teste, setTeste] = useState<string | null>(null)

    async function testar() {
        setTeste("testando…")
        try {
            const r = await api.testarConexao(modelo.id)
            setTeste(r.ok === false ? "falhou" : r.ok === null ? (r.resposta ?? "salva") : `ok: ${r.resposta ?? r.dimensao}`)
        } catch (e) {
            setTeste(e instanceof Error ? e.message : "erro")
        }
    }

    return (
        <div className={`card-modelo ${modelo.ativa ? "ativa" : ""}`}>
            <div className="modelo-topo" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <span className="modelo">{modelo.modelo}</span>
                {modelo.ativa ? (
                    <span className="tag-ativa">ativa</span>
                ) : (
                    <span className="tag-fb">{modelo.ordem_fallback ? `fallback ${modelo.ordem_fallback}` : "—"}</span>
                )}
            </div>

            {aberto && (
                <div className="modelo-corpo">
                    <FormModelo
                        plataforma={plataforma}
                        categoria={modelo.categoria}
                        inicial={modelo}
                        aoSalvar={async (d) => {
                            await api.editarConexao(modelo.id, d)
                            await recarregar()
                        }}
                    />
                    <div className="linha-acoes">
                        {!modelo.ativa && (
                            <button onClick={async () => { await api.ativarConexao(modelo.id); await recarregar() }}>
                                Tornar ativa
                            </button>
                        )}
                        {!modelo.ativa && (
                            <label className="fb-input">
                                Fallback nº
                                <input
                                    type="number" min={2} defaultValue={modelo.ordem_fallback ?? ""}
                                    onBlur={async (e) => {
                                        const v = e.target.value ? Number(e.target.value) : null
                                        await api.fallbackConexao(modelo.id, v)
                                        await recarregar()
                                    }}
                                />
                            </label>
                        )}
                        <button className="secundario" onClick={testar}>Testar</button>
                        {teste && <span className="teste-res">{teste}</span>}
                        <button
                            className="perigo"
                            onClick={async () => {
                                if (confirm(`Apagar o modelo "${modelo.modelo}"?`)) {
                                    await api.apagarConexao(modelo.id)
                                    await recarregar()
                                }
                            }}
                        >
                            Apagar
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}

function FormPlataforma({
    inicial, aoSalvar, aoCancelar,
}: {
    inicial?: Plataforma
    aoSalvar: (d: PlataformaInput) => Promise<void>
    aoCancelar?: () => void
}) {
    const [f, setF] = useState<PlataformaInput>({
        titulo: inicial?.titulo ?? "",
        endpoint: inicial?.endpoint ?? "",
        api_key: "",
    })
    const [salvando, setSalvando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [conhecidas, setConhecidas] = useState<{ nome: string; endpoint: string }[]>([])

    useEffect(() => { api.catalogoPlataformas().then(setConhecidas).catch(() => setConhecidas([])) }, [])

    function escolher(nome: string) {
        setF((x) => ({ ...x, titulo: nome }))
        const c = conhecidas.find((p) => p.nome === nome)
        if (c) setF((x) => ({ ...x, titulo: nome, endpoint: c.endpoint }))
    }

    return (
        <div className="form-ia">
            <label>
                Plataforma
                <input
                    value={f.titulo}
                    onChange={(e) => escolher(e.target.value)}
                    placeholder="ex: Together"
                    list="plataformas-conhecidas"
                />
                <datalist id="plataformas-conhecidas">
                    {conhecidas.map((p) => <option key={p.nome} value={p.nome} />)}
                </datalist>
            </label>
            <label>
                Endpoint
                <input
                    value={f.endpoint}
                    onChange={(e) => setF((x) => ({ ...x, endpoint: e.target.value }))}
                    placeholder="https://api.together.xyz/v1"
                />
            </label>
            <label>
                API key {inicial && <span className="mant">(em branco = mantém a atual)</span>}
                <CampoSecreto
                    valor={f.api_key}
                    aoMudar={(v) => setF((x) => ({ ...x, api_key: v }))}
                    placeholder={inicial ? "•••• mantida" : "cole a chave"}
                    aoRevelar={inicial ? async () => (await api.revelarChave(inicial.id)).api_key : undefined}
                />
            </label>
            {erro && <p className="falha">{erro}</p>}
            <div className="linha-acoes">
                <button
                    disabled={salvando}
                    onClick={async () => {
                        setSalvando(true); setErro(null)
                        try {
                            await aoSalvar(f)
                        } catch (e) {
                            setErro(e instanceof Error ? e.message : "Erro ao salvar")
                        } finally {
                            setSalvando(false)
                        }
                    }}
                >
                    {salvando ? "Salvando…" : "Salvar plataforma"}
                </button>
                {aoCancelar && <button className="secundario" onClick={aoCancelar}>Cancelar</button>}
            </div>
        </div>
    )
}

function FormModelo({
    plataforma, categoria, inicial, aoSalvar, aoCancelar,
}: {
    plataforma: Plataforma
    categoria: string
    inicial?: ConexaoIA
    aoSalvar: (d: ConexaoInput) => Promise<void>
    aoCancelar?: () => void
}) {
    const [lista, setLista] = useState<{ id: string; nota?: string }[]>([])
    const [livre, setLivre] = useState(false)
    const [f, setF] = useState<ConexaoInput>({
        platform_id: plataforma.id,
        nome: inicial?.nome ?? `${plataforma.titulo} — ${categoria}`,
        modelo: inicial?.modelo ?? "",
        categoria,
        max_tokens: inicial?.max_tokens ?? 4000,
        temperatura: inicial?.temperatura ?? 0.7,
    })

    // carrega a lista de modelos do CATÁLOGO (banco), por plataforma+categoria
    useEffect(() => {
        api.catalogoModelos(plataforma.titulo, categoria)
            .then((ms) => {
                const l = ms.map((m) => ({ id: m.model_id, nota: m.rotulo || (m.dim ? `dim ${m.dim}` : "") }))
                setLista(l)
                if (!inicial && l[0]) setF((x) => (x.modelo ? x : { ...x, modelo: l[0].id }))
                if (l.length === 0 || (!!inicial?.modelo && !l.some((m) => m.id === inicial.modelo))) setLivre(true)
            })
            .catch(() => { setLista([]); setLivre(true) })
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])
    const [salvando, setSalvando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    function up(campo: keyof ConexaoInput, valor: string | number) {
        setF((x) => ({ ...x, [campo]: valor }))
    }

    return (
        <div className="form-ia">
            <label>
                Modelo
                {livre ? (
                    <>
                        <input
                            value={f.modelo}
                            onChange={(e) => up("modelo", e.target.value)}
                            placeholder={lista[0]?.id ?? "id do modelo"}
                        />
                        {lista.length > 0 && (
                            <button className="link" type="button" onClick={() => { setLivre(false); up("modelo", lista[0].id) }}>
                                ← voltar à lista
                            </button>
                        )}
                    </>
                ) : (
                    <select
                        value={f.modelo}
                        onChange={(e) => {
                            if (e.target.value === OUTRO) { setLivre(true); up("modelo", "") }
                            else up("modelo", e.target.value)
                        }}
                    >
                        {lista.map((m) => (
                            <option key={m.id} value={m.id}>{m.id}{m.nota ? ` — ${m.nota}` : ""}</option>
                        ))}
                        <option value={OUTRO}>outro (digitar)…</option>
                    </select>
                )}
            </label>
            <label>Apelido<input value={f.nome} onChange={(e) => up("nome", e.target.value)} /></label>
            <div className="dupla">
                <label>Max tokens<input type="number" value={f.max_tokens} onChange={(e) => up("max_tokens", Number(e.target.value))} /></label>
                <label>Temperatura<input type="number" step="0.1" value={f.temperatura} onChange={(e) => up("temperatura", Number(e.target.value))} /></label>
            </div>
            {erro && <p className="falha">{erro}</p>}
            <div className="linha-acoes">
                <button
                    disabled={salvando}
                    onClick={async () => {
                        setSalvando(true); setErro(null)
                        try {
                            await aoSalvar(f)
                        } catch (e) {
                            setErro(e instanceof Error ? e.message : "Erro ao salvar")
                        } finally {
                            setSalvando(false)
                        }
                    }}
                >
                    {salvando ? "Salvando…" : "Salvar modelo"}
                </button>
                {aoCancelar && <button className="secundario" onClick={aoCancelar}>Cancelar</button>}
            </div>
        </div>
    )
}
