import { useEffect, useState } from "react"
import { api, type ConexaoIA, type ConexaoInput } from "./api"
import CampoSecreto from "./CampoSecreto"

// As 5 categorias que o usuário pediu, separadas: LLM, VLM, STT, TTS + Embeddings (RAG).
const CATEGORIAS: { chave: string; rotulo: string; dica: string }[] = [
    { chave: "texto", rotulo: "LLM — Texto", dica: "chat/completions" },
    { chave: "visao", rotulo: "VLM — Visão", dica: "chat/completions com imagem" },
    { chave: "embeddings", rotulo: "Embeddings — RAG", dica: "embeddings" },
    { chave: "transcricao", rotulo: "STT — Transcrição", dica: "audio/transcriptions" },
    { chave: "voz", rotulo: "TTS — Voz", dica: "audio/speech" },
]

export default function ConexoesIA() {
    const [conexoes, setConexoes] = useState<ConexaoIA[] | null>(null)

    async function recarregar() {
        setConexoes(await api.conexoesIA())
    }
    useEffect(() => {
        recarregar().catch(() => setConexoes([]))
    }, [])

    if (!conexoes) return <p className="neutro">Carregando conexões…</p>

    return (
        <div>
            <p className="explica">
                Cadastre suas IAs. A chave fica <strong>criptografada</strong> no servidor e nunca
                aparece de volta — só os 4 últimos dígitos. A ativa é a 1ª tentada; as demais entram
                pela ordem de fallback numerada.
            </p>
            {CATEGORIAS.map((cat) => (
                <Secao
                    key={cat.chave}
                    categoria={cat}
                    conexoes={conexoes.filter((c) => c.categoria === cat.chave)}
                    aoMudar={setConexoes}
                    recarregar={recarregar}
                />
            ))}
        </div>
    )
}

function Secao({
    categoria, conexoes, aoMudar, recarregar,
}: {
    categoria: { chave: string; rotulo: string; dica: string }
    conexoes: ConexaoIA[]
    aoMudar: (c: ConexaoIA[]) => void
    recarregar: () => Promise<void>
}) {
    const [adicionando, setAdicionando] = useState(false)

    return (
        <section className="secao-ia">
            <div className="secao-cab">
                <h3>{categoria.rotulo} <span className="dica">{categoria.dica}</span></h3>
                <button className="add" onClick={() => setAdicionando((v) => !v)}>
                    {adicionando ? "Cancelar" : "+ Adicionar"}
                </button>
            </div>

            {adicionando && (
                <Formulario
                    categoria={categoria.chave}
                    aoSalvar={async (dados) => {
                        await api.criarConexao(dados)
                        setAdicionando(false)
                        await recarregar()
                    }}
                    aoCancelar={() => setAdicionando(false)}
                />
            )}

            {conexoes.length === 0 && !adicionando && <p className="vazio">Nenhuma conexão nesta categoria.</p>}
            {conexoes.map((c) => (
                <Card key={c.id} conexao={c} aoMudar={aoMudar} recarregar={recarregar} />
            ))}
        </section>
    )
}

function Card({
    conexao, aoMudar, recarregar,
}: {
    conexao: ConexaoIA
    aoMudar: (c: ConexaoIA[]) => void
    recarregar: () => Promise<void>
}) {
    const [aberto, setAberto] = useState(false)
    const [teste, setTeste] = useState<string | null>(null)

    async function testar() {
        setTeste("testando…")
        try {
            const r = await api.testarConexao(conexao.id)
            setTeste(r.ok === false ? "falhou" : r.ok === null ? (r.resposta ?? "salva") : `ok: ${r.resposta ?? r.dimensao}`)
        } catch (e) {
            setTeste(e instanceof Error ? e.message : "erro")
        }
    }

    return (
        <div className={`card-ia ${conexao.ativa ? "ativa" : ""}`}>
            <div className="card-topo" onClick={() => setAberto((v) => !v)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <strong>{conexao.nome}</strong>
                <span className="modelo">{conexao.modelo}</span>
                <span className="chave">{conexao.chave_mascarada || "sem chave"}</span>
                {conexao.ativa ? (
                    <span className="tag-ativa">ativa</span>
                ) : (
                    <span className="tag-fb">{conexao.ordem_fallback ? `fallback ${conexao.ordem_fallback}` : "—"}</span>
                )}
            </div>

            {aberto && (
                <div className="card-corpo">
                    <Formulario
                        categoria={conexao.categoria}
                        inicial={conexao}
                        aoSalvar={async (dados) => {
                            await api.editarConexao(conexao.id, dados)
                            await recarregar()
                        }}
                    />
                    <div className="linha-acoes">
                        {!conexao.ativa && (
                            <button onClick={async () => aoMudar(await api.ativarConexao(conexao.id))}>Tornar ativa</button>
                        )}
                        {!conexao.ativa && (
                            <label className="fb-input">
                                Fallback nº
                                <input
                                    type="number" min={2} defaultValue={conexao.ordem_fallback ?? ""}
                                    onBlur={async (e) => {
                                        const v = e.target.value ? Number(e.target.value) : null
                                        aoMudar(await api.fallbackConexao(conexao.id, v))
                                    }}
                                />
                            </label>
                        )}
                        <button className="secundario" onClick={testar}>Testar</button>
                        {teste && <span className="teste-res">{teste}</span>}
                        <button
                            className="perigo"
                            onClick={async () => {
                                if (confirm(`Apagar "${conexao.nome}"?`)) {
                                    await api.apagarConexao(conexao.id)
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

function Formulario({
    categoria, inicial, aoSalvar, aoCancelar,
}: {
    categoria: string
    inicial?: ConexaoIA
    aoSalvar: (d: ConexaoInput) => Promise<void>
    aoCancelar?: () => void
}) {
    const [f, setF] = useState<ConexaoInput>({
        nome: inicial?.nome ?? "",
        endpoint: inicial?.endpoint ?? "https://api.together.xyz/v1",
        api_key: "",
        modelo: inicial?.modelo ?? (categoria === "texto" ? "meta-llama/Llama-3.3-70B-Instruct-Turbo" : ""),
        categoria,
        max_tokens: inicial?.max_tokens ?? 4000,
        temperatura: inicial?.temperatura ?? 0.7,
    })
    const [salvando, setSalvando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    function up(campo: keyof ConexaoInput, valor: string | number) {
        setF((x) => ({ ...x, [campo]: valor }))
    }

    async function enviar() {
        setSalvando(true)
        setErro(null)
        try {
            await aoSalvar(f)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Erro ao salvar")
        } finally {
            setSalvando(false)
        }
    }

    return (
        <div className="form-ia">
            <label>Nome<input value={f.nome} onChange={(e) => up("nome", e.target.value)} placeholder="ex: Together principal" /></label>
            <label>Endpoint<input value={f.endpoint} onChange={(e) => up("endpoint", e.target.value)} placeholder="https://api.together.xyz/v1" /></label>
            <label>Modelo<input value={f.modelo} onChange={(e) => up("modelo", e.target.value)} placeholder="meta-llama/Llama-3.3-70B-Instruct-Turbo" /></label>
            <label>
                API key {inicial && <span className="mant">(em branco = mantém a atual)</span>}
                <CampoSecreto
                    valor={f.api_key}
                    aoMudar={(v) => up("api_key", v)}
                    placeholder={inicial ? "•••• mantida" : "cole a chave"}
                    aoRevelar={inicial ? async () => (await api.revelarChave(inicial.id)).api_key : undefined}
                />
            </label>
            <div className="dupla">
                <label>Max tokens<input type="number" value={f.max_tokens} onChange={(e) => up("max_tokens", Number(e.target.value))} /></label>
                <label>Temperatura<input type="number" step="0.1" value={f.temperatura} onChange={(e) => up("temperatura", Number(e.target.value))} /></label>
            </div>
            {erro && <p className="falha">{erro}</p>}
            <div className="linha-acoes">
                <button disabled={salvando} onClick={enviar}>{salvando ? "Salvando…" : "Salvar"}</button>
                {aoCancelar && <button className="secundario" onClick={aoCancelar}>Cancelar</button>}
            </div>
        </div>
    )
}
