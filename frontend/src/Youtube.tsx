import { useEffect, useState } from "react"
import { api, type YoutubeStatus, type YoutubeUso } from "./api"
import CampoSecreto from "./CampoSecreto"

export default function Youtube() {
    const [st, setSt] = useState<YoutubeStatus | null>(null)
    const [uso, setUso] = useState<YoutubeUso | null>(null)
    const [chave, setChave] = useState("")
    const [teste, setTeste] = useState<string | null>(null)
    const [salvando, setSalvando] = useState(false)

    async function carregar() { setSt(await api.adminYoutube().catch(() => null)) }
    async function carregarUso() { setUso(await api.adminYoutubeUso().catch(() => null)) }
    useEffect(() => { void carregar(); void carregarUso() }, [])

    async function salvar() {
        if (!chave.trim()) return
        setSalvando(true); setTeste(null)
        try { setSt(await api.salvarYoutube(chave)); setChave("") }
        finally { setSalvando(false) }
    }
    async function testar() {
        setTeste("testando…")
        const r = await api.testarYoutube().catch((e) => ({ ok: false, mensagem: e instanceof Error ? e.message : "erro" }))
        setTeste(r.mensagem)
    }
    async function apagar() {
        if (!confirm("Apagar a chave do YouTube?")) return
        await api.apagarYoutube()
        await carregar()
    }

    if (!st) return <p className="neutro">Carregando…</p>

    return (
        <div>
            <p className="explica">
                Cadastre a chave da <strong>YouTube Data API v3</strong> para o tutor trazer <strong>vídeos reais</strong>
                {" "}(título, canal, miniatura) em vez de só um link de busca, quando sugerir material de estudo. Grátis até
                10 mil buscas/dia — bem acima do uso do chat. Não consome crédito nem orçamento de IA. Só você (admin) vê
                esta aba.
            </p>

            {uso && (
                <div className={`cartao ${uso.pct >= 80 ? "orcamento estourado" : ""}`}>
                    <div className="saude-cab">
                        <strong>Uso do pool hoje</strong>
                        <button className="link" onClick={carregarUso} title="Atualizar">↻</button>
                    </div>
                    <div className="uso-grade">
                        <div className="uso-item destaque"><span className="uso-num">{uso.buscas_hoje}</span><span className="uso-rot">buscas hoje</span></div>
                        <div className="uso-item"><span className="uso-num">{uso.unidades_hoje.toLocaleString("pt-BR")}</span><span className="uso-rot">unidades da cota Google</span></div>
                        <div className="uso-item"><span className="uso-num">{uso.pct}%</span><span className="uso-rot">de {uso.cota_diaria_unidades.toLocaleString("pt-BR")}/dia</span></div>
                    </div>
                    <p className="dica">
                        Cada busca custa 100 unidades da cota do Google (fixo, documentado por eles). Inclui o uso de
                        TODOS — inclusive o seu — porque é a cota real sendo gasta, não só a da comunidade.
                    </p>
                </div>
            )}

            <div className="cartao">
                <div className="saude-cab">
                    <strong>🎬 Chave da API</strong>
                    {st.configurada && <span className="saude-badge ok">configurada</span>}
                </div>
                {st.configurada && <p className="dica">Chave atual: <b>{st.chave_mascarada}</b></p>}
                <label>{st.configurada ? "Trocar a chave" : "Chave da API (YouTube Data API v3)"}
                    <CampoSecreto valor={chave} aoMudar={setChave} placeholder="AIza…" />
                </label>
                <div className="linha-acoes">
                    <button disabled={salvando || !chave.trim()} onClick={salvar}>{salvando ? "Salvando…" : "Salvar"}</button>
                    {st.configurada && <button className="secundario" onClick={testar}>Testar</button>}
                    {st.configurada && <button className="perigo" onClick={apagar}>Apagar</button>}
                    {teste && <span className="dica">{teste}</span>}
                </div>
            </div>

            <div className="cartao" style={{ marginTop: 16 }}>
                <h3 style={{ margin: "0 0 6px" }}>Como criar a chave no Google Cloud</h3>
                <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7, fontSize: ".9rem" }}>
                    <li>Entre em <b>console.cloud.google.com</b> com sua conta Google e crie um projeto (ou use um existente).</li>
                    <li>Em <b>APIs e serviços → Biblioteca</b>, procure <b>"YouTube Data API v3"</b> e clique em <b>Ativar</b>.</li>
                    <li>Em <b>APIs e serviços → Credenciais → Criar credenciais → Chave de API</b>, copie a chave gerada.</li>
                    <li>(Recomendado) Restrinja a chave para só a YouTube Data API v3, em "Restrições de API".</li>
                    <li>Cole a chave acima e clique em <b>Salvar</b>, depois em <b>Testar</b> — deve dizer "Conectado — N resultado(s)".</li>
                </ol>
            </div>
        </div>
    )
}
