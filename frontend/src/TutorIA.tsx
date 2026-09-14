import { useEffect, useRef, useState } from "react"
import { api, type ChatMsg, type Conversa, type DocTutor, type MeuRecurso, type ModelosChat } from "./api"
import { Corpo, PopupIA, PopupVoz, checarMicrofone, calcularRms, tipoAudioSuportado, type CampoModelo, type EstadoMic } from "./Chat"
import SeletorLista from "./SeletorLista"

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
    // [123]: seletor de IA por categoria, mesmo mecanismo do Chat de estudo.
    const [modelos, setModelos] = useState<ModelosChat | null>(null)
    const [cfgAberta, setCfgAberta] = useState(false)
    const [linkVideo, setLinkVideo] = useState("")
    const [enviandoVideo, setEnviandoVideo] = useState(false)
    const [gravandoVideo, setGravandoVideo] = useState(false)
    const [segVideo, setSegVideo] = useState(0)
    const [infoVideo, setInfoVideo] = useState<{ titulo: string | null; duracao_s: number | null } | null>(null)
    const [enviandoArquivo, setEnviandoArquivo] = useState(false)
    const [conhecimentoAberto, setConhecimentoAberto] = useState(false)
    const [gravando, setGravando] = useState(false)
    const [gravSeg, setGravSeg] = useState(0)
    const [respondendoVoz, setRespondendoVoz] = useState(false)
    const [mic, setMic] = useState<EstadoMic>(null)
    const [vozAberta, setVozAberta] = useState(false)
    // [120]: "modo carro" — liga uma vez, fica ouvindo, fala, envia e responde
    // sozinho (mesmo mecanismo do Chat de estudo, [096], reusado aqui: nível
    // de som via Web Audio API, não reconhecimento de voz de verdade).
    const [maosLivres, setMaosLivres] = useState(false)
    const [ouvindo, setOuvindo] = useState(false)
    const gravadorRef = useRef<MediaRecorder | null>(null)
    const chunksRef = useRef<Blob[]>([])
    const gravCronRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const gravInicioRef = useRef<number | null>(null)
    const streamMLRef = useRef<MediaStream | null>(null)
    const ctxMLRef = useRef<AudioContext | null>(null)
    const analiserMLRef = useRef<AnalyserNode | null>(null)
    const bufferMLRef = useRef<Float32Array<ArrayBuffer> | null>(null)
    const rafMLRef = useRef<number | null>(null)
    const limiarMLRef = useRef(0.02)
    const inicioFalaRef = useRef<number | null>(null)
    const inicioSilencioRef = useRef<number | null>(null)
    const maosLivresRef = useRef(false)   // o loop de RAF lê isto, não o state (fecharia sobre valor velho)
    const pausarEscutaRef = useRef(false) // true enquanto processa/a resposta falada toca — nunca ouve o próprio áudio da IA
    const ativaRef = useRef(ativa)
    useEffect(() => { ativaRef.current = ativa }, [ativa])
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
        api.chatModelos().then(setModelos).catch(() => setModelos(null))
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

    async function trocarModelo(campo: CampoModelo, valor: number | null) {
        if (ativa == null) return
        await api.chatEditarConversa(ativa, { [campo]: valor })
        await carregarConversas()
    }

    async function alternarConhecimentoAtivo(docId: number) {
        if (ativa == null || !conversa) return
        const atual = new Set(conversa.rag_doc_ids)
        atual.has(docId) ? atual.delete(docId) : atual.add(docId)
        await api.chatEditarConversa(ativa, { rag_doc_ids: [...atual] })
        await carregarConversas()
    }

    /** [123]: com o modo carro ligado, mensagem DIGITADA também fala de volta
     *  — antes só quem falava pelo microfone ouvia a resposta. */
    async function mandar(msg: string) {
        if (ativa == null || !msg.trim() || enviando) return
        setEnviando(true); setErro(null)
        const otimista: ChatMsg = { role: "user", conteudo: msg, question_id: null }
        setMsgs((m) => [...m, otimista])
        setTexto("")
        function devolverEscuta() {
            pausarEscutaRef.current = false
            if (maosLivresRef.current) setOuvindo(true)
        }
        if (maosLivres) pausarEscutaRef.current = true  // não escuta a própria resposta tocando (eco)
        try {
            if (maosLivres) {
                const r = await api.chatEnviarFalado(ativa, msg, null)
                setMsgs((m) => [...m, { role: "assistant", conteudo: r.resposta, question_id: null }])
                aoGastar?.()
                const audioEl = audioRef.current
                if (audioEl) {
                    audioEl.onended = devolverEscuta
                    audioEl.onerror = devolverEscuta
                    audioEl.src = `data:audio/mpeg;base64,${r.audio_b64}`
                    try {
                        await audioEl.play()
                    } catch {
                        setErro("A resposta chegou, mas o navegador bloqueou o áudio automático. Toque em qualquer botão do chat uma vez pra liberar o som.")
                        devolverEscuta()
                    }
                } else devolverEscuta()
            } else {
                const r = await api.chatEnviar(ativa, msg, null)
                setMsgs((m) => [...m, { role: "assistant", conteudo: r.resposta, question_id: null }])
                aoGastar?.()
            }
        } catch (e) {
            setMsgs((m) => m.filter((x) => x !== otimista))
            setTexto(msg)
            setErro(e instanceof Error ? e.message : "Falha ao falar com o tutor.")
            if (maosLivres) devolverEscuta()
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

    async function abrirPopupVoz() {
        setVozAberta((v) => !v)
        if (mic == null) setMic(await checarMicrofone(false))
    }

    /** Envia o áudio gravado (aperta-e-segura OU mãos-livres) — transcreve,
     *  responde, fala de volta. Lê `ativa` pelo REF, não pelo state fechado
     *  em closure — chamada tanto de um clique síncrono quanto de dentro do
     *  loop do mãos-livres, que pode disparar minutos depois de o componente
     *  ter renderizado de novo. Ao terminar, devolve o controle pro
     *  mãos-livres continuar ouvindo, se estiver ligado. */
    async function enviarAudio(blob: Blob) {
        const cid = ativaRef.current
        if (cid == null) return
        setRespondendoVoz(true); setErro(null)

        function devolverEscuta() {
            pausarEscutaRef.current = false
            if (maosLivresRef.current) setOuvindo(true)
        }

        try {
            const r = await api.chatEnviarAudio(cid, blob, null)
            setMsgs((m) => [...m, { role: "user", conteudo: r.transcricao, question_id: null },
                                  { role: "assistant", conteudo: r.resposta, question_id: null }])
            aoGastar?.()
            const audioEl = audioRef.current
            if (audioEl) {
                audioEl.onended = devolverEscuta
                audioEl.onerror = devolverEscuta
                audioEl.src = `data:audio/mpeg;base64,${r.audio_b64}`
                try {
                    await audioEl.play()
                } catch {
                    setErro("A resposta chegou, mas o navegador bloqueou o áudio automático. Toque em qualquer botão do chat uma vez pra liberar o som.")
                    devolverEscuta()
                }
            } else {
                devolverEscuta()
            }
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Falha no chat por voz.")
            devolverEscuta()
        } finally { setRespondendoVoz(false) }
    }

    /** Aperta o 🎤: pede o microfone de verdade (stream novo, fechado ao
     *  soltar) e grava. Desabilitado enquanto o mãos-livres está ligado —
     *  dois `MediaRecorder` no mesmo microfone não faz sentido. */
    async function iniciarGravacao() {
        if (gravando || respondendoVoz || maosLivres || ativa == null) return
        setErro(null)
        let stream: MediaStream
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        } catch (e) {
            const negada = e instanceof DOMException && e.name === "NotAllowedError"
            setErro(negada ? "Permissão de microfone negada — habilite nas configurações do navegador."
                : "Não foi possível acessar o microfone.")
            return
        }
        const tipo = tipoAudioSuportado()
        const rec = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
        chunksRef.current = []
        rec.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
        rec.onstop = () => {
            if (gravCronRef.current) { clearInterval(gravCronRef.current); gravCronRef.current = null }
            stream.getTracks().forEach((t) => t.stop())
            const blob = new Blob(chunksRef.current, { type: tipo || "audio/webm" })
            chunksRef.current = []
            gravadorRef.current = null
            setGravando(false)
            if (blob.size > 500) void enviarAudio(blob)  // ignora clique acidental (áudio quase vazio)
        }
        gravadorRef.current = rec
        rec.start()
        setGravando(true)
        setGravSeg(0)
        gravCronRef.current = setInterval(() => setGravSeg((s) => s + 1), 1000)
    }
    function pararGravacao() {
        if (gravadorRef.current && gravadorRef.current.state !== "inactive") gravadorRef.current.stop()
    }

    /** Liga o "modo carro": pede o microfone UMA vez (stream fica aberto
     *  enquanto ligado), calibra ~700ms de ruído ambiente pro limiar de fala,
     *  e começa o loop de escuta. Funciona em qualquer dispositivo — mobile,
     *  desktop ou tablet — é a mesma API do navegador nos três. */
    async function ativarMaosLivres() {
        if (maosLivres || ativa == null) return
        setErro(null)
        let stream: MediaStream
        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        } catch (e) {
            const negada = e instanceof DOMException && e.name === "NotAllowedError"
            setErro(negada ? "Permissão de microfone negada — habilite nas configurações do navegador."
                : "Não foi possível acessar o microfone.")
            return
        }
        if (typeof AudioContext === "undefined") {
            stream.getTracks().forEach((t) => t.stop())
            setErro("Este navegador não permite detectar fala automaticamente (sem Web Audio API). Use o botão de apertar-e-segurar.")
            return
        }
        const ctx = new AudioContext()
        const fonte = ctx.createMediaStreamSource(stream)
        const analiser = ctx.createAnalyser()
        analiser.fftSize = 1024
        fonte.connect(analiser)
        const buffer = new Float32Array(analiser.fftSize)

        streamMLRef.current = stream
        ctxMLRef.current = ctx
        analiserMLRef.current = analiser
        bufferMLRef.current = buffer
        inicioFalaRef.current = null
        inicioSilencioRef.current = null
        pausarEscutaRef.current = false
        maosLivresRef.current = true
        setMaosLivres(true)
        setVozAberta(false)

        const amostras: number[] = []
        const fimCalibragem = performance.now() + 700
        while (performance.now() < fimCalibragem) {
            amostras.push(calcularRms(analiser, buffer))
            await new Promise((r) => setTimeout(r, 40))
        }
        const media = amostras.reduce((a, b) => a + b, 0) / (amostras.length || 1)
        limiarMLRef.current = Math.max(0.012, media + 0.018)

        setOuvindo(true)
        loopEscutaML()
    }

    function pararTudoML() {
        if (rafMLRef.current != null) { cancelAnimationFrame(rafMLRef.current); rafMLRef.current = null }
        if (gravCronRef.current) { clearInterval(gravCronRef.current); gravCronRef.current = null }
        if (gravadorRef.current && gravadorRef.current.state !== "inactive") {
            gravadorRef.current.onstop = null  // não dispara envio ao desligar no meio de uma gravação
            gravadorRef.current.stop()
        }
        gravadorRef.current = null
        streamMLRef.current?.getTracks().forEach((t) => t.stop())
        streamMLRef.current = null
        void ctxMLRef.current?.close().catch(() => {})
        ctxMLRef.current = null
        analiserMLRef.current = null
        bufferMLRef.current = null
        inicioFalaRef.current = null
        inicioSilencioRef.current = null
        gravInicioRef.current = null
        pausarEscutaRef.current = false
    }

    function desativarMaosLivres() {
        maosLivresRef.current = false
        setMaosLivres(false)
        setOuvindo(false)
        setGravando(false)
        pararTudoML()
    }

    function alternarMaosLivres() {
        if (maosLivres) desativarMaosLivres()
        else void ativarMaosLivres()
    }

    /** Começa a gravar no stream JÁ ABERTO do mãos-livres (sem pedir
     *  permissão de novo) — reaproveita `gravadorRef`/`gravando`/`gravSeg`. */
    function comecarGravarML() {
        const stream = streamMLRef.current
        if (!stream) return
        const tipo = tipoAudioSuportado()
        const gravador = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
        chunksRef.current = []
        gravador.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
        gravador.onstop = () => {
            const blob = new Blob(chunksRef.current, { type: tipo || "audio/webm" })
            chunksRef.current = []
            gravadorRef.current = null
            if (gravCronRef.current) { clearInterval(gravCronRef.current); gravCronRef.current = null }
            gravInicioRef.current = null
            setGravando(false)
            if (blob.size > 500) {
                pausarEscutaRef.current = true  // não escuta a própria resposta tocando (eco)
                void enviarAudio(blob)
            } else if (maosLivresRef.current) {
                setOuvindo(true)  // blip — descarta e volta a ouvir direto
            }
        }
        gravadorRef.current = gravador
        gravInicioRef.current = performance.now()
        gravador.start()
        setGravando(true)
        setGravSeg(0)
        gravCronRef.current = setInterval(() => setGravSeg((s) => s + 1), 1000)
    }

    const MAX_GRAVACAO_ML_MS = 25000
    const MIN_FALA_MS = 220
    const SILENCIO_PARA_ENVIAR_MS = 1100

    /** Loop de detecção de fala (RAF, não setInterval). Roda por minutos:
     *  NUNCA lê state diretamente, só refs, senão fecharia sobre valor velho. */
    function loopEscutaML() {
        rafMLRef.current = requestAnimationFrame(loopEscutaML)
        const analiser = analiserMLRef.current
        const buffer = bufferMLRef.current
        if (!analiser || !buffer || !maosLivresRef.current || pausarEscutaRef.current) return

        const nivel = calcularRms(analiser, buffer)
        const agora = performance.now()

        if (!gravadorRef.current) {
            if (nivel > limiarMLRef.current) {
                if (inicioFalaRef.current == null) inicioFalaRef.current = agora
                if (agora - inicioFalaRef.current >= MIN_FALA_MS) {
                    inicioFalaRef.current = null
                    inicioSilencioRef.current = null
                    setOuvindo(false)
                    comecarGravarML()
                }
            } else {
                inicioFalaRef.current = null
            }
            return
        }

        if (nivel < limiarMLRef.current) {
            if (inicioSilencioRef.current == null) inicioSilencioRef.current = agora
            if (agora - inicioSilencioRef.current >= SILENCIO_PARA_ENVIAR_MS) {
                inicioSilencioRef.current = null
                pararGravacao()
            }
        } else {
            inicioSilencioRef.current = null
        }
        if (gravInicioRef.current != null && agora - gravInicioRef.current >= MAX_GRAVACAO_ML_MS) {
            pararGravacao()
        }
    }

    useEffect(() => () => pararTudoML(), [])

    return (
        <div className="chat">
            <aside className="chat-painel">
                <div className="chat-box" style={{ gridRow: "1 / 3" }}>
                    <div className="chat-box-cab"><h4>Tutor IA</h4></div>
                    <div className="chat-box-corpo">
                        <button className="btn-nova-conversa" onClick={() => setNovaAberta((v) => !v)}>
                            {novaAberta ? <>✕ Cancelar</> : <>✎ Nova conversa</>}
                        </button>
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
                                <SeletorLista
                                    itens={docs.map((d) => ({
                                        id: d.id, label: d.titulo, titulo: d.descricao, desabilitado: !d.indexado,
                                        sublabel: !d.indexado
                                            ? `🕓 em análise (${d.tentativas_indexacao} tentativa${d.tentativas_indexacao === 1 ? "" : "s"})`
                                            : d.enviado_por ? `de ${d.enviado_por}` : undefined,
                                    }))}
                                    selecionados={novaSelecao} aoAlternar={alternarNovaSelecao}
                                    vazio='Nenhum documento classificado pra "Tutor IA" ainda.'
                                />
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
                                <SeletorLista
                                    itens={docs.map((d) => ({
                                        id: d.id, label: d.titulo, titulo: d.descricao, desabilitado: !d.indexado,
                                        sublabel: !d.indexado
                                            ? `🕓 em análise (${d.tentativas_indexacao} tentativa${d.tentativas_indexacao === 1 ? "" : "s"})`
                                            : d.enviado_por ? `de ${d.enviado_por}` : undefined,
                                    }))}
                                    selecionados={new Set(conversa.rag_doc_ids)} aoAlternar={alternarConhecimentoAtivo}
                                    vazio='Nenhum documento classificado pra "Tutor IA" ainda.'
                                />
                            )}
                        </div>

                        <div className="chat-compositor">
                            <div className="chat-caixa">
                                {maosLivres && (
                                    <p className="maos-livres-tarja">
                                        🚗 modo carro ligado — {gravando ? `gravando (${gravSeg}s)…` : respondendoVoz ? "processando e respondendo…" : ouvindo ? "ouvindo, fale quando quiser…" : "ativo"}
                                    </p>
                                )}
                                <div className="chat-botoes">
                                    <label className="link" style={{ margin: 0 }}>
                                        Persona:
                                        <select value={conversa?.persona ?? "professor"} onChange={(e) => trocarPersona(e.target.value as "professor" | "amigo")} style={{ marginLeft: 4 }}>
                                            <option value="professor">professor</option>
                                            <option value="amigo">amigo</option>
                                        </select>
                                    </label>
                                    <span className="chat-espaco" />

                                    {/* [123]: modo carro destacado, ao lado da escolha de IA — antes só
                                        vivia dentro do popup do microfone (⌄), pouco visível. */}
                                    <button className={`pill voz-mode ${maosLivres ? "ativo" : ""}`} onClick={alternarMaosLivres}
                                        title="Modo carro: liga uma vez, fica ouvindo, fala, envia e responde sozinho">
                                        🚗 Voz mode
                                    </button>

                                    {conversa && (
                                        <span className="popup-anchor">
                                            <button className="pill" onClick={() => setCfgAberta((v) => !v)}>
                                                <span className="pill-modelo">
                                                    {conversa.modelo_texto_id
                                                        ? modelos?.texto.find((m) => m.id === conversa.modelo_texto_id)?.nome ?? "IA"
                                                        : "Padrão do sistema"}
                                                </span>
                                                <span className="chevron">⌄</span>
                                            </button>
                                            {cfgAberta && (
                                                <>
                                                    <div className="popup-backdrop" onClick={() => setCfgAberta(false)} />
                                                    <PopupIA conversa={conversa} modelos={modelos} onTrocarModelo={trocarModelo} mostrarModoConversa={false} />
                                                </>
                                            )}
                                        </span>
                                    )}

                                    <span className={`mic-grupo ${maosLivres ? "maos-livres-ativo" : ""}`}>
                                        <button
                                            className={`icone-mic-rec ${gravando ? "gravando" : ""}`}
                                            disabled={respondendoVoz || maosLivres || mic?.count === 0}
                                            title={mic?.count === 0 ? "Nenhum microfone detectado" : maosLivres ? "Desligue o modo carro pra gravar assim" : gravando ? "Solte para enviar" : "Segure para gravar sua pergunta"}
                                            onPointerDown={(e) => { e.preventDefault(); void iniciarGravacao() }}
                                            onPointerUp={pararGravacao}
                                            onPointerLeave={() => { if (gravando) pararGravacao() }}
                                            onPointerCancel={() => { if (gravando) pararGravacao() }}
                                        >
                                            {maosLivres
                                                ? (gravando ? `⏹ ${gravSeg}s` : respondendoVoz ? "🎧…" : ouvindo ? "🎙️ ouvindo" : "🚗")
                                                : (respondendoVoz ? "…" : gravando ? `⏹ ${gravSeg}s` : "🎤")}
                                        </button>
                                        <span className="popup-anchor">
                                            <button className="icone-mic-chevron" onClick={abrirPopupVoz} title="Voz e microfone">
                                                <span className="chevron">⌄</span>
                                            </button>
                                            {vozAberta && (
                                                <>
                                                    <div className="popup-backdrop" onClick={() => setVozAberta(false)} />
                                                    <PopupVoz mic={mic} onVerificar={async () => setMic(await checarMicrofone(true))}
                                                        maosLivres={maosLivres} onAlternarMaosLivres={alternarMaosLivres} />
                                                </>
                                            )}
                                        </span>
                                    </span>
                                </div>
                                <textarea value={texto} onChange={(e) => setTexto(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); mandar(texto) } }}
                                    placeholder="Pergunte ao Tutor IA…" rows={2} />
                                <button disabled={enviando || !texto.trim()} onClick={() => mandar(texto)}>Enviar ▸</button>
                            </div>
                        </div>
                        <audio ref={audioRef} hidden />
                    </>
                )}
            </section>
        </div>
    )
}
