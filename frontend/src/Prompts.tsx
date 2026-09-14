import { useEffect, useState } from "react"
import { api, type PromptItem } from "./api"

/** [125]: um card por prompt — editar `texto` aqui muda o que o backend
 * manda pra IA na PRÓXIMA chamada, sem deploy. `nome`/`onde_usado`/
 * `como_funciona` vêm do banco também; o front nunca chumba essas
 * descrições. Expansível/recolhível, mesmo padrão do Caderno/Biblioteca. */
function CardPrompt({ p, aoSalvar }: { p: PromptItem; aoSalvar: (chave: string, texto: string) => Promise<void> }) {
    const [aberto, setAberto] = useState(false)
    const [texto, setTexto] = useState(p.texto)
    const [salvando, setSalvando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const mudou = texto !== p.texto

    async function salvar() {
        setErro(null); setSalvando(true)
        try { await aoSalvar(p.chave, texto) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao salvar") }
        finally { setSalvando(false) }
    }

    return (
        <div className={`caderno-linha ${aberto ? "aberto" : ""}`}>
            <div className="caderno-cab" onClick={() => setAberto((a) => !a)}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <strong style={{ display: "block", overflowWrap: "anywhere" }}>{p.nome}</strong>
                    <span className="caderno-meta">{p.onde_usado}</span>
                </div>
            </div>
            {aberto && (
                <div className="caderno-corpo-sim">
                    <p className="dica" style={{ margin: "0 0 10px" }}>{p.como_funciona}</p>
                    <label>Texto do prompt (enviado à IA)
                        <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={14}
                            style={{ fontFamily: "monospace", fontSize: ".85rem" }} />
                    </label>
                    {erro && <p className="falha">{erro}</p>}
                    <div className="linha-acoes" style={{ marginTop: 8 }}>
                        <button disabled={salvando || !mudou || !texto.trim()} onClick={salvar}>
                            {salvando ? "Salvando…" : "Salvar"}
                        </button>
                        {mudou && (
                            <button className="link" onClick={() => setTexto(p.texto)}>descartar edição</button>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

export default function Prompts() {
    const [lista, setLista] = useState<PromptItem[] | null>(null)
    const [erro, setErro] = useState<string | null>(null)

    async function carregar() { setLista(await api.prompts()) }
    useEffect(() => { carregar().catch((e) => setErro(e instanceof Error ? e.message : "Falha ao carregar")) }, [])

    async function salvar(chave: string, texto: string) {
        const atualizado = await api.editarPrompt(chave, texto)
        setLista((ls) => ls?.map((x) => (x.chave === chave ? atualizado : x)) ?? ls)
    }

    if (erro) return <p className="falha">{erro}</p>
    if (!lista) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Todo prompt que o app manda pra IA está aqui — a base de dados é a <strong>única fonte</strong> do
                texto: não existe mais nada fixo no código. Editar o <strong>texto</strong> de um prompt muda o
                comportamento da IA na <strong>próxima chamada</strong>, sem precisar de deploy. Cada card mostra
                onde aquele prompt é usado e como funciona antes de você editar. Só administrador vê esta aba.
            </p>
            {lista.map((p) => <CardPrompt key={p.chave} p={p} aoSalvar={salvar} />)}
        </div>
    )
}
