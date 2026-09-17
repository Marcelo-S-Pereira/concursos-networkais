import { useEffect, useRef, useState } from "react"
import { api, type IconeCatalogoLinha } from "./api"
import { BIBLIOTECA_ICONES, NOMES_BIBLIOTECA_ICONES } from "./iconesBiblioteca"
import { useIcones } from "./Icone"

function PreviaIcone({ nome }: { nome: string }) {
    const miolo = BIBLIOTECA_ICONES[nome]
    if (!miolo) return null
    return (
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
            dangerouslySetInnerHTML={{ __html: miolo }} />
    )
}

function LinhaSlot({ linha, aberto, onAbrir, aoMudar }: {
    linha: IconeCatalogoLinha
    aberto: boolean
    onAbrir: () => void
    aoMudar: (novas: IconeCatalogoLinha[]) => void
}) {
    const [busca, setBusca] = useState("")
    const [erro, setErro] = useState<string | null>(null)
    const [enviando, setEnviando] = useState(false)
    const arquivoRef = useRef<HTMLInputElement>(null)

    const filtrados = busca.trim()
        ? NOMES_BIBLIOTECA_ICONES.filter((n) => n.includes(busca.trim().toLowerCase()))
        : NOMES_BIBLIOTECA_ICONES

    async function escolher(nome: string) {
        setErro(null)
        try { aoMudar(await api.iconesEscolherBiblioteca(linha.slot, nome)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao escolher.") }
    }
    async function enviarArquivo(arquivo: File) {
        setErro(null); setEnviando(true)
        try { aoMudar(await api.iconesEnviarUpload(linha.slot, arquivo)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao enviar.") }
        finally { setEnviando(false) }
    }
    async function remover() {
        setErro(null)
        try { aoMudar(await api.iconesRemover(linha.slot)) }
        catch (e) { setErro(e instanceof Error ? e.message : "Falha ao remover.") }
    }

    return (
        <div className={`caderno-linha ${aberto ? "aberto" : ""}`}>
            <div className="caderno-cab" onClick={onAbrir}>
                <span className="seta">{aberto ? "▾" : "▸"}</span>
                <span className="icone-preview">
                    {linha.atual?.tipo === "upload" ? (
                        <img src={`/api/v1/icones/arquivo/${encodeURIComponent(linha.slot)}`} alt="" className="icone-custom" />
                    ) : linha.atual?.tipo === "biblioteca" ? (
                        <PreviaIcone nome={linha.atual.valor} />
                    ) : null}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <strong>{linha.rotulo}</strong>
                    <span className="caderno-meta">
                        {linha.atual ? `ícone ${linha.atual.tipo === "upload" ? "enviado" : linha.atual.valor}` : "sem ícone — mostra o texto"}
                    </span>
                </div>
            </div>
            {aberto && (
                <div className="caderno-corpo-sim">
                    <label>Buscar na biblioteca
                        <input value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex: book, mic, chat…" />
                    </label>
                    <div className="grade-icones">
                        {filtrados.map((nome) => (
                            <button key={nome} className={`icone-opcao ${linha.atual?.valor === nome ? "sel" : ""}`}
                                title={nome} onClick={() => escolher(nome)}>
                                <PreviaIcone nome={nome} />
                            </button>
                        ))}
                        {!filtrados.length && <p className="neutro">Nenhum ícone bate com "{busca}".</p>}
                    </div>
                    <div className="linha-acoes" style={{ marginTop: 10 }}>
                        <input ref={arquivoRef} type="file" accept="image/png,image/svg+xml,image/jpeg,image/webp" hidden
                            onChange={(e) => { const f = e.target.files?.[0]; if (f) void enviarArquivo(f); e.target.value = "" }} />
                        <button className="secundario" disabled={enviando} onClick={() => arquivoRef.current?.click()}>
                            {enviando ? "Enviando…" : "Importar arquivo"}
                        </button>
                        {linha.atual && <button className="perigo" onClick={remover}>Remover ícone</button>}
                    </div>
                    {erro && <p className="falha">{erro}</p>}
                </div>
            )}
        </div>
    )
}

export default function Icones() {
    const [catalogo, setCatalogo] = useState<IconeCatalogoLinha[] | null>(null)
    const [abertoSlot, setAbertoSlot] = useState<string | null>(null)
    const { refrescar } = useIcones()

    useEffect(() => { api.iconesCatalogo().then(setCatalogo).catch(() => setCatalogo([])) }, [])

    function aplicarMudanca(novas: IconeCatalogoLinha[]) {
        setCatalogo(novas)
        refrescar()  // o resto do app (menu, compositor) reflete a escolha na hora
    }

    if (!catalogo) return <p className="neutro">Carregando…</p>

    const grupos = [...new Set(catalogo.map((l) => l.grupo))]
    return (
        <div>
            <p className="explica">
                Escolha o ícone de cada botão — da biblioteca curada ou enviando seu próprio arquivo (PNG/SVG/JPG,
                até 1MB). Sem escolha, o botão mostra o texto normalmente, como hoje. Com escolha, o ícone
                <strong> substitui</strong> o texto (fica só o ícone, com o nome aparecendo ao passar o mouse).
            </p>
            {grupos.map((grupo) => (
                <div key={grupo} style={{ marginTop: 16 }}>
                    <h3 style={{ margin: "0 0 8px", fontSize: ".95rem" }}>{grupo}</h3>
                    {catalogo.filter((l) => l.grupo === grupo).map((linha) => (
                        <LinhaSlot key={linha.slot} linha={linha} aberto={abertoSlot === linha.slot}
                            onAbrir={() => setAbertoSlot((s) => (s === linha.slot ? null : linha.slot))}
                            aoMudar={aplicarMudanca} />
                    ))}
                </div>
            ))}
        </div>
    )
}
