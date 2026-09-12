import { type ReactNode, useEffect, useRef, useState } from "react"
import { api, type ChatMsg, type Conversa, type DocChat, type Exame, type GemeaT, type LimitesUso, type MeuRecurso, type ModelosChat, type Questao, type VideoResultado } from "./api"

/** [115]: questão anotada com o caderno de origem — necessário quando a
 *  conversa reúne mais de um caderno (o número Q1 de um pode colidir com o
 *  Q1 de outro; `examId` desambigua). */
type QuestaoCad = Questao & { examId: number }

/** Texto puro a partir do HTML do enunciado — só para preview, nunca renderizado como HTML. */
function semHtml(t: string) {
    return t.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim()
}

/** Ações de estudo: cada botão manda um pedido pronto, para o aluno não ter que
 *  saber formular o prompt. É o fluxo "uma questão de cada vez". */
const ACOES = [
    { id: "explicar", rot: "📖 Explicar", curto: "Explicação", prompt: (n: number) => `Explique a questão Q${n}: por que a alternativa correta está certa e por que cada uma das outras está errada.` },
    { id: "aula", rot: "🎓 Mini-aula", curto: "Mini-aula", prompt: (n: number) => `Dê uma mini-aula do conceito que a questão Q${n} cobra. Comece do começo, seja curto e termine com um exemplo.` },
    { id: "macete", rot: "💡 Macete", curto: "Macete", prompt: (n: number) => `Dê um macete para a questão Q${n}: gancho de memória, regra rápida, os passos, quando usar e quando NÃO usar.` },
    {
        id: "videos", rot: "▶ Vídeos", curto: "Vídeos",
        prompt: (n: number) => `Quero vídeos que expliquem A QUESTÃO Q${n} desta prova de concurso, não uma aula genérica ` +
            `do tema. Dê de 3 a 5 termos de busca ESPECÍFICOS para o YouTube: combine a banca do caderno (se você souber ` +
            `pelo contexto), a disciplina/conceito exato da questão, e uma palavra como "questão comentada", "resolução ` +
            `comentada" ou "prova comentada" — nunca só "aula de [tema]" solto. Antes deles, uma frase dizendo o que ` +
            `procurar. Cada termo numa linha própria começando com "BUSCAR: ".`,
    },
]

/** Mesmo padrão que o backend usa em chat.py (_RE_RESPOSTA) — deriva quem já
 *  respondeu qual questão a partir do próprio histórico, sem estado paralelo.
 *  [115]: prefixo "Q{examId}.{numero}" opcional — só usado com mais de 1
 *  caderno selecionado na conversa (senão "Q{numero}" sozinho, como sempre). */
const RE_RESPOSTA = /^Minha resposta da Q(?:(\d+)\.)?(\d+):\s*([A-E])\s*$/i

/** Linha "BUSCAR: termo" da resposta — o modelo não navega, então nunca dá o
 *  link do vídeo; o link de busca simples é sempre a reserva (funciona sem
 *  chave). "ver vídeos reais" busca de verdade na YouTube Data API e mostra
 *  cartão com miniatura/título/canal, quando o admin cadastrou a chave. */
function LinhaVideo({ termo, recurso }: { termo: string; recurso?: MeuRecurso }) {
    const [resultados, setResultados] = useState<VideoResultado[] | null>(null)
    const [carregando, setCarregando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function verVideosReais() {
        setCarregando(true); setErro(null)
        try {
            const r = await api.chatVideos(termo)
            setResultados(r.resultados)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Busca real indisponível.")
        } finally { setCarregando(false) }
    }

    const restam = recurso?.limite_diario != null ? Math.max(0, recurso.limite_diario - recurso.usado_hoje) : null
    const podeVer = !!recurso?.liberado && (restam == null || restam > 0)

    return (
        <div className="busca-video-bloco">
            <div className="busca-video-linha">
                <a className="busca-video" href={`https://www.youtube.com/results?search_query=${encodeURIComponent(termo)}`}
                    target="_blank" rel="noopener noreferrer">▶ buscar “{termo}” no YouTube</a>
                {resultados == null && podeVer && (
                    <button className="link" onClick={verVideosReais} disabled={carregando}>
                        {carregando ? "buscando…" : `🔎 ver vídeos reais${restam != null ? ` (${restam} hoje)` : ""}`}
                    </button>
                )}
            </div>
            {erro && <p className="popup-aviso" style={{ margin: "3px 0" }}>{erro}</p>}
            {resultados && resultados.length > 0 && (
                <div className="video-cards">
                    {resultados.map((v) => (
                        <a key={v.video_id} className="video-card" href={v.url} target="_blank" rel="noopener noreferrer">
                            {v.miniatura && <img src={v.miniatura} alt="" />}
                            <span className="video-card-titulo">{v.titulo}</span>
                            <span className="video-card-canal">{v.canal}</span>
                        </a>
                    ))}
                </div>
            )}
            {resultados && !resultados.length && <p className="popup-vazio">Nenhum resultado encontrado.</p>}
        </div>
    )
}

/** Renderiza a resposta, linha a linha; "BUSCAR: x" vira o bloco de vídeo acima.
 *  Exportado — reaproveitado pela aba Tutor IA ([109]), mesma convenção. */
export function Corpo({ texto, recursoVideos }: { texto: string; recursoVideos?: MeuRecurso }) {
    const linhas = texto.split("\n")
    return (
        <>
            {linhas.map((l, i) => {
                const busca = l.match(/^\s*BUSCAR:\s*(.+?)\s*$/)
                if (busca) return <LinhaVideo key={i} termo={busca[1].replace(/^["']|["']$/g, "")} recurso={recursoVideos} />
                const fig = l.match(/^\s*FIGURA:(\d+)\s*$/)
                if (fig) return <img key={i} className="figura" src={api.figuraUrl(Number(fig[1]))} alt="Figura da questão" />
                return <span key={i} style={{ whiteSpace: "pre-wrap" }}>{l}{i < linhas.length - 1 ? "\n" : ""}</span>
            })}
        </>
    )
}

type CampoModelo = "modelo_texto_id" | "modelo_visao_id" | "modelo_voz_id" | "modelo_transcricao_id"

const CATEGORIAS_IA: { campo: CampoModelo; rot: string; lista: keyof ModelosChat; ligado: boolean }[] = [
    { campo: "modelo_texto_id", rot: "Texto", lista: "texto", ligado: true },
    { campo: "modelo_visao_id", rot: "Imagem", lista: "visao", ligado: true },
    { campo: "modelo_voz_id", rot: "Voz (fala a resposta)", lista: "voz", ligado: true },
    { campo: "modelo_transcricao_id", rot: "Transcrição (ouve você)", lista: "transcricao", ligado: true },
]

/** Popup ancorado no botão que o abriu — abre para cima, fecha ao clicar fora
 *  (via um backdrop invisível, sem listener de documento). Padrão interfaces de chat modernas. */
/** `align="direita"` para popups ancorados perto da borda direita do
 *  compositor (senão vazam da tela abrindo para a direita). */
function Popup({ children, className = "", align = "esquerda" }: { children: ReactNode; className?: string; align?: "esquerda" | "direita" }) {
    return <div className={`popup-menu ${align === "direita" ? "popup-direita" : ""} ${className}`} onClick={(e) => e.stopPropagation()}>{children}</div>
}

function PopupIA({
    conversa, modelos, onTrocarModelo, onTrocarModo,
}: {
    conversa: Conversa
    modelos: ModelosChat | null
    onTrocarModelo: (campo: CampoModelo, valor: number | null) => void
    onTrocarModo: (modoVoz: boolean) => void
}) {
    return (
        <Popup className="popup-ia" align="direita">
            <div className="popup-secao">
                <p className="popup-titulo">Modo de conversa</p>
                <button className={`popup-linha ${!conversa.modo_voz ? "sel" : ""}`} onClick={() => onTrocarModo(false)}>
                    <span>💬 Texto</span>{!conversa.modo_voz && <span className="check">✓</span>}
                </button>
                <button className={`popup-linha ${conversa.modo_voz ? "sel" : ""}`} onClick={() => onTrocarModo(true)}>
                    <span>🎙️ Voz</span>{conversa.modo_voz && <span className="check">✓</span>}
                </button>
            </div>
            {CATEGORIAS_IA.map((cat) => {
                const opcoes = modelos?.[cat.lista] ?? []
                return (
                    <div className="popup-secao" key={cat.campo}>
                        <p className="popup-titulo">{cat.rot}{!cat.ligado && <span className="popup-badge">em breve</span>}</p>
                        {!opcoes.length ? (
                            <p className="popup-vazio">nenhum modelo cadastrado</p>
                        ) : (
                            <>
                                <button className={`popup-linha ${!conversa[cat.campo] ? "sel" : ""}`} onClick={() => onTrocarModelo(cat.campo, null)}>
                                    <span>Padrão do sistema</span>{!conversa[cat.campo] && <span className="check">✓</span>}
                                </button>
                                {opcoes.map((m) => (
                                    <button key={m.id} className={`popup-linha ${conversa[cat.campo] === m.id ? "sel" : ""}`}
                                        onClick={() => onTrocarModelo(cat.campo, m.id)}>
                                        <span className="popup-nome">{m.nome}<span className="popup-sub">{m.modelo}</span></span>
                                        {conversa[cat.campo] === m.id && <span className="check">✓</span>}
                                    </button>
                                ))}
                            </>
                        )}
                    </div>
                )
            })}
        </Popup>
    )
}

function PopupAnexar({ onArquivo, onCaptura }: { onArquivo: () => void; onCaptura: () => void }) {
    return (
        <Popup className="popup-anexar">
            <button className="popup-linha" onClick={onArquivo}><span>📎 Adicionar arquivo ou foto</span></button>
            <button className="popup-linha" onClick={onCaptura}><span>📷 Fazer captura de tela</span></button>
            <p className="popup-vazio">Só imagem — a IA ainda não lê vídeo.</p>
        </Popup>
    )
}

/** Popup único para todos os recursos manuais (Explicar/Mini-aula/Macete/
 *  Gêmeas/Vídeos). Regra de ouro: o gabarito nunca aparece antes de o aluno
 *  responder — então, sem resposta ainda, este popup mostra o seletor A-E em
 *  vez das ações; o backend também recusa revelar o gabarito até ver a
 *  mensagem de resposta (dupla trava, não só de UI). "Modo" é só rótulo por
 *  enquanto — Automático ainda não tem comportamento definido. */
function PopupAcoes({
    emFoco, respondida, pedindo, gemeaAtual, enviando, modoEstudo,
    onPedir, onResponder, onAcao, onGemeas, onResponderGemea, onTrocarModo,
}: {
    emFoco: Questao | null
    respondida: string | undefined
    pedindo: boolean
    gemeaAtual: GemeaT | null
    enviando: boolean
    modoEstudo: "manual" | "automatico"
    onPedir: () => void
    onResponder: (letra: string) => void
    onAcao: (a: (typeof ACOES)[number]) => void
    onGemeas: () => void
    onResponderGemea: (letra: string) => void
    onTrocarModo: (modo: "manual" | "automatico") => void
}) {
    const letras = emFoco?.alternativas?.length ? emFoco.alternativas.map((a) => a.letra) : ["A", "B", "C", "D", "E"]
    const letrasGemea = gemeaAtual ? Object.keys(gemeaAtual.alternativas).sort() : []
    return (
        <Popup className="popup-acoes">
            <div className="popup-secao">
                <p className="popup-titulo">Modo</p>
                <button className={`popup-linha ${modoEstudo === "manual" ? "sel" : ""}`} onClick={() => onTrocarModo("manual")}>
                    <span>✍️ Manual</span>{modoEstudo === "manual" && <span className="check">✓</span>}
                </button>
                <button className={`popup-linha ${modoEstudo === "automatico" ? "sel" : ""}`} onClick={() => onTrocarModo("automatico")}>
                    <span>⚡ Automático</span>{modoEstudo === "automatico" && <span className="check">✓</span>}
                </button>
                {modoEstudo === "automatico" && (
                    <p className="popup-vazio">Depois que você responder, o app PERGUNTA se quer mini-aula, depois macete, depois gêmeas — um de cada vez. Nunca manda nada pra IA sem você confirmar.</p>
                )}
            </div>
            <div className="popup-secao">
                {!emFoco ? (
                    <p className="popup-vazio">Escolha uma questão embaixo do campo de mensagem.</p>
                ) : gemeaAtual ? (
                    <>
                        <p className="popup-titulo">Sua resposta — questão gêmea</p>
                        <div className="resposta-gate">
                            {letrasGemea.map((l) => (
                                <button key={l} className="resposta-letra" disabled={enviando} onClick={() => onResponderGemea(l)}>{l}</button>
                            ))}
                        </div>
                    </>
                ) : respondida ? (
                    <>
                        <p className="popup-titulo">Q{emFoco.numero} · você marcou {respondida}</p>
                        <button className="popup-linha" disabled={enviando} onClick={onGemeas}>
                            <span>👯 Questões gêmeas</span>
                        </button>
                        {ACOES.map((a) => (
                            <button key={a.id} className="popup-linha" disabled={enviando} onClick={() => onAcao(a)}>
                                <span>{a.rot}</span>
                            </button>
                        ))}
                    </>
                ) : pedindo ? (
                    <>
                        <p className="popup-titulo">Sua resposta — Q{emFoco.numero}</p>
                        <div className="resposta-gate">
                            {letras.map((l) => (
                                <button key={l} className="resposta-letra" disabled={enviando} onClick={() => onResponder(l)}>{l}</button>
                            ))}
                        </div>
                        <p className="popup-vazio">Responda primeiro — o gabarito só aparece depois.</p>
                    </>
                ) : (
                    <>
                        <p className="popup-titulo">Q{emFoco.numero}</p>
                        <button className="popup-linha" disabled={enviando} onClick={onPedir}>
                            <span>📖 Ler questão</span>
                        </button>
                        {ACOES.map((a) => (
                            <button key={a.id} className="popup-linha" disabled={enviando} onClick={() => onAcao(a)}>
                                <span>{a.rot}</span>
                            </button>
                        ))}
                    </>
                )}
            </div>
        </Popup>
    )
}

/** Captura REAL de tela via mediaDevices — abre o seletor nativo do navegador
 *  (tela inteira / janela / aba), tira um frame e vira o mesmo anexo de
 *  imagem que o upload de arquivo usa. Cancelar o seletor não é erro. */
async function capturarTela(): Promise<{ b64: string; erro: string | null }> {
    if (!navigator.mediaDevices?.getDisplayMedia) {
        return { b64: "", erro: "Este navegador não permite captura de tela." }
    }
    let stream: MediaStream | null = null
    try {
        stream = await navigator.mediaDevices.getDisplayMedia({ video: true })
        const video = document.createElement("video")
        video.srcObject = stream
        await video.play()
        await new Promise((r) => requestAnimationFrame(r))
        const canvas = document.createElement("canvas")
        canvas.width = video.videoWidth
        canvas.height = video.videoHeight
        canvas.getContext("2d")?.drawImage(video, 0, 0)
        const dataUrl = canvas.toDataURL("image/png")
        return { b64: dataUrl.slice(dataUrl.indexOf(",") + 1), erro: null }
    } catch (e) {
        const cancelou = e instanceof DOMException && e.name === "NotAllowedError"
        return { b64: "", erro: cancelou ? null : "Não foi possível capturar a tela." }
    } finally {
        stream?.getTracks().forEach((t) => t.stop())
    }
}

const TIPOS_AUDIO_PREF = ["audio/webm", "audio/mp4"]
function tipoAudioSuportado(): string {
    for (const t of TIPOS_AUDIO_PREF) if (MediaRecorder.isTypeSupported(t)) return t
    return ""
}

/** Volume (RMS) do frame atual do microfone, 0..~1. É a base da detecção de
 *  fala do mãos-livres — nível de som, não reconhecimento de voz de verdade. */
function calcularRms(analiser: AnalyserNode, buffer: Float32Array<ArrayBuffer>): number {
    analiser.getFloatTimeDomainData(buffer)
    let soma = 0
    for (let i = 0; i < buffer.length; i++) soma += buffer[i] * buffer[i]
    return Math.sqrt(soma / buffer.length)
}

export type EstadoMic = { count: number; erro: string | null } | null

/** Checagem REAL de microfone via mediaDevices — nunca decorativa. Sem pedir
 *  permissão ela só enumera dispositivos (não pede nada ao usuário); com
 *  `pedirPermissao` chama getUserMedia de verdade e reavalia. Exportada —
 *  reaproveitada pela aba Tutor IA ([109]), mesmo padrão de honestidade. */
export async function checarMicrofone(pedirPermissao: boolean): Promise<EstadoMic> {
    if (!navigator.mediaDevices?.enumerateDevices) {
        return { count: 0, erro: "Este navegador não oferece acesso a microfone." }
    }
    try {
        if (pedirPermissao) {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
            stream.getTracks().forEach((t) => t.stop())
        }
        const dispositivos = await navigator.mediaDevices.enumerateDevices()
        const entradas = dispositivos.filter((d) => d.kind === "audioinput")
        return { count: entradas.length, erro: entradas.length ? null : "Nenhum microfone foi detectado neste dispositivo." }
    } catch (e) {
        const negada = e instanceof DOMException && e.name === "NotAllowedError"
        return { count: 0, erro: negada ? "Permissão de microfone negada — habilite nas configurações do navegador." : "Não foi possível acessar o microfone." }
    }
}

function PopupVoz({
    mic, onVerificar, maosLivres, onAlternarMaosLivres,
}: {
    mic: EstadoMic
    onVerificar: () => void
    maosLivres: boolean
    onAlternarMaosLivres: () => void
}) {
    return (
        <Popup className="popup-voz" align="direita">
            <div className="popup-secao">
                <p className="popup-titulo">Mãos livres</p>
                <button className={`popup-linha ${maosLivres ? "sel" : ""}`} onClick={onAlternarMaosLivres}>
                    <span>🚗 {maosLivres ? "Desligar" : "Ligar"} — fica ouvindo, fala, envia e responde sozinho</span>
                    {maosLivres && <span className="check">✓</span>}
                </button>
                <p className="popup-vazio">
                    Como o modo de voz do ChatGPT: liga uma vez e conversa sem tocar na tela — bom pra usar no carro.
                    Detecta pelo NÍVEL DE SOM quando você começa e para de falar (não é reconhecimento de voz de
                    verdade); em lugar muito barulhento pode disparar sozinho ou demorar a perceber o silêncio. Se
                    atrapalhar, desligue e use o botão de apertar-e-segurar abaixo.
                </p>
            </div>
            <div className="popup-secao">
                <p className="popup-titulo">Como gravar (manual)</p>
                <p className="popup-vazio">Toque e segure o 🎤 no compositor para gravar sua pergunta; solte para
                    enviar. O tutor ouve, responde e fala de volta.</p>
            </div>
            <div className="popup-secao">
                <p className="popup-titulo">Microfone</p>
                {mic == null ? (
                    <p className="popup-vazio">verificando…</p>
                ) : mic.erro ? (
                    <>
                        <p className="popup-aviso">⚠ {mic.erro}</p>
                        <button className="popup-linha" onClick={onVerificar}><span>⚙️ Permitir e verificar novamente</span></button>
                    </>
                ) : (
                    <p className="popup-ok">🎙️ {mic.count} microfone{mic.count === 1 ? "" : "s"} detectado{mic.count === 1 ? "" : "s"}</p>
                )}
            </div>
        </Popup>
    )
}

function Ritmo({ l }: { l: LimitesUso }) {
    if (l.isento) return <p className="chat-ritmo livre">Uso livre — administrador, sem limite de ritmo.</p>
    const partes: string[] = []
    if (l.sessao.limite) partes.push(`sessão ${l.janela_sessao_h}h: ${l.sessao.usadas}/${l.sessao.limite}`)
    if (l.semana.limite) partes.push(`${l.janela_semana_d}d: ${l.semana.usadas}/${l.semana.limite}`)
    if (!partes.length) return null
    const apertado = (l.sessao.limite && l.sessao.usadas / l.sessao.limite >= 0.8)
        || (l.semana.limite && l.semana.usadas / l.semana.limite >= 0.8)
    const volta = l.sessao.reinicia_em ? new Date(l.sessao.reinicia_em) : null
    return (
        <p className={`chat-ritmo ${apertado ? "apertado" : ""}`}>
            {partes.join(" · ")}
            {volta && <><br />reinicia {volta.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</>}
        </p>
    )
}

export default function Chat({ aoGastar }: { aoGastar?: () => void }) {
    const [conversas, setConversas] = useState<Conversa[]>([])
    const [cadernos, setCadernos] = useState<Exame[]>([])
    const [docsChat, setDocsChat] = useState<DocChat[]>([])
    const [modelos, setModelos] = useState<ModelosChat | null>(null)
    const [ativa, setAtiva] = useState<number | null>(null)
    const [msgs, setMsgs] = useState<ChatMsg[]>([])
    const [questoes, setQuestoes] = useState<QuestaoCad[]>([])
    const [texto, setTexto] = useState("")
    const [qid, setQid] = useState<number | "">("")
    const [anexo, setAnexo] = useState<{ nome: string; b64: string } | null>(null)
    const [enviando, setEnviando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)
    const [novaAberta, setNovaAberta] = useState(false)
    // [115]: múltiplos cadernos e múltiplas fontes RAG numa conversa só,
    // mais o modo de escolha de questão (normal = aluno escolhe; random = o
    // backend sorteia entre os cadernos escolhidos).
    const [novosCadernos, setNovosCadernos] = useState<Set<number>>(new Set())
    const [novasFontesRag, setNovasFontesRag] = useState<Set<number>>(new Set())
    const [novoModoQuestao, setNovoModoQuestao] = useState<"normal" | "random">("normal")
    const [limites, setLimites] = useState<LimitesUso | null>(null)
    const [cfgAberta, setCfgAberta] = useState(false)
    const [anexarAberta, setAnexarAberta] = useState(false)
    const [vozAberta, setVozAberta] = useState(false)
    const [acoesAberta, setAcoesAberta] = useState(false)
    // Só mostra o seletor A-E depois de pedido explicitamente ("Responder esta
    // questão"/[089]) — nunca sozinho ao escolher a questão. Guardar o id (não
    // um bool solto) faz trocar de questão resetar o pedido de graça, por
    // comparação, sem precisar de efeito.
    const [pedindoQid, setPedindoQid] = useState<number | null>(null)
    // Gêmeas: as 2 geradas para a questão principal atual + qual está em
    // andamento (índice -1 = nenhuma). Sequencial de propósito — uma de cada
    // vez, como no fluxo real (gerar → responder → corrigir → próxima).
    const [gemeas, setGemeas] = useState<GemeaT[]>([])
    const [gemeaIdx, setGemeaIdx] = useState(-1)
    // Manual (padrão) ou Automático — no automático, depois de cada resposta
    // REAL do aluno (nunca simulada), o fluxo caminha sozinho pelas etapas
    // (correção → mini-aula → macete → gêmeas → fechamento), mas SEMPRE
    // PERGUNTA antes de cada uma (nunca dispara IA sem confirmação — bug
    // relatado pelo usuário, corrigido no [097]). É rótulo por conversa, não
    // persiste no banco (escolha de sessão).
    const [modoEstudo, setModoEstudo] = useState<"manual" | "automatico">("manual")
    // Qual oferta está esperando "Sim"/"Pular" agora, no modo automático.
    const [ofertaAutomatica, setOfertaAutomatica] = useState<"aula" | "macete" | "gemeas" | null>(null)
    // Pra montar o Fechamento no fim do ciclo: a letra que o aluno marcou na
    // principal + o resultado de cada gêmea, conforme confirmados pelo servidor.
    const [resultadosSessao, setResultadosSessao] = useState<{ letraPrincipal: string | null; gemeaOks: boolean[] }>({ letraPrincipal: null, gemeaOks: [] })
    // Lado da mão livre no trem/ônibus — conveniência do aparelho, não dado do
    // usuário; fica só no localStorage, nunca no backend.
    const [ladoMao, setLadoMao] = useState<"esquerda" | "direita">(() => {
        try { return localStorage.getItem("concursos_chat_lado") === "esquerda" ? "esquerda" : "direita" }
        catch { return "direita" }
    })
    function trocarLado() {
        setLadoMao((l) => {
            const novo = l === "direita" ? "esquerda" : "direita"
            try { localStorage.setItem("concursos_chat_lado", novo) } catch { /* privado/bloqueado — segue só na sessão */ }
            return novo
        })
    }
    const [mic, setMic] = useState<EstadoMic>(null)
    const [recursos, setRecursos] = useState<Record<string, MeuRecurso>>({})
    // Gravação: aperta e segura o 🎤 (pointer down/up — funciona com mouse e
    // toque no mesmo handler), solta e envia. `gravSeg` só de exibição (não
    // decide nada no servidor — o custo real vem da duração que a Together
    // devolve na transcrição).
    const [gravando, setGravando] = useState(false)
    const [gravSeg, setGravSeg] = useState(0)
    const [respondendoVoz, setRespondendoVoz] = useState(false)
    const gravadorRef = useRef<MediaRecorder | null>(null)
    const pedacosRef = useRef<Blob[]>([])
    const gravCronRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const gravInicioRef = useRef<number | null>(null)
    const fim = useRef<HTMLDivElement>(null)
    const arquivo = useRef<HTMLInputElement>(null)
    const audioRespostaRef = useRef<HTMLAudioElement | null>(null)

    // Mãos livres ("como o modo de voz do ChatGPT"): liga uma vez, fica
    // ouvindo, detecta quando o aluno fala (nível de som — Web Audio API, não
    // reconhecimento de voz de verdade), grava, envia sozinho ao detectar
    // silêncio, e volta a ouvir depois que a resposta falada termina. O botão
    // de apertar-e-segurar continua existindo do lado, intacto.
    const [maosLivres, setMaosLivres] = useState(false)
    const [ouvindo, setOuvindo] = useState(false)
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

    // Espelham o state em refs pro loop de RAF (que roda por minutos) nunca ler
    // um valor velho de qual conversa/questão está ativa.
    const ativaRef = useRef(ativa)
    useEffect(() => { ativaRef.current = ativa }, [ativa])
    const qidRef = useRef(qid)
    useEffect(() => { qidRef.current = qid }, [qid])
    const conversasRef = useRef(conversas)
    useEffect(() => { conversasRef.current = conversas }, [conversas])

    async function carregarConversas() { setConversas(await api.chatConversas().catch(() => [])) }
    useEffect(() => {
        carregarConversas()
        api.exames().then(setCadernos).catch(() => setCadernos([]))
        api.chatDocumentosRag().then(setDocsChat).catch(() => setDocsChat([]))
        api.chatModelos().then(setModelos).catch(() => setModelos(null))
        api.chatLimites().then(setLimites).catch(() => setLimites(null))
        api.chatRecursos().then(setRecursos).catch(() => setRecursos({}))
    }, [])
    useEffect(() => {
        if (ativa == null) { setMsgs([]); setQuestoes([]); setQid(""); return }
        api.chatMensagens(ativa).then((d) => {
            setMsgs(d.mensagens)
            const ids = d.exam_ids?.length ? d.exam_ids : (d.exam_id ? [d.exam_id] : [])
            if (ids.length) {
                Promise.all(ids.map((eid) =>
                    api.questoes(eid).then((qs) => qs.filter((q) => !q.descartada).map((q) => ({ ...q, examId: eid })))
                )).then((listas) => setQuestoes(listas.flat())).catch(() => setQuestoes([]))
            } else setQuestoes([])
        }).catch(() => {})
    }, [ativa])
    useEffect(() => { fim.current?.scrollIntoView({ behavior: "smooth" }) }, [msgs])
    // Trocar de questão no seletor encerra qualquer sequência de gêmeas em
    // andamento — elas pertencem à questão anterior, não fazem sentido soltas.
    useEffect(() => { setGemeas([]); setGemeaIdx(-1); setResultadosSessao({ letraPrincipal: null, gemeaOks: [] }); setOfertaAutomatica(null) }, [qid])

    const conversa = conversas.find((c) => c.id === ativa) ?? null
    const emFoco = questoes.find((q) => q.id === qid) ?? null
    const examIdsConversa = conversa?.exam_ids ?? []
    // Deriva do próprio histórico — mesma fonte de verdade que o backend usa em
    // chat.py (_respondidas). Nenhum estado paralelo pra desincronizar.
    // [115]: chave (examId.numero) — com 1 caderno só, "Qn" sem prefixo resolve
    // pro único exam_id; com mais de 1, mensagem sem prefixo é ambígua e é
    // ignorada (nunca revela gabarito por engano, mesma regra do backend).
    const respondidas = new Map<string, string>()
    for (const m of msgs) {
        if (m.role !== "user") continue
        const r = RE_RESPOSTA.exec(m.conteudo)
        if (!r) continue
        const eid = r[1] ? Number(r[1]) : (examIdsConversa.length === 1 ? examIdsConversa[0] : null)
        if (eid != null) respondidas.set(`${eid}.${r[2]}`, r[3].toUpperCase())
    }
    const respostaFoco = emFoco ? respondidas.get(`${emFoco.examId}.${emFoco.numero}`) : undefined
    const pedindoResposta = emFoco != null && pedindoQid === emFoco.id
    const mostrandoGemeaFlutuante = gemeaIdx >= 0 && !!gemeas[gemeaIdx]
    const mostrandoPrincipalFlutuante = !!emFoco && !respostaFoco && pedindoResposta && gemeaIdx < 0
    const mostrandoFlutuante = mostrandoGemeaFlutuante || mostrandoPrincipalFlutuante
    const cadernosDaConversa = cadernos.filter((c) => examIdsConversa.includes(c.id))
    const modeloTextoLabel = conversa?.modelo_texto_id
        ? modelos?.texto.find((m) => m.id === conversa.modelo_texto_id)?.nome ?? "IA"
        : "Padrão do sistema"

    function alternarNovoCaderno(id: number) {
        setNovosCadernos((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
    }
    function alternarNovaFonteRag(id: number) {
        setNovasFontesRag((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
    }

    async function novaConversa() {
        setErro(null)
        try {
            const c = await api.chatCriarConversa([...novosCadernos], "Nova conversa", {
                modo_questao: novoModoQuestao, rag_doc_ids: [...novasFontesRag],
            })
            setNovaAberta(false); setNovosCadernos(new Set()); setNovasFontesRag(new Set()); setNovoModoQuestao("normal")
            await carregarConversas(); setAtiva(c.id)
        } catch (e: unknown) {
            setErro(e instanceof Error ? e.message : "Não foi possível criar a conversa.")
        }
    }

    async function trocarModelo(campo: "modelo_texto_id" | "modelo_visao_id" | "modelo_voz_id" | "modelo_transcricao_id", valor: number | null) {
        if (ativa == null) return
        await api.chatEditarConversa(ativa, { [campo]: valor })
        await carregarConversas()
    }

    async function trocarModo(modoVoz: boolean) {
        if (ativa == null) return
        await api.chatEditarConversa(ativa, { modo_voz: modoVoz })
        await carregarConversas()
    }

    function escolherArquivo(f: File | null) {
        if (!f) return
        const leitor = new FileReader()
        leitor.onload = () => {
            const s = String(leitor.result || "")
            setAnexo({ nome: f.name, b64: s.includes(",") ? s.slice(s.indexOf(",") + 1) : s })
        }
        leitor.readAsDataURL(f)
    }

    async function acionarCaptura() {
        setAnexarAberta(false)
        const r = await capturarTela()
        if (r.erro) setErro(r.erro)
        else if (r.b64) setAnexo({ nome: "captura-de-tela.png", b64: r.b64 })
    }

    async function abrirPopupVoz() {
        setVozAberta((v) => !v)
        if (mic == null) setMic(await checarMicrofone(false))
    }

    /** Aperta o 🎤: pede o microfone de verdade (um stream NOVO, fechado ao
     *  soltar) e começa a gravar. Erro real (sem microfone/permissão negada)
     *  aparece na faixa de erro do chat, não fica escondido. */
    async function iniciarGravacao() {
        if (gravando || enviando || respondendoVoz || maosLivres || ativa == null) return
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
        const gravador = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
        pedacosRef.current = []
        gravador.ondataavailable = (e) => { if (e.data.size > 0) pedacosRef.current.push(e.data) }
        gravador.onstop = () => {
            stream.getTracks().forEach((t) => t.stop())
            const blob = new Blob(pedacosRef.current, { type: tipo || "audio/webm" })
            pedacosRef.current = []
            if (blob.size > 500) void enviarAudio(blob)  // ignora clique acidental (áudio quase vazio)
        }
        gravadorRef.current = gravador
        gravador.start()
        setGravando(true)
        setGravSeg(0)
        gravCronRef.current = setInterval(() => setGravSeg((s) => s + 1), 1000)
    }

    function pararGravacao() {
        if (gravCronRef.current) { clearInterval(gravCronRef.current); gravCronRef.current = null }
        if (gravadorRef.current && gravadorRef.current.state !== "inactive") gravadorRef.current.stop()
        gravadorRef.current = null
        setGravando(false)
    }

    /** Envia o áudio gravado: transcreve, responde, fala de volta — e toca a
     *  resposta sozinha. Mesma lógica de erro/limites/saldo de `mandar()`, mas
     *  sem devolver texto ao campo em erro (não havia texto, era fala). Lê
     *  `ativa`/`qid`/`conversas` pelos REFS — chamada tanto pelo aperta-e-
     *  segura (síncrono) quanto pelo mãos-livres (pode disparar minutos depois
     *  de o componente ter renderizado de novo). Ao terminar — sucesso, erro
     *  ou fim da fala tocada — devolve o controle pro mãos-livres continuar
     *  ouvindo, se estiver ligado. */
    async function enviarAudio(blob: Blob) {
        const cid = ativaRef.current
        if (cid == null) return
        const eraNova = conversasRef.current.find((c) => c.id === cid)?.titulo === "Nova conversa"
        const qidAtual = qidRef.current
        setRespondendoVoz(true); setErro(null)

        function devolverEscuta() {
            pausarEscutaRef.current = false
            if (maosLivresRef.current) setOuvindo(true)
        }

        try {
            const r = await api.chatEnviarAudio(cid, blob, qidAtual === "" ? null : Number(qidAtual))
            setMsgs((m) => [
                ...m,
                { role: "user", conteudo: r.transcricao, question_id: qidAtual === "" ? null : Number(qidAtual) },
                { role: "assistant", conteudo: r.resposta, question_id: null },
            ])
            setLimites(r.limites)
            if (eraNova) await api.chatEditarConversa(cid, { titulo: r.transcricao.slice(0, 60) }).catch(() => {})
            await carregarConversas(); aoGastar?.()
            const audioEl = audioRespostaRef.current
            if (audioEl) {
                audioEl.onended = devolverEscuta
                audioEl.onerror = devolverEscuta
                audioEl.src = `data:audio/mp3;base64,${r.audio_b64}`
                await audioEl.play().catch(devolverEscuta)
            } else {
                devolverEscuta()
            }
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Falha no chat por voz.")
            devolverEscuta()
        } finally { setRespondendoVoz(false) }
    }

    /** Liga o mãos-livres: pede o microfone UMA vez (stream fica aberto
     *  enquanto ligado, diferente do aperta-e-segura), calibra ~700ms de
     *  ruído ambiente pro limiar de fala, e começa o loop de escuta. */
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

        // calibra o ruído ambiente por ~700ms antes de começar a decidir nada
        const amostras: number[] = []
        const fim2 = performance.now() + 700
        while (performance.now() < fim2) {
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
     *  permissão de novo) — reaproveita `gravadorRef`/`gravando`/`gravSeg`, a
     *  mesma UI do aperta-e-segura já reage sozinha. */
    function comecarGravarML() {
        const stream = streamMLRef.current
        if (!stream) return
        const tipo = tipoAudioSuportado()
        const gravador = tipo ? new MediaRecorder(stream, { mimeType: tipo }) : new MediaRecorder(stream)
        pedacosRef.current = []
        gravador.ondataavailable = (e) => { if (e.data.size > 0) pedacosRef.current.push(e.data) }
        gravador.onstop = () => {
            const blob = new Blob(pedacosRef.current, { type: tipo || "audio/webm" })
            pedacosRef.current = []
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

    /** Loop de detecção de fala (RAF, não setInterval — mais barato e some
     *  sozinho se a aba perder foco). Roda por minutos: NUNCA lê state
     *  diretamente, só refs, senão fecharia sobre valores velhos. */
    function loopEscutaML() {
        rafMLRef.current = requestAnimationFrame(loopEscutaML)
        const analiser = analiserMLRef.current
        const buffer = bufferMLRef.current
        if (!analiser || !buffer || !maosLivresRef.current || pausarEscutaRef.current) return

        const nivel = calcularRms(analiser, buffer)
        const agora = performance.now()

        if (!gravadorRef.current) {
            // ouvindo: esperando o volume passar do limiar por tempo suficiente pra ser fala, não um blip
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

        // gravando: esperando silêncio sustentado pra considerar que a fala terminou
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
            pararGravacao()  // teto de segurança — ruído contínuo não trava gravando pra sempre
        }
    }

    // Desliga tudo se o componente desmontar com o mãos-livres ligado (trocar
    // de aba, sair do chat) — nunca deixa o microfone aberto sozinho.
    useEffect(() => () => pararTudoML(), [])

    async function mandar(conteudo: string, comAnexo = true, titulo?: string) {
        if (!conteudo.trim() || ativa == null || enviando) return
        const cid = ativa
        const eraNova = conversa?.titulo === "Nova conversa"
        setEnviando(true); setErro(null)
        const b64 = comAnexo ? anexo?.b64 ?? null : null
        const meu: ChatMsg = { role: "user", conteudo: conteudo.trim(), question_id: qid === "" ? null : Number(qid) }
        setMsgs((m) => [...m, meu]); setTexto(""); if (comAnexo) setAnexo(null)
        try {
            const r = await api.chatEnviar(cid, meu.conteudo, meu.question_id, b64)
            setMsgs((m) => [...m, { role: "assistant", conteudo: r.resposta, question_id: null }])
            setLimites(r.limites)
            // título curto quando veio de um botão de ação (senão fica o prompt inteiro)
            if (eraNova && titulo) await api.chatEditarConversa(cid, { titulo }).catch(() => {})
            await carregarConversas(); aoGastar?.()
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Falha ao falar com a IA.")
            setMsgs((m) => m.slice(0, -1))
            setTexto(meu.conteudo)  // devolve o que ele escreveu, em vez de perder
            api.chatLimites().then(setLimites).catch(() => {})
        } finally { setEnviando(false) }
    }

    /** "Ler questão" — imprime o cartão real (texto ou imagem + alternativas),
     *  sem IA nenhuma, e só então libera o A-E. */
    async function lerQuestao(q: Questao) {
        if (ativa == null || enviando) return
        setAcoesAberta(false)
        setEnviando(true); setErro(null)
        try {
            const r = await api.chatLerQuestao(ativa, q.id)
            setMsgs((m) => [...m, { role: "assistant", conteudo: r.conteudo, question_id: q.id }])
            setPedindoQid(q.id)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível abrir a questão.")
        } finally { setEnviando(false) }
    }

    /** Responde a principal e, no modo AUTOMÁTICO, PERGUNTA se quer a
     *  mini-aula — nunca dispara IA sem confirmação. O aluno respondeu de
     *  verdade; a automação só caminha pelas etapas em ordem, sempre com
     *  "Sim"/"Pular" antes de cada uma (bug relatado: antes disparava tudo
     *  de uma vez, sem perguntar — corrigido). */
    async function responderPrincipal(q: QuestaoCad, letra: string) {
        setResultadosSessao((s) => ({ ...s, letraPrincipal: letra }))
        // [115]: prefixo só quando a conversa tem mais de 1 caderno — com 1 só,
        // formato idêntico a sempre foi ("Minha resposta da Q{n}: {letra}").
        const rotulo = examIdsConversa.length > 1 ? `${q.examId}.${q.numero}` : String(q.numero)
        await mandar(`Minha resposta da Q${rotulo}: ${letra}`, false, `Q${q.numero} · resposta`)
        if (modoEstudo === "automatico") setOfertaAutomatica("aula")
    }

    /** [115]: modo "random" — pede ao backend pra sortear uma questão entre
     *  os cadernos da conversa e imprime como o "Ler questão" de sempre. */
    async function questaoAleatoria() {
        if (ativa == null || enviando) return
        setEnviando(true); setErro(null)
        try {
            const r = await api.chatQuestaoAleatoria(ativa)
            setMsgs((m) => [...m, { role: "assistant", conteudo: r.conteudo, question_id: r.question_id }])
            setQid(r.question_id)
            setPedindoQid(r.question_id)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível sortear uma questão.")
        } finally { setEnviando(false) }
    }

    const OFERTAS_AUTO: Record<"aula" | "macete" | "gemeas", { pergunta: string; sim: string }> = {
        aula: { pergunta: "Quer uma mini-aula deste conteúdo?", sim: "🎓 Sim, quero" },
        macete: { pergunta: "Quer o macete desta questão?", sim: "💡 Sim, quero" },
        gemeas: { pergunta: "Quer praticar com 2 questões gêmeas?", sim: "👯 Sim, quero" },
    }

    /** Aceita a oferta atual (manda a IA de verdade) e avança pra próxima
     *  oferta — sempre uma pergunta por vez, nunca em lote. */
    async function aceitarOferta(q: Questao) {
        const oferta = ofertaAutomatica
        setOfertaAutomatica(null)
        if (oferta === "aula") {
            const aula = ACOES.find((a) => a.id === "aula")
            if (aula) await mandar(aula.prompt(q.numero), false, `Q${q.numero} · ${aula.curto}`)
            setOfertaAutomatica("macete")
        } else if (oferta === "macete") {
            const macete = ACOES.find((a) => a.id === "macete")
            if (macete) await mandar(macete.prompt(q.numero), false, `Q${q.numero} · ${macete.curto}`)
            setOfertaAutomatica("gemeas")
        } else if (oferta === "gemeas") {
            await iniciarGemeasPara(q)  // o fechamento dispara sozinho ao fim das 2 gêmeas (já era assim)
        }
    }

    /** Pula a oferta atual sem mandar nada pra IA, e oferece a próxima. */
    function pularOferta() {
        setOfertaAutomatica((atual) => atual === "aula" ? "macete" : atual === "macete" ? "gemeas" : null)
    }

    async function fecharCiclo(q: Questao, letraPrincipal: string, gemeaOks: boolean[]) {
        if (ativa == null) return
        try {
            const r = await api.chatFechamento(ativa, q.id, letraPrincipal, gemeaOks[0] ?? false, gemeaOks[1] ?? false)
            setMsgs((m) => [...m, { role: "assistant", conteudo: r.conteudo, question_id: q.id }])
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível montar o fechamento.")
        }
    }

    async function mostrarGemea(g: GemeaT, idx: number) {
        if (ativa == null) return
        const r = await api.chatLerGemea(ativa, g.id, idx === 0 ? "A" : "B")
        setMsgs((m) => [...m, { role: "assistant", conteudo: r.conteudo, question_id: null }])
        setGemeaIdx(idx)
    }

    /** Gera as 2 gêmeas (mecanismo real do [046]) e mostra a primeira. */
    async function iniciarGemeasPara(q: Questao) {
        if (ativa == null || enviando) return
        setAcoesAberta(false)
        setEnviando(true); setErro(null)
        try {
            const pares = await api.gerarGemeas(q.id)
            setGemeas(pares)
            if (pares[0]) await mostrarGemea(pares[0], 0)
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Não foi possível gerar as gêmeas.")
        } finally { setEnviando(false) }
    }

    /** Corrige a gêmea atual (gabarito recalculado no servidor) e avança pra
     *  próxima — uma de cada vez, como no fluxo real. */
    async function responderGemeaAtual(letra: string) {
        if (ativa == null || gemeaIdx < 0 || !gemeas[gemeaIdx] || enviando) return
        const g = gemeas[gemeaIdx]
        setAcoesAberta(false)
        setEnviando(true); setErro(null)
        try {
            const r = await api.chatResponderGemea(ativa, g.id, letra)
            setMsgs((m) => [
                ...m,
                { role: "user", conteudo: `Minha resposta da gêmea: ${letra}`, question_id: null },
                { role: "assistant", conteudo: r.conteudo, question_id: null },
            ])
            const oksAtualizados = [...resultadosSessao.gemeaOks, r.acertou]
            setResultadosSessao((s) => ({ ...s, gemeaOks: oksAtualizados }))
            const proximo = gemeaIdx + 1
            if (proximo < gemeas.length) {
                await mostrarGemea(gemeas[proximo], proximo)
            } else {
                setGemeaIdx(-1); setGemeas([])
                if (modoEstudo === "automatico" && emFoco && resultadosSessao.letraPrincipal) {
                    await fecharCiclo(emFoco, resultadosSessao.letraPrincipal, oksAtualizados)
                }
            }
        } catch (e) {
            setErro(e instanceof Error ? e.message : "Falha ao corrigir a gêmea.")
        } finally { setEnviando(false) }
    }

    return (
        <div className="chat">
            <aside className="chat-painel">
                {/* metade de cima: tudo que é configurável / exploração */}
                <div className="chat-box">
                    <div className="chat-box-cab"><h4>Configurações e recursos</h4></div>
                    <div className="chat-box-corpo">
                        {ativa == null ? (
                            <p className="chat-vazio">Abra uma conversa para configurar.</p>
                        ) : (
                            <>
                                <p className="chat-caderno">
                                    📗 {cadernosDaConversa.length
                                        ? cadernosDaConversa.map((c) => `${c.orgao} · ${c.cargo}`).join(" + ")
                                        : "Sem caderno — conversa livre"}
                                    {conversa?.modo_questao === "random" && " · 🎲 modo aleatório"}
                                </p>
                                <p className="popup-vazio">A questão em estudo agora se escolhe embaixo do campo de
                                    mensagem, do lado da conversa.</p>

                                {limites && <Ritmo l={limites} />}
                            </>
                        )}
                    </div>
                </div>

                {/* metade de baixo: as conversas */}
                <div className="chat-box">
                    <div className="chat-box-cab">
                        <h4>Conversas</h4>
                        <button className="link" onClick={() => setNovaAberta((v) => !v)}>{novaAberta ? "cancelar" : "+ nova"}</button>
                    </div>
                    <div className="chat-box-corpo">
                        {novaAberta && (
                            <div className="chat-nova">
                                <p className="dica" style={{ margin: "0 0 4px" }}>Cadernos (nenhum = conversa livre, sem caderno):</p>
                                <div className="rag-uso" style={{ marginBottom: 8 }}>
                                    {cadernos.map((c) => (
                                        <label key={c.id}>
                                            <input type="checkbox" checked={novosCadernos.has(c.id)} onChange={() => alternarNovoCaderno(c.id)} />
                                            {c.orgao} · {c.cargo}
                                        </label>
                                    ))}
                                    {!cadernos.length && <p className="dica">Nenhum caderno cadastrado ainda.</p>}
                                </div>
                                {docsChat.length > 0 && (
                                    <>
                                        <p className="dica" style={{ margin: "0 0 4px" }}>Fontes da biblioteca (opcional, vazio = usa todas classificadas "Chat de estudos"):</p>
                                        <div className="rag-uso" style={{ marginBottom: 8 }}>
                                            {docsChat.map((d) => (
                                                <label key={d.id} title={d.descricao}>
                                                    <input type="checkbox" disabled={!d.indexado} checked={novasFontesRag.has(d.id)} onChange={() => alternarNovaFonteRag(d.id)} />
                                                    {d.titulo}
                                                    {!d.indexado && <span className="dica"> · 🕓 em análise</span>}
                                                </label>
                                            ))}
                                        </div>
                                    </>
                                )}
                                <label>Escolha da questão
                                    <select value={novoModoQuestao} onChange={(e) => setNovoModoQuestao(e.target.value as "normal" | "random")}>
                                        <option value="normal">🎯 Normal — eu escolho a questão</option>
                                        <option value="random">🎲 Aleatório — o sistema sorteia do(s) caderno(s)</option>
                                    </select>
                                </label>
                                {novoModoQuestao === "random" && !novosCadernos.size && (
                                    <p className="falha" style={{ margin: "4px 0 0" }}>Escolha pelo menos um caderno para o modo aleatório.</p>
                                )}
                                <button disabled={novoModoQuestao === "random" && !novosCadernos.size} onClick={novaConversa}>Criar conversa</button>
                                {erro && <p className="falha" style={{ margin: "4px 0 0" }}>{erro}</p>}
                            </div>
                        )}
                        {conversas.map((c) => (
                            <div key={c.id} className={`chat-conv ${c.id === ativa ? "ativa" : ""}`} onClick={() => setAtiva(c.id)}>
                                <span className="chat-conv-titulo">{c.titulo}</span>
                                <button className="link" title="Apagar conversa" onClick={async (e) => { e.stopPropagation(); if (confirm("Apagar conversa?")) { await api.chatApagar(c.id); if (ativa === c.id) setAtiva(null); await carregarConversas() } }}>✕</button>
                            </div>
                        ))}
                        {!conversas.length && !novaAberta && <p className="chat-vazio">Nenhuma conversa ainda.</p>}
                    </div>
                </div>
            </aside>

            <section className="chat-thread">
                {ativa == null ? (
                    <div className="chat-abertura">
                        <h3>Tutor de estudo</h3>
                        <p>Crie uma conversa e escolha o caderno. O tutor ensina com base nas questões daquele caderno — texto e imagens — uma questão de cada vez.</p>
                    </div>
                ) : (
                    <>
                        <div className={`chat-msgs${mostrandoFlutuante ? ` reserva-lado lado-${ladoMao}` : ""}`}>
                            {!msgs.length && (
                                <div className="chat-abertura">
                                    <p>Escreva sua dúvida abaixo — ou escolha uma questão logo abaixo do campo de mensagem e use os botões de estudo.</p>
                                </div>
                            )}
                            {msgs.map((m, i) => (
                                <div key={i} className={`chat-msg ${m.role}`}>
                                    <div className="chat-bolha"><Corpo texto={m.conteudo} recursoVideos={recursos.youtube_videos} /></div>
                                </div>
                            ))}
                            {enviando && <div className="chat-msg assistant"><div className="chat-bolha pensando">pensando…</div></div>}
                            {respondendoVoz && <div className="chat-msg assistant"><div className="chat-bolha pensando">ouvindo e respondendo…</div></div>}
                            <div ref={fim} />
                        </div>

                        {erro && <p className="falha chat-erro">{erro}</p>}

                        {ofertaAutomatica && emFoco && (
                            <div className="oferta-auto">
                                <span>{OFERTAS_AUTO[ofertaAutomatica].pergunta}</span>
                                <button onClick={() => aceitarOferta(emFoco)}>{OFERTAS_AUTO[ofertaAutomatica].sim}</button>
                                <button className="secundario" onClick={pularOferta}>Pular</button>
                            </div>
                        )}

                        <div className="chat-compositor">
                            {/* Toca sozinho a resposta falada quando o chat responde por voz. */}
                            <audio ref={audioRespostaRef} hidden />
                            {/* Uma mão só, segurando a barra do trem — o polegar livre troca de
                                lado. Ancorado no PRÓPRIO compositor (bottom:100% dele, não um
                                número de px chutado) — se adapta sozinho à altura real dele,
                                nunca sobrepõe. */}
                            {ativa != null && (
                                <button className={`lado-toggle lado-${ladoMao}`} onClick={trocarLado}
                                    title={`Respostas do lado ${ladoMao === "direita" ? "direito" : "esquerdo"} — toque para trocar`}>
                                    {ladoMao === "direita" ? "👉" : "👈"}
                                </button>
                            )}
                            {mostrandoGemeaFlutuante && (
                                <div className={`resposta-flutuante lado-${ladoMao}`}>
                                    {Object.keys(gemeas[gemeaIdx].alternativas).sort().map((l) => (
                                        <button key={l} className="resposta-letra flutuante" disabled={enviando}
                                            onClick={() => responderGemeaAtual(l)}>{l}</button>
                                    ))}
                                </div>
                            )}
                            {mostrandoPrincipalFlutuante && emFoco && (
                                <div className={`resposta-flutuante lado-${ladoMao}`}>
                                    {(emFoco.alternativas?.length ? emFoco.alternativas.map((a) => a.letra) : ["A", "B", "C", "D", "E"]).map((l) => (
                                        <button key={l} className="resposta-letra flutuante" disabled={enviando}
                                            onClick={() => responderPrincipal(emFoco, l)}>{l}</button>
                                    ))}
                                </div>
                            )}
                            <div className="chat-caixa">
                                {maosLivres && (
                                    <p className="maos-livres-tarja">
                                        🚗 mãos livres ligado — {gravando ? `gravando (${gravSeg}s)…` : respondendoVoz ? "processando e respondendo…" : ouvindo ? "ouvindo, fale quando quiser…" : "ativo"}
                                    </p>
                                )}
                                {conversa?.modo_voz && !maosLivres && (
                                    <button
                                        className={`voz-grande ${gravando ? "gravando" : ""}`}
                                        disabled={respondendoVoz}
                                        onPointerDown={(e) => { e.preventDefault(); void iniciarGravacao() }}
                                        onPointerUp={pararGravacao}
                                        onPointerLeave={() => { if (gravando) pararGravacao() }}
                                        onPointerCancel={() => { if (gravando) pararGravacao() }}
                                    >
                                        {respondendoVoz ? "🎧 respondendo…" : gravando ? `⏹ solte para enviar (${gravSeg}s)` : "🎤 segure para falar"}
                                    </button>
                                )}
                                <textarea value={texto} onChange={(e) => setTexto(e.target.value)} rows={2}
                                    placeholder={emFoco ? `Pergunte sobre a Q${emFoco.numero}…` : conversa?.modo_voz ? "…ou escreva aqui" : "Escreva sua pergunta…"}
                                    onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); mandar(texto) } }} />
                                {anexo && <span className="chat-anexo">🖼 {anexo.nome}<button className="link" onClick={() => setAnexo(null)}>✕</button></span>}
                                <div className="chat-botoes">
                                    <input ref={arquivo} type="file" accept="image/*" hidden
                                        onChange={(e) => { escolherArquivo(e.target.files?.[0] ?? null); e.target.value = "" }} />

                                    <span className="popup-anchor">
                                        <button className="icone-add" onClick={() => setAnexarAberta((v) => !v)} title="Anexar">+</button>
                                        {anexarAberta && (
                                            <>
                                                <div className="popup-backdrop" onClick={() => setAnexarAberta(false)} />
                                                <PopupAnexar onArquivo={() => { setAnexarAberta(false); arquivo.current?.click() }} onCaptura={acionarCaptura} />
                                            </>
                                        )}
                                    </span>

                                    <span className="popup-anchor">
                                        <button className="icone-add" onClick={() => setAcoesAberta((v) => !v)} title="Mini-aula, macete e outros recursos">🎓</button>
                                        {acoesAberta && (
                                            <>
                                                <div className="popup-backdrop" onClick={() => setAcoesAberta(false)} />
                                                <PopupAcoes
                                                    emFoco={emFoco}
                                                    respondida={respostaFoco}
                                                    pedindo={pedindoResposta}
                                                    gemeaAtual={gemeaIdx >= 0 ? gemeas[gemeaIdx] ?? null : null}
                                                    enviando={enviando}
                                                    modoEstudo={modoEstudo}
                                                    onTrocarModo={setModoEstudo}
                                                    onPedir={() => emFoco && lerQuestao(emFoco)}
                                                    onResponder={(letra) => {
                                                        setAcoesAberta(false)
                                                        if (emFoco) responderPrincipal(emFoco, letra)
                                                    }}
                                                    onAcao={(a) => {
                                                        setAcoesAberta(false)
                                                        if (emFoco) mandar(a.prompt(emFoco.numero), false, `Q${emFoco.numero} · ${a.curto}`)
                                                    }}
                                                    onGemeas={() => emFoco && iniciarGemeasPara(emFoco)}
                                                    onResponderGemea={responderGemeaAtual}
                                                />
                                            </>
                                        )}
                                    </span>

                                    <span className="chat-espaco" />

                                    {conversa && (
                                        <span className="popup-anchor">
                                            <button className="pill" onClick={() => setCfgAberta((v) => !v)}>
                                                <span className="pill-modelo">{modeloTextoLabel}</span>
                                                <span className="chevron">⌄</span>
                                            </button>
                                            {cfgAberta && (
                                                <>
                                                    <div className="popup-backdrop" onClick={() => setCfgAberta(false)} />
                                                    <PopupIA conversa={conversa} modelos={modelos} onTrocarModelo={trocarModelo} onTrocarModo={trocarModo} />
                                                </>
                                            )}
                                        </span>
                                    )}

                                    <span className={`mic-grupo ${maosLivres ? "maos-livres-ativo" : ""}`}>
                                        <button
                                            className={`icone-mic-rec ${gravando ? "gravando" : ""}`}
                                            disabled={respondendoVoz || maosLivres}
                                            title={maosLivres ? "Desligue o mãos-livres pra gravar assim" : gravando ? "Solte para enviar" : "Segure para gravar sua pergunta"}
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

                                    <button className="chat-enviar" disabled={enviando || !texto.trim()} onClick={() => mandar(texto)}>
                                        {enviando ? "…" : "Enviar ▸"}
                                    </button>
                                </div>
                            </div>
                        </div>

                        {/* Escolha da questão: do lado da IA, embaixo do campo de mensagem —
                            não mais no painel de configurações à esquerda. */}
                        {questoes.length > 0 && (
                            <div className="chat-questao-picker">
                                {conversa?.modo_questao === "random" ? (
                                    <button disabled={enviando} onClick={questaoAleatoria} style={{ width: "100%" }}>
                                        🎲 Questão aleatória
                                    </button>
                                ) : (
                                    <label>Questão em estudo
                                        <select value={qid} onChange={(e) => setQid(e.target.value === "" ? "" : Number(e.target.value))}>
                                            <option value="">— escolher —</option>
                                            {questoes.map((q) => (
                                                <option key={q.id} value={q.id}>
                                                    Q{examIdsConversa.length > 1 ? `${q.examId}.${q.numero}` : q.numero} · {q.disciplina}{q.tem_figura ? " 🖼" : ""}
                                                </option>
                                            ))}
                                        </select>
                                    </label>
                                )}
                                {emFoco && (
                                    <div className="chat-foco">
                                        <p className="chat-foco-enun">{semHtml(emFoco.pergunta || emFoco.enunciado).slice(0, 150) || "(sem enunciado)"}…</p>
                                        {emFoco.tem_figura && <p className="chat-foco-fig">🖼 tem figura — a IA de imagem lê</p>}
                                        <p className="chat-foco-status">
                                            {respostaFoco ? `✓ você respondeu ${respostaFoco} — veja os recursos no botão 🎓` : "Abra o botão 🎓 e toque em \"Ler questão\" para ver o enunciado e responder."}
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}
                    </>
                )}
            </section>
        </div>
    )
}
