import { useEffect, useRef, useState } from "react"
import { api, type ChatMsg, type Conversa, type DocTutor, type MeuRecurso, type ModelosChat, type VozKokoro } from "./api"
import { Corpo, Popup, PopupIA, calcularRms, tipoAudioSuportado, desbloquearAudio, tocarAudioResposta, type CampoModelo } from "./Chat"
import SeletorLista from "./SeletorLista"
import Icone from "./Icone"
import Feedback from "./Feedback"
import { VozTempoReal } from "./vozTempoReal"

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
export default function TutorIA({ aoGastar }: { aoGastar?: () => void; modo: "celular" | "computador" }) {
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
    const [vozes, setVozes] = useState<VozKokoro[] | null>(null)
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
    // [157]: seletor de persona virou popup (mais personas no futuro), igual
    // ao seletor de modelo — "cfgAberta" já existia pra esse.
    const [personaAberta, setPersonaAberta] = useState(false)
    // [120]: "modo carro" — liga uma vez, fica ouvindo, fala, envia e responde
    // sozinho (mesmo mecanismo do Chat de estudo, [096], reusado aqui: nível
    // de som via Web Audio API, não reconhecimento de voz de verdade).
    const [maosLivres, setMaosLivres] = useState(false)
    const [ouvindo, setOuvindo] = useState(false)
    const gravadorRef = useRef<MediaRecorder | null>(null)
    const gravCronRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const gravInicioRef = useRef<number | null>(null)
    const streamMLRef = useRef<MediaStream | null>(null)
    const ctxMLRef = useRef<AudioContext | null>(null)
    const analiserMLRef = useRef<AnalyserNode | null>(null)
    const bufferMLRef = useRef<Float32Array<ArrayBuffer> | null>(null)
    const rafMLRef = useRef<number | null>(null)
    const limiarMLRef = useRef(0.02)
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
    const topoRef = useRef<HTMLDivElement>(null)  // [164]: pro botão "ir ao topo" — marcador no início de `.chat-msgs`
    const arquivoRef = useRef<HTMLInputElement>(null)
    // [132]: mesmo mecanismo do Chat de estudo — quando o autoplay falha, guarda
    // a resposta pendente pra um botão de clique real tocar (clique sempre passa
    // pela política de autoplay, independente da causa exata do bloqueio).
    const [audioPendente, setAudioPendente] = useState(false)
    const pendenteDevolverRef = useRef<(() => void) | null>(null)
    // [135]: guarda o último áudio pendente em base64, pra um 2º mecanismo de
    // reprodução (Web Audio API) poder tentar tocar o MESMO áudio se o
    // <audio> nativo falhar — teste isolado (Etapa 18 do roteiro do GPT)
    // pra descobrir se o problema é especificamente o HTMLAudioElement neste
    // ambiente, sem precisar da arquitetura de streaming inteira ainda.
    const ultimoAudioB64Ref = useRef<string | null>(null)
    const webAudioCtxRef = useRef<AudioContext | null>(null)
    const conversa = conversas.find((c) => c.id === ativa) ?? null
    const videoId = extrairIdYoutube(linkVideo)

    /** [135]: decodifica o MESMO base64 que o <audio> tentou tocar, mas via
     *  Web Audio API (AudioContext + AudioBufferSourceNode) — API do
     *  navegador diferente do HTMLAudioElement. Se isso funcionar onde o
     *  <audio> falha, prova que o problema é do elemento, não da política de
     *  autoplay nem da fonte do áudio (base64/URL) — informação real, não
     *  suposição, sem precisar construir streaming de chunks ainda. */
    async function tocarViaWebAudio(base64: string): Promise<void> {
        if (!webAudioCtxRef.current) webAudioCtxRef.current = new AudioContext()
        const ctx = webAudioCtxRef.current
        if (ctx.state === "suspended") await ctx.resume()
        const binario = atob(base64)
        const bytes = new Uint8Array(binario.length)
        for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i)
        const buffer = await ctx.decodeAudioData(bytes.buffer.slice(0))
        const fonte = ctx.createBufferSource()
        fonte.buffer = buffer
        fonte.connect(ctx.destination)
        fonte.start()
        console.log("[WEB AUDIO PLAY OK]", { duracao: buffer.duration, sampleRate: buffer.sampleRate, ctxState: ctx.state })
    }

    // [135]: conversa por voz em TEMPO REAL — STT/LLM/TTS todos em streaming
    // por um WebSocket próprio (ver vozTempoReal.ts), diferente do modo voz
    // "grava→sobe→transcreve→responde→fala" de cima. Só desktop, experimental,
    // módulo isolado — nada aqui toca no que já funciona.
    const [vtrAtivo, setVtrAtivo] = useState(false)
    const [vtrEstado, setVtrEstado] = useState<"conectando" | "ouvindo" | "processando" | "falando" | "encerrado">("encerrado")
    const [vtrTranscricao, setVtrTranscricao] = useState("")
    const [vtrResposta, setVtrResposta] = useState("")
    const [vtrErro, setVtrErro] = useState<string | null>(null)
    // [145]: aviso informativo (ex: STT reconectou sozinho) — separado do
    // erro pra não parecer que a sessão quebrou quando ela só se recuperou.
    const [vtrAviso, setVtrAviso] = useState<string | null>(null)
    const vtrRef = useRef<VozTempoReal | null>(null)

    async function alternarVozTempoReal() {
        if (vtrAtivo) {
            vtrRef.current?.parar()
            vtrRef.current = null
            setVtrAtivo(false)
            return
        }
        if (ativa == null) return
        setVtrErro(null)
        setVtrAviso(null)
        setVtrTranscricao("")
        setVtrResposta("")
        let respostaAcumulada = ""
        // [136]: pedido do usuário — cada palavra falada precisa aparecer na
        // tela (igual assistentes de IA), não só numa tarja de status discreta.
        // O PARCIAL vive só em vtrTranscricao/vtrResposta (bolha "ao vivo",
        // renderizada à parte); ao FINALIZAR, vira mensagem de verdade em
        // `msgs` (persiste na tela, mesmo formato das mensagens digitadas).
        const sessao = new VozTempoReal(ativa, (ev) => {
            if (ev.tipo === "estado") {
                // [151]: log real — pra saber se "ouvindo" chega ANTES do
                // texto/áudio da resposta terminarem (achado relatado: balão
                // some/some aparecer enquanto o Kokoro ainda fala).
                console.log(`[VTR-UI] estado -> ${ev.valor} (respostaAcumulada.length=${respostaAcumulada.length})`)
                setVtrEstado(ev.valor)
                if (ev.valor === "ouvindo") {
                    if (respostaAcumulada.trim()) {
                        setMsgs((m) => [...m, { role: "assistant", conteudo: respostaAcumulada.trim(), question_id: null }])
                    }
                    respostaAcumulada = ""
                    setVtrResposta("")
                }
            } else if (ev.tipo === "transcricao_parcial") {
                setVtrTranscricao(ev.texto)
            } else if (ev.tipo === "transcricao_final") {
                setVtrTranscricao("")
                // [146]: achado real — sem o trim, um commit disparado por
                // ruído/silêncio (sem fala de verdade) faz a Together
                // devolver transcrição vazia/só espaço, e isso virava um
                // balão de usuário vazio, persistido pra sempre na conversa.
                if (ev.texto.trim()) {
                    setMsgs((m) => [...m, { role: "user", conteudo: ev.texto, question_id: null }])
                }
            } else if (ev.tipo === "resposta_parcial") {
                respostaAcumulada += ev.texto
                // [151]: log real — timestamp de cada pedaço de texto que
                // chega, pra saber se o problema é "não chega" ou "chega mas
                // não aparece na tela" (achado relatado: balão não cresce).
                console.log(`[VTR-UI] resposta_parcial t=${performance.now().toFixed(0)}ms len_total=${respostaAcumulada.length}`)
                setVtrResposta(respostaAcumulada)
            } else if (ev.tipo === "erro") {
                setVtrErro(ev.detalhe)
            } else if (ev.tipo === "aviso") {
                setVtrAviso(ev.detalhe)
            }
        })
        vtrRef.current = sessao
        setVtrAtivo(true)
        try {
            await sessao.iniciar()
        } catch (e) {
            setVtrErro(e instanceof Error ? e.message : "Falha ao iniciar a conversa por voz.")
            setVtrAtivo(false)
            vtrRef.current = null
        }
    }

    useEffect(() => () => vtrRef.current?.parar(), [])  // encerra a sessão se o componente desmontar

    /** [144]: celular e desktop tratados IGUAL — pedido do usuário, pra
     *  funcionar por ativação só de voz (útil dirigindo, sem precisar
     *  clicar em nada). O [134] fazia o desktop nunca tentar tocar sozinho
     *  (ia direto pro botão manual) por falhas de autoplay medidas na época;
     *  como `ativarMaosLivres()` já desbloqueia o `<audio>` dentro do
     *  clique real que liga o modo voz (mesmo mecanismo que já faz o
     *  celular tocar sozinho), a tentativa automática merece uma chance
     *  real em vez de ser pulada de propósito. O botão "🔊 Ouvir resposta"
     *  continua existindo como rede de segurança — só aparece se a
     *  tentativa automática realmente falhar, nos dois dispositivos. */
    async function tocarResposta(audioEl: HTMLAudioElement | null, audioB64: string, devolverEscuta: () => void) {
        ultimoAudioB64Ref.current = audioB64
        const src = `data:audio/mpeg;base64,${audioB64}`
        const res = await tocarAudioResposta(audioEl, src, devolverEscuta)
        if (!res.tocou) {
            setErro(`A resposta chegou, mas o áudio não tocou sozinho (${res.erroNome ?? "erro desconhecido"}). Toque em "🔊 Ouvir resposta" abaixo.`)
            pendenteDevolverRef.current = devolverEscuta
            setAudioPendente(true)
        }
    }

    async function carregarConversas() { setConversas(await api.chatConversas("tutor").catch(() => [])) }
    async function carregarDocs() { setDocs(await api.tutorDocumentos().catch(() => [])) }
    useEffect(() => {
        void carregarConversas()
        void carregarDocs()
        api.chatRecursos().then(setRecursos).catch(() => setRecursos({}))
        api.chatModelos().then(setModelos).catch(() => setModelos(null))
        api.chatVozes().then(setVozes).catch(() => setVozes(null))
    }, [])
    // [152]: `vtrResposta`/`vtrTranscricao` mudam a cada pedacinho de texto
    // (várias vezes por segundo durante o "Tempo real", [136]) — antes,
    // CADA mudança disparava um `scrollIntoView({behavior:"smooth"})` novo,
    // cancelando a animação anterior no meio e competindo por tempo de
    // layout/paint bem na hora em que o microfone também está processando
    // áudio continuamente ([096]/[136]). Coalescer num único scroll por
    // frame (a mudança mais recente sempre vence) reduz esse trabalho sem
    // mudar o resultado final (ainda termina rolado até o fim).
    useEffect(() => {
        const id = requestAnimationFrame(() => fimRef.current?.scrollIntoView({ behavior: "smooth" }))
        return () => cancelAnimationFrame(id)
    }, [msgs, vtrTranscricao, vtrResposta])
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

    async function trocarVoz(voz: string | null) {
        if (ativa == null) return
        await api.chatEditarConversa(ativa, voz === null ? { limpar_voz: true } : { voz_escolhida: voz })
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
                    await tocarResposta(audioEl, r.audio_b64, devolverEscuta)
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

    /** [132]: toca a resposta pendente a partir de um CLIQUE real — a
     *  política de autoplay do navegador sempre permite reprodução iniciada
     *  assim, funciona independente da causa exata do bloqueio automático. */
    async function tocarManual() {
        const audioEl = audioRef.current
        try {
            await audioEl?.play()
            console.log("[TTS PLAY MANUAL OK — audio element]")
            setErro(null)
            return
        } catch (err) {
            const e = err as DOMException
            console.error("[TTS PLAY MANUAL FAILED — audio element]", { name: e?.name, message: e?.message })
            // [135]: 2ª tentativa, API diferente do navegador (Web Audio, não
            // HTMLAudioElement) — só roda se a 1ª falhou, mesmo áudio, mesmo
            // clique real (ainda dentro do mesmo gesto síncrono).
            if (ultimoAudioB64Ref.current) {
                try {
                    await tocarViaWebAudio(ultimoAudioB64Ref.current)
                    setErro(null)
                    return
                } catch (err2) {
                    const e2 = err2 as Error
                    console.error("[WEB AUDIO PLAY FAILED]", { name: e2?.name, message: e2?.message })
                    setErro(`Nada tocou por nenhum dos dois mecanismos (elemento: ${e?.name ?? "?"}; Web Audio: ${e2?.name ?? "?"}). Verifique se a aba/site está silenciado (clique com o botão direito na aba) ou a saída de áudio do sistema.`)
                    return
                }
            }
            setErro(`Mesmo com o clique direto, o áudio não tocou (${e?.name ?? "erro desconhecido"}).`)
        } finally {
            setAudioPendente(false)
            pendenteDevolverRef.current?.()
            pendenteDevolverRef.current = null
        }
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
                await tocarResposta(audioEl, r.audio_b64, devolverEscuta)
            } else {
                devolverEscuta()
            }
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Falha no chat por voz.")
            devolverEscuta()
        } finally { setRespondendoVoz(false) }
    }

    // [157]: o botão de apertar-e-segurar (mic-grupo) saiu do compositor — o
    // usuário decidiu que "Modo voz" (mãos-livres) e "Tempo real" já bastam
    // pra falar com o Tutor IA, então `iniciarGravacao` (que abria um stream
    // NOVO a cada toque) ficou sem chamador e foi removida. `pararGravacao`
    // continua — é chamada pelo loop do mãos-livres (`loopEscutaML`) pra
    // parar a gravação JÁ aberta em `gravadorRef` quando detecta silêncio.
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
        // [129]: desbloqueia o áudio AQUI, dentro do clique real que ligou o
        // modo voz — depois disso o navegador deixa tocar sozinho a cada
        // turno, porque nenhum turno seguinte tem um clique próprio.
        await desbloquearAudio(audioRef.current)
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
        inicioSilencioRef.current = null
        pausarEscutaRef.current = false
        maosLivresRef.current = true
        setMaosLivres(true)

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
        // [129]: array LOCAL a esta instância — com blips iniciando a
        // gravação (pra não perder o começo da fala), uma gravação nova pode
        // começar antes do onstop da anterior disparar; um buffer
        // compartilhado misturaria os dois áudios.
        const pedacos: Blob[] = []
        gravador.ondataavailable = (e) => { if (e.data.size > 0) pedacos.push(e.data) }
        gravador.onstop = () => {
            const blob = new Blob(pedacos, { type: tipo || "audio/webm" })
            if (gravCronRef.current) { clearInterval(gravCronRef.current); gravCronRef.current = null }
            gravInicioRef.current = null
            setGravando(false)
            // só limpa a referência se ainda for ESTE gravador — uma gravação
            // mais nova pode já ter assumido `gravadorRef.current` enquanto
            // este `onstop` (assíncrono) esperava pra disparar
            if (gravadorRef.current === gravador) gravadorRef.current = null
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
    const SILENCIO_PARA_ENVIAR_MS = 1100

    /** Loop de detecção de fala (RAF, não setInterval). Roda por minutos:
     *  NUNCA lê state diretamente, só refs, senão fecharia sobre valor velho.
     *
     *  [129]: grava já no 1º sinal de volume — MediaRecorder não tem como
     *  capturar áudio de ANTES de start(), então esperar aqui pra "confirmar
     *  que é fala" cortava o começo da frase. E, uma vez gravando, o único
     *  critério pra PARAR é silêncio sustentado — sem uma janela de
     *  confirmação separada, que cortava fala real com uma pausa natural no
     *  meio. Ruído breve (blip) vira gravação igual, mas termina rápido e
     *  sai pequena — o onstop de `comecarGravarML` já descarta blob minúsculo. */
    function loopEscutaML() {
        rafMLRef.current = requestAnimationFrame(loopEscutaML)
        const analiser = analiserMLRef.current
        const buffer = bufferMLRef.current
        if (!analiser || !buffer || !maosLivresRef.current || pausarEscutaRef.current) return

        const nivel = calcularRms(analiser, buffer)
        const agora = performance.now()

        if (!gravadorRef.current) {
            if (nivel > limiarMLRef.current) {
                setOuvindo(false)
                comecarGravarML()
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
                    <div className="chat-box-cab"><h4>Tutor IA</h4> <Feedback ferramenta="tutor_ia" /></div>
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
                            <div key={c.id}>
                                <div className={`chat-conv ${c.id === ativa ? "ativa" : ""}`} onClick={() => abrirConversa(c.id)}>
                                    <span className="chat-conv-titulo">{c.titulo}</span>
                                    {/* [157]: a escolha de RAG saiu de cima do compositor — agora mora
                                        na edição da própria conversa, aqui na lista, não mais flutuando
                                        acima de onde o aluno digita. */}
                                    {c.id === ativa && (
                                        <button className="link" title="Conhecimento desta conversa (RAG)" onClick={(e) => {
                                            e.stopPropagation(); setConhecimentoAberto((v) => !v)
                                        }}>✏️</button>
                                    )}
                                    <button className="link" title="Apagar conversa" onClick={async (e) => {
                                        e.stopPropagation()
                                        if (confirm("Apagar conversa?")) { await api.chatApagar(c.id); if (ativa === c.id) setAtiva(null); await carregarConversas() }
                                    }}>✕</button>
                                </div>
                                {c.id === ativa && conhecimentoAberto && conversa && (
                                    <div className="chat-nova" style={{ margin: "2px 0 8px" }}>
                                        <p className="dica" style={{ margin: "0 0 4px" }}>
                                            Conhecimento desta conversa (vazio = usa tudo que estiver classificado):
                                        </p>
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
                                    </div>
                                )}
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
                            {/* [164]: marcador do topo — `scrollIntoView` rola SEJA lá qual for
                                o ancestral que de fato tem scroll (no desktop é `.chat-msgs`; no
                                mobile é a PÁGINA INTEIRA, porque em modo celular `.chat-thread`
                                cresce junto com o conteúdo em vez de ficar com altura travada).
                                `msgsRef.scrollTo()` só funcionava no desktop — no mobile
                                `.chat-msgs` nunca tinha scroll próprio pra rolar, então o botão
                                não fazia nada. */}
                            <div ref={topoRef} />
                            {!msgs.length && (
                                <div className="chat-abertura">
                                    <p>Escreva sua dúvida abaixo, ou use "Modo voz"/"Tempo real" pra falar.</p>
                                </div>
                            )}
                            {msgs.map((m, i) => (
                                <div key={i} className={`chat-msg ${m.role}`}>
                                    <div className="chat-bolha"><Corpo texto={m.conteudo} recursoVideos={recursos.youtube_videos} /></div>
                                </div>
                            ))}
                            {enviando && <div className="chat-msg assistant"><div className="chat-bolha pensando">pensando…</div></div>}
                            {/* [136]: palavra por palavra na tela, igual assistentes de IA — bolha
                                "ao vivo" enquanto ainda não finalizou (depois vira mensagem real). */}
                            {/* [146]: `.trim()` no lugar de truthy puro — um delta que chega só
                                com espaço (comum no primeiro token do LLM) fazia essa bolha
                                aparecer visualmente "vazia" (só o formato da bolha, sem texto). */}
                            {vtrAtivo && vtrTranscricao.trim() && (
                                <div className="chat-msg user"><div className="chat-bolha">{vtrTranscricao}</div></div>
                            )}
                            {vtrAtivo && vtrResposta.trim() && (
                                <div className="chat-msg assistant"><div className="chat-bolha">{vtrResposta}</div></div>
                            )}
                            <div ref={fimRef} />
                        </div>
                        {erro && <p className="falha chat-erro">{erro}</p>}
                        {audioPendente && (
                            <button className="btn-ouvir-pendente" onClick={tocarManual}>🔊 Ouvir resposta</button>
                        )}

                        <div className="chat-compositor">
                            {/* [160]: o usuário achou sem sentido flutuar no canto de cima das
                                mensagens — pediu explicitamente acima do Enviar, com folga (não
                                colado). Reaproveita a MESMA técnica do [093] (filho de
                                `.chat-compositor`, que já é `position:relative`, ancorado por
                                `bottom:100%`) — já resolveu sobreposição de botão flutuante antes. */}
                            {/* [163]: par subir/descer — mesmo atalho rápido dos dois lados. */}
                            {msgs.length > 0 && (
                                <>
                                    <button className="btn-topo btn-topo-fim" title="Ir para o final da conversa"
                                        onClick={() => fimRef.current?.scrollIntoView({ behavior: "smooth" })}>
                                        <Icone slot="chat.ir_fim" textoPadrao="🔽" />
                                    </button>
                                    <button className="btn-topo" title="Ir para o topo da conversa"
                                        onClick={() => topoRef.current?.scrollIntoView({ behavior: "smooth" })}>
                                        <Icone slot="chat.ir_topo" textoPadrao="🔼" />
                                    </button>
                                </>
                            )}
                            <div className="chat-caixa">
                                {maosLivres && (
                                    <p className="maos-livres-tarja">
                                        Modo voz ligado — {gravando ? `gravando (${gravSeg}s)…` : respondendoVoz ? "processando e respondendo…" : ouvindo ? "ouvindo, fale quando quiser…" : "ativo"}
                                    </p>
                                )}
                                {vtrAtivo && (
                                    // [146]: só o estado + avisos aqui — a transcrição/resposta ao
                                    // vivo (bolha "Você:"/"IA:") saiu daqui porque ficava colada em
                                    // cima da caixa de digitar, dando a impressão errada de estar
                                    // "escrevendo ali". A única área onde o texto falado aparece
                                    // agora é o histórico de mensagens, acima (mesmo balão de sempre).
                                    <div className="maos-livres-tarja" style={{ display: "flex", flexDirection: "column", gap: 4, alignItems: "flex-start" }}>
                                        <strong>
                                            🎙️ Tempo real — {vtrEstado === "conectando" ? "conectando…" : vtrEstado === "ouvindo" ? "ouvindo, fale quando quiser…" : vtrEstado === "processando" ? "pensando…" : vtrEstado === "falando" ? "respondendo…" : "encerrado"}
                                        </strong>
                                        {vtrAviso && <span className="dica">{vtrAviso}</span>}
                                        {vtrErro && <span className="falha">{vtrErro}</span>}
                                    </div>
                                )}
                                {/* [157]: textarea livre, sem nenhum botão em cima — o usuário pediu
                                    pra "deixar onde eu digito texto livre". Os controles (persona,
                                    modelo, modo voz, tempo real) desceram pra depois do Enviar, em
                                    ícone só (sem mic-grupo — "Modo voz"/"Tempo real" já bastam). */}
                                <textarea value={texto} onChange={(e) => setTexto(e.target.value)}
                                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); mandar(texto) } }}
                                    placeholder="Pergunte ao Tutor IA…" rows={2} />
                                <div className="chat-botoes chat-botoes-baixo">
                                    {conversa && (
                                        <span className="popup-anchor">
                                            <button className="pill icone-so" onClick={() => setCfgAberta((v) => !v)}
                                                title={`IA: ${conversa.modelo_texto_id ? modelos?.texto.find((m) => m.id === conversa.modelo_texto_id)?.nome ?? "IA" : "Padrão do sistema"}`}>
                                                <Icone slot="compositor.modelo" textoPadrao="IA" />
                                            </button>
                                            {cfgAberta && (
                                                <>
                                                    <div className="popup-backdrop" onClick={() => setCfgAberta(false)} />
                                                    <PopupIA conversa={conversa} modelos={modelos} vozes={vozes} onTrocarModelo={trocarModelo} onTrocarVoz={trocarVoz} mostrarModoConversa={false} />
                                                </>
                                            )}
                                        </span>
                                    )}

                                    <span className="popup-anchor">
                                        <button className="pill icone-so" onClick={() => setPersonaAberta((v) => !v)}
                                            title={`Persona: ${conversa?.persona ?? "professor"}`}>
                                            <Icone slot="compositor.persona" textoPadrao="Persona" />
                                        </button>
                                        {personaAberta && (
                                            <>
                                                <div className="popup-backdrop" onClick={() => setPersonaAberta(false)} />
                                                {/* [157]: popup, não mais <select> — o usuário vai adicionar mais
                                                    personas no futuro (modo de edição de prompt/agente), então
                                                    isto precisa escalar como uma lista, igual ao seletor de IA. */}
                                                <Popup align="direita">
                                                    <div className="popup-secao">
                                                        <p className="popup-titulo">Persona</p>
                                                        <button className={`popup-linha ${(conversa?.persona ?? "professor") === "professor" ? "sel" : ""}`}
                                                            onClick={() => { void trocarPersona("professor"); setPersonaAberta(false) }}>
                                                            <span>Professor</span>{(conversa?.persona ?? "professor") === "professor" && <span className="check">✓</span>}
                                                        </button>
                                                        <button className={`popup-linha ${conversa?.persona === "amigo" ? "sel" : ""}`}
                                                            onClick={() => { void trocarPersona("amigo"); setPersonaAberta(false) }}>
                                                            <span>Amigo</span>{conversa?.persona === "amigo" && <span className="check">✓</span>}
                                                        </button>
                                                    </div>
                                                </Popup>
                                            </>
                                        )}
                                    </span>

                                    {/* [123]: destacado — antes só vivia dentro do popup do microfone (⌄),
                                        pouco visível; [157]: ícone só, sem o mic-grupo do lado. */}
                                    <button className={`pill voz-mode icone-so ${maosLivres ? "ativo" : ""}`} onClick={alternarMaosLivres}
                                        title="Modo voz: liga uma vez, fica ouvindo, fala, envia e responde sozinho">
                                        <Icone slot="compositor.modo_voz" textoPadrao="Modo voz" />
                                    </button>

                                    <span className="chat-espaco" />

                                    {/* [159]: à direita, colado no Enviar, e maior que os outros 3 — o
                                        usuário decidiu que "Tempo real" é o mais importante do grupo.
                                        [135]/[142]: conversa por voz em TEMPO REAL — experimental, em
                                        qualquer dispositivo. Módulo isolado (vozTempoReal.ts), não usa
                                        MediaRecorder nem o pipeline de cima ("Modo voz"/aperta-e-
                                        segura/mãos-livres, separado por `modo` em tocarResposta());
                                        STT/LLM/TTS em streaming por um WebSocket próprio. */}
                                    {conversa && (
                                        <button className={`pill voz-mode icone-so icone-destaque ${vtrAtivo ? "ativo" : ""}`} onClick={alternarVozTempoReal}
                                            title="Conversa por voz em tempo real (experimental) — fala e ouve em streaming, sem esperar gravação terminar">
                                            <Icone slot="compositor.tempo_real" textoPadrao="Tempo real" />
                                        </button>
                                    )}
                                    <button className="btn-enviar" disabled={enviando || !texto.trim()} onClick={() => mandar(texto)} title="Enviar">
                                        <Icone slot="compositor.enviar" textoPadrao="Enviar ▸" />
                                    </button>
                                </div>
                            </div>
                        </div>
                        <audio ref={audioRef} hidden />
                    </>
                )}
            </section>
        </div>
    )
}
