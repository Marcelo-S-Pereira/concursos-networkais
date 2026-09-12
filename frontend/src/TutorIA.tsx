import { useEffect, useRef, useState } from "react"
import { api, type ChatMsg, type Conversa, type DocTutor, type MeuRecurso } from "./api"
import { Corpo, checarMicrofone, type EstadoMic } from "./Chat"

/** [111]: extrai o ID de um link do YouTube em qualquer formato comum
 *  (watch?v=, youtu.be/, embed/, shorts/) — null se não reconhecer. */
function extrairIdYoutube(url: string): string | null {
    const m = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/)
    return m ? m[1] : null
}

/** "9min 12s" / "1h 2min" — só pra mostrar a duração estimada do vídeo. */
function fmtDuracao(total: number): string {
    const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60
    if (h > 0) return `${h}h ${m}min`
    if (m > 0) return `${m}min ${s}s`
    return `${s}s`
}

/** Durante a gravação: "Ns / duração total" se soubermos a duração real do
 * vídeo (progresso de verdade); senão só o contador de segundos decorridos. */
function fmtProgresso(decorridoS: number, totalS: number | null): string {
    if (!totalS) return `${decorridoS}s`
    return `${decorridoS}s / ${fmtDuracao(totalS)}`
}

/** Aba Tutor IA ([109]/[110]): especialista geral grounded na biblioteca RAG
 * classificada "Tutor IA" ([106]/[108]) — reaproveita 100% do pipeline de
 * crédito/voz/modelo do Chat de estudos (mesma tabela de conversa, só
 * `modo="tutor"`). Cada conversa escolhe QUAIS documentos usar
 * (`rag_doc_ids`, [110]) — vazio usa todos os classificados. PDF/vídeo aqui
 * enviados entram na Biblioteca do admin, com a autoria do usuário, e já
 * ficam disponíveis pra escolher (e, se enviados dentro de uma conversa
 * ativa, já entram na seleção dela automaticamente). */
export default function TutorIA({ aoGastar }: { aoGastar?: () => void }) {
    const [conversas, setConversas] = useState<Conversa[]>([])
    const [ativa, setAtiva] = useState<number | null>(null)
    const [msgs, setMsgs] = useState<ChatMsg[]>([])
    const [texto, setTexto] = useState("")
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [aviso, setAviso] = useState<string | null>(null)
    const [novaAberta, setNovaAberta] = useState(false)
    const [novoTitulo, setNovoTitulo] = useState("")
    const [novaPersona, setNovaPersona] = useState<"professor" | "amigo">("professor")
    const [novaSelecao, setNovaSelecao] = useState<Set<number>>(new Set())
    const [docs, setDocs] = useState<DocTutor[]>([])
    const [recursos, setRecursos] = useState<Record<string, MeuRecurso>>({})
    const [linkVideo, setLinkVideo] = useState("")
    const [enviandoVideo, setEnviandoVideo] = useState(false)
    const [gravandoVideo, setGravandoVideo] = useState(false)
    const [segVideo, setSegVideo] = useState(0)
    const [infoVideo, setInfoVideo] = useState<{ titulo: string | null; duracao_s: number | null } | null>(null)
    const [enviandoArquivo, setEnviandoArquivo] = useState(false)
    const [conhecimentoAberto, setConhecimentoAberto] = useState(false)
    const [gravando, setGravando] = useState(false)
    const [mic, setMic] = useState<EstadoMic>(null)
    const gravadorRef = useRef<MediaRecorder | null>(null)
    const chunksRef = useRef<Blob[]>([])
    const gravadorVideoRef = useRef<MediaRecorder | null>(null)
    const pedacosVideoRef = useRef<Blob[]>([])
    const cronVideoRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const audioRef = useRef<HTMLAudioElement>(null)
    const fimRef = useRef<HTMLDivElement>(null)
    const arquivoRef = useRef<HTMLInputElement>(null)
    const conversa = conversas.find((c) => c.id === ativa) ?? null
    const videoId = extrairIdYoutube(linkVideo)

    async function carregarConversas() { setConversas(await api.chatConversas("tutor").catch(() => [])) }
    async function carregarDocs() { setDocs(await api.tutorDocumentos().catch(() => [])) }
    useEffect(() => {
        void carregarConversas()
        void carregarDocs()
        api.chatRecursos().then(setRecursos).catch(() => setRecursos({}))
        checarMicrofone(false).then(setMic).catch(() => setMic(null))
    }, [])
    useEffect(() => { fimRef.current?.scrollIntoView({ behavior: "smooth" }) }, [msgs])
    useEffect(() => {
        if (!videoId) { setInfoVideo(null); return }
        let vivo = true
        const t = setTimeout(() => {
            api.tutorVideoInfo(linkVideo).then((r) => { if (vivo) setInfoVideo(r) }).catch(() => { if (vivo) setInfoVideo(null) })
        }, 300)
        return () => { vivo = false; clearTimeout(t) }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [videoId])

    async function abrirConversa(cid: number) {
        setAtiva(cid); setErro(null); setAviso(null); setConhecimentoAberto(false)
        try {
            const c = await api.chatMensagens(cid)
            setMsgs(c.mensagens)
        } catch { setMsgs([]) }
    }

    function alternarNovaSelecao(id: number) {
        setNovaSelecao((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
    }

    async function novaConversa() {
        setErro(null)
        try {
            const c = await api.chatCriarConversa([], novoTitulo.trim() || "Nova conversa",
                { modo: "tutor", persona: novaPersona, rag_doc_ids: [...novaSelecao] })
            setNovaAberta(false); setNovoTitulo(""); setNovaSelecao(new Set())
            await carregarConversas()
            await abrirConversa(c.id)
        } catch (e) { setErro(e instanceof Error ? e.message : "Não foi possível criar a conversa.") }
    }

    async function trocarPersona(persona: "professor" | "amigo") {
        if (ativa == null) return
        await api.chatEditarConversa(ativa, { persona })
        await carregarConversas()
    }

    async function alternarConhecimentoAtivo(docId: number) {
        if (ativa == null || !conversa) return
        const atual = new Set(conversa.rag_doc_ids)
        atual.has(docId) ? atual.delete(docId) : atual.add(docId)
        await api.chatEditarConversa(ativa, { rag_doc_ids: [...atual] })
        await carregarConversas()
    }

    async function mandar(msg: string) {
        if (ativa == null || !msg.trim() || enviando) return
        setEnviando(true); setErro(null)
        const otimista: ChatMsg = { role: "user", conteudo: msg, question_id: null }
        setMsgs((m) => [...m, otimista])
        setTexto("")
        try {
            const r = await api.chatEnviar(ativa, msg, null)
            setMsgs((m) => [...m, { role: "assistant", conteudo: r.resposta, question_id: null }])
            aoGastar?.()
        } catch (e) {
            setMsgs((m) => m.filter((x) => x !== otimista))
            setTexto(msg)
            setErro(e instanceof Error ? e.message : "Falha ao falar com o tutor.")
        } finally { setEnviando(false) }
    }

    async function enviarArquivos(arquivos: FileList) {
        setEnviandoArquivo(true); setErro(null); setAviso(null)
        try {
            const r = await api.tutorEnviarArquivos([...arquivos], ativa)
            setAviso(`Adicionado ao conhecimento do Tutor IA: ${r.map((d) => `"${d.titulo}"`).join(", ")}.`)
            await carregarDocs()
            if (ativa != null) await carregarConversas()
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao enviar o(s) arquivo(s).") }
        finally { setEnviandoArquivo(false) }
    }

    /** [111]: envia o áudio já gravado da aba (não baixa nada do YouTube —
     *  quem reproduziu foi o navegador do próprio usuário). */
    async function enviarAudioVideo(blob: Blob) {
        setEnviandoVideo(true); setErro(null); setAviso(null)
        try {
            const r = await api.tutorEnviarVideoAudio(blob, linkVideo.trim(), ativa)
            setAviso(`Vídeo transcrito e adicionado ao conhecimento do Tutor IA: "${r.titulo}".`)
            setLinkVideo("")
            await carregarDocs()
            if (ativa != null) await carregarConversas()
        } catch (e) { setErro(e instanceof Error ? e.message : "Falha ao transcrever o áudio gravado.") }
        finally { setEnviandoVideo(false) }
    }

    /** Pede pra compartilhar a ABA (com áudio) via `getDisplayMedia` — o
     *  mesmo mecanismo da captura de tela ([082]), só que também pegando o
     *  som. Grava só a faixa de ÁUDIO (descarta vídeo, upload bem menor). */
    function iniciarGravacaoVideo() {
        if (gravandoVideo || !videoId) return
        setErro(null); setAviso(null)
        navigator.mediaDevices.getDisplayMedia({ video: true, audio: true }).then((stream) => {
            const faixasAudio = stream.getAudioTracks()
            if (faixasAudio.length === 0) {
                stream.getTracks().forEach((t) => t.stop())
                setErro('Nenhum áudio foi compartilhado — escolha "Esta guia" e marque "Compartilhar áudio da guia".')
                return
            }
            const streamAudio = new MediaStream(faixasAudio)
            const tipo = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4"
            const gravador = new MediaRecorder(streamAudio, { mimeType: tipo })
            pedacosVideoRef.current = []
            gravador.ondataavailable = (e) => { if (e.data.size > 0) pedacosVideoRef.current.push(e.data) }
            gravador.onstop = () => {
                stream.getTracks().forEach((t) => t.stop())
                const blobPronto = new Blob(pedacosVideoRef.current, { type: tipo })
                pedacosVideoRef.current = []
                gravadorVideoRef.current = null
                if (cronVideoRef.current) { clearInterval(cronVideoRef.current); cronVideoRef.current = null }
                setGravandoVideo(false)
                if (blobPronto.size < 2000) { setErro("Gravação muito curta ou vazia — tente de novo."); return }
                void enviarAudioVideo(blobPronto)
            }
            // se o usuário parar o compartilhamento pelo indicador nativo do navegador
            faixasAudio[0].onended = () => { if (gravador.state !== "inactive") gravador.stop() }
            gravadorVideoRef.current = gravador
            gravador.start()
            setGravandoVideo(true)
            setSegVideo(0)
            cronVideoRef.current = setInterval(() => setSegVideo((s) => s + 1), 1000)
        }).catch((e) => {
            const negado = e instanceof DOMException && e.name === "NotAllowedError"
            setErro(negado ? "Permissão de compartilhamento negada." : "Não foi possível iniciar a captura de áudio.")
        })
    }

    function pararGravacaoVideo() {
        if (gravadorVideoRef.current && gravadorVideoRef.current.state !== "inactive") gravadorVideoRef.current.stop()
    }

    async function iniciarGravacao() {
        if (ativa == null || gravadorRef.current) return
        setErro(null)
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            const tipo = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" : "audio/mp4"
            const rec = new MediaRecorder(stream, { mimeType: tipo })
            chunksRef.current = []
            rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
            rec.onstop = async () => {
                stream.getTracks().forEach((t) => t.stop())
                const blob = new Blob(chunksRef.current, { type: tipo })
                gravadorRef.current = null
                if (ativa == null) return
                setEnviando(true)
                try {
                    const r = await api.chatEnviarAudio(ativa, blob, null)
                    setMsgs((m) => [...m, { role: "user", conteudo: r.transcricao, question_id: null },
                                          { role: "assistant", conteudo: r.resposta, question_id: null }])
                    aoGastar?.()
                    if (audioRef.current) {
                        audioRef.current.src = `data:audio/mpeg;base64,${r.audio_b64}`
                        void audioRef.current.play()
                    }
                } catch (e) { setErro(e instanceof Error ? e.message : "Falha no chat por voz.") }
                finally { setEnviando(false) }
            }
            gravadorRef.current = rec
            rec.start()
            setGravando(true)
        } catch {
            setErro("Não consegui acessar o microfone — verifique a permissão do navegador.")
        }
    }
    function pararGravacao() {
        gravadorRef.current?.stop()
        setGravando(false)
    }

    return (
        <div className="chat">
            <aside className="chat-painel">
                <div className="chat-box" style={{ gridRow: "1 / 3" }}>
                    <div className="chat-box-cab">
                        <h4>Tutor IA</h4>
                        <button className="link" onClick={() => setNovaAberta((v) => !v)}>{novaAberta ? "cancelar" : "+ nova"}</button>
                    </div>
                    <div className="chat-box-corpo">
                        <p className="dica" style={{ margin: "0 0 8px" }}>
                            Especialista geral, baseado nos documentos que você escolher da biblioteca — os que
                            você ou o admin classificaram pra "Tutor IA". Pergunte, peça mini-aulas, vídeos, ou
                            converse por voz.
                        </p>
                        {novaAberta && (
                            <div className="chat-nova">
                                <label>Título<input value={novoTitulo} onChange={(e) => setNovoTitulo(e.target.value)} placeholder="ex: Segurança da informação" /></label>
                                <label>O tutor interage como
                                    <select value={novaPersona} onChange={(e) => setNovaPersona(e.target.value as "professor" | "amigo")}>
                                        <option value="professor">Professor (formal, estruturado)</option>
                                        <option value="amigo">Amigo (leve, direto)</option>
                                    </select>
                                </label>
                                <p className="dica" style={{ margin: "6px 0 2px" }}>
                                    Conhecimento desta conversa (vazio = usa tudo que estiver classificado):
                                </p>
                                <ListaDocs docs={docs} selecionados={novaSelecao} aoAlternar={alternarNovaSelecao} />
                                <button onClick={novaConversa}>Criar conversa</button>
                                {erro && <p className="falha" style={{ margin: "4px 0 0" }}>{erro}</p>}
                            </div>
                        )}
                        {conversas.map((c) => (
                            <div key={c.id} className={`chat-conv ${c.id === ativa ? "ativa" : ""}`} onClick={() => abrirConversa(c.id)}>
                                <span className="chat-conv-titulo">{c.titulo}</span>
                                <button className="link" title="Apagar conversa" onClick={async (e) => {
                                    e.stopPropagation()
                                    if (confirm("Apagar conversa?")) { await api.chatApagar(c.id); if (ativa === c.id) setAtiva(null); await carregarConversas() }
                                }}>✕</button>
                            </div>
                        ))}
                        {!conversas.length && !novaAberta && <p className="chat-vazio">Nenhuma conversa ainda.</p>}

                        <div className="recursos-bloco">
                            <p className="dica" style={{ marginBottom: 6 }}><b>Ensinar o Tutor IA</b> — envie PDF(s)/
                                Markdown, ou o link de um vídeo do YouTube que você escolheu; o conteúdo entra na
                                Biblioteca (com seu nome) e passa a poder ser escolhido em qualquer conversa.</p>
                            <input ref={arquivoRef} type="file" accept=".pdf,.md,.markdown,.txt,application/pdf,text/markdown,text/plain" multiple hidden
                                onChange={(e) => e.target.files?.length && enviarArquivos(e.target.files)} />
                            <button className="secundario" disabled={enviandoArquivo} onClick={() => arquivoRef.current?.click()} style={{ marginBottom: 8, width: "100%" }}>
                                {enviandoArquivo ? "Enviando…" : "📎 Anexar PDF/Markdown (vários)"}
                            </button>
                            <div className="regras-linha">
                                <input value={linkVideo} onChange={(e) => setLinkVideo(e.target.value)}
                                    placeholder="link do YouTube" style={{ flex: 1 }} disabled={gravandoVideo} />
                            </div>
                            {videoId && (
                                <div className="video-captura">
                                    <iframe
                                        src={`https://www.youtube-nocookie.com/embed/${videoId}`}
                                        title="Vídeo do YouTube" allow="autoplay" />
                                    <p className="dica" style={{ margin: "6px 0" }}>
                                        1) Aperte ▶ no vídeo acima. 2) Clique em "gravar áudio da aba" e, na janela
                                        que o navegador abrir, escolha <b>Esta guia</b> (ou aba) e marque
                                        <b> "Compartilhar áudio da guia"</b>. Funciona melhor no Chrome/Edge — alguns
                                        navegadores não suportam compartilhar áudio de aba.
                                    </p>
                                    <p className="dica" style={{ margin: "0 0 6px" }}>
                                        {infoVideo?.duracao_s
                                            ? `Duração do vídeo: ${fmtDuracao(infoVideo.duracao_s)} — a gravação leva
                                               esse tempo, porque captura o áudio conforme o vídeo toca de verdade.`
                                            : "A gravação leva o mesmo tempo da duração do vídeo (o áudio é capturado em tempo real, não é possível acelerar o processamento)."}
                                        {" "}Você pode <b>trocar de aba ou usar outro app</b> enquanto grava — o
                                        vídeo continua tocando e sendo gravado nesta aba em segundo plano, desde que
                                        você não a feche nem pare o compartilhamento. Quando parar, o áudio é
                                        transcrito (segundos, não minutos) e vira conhecimento do Tutor IA
                                        automaticamente.
                                    </p>
                                    {!gravandoVideo ? (
                                        <button className="secundario" disabled={enviandoVideo} onClick={iniciarGravacaoVideo} style={{ width: "100%" }}>
                                            {enviandoVideo ? "Transcrevendo…" : "🎙️ Gravar áudio da aba"}
                                        </button>
                                    ) : (
                                        <button className="gravando-video" onClick={pararGravacaoVideo} style={{ width: "100%" }}>
                                            ⏹ Parar e transcrever ({fmtProgresso(segVideo, infoVideo?.duracao_s ?? null)})
                                        </button>
                                    )}
                                </div>
                            )}
                            {aviso && <p className="dica" style={{ color: "var(--ok)" }}>{aviso}</p>}
                        </div>
                    </div>
                </div>
            </aside>

            <section className="chat-thread">
                {ativa == null ? (
                    <div className="chat-abertura">
                        <h3>Tutor IA</h3>
                        <p>Crie uma conversa pra estudar qualquer assunto que tenha material na Biblioteca —
                            ou converse livremente; o tutor avisa quando não tem material específico sobre algo.</p>
                    </div>
                ) : (
                    <>
                        <div className="chat-msgs">
                            {!msgs.length && (
                                <div className="chat-abertura">
                                    <p>Escreva sua dúvida abaixo, ou aperte e segure o microfone pra falar.</p>
                                </div>
                            )}
                            {msgs.map((m, i) => (
                                <div key={i} className={`chat-msg ${m.role}`}>
                                    <div className="chat-bolha"><Corpo texto={m.conteudo} recursoVideos={recursos.youtube_videos} /></div>
                                </div>
                            ))}
                            {enviando && <div className="chat-msg assistant"><div className="chat-bolha pensando">pensando…</div></div>}
                            <div ref={fimRef} />
                        </div>
                        {erro && <p className="falha chat-erro">{erro}</p>}

                        <div className="chat-nova" style={{ margin: "0 14px" }}>
                            <button className="link" onClick={() => setConhecimentoAberto((v) => !v)}>
                                📚 Conhecimento desta conversa {conversa && conversa.rag_doc_ids.length > 0 ? `(${conversa.rag_doc_ids.length} escolhido(s))` : "(usando tudo classificado)"}
                                {conhecimentoAberto ? " ▾" : " ▸"}
                            </button>
                            {conhecimentoAberto && conversa && (
                                <ListaDocs docs={docs} selecionados={new Set(conversa.rag_doc_ids)} aoAlternar={alternarConhecimentoAtivo} />
                            )}
                        </div>

                        <div className="chat-compositor">
                            <div className="chat-botoes">
                                <label className="link" style={{ margin: 0 }}>
                                    Persona:
                                    <select value={conversa?.persona ?? "professor"} onChange={(e) => trocarPersona(e.target.value as "professor" | "amigo")} style={{ marginLeft: 4 }}>
                                        <option value="professor">professor</option>
                                        <option value="amigo">amigo</option>
                                    </select>
                                </label>
                                <button
                                    className={gravando ? "gravando" : ""}
                                    onPointerDown={iniciarGravacao} onPointerUp={pararGravacao}
                                    onPointerLeave={() => gravando && pararGravacao()}
                                    disabled={enviando || mic?.count === 0}
                                    title={mic?.count === 0 ? "Nenhum microfone detectado" : "Aperte e segure para falar"}
                                >
                                    {gravando ? "🔴 gravando…" : "🎤 falar"}
                                </button>
                            </div>
                            <textarea value={texto} onChange={(e) => setTexto(e.target.value)}
                                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); mandar(texto) } }}
                                placeholder="Pergunte ao Tutor IA…" rows={2} />
                            <button disabled={enviando || !texto.trim()} onClick={() => mandar(texto)}>Enviar ▸</button>
                        </div>
                        <audio ref={audioRef} hidden />
                    </>
                )}
            </section>
        </div>
    )
}

/** Lista de documentos classificados pro Tutor IA, com checkbox — "em
 * análise" (com a contagem de tentativas) quando ainda não indexou, [110]. */
function ListaDocs({ docs, selecionados, aoAlternar }: {
    docs: DocTutor[]; selecionados: Set<number>; aoAlternar: (id: number) => void
}) {
    if (!docs.length) return <p className="dica">Nenhum documento classificado pra "Tutor IA" ainda.</p>
    return (
        <div className="rag-uso" style={{ marginBottom: 8 }}>
            {docs.map((d) => (
                <label key={d.id} title={d.descricao}>
                    <input type="checkbox" disabled={!d.indexado} checked={selecionados.has(d.id)}
                        onChange={() => aoAlternar(d.id)} />
                    {d.titulo}
                    {!d.indexado && <span className="dica"> · 🕓 em análise ({d.tentativas_indexacao} tentativa{d.tentativas_indexacao === 1 ? "" : "s"})</span>}
                    {d.enviado_por && <span className="dica"> · de {d.enviado_por}</span>}
                </label>
            ))}
        </div>
    )
}
