/** [135]: cliente da voz em tempo real do Tutor IA — WebSocket próprio
 *  (`/ws/tutor-voz`), microfone capturado em PCM16 16kHz (não MediaRecorder
 *  — precisa de amostra crua pra mandar aos poucos enquanto fala, não um
 *  blob gravado inteiro).
 *
 *  [141]: a resposta é tocada por um `<audio>` comum, NÃO mais Web Audio API
 *  crua — achado real (teste isolado, `Artifact`/[140]): o MESMO áudio do
 *  Kokoro tocou perfeitamente num `<audio controls>` simples na máquina do
 *  usuário, mas nunca tocou via `AudioContext`+`AudioBufferSourceNode` no
 *  app (mesmo com o contexto "running", sink correto, sem erro nenhum no
 *  console). A causa exata da diferença não foi provada (hipótese de
 *  "ducking" de comunicação do Windows foi levantada e não confirmada/
 *  descartada) — mas em vez de continuar caçando a causa, a correção usa o
 *  mecanismo que JÁ PROVOU funcionar nessa máquina: monta cada FRASE
 *  completa (o backend já manda `sentence_end` por frase) como um WAV de
 *  verdade e toca no mesmo elemento `<audio>` reusado nas outras modalidades
 *  de voz do projeto (mesmo padrão de desbloqueio por gesto real do [129]).
 *
 *  Módulo isolado de propósito — nada aqui é usado pelo aperta-e-segura/
 *  mãos-livres existentes (que continuam com MediaRecorder, intocados). Só
 *  entra em jogo pelo botão novo, só no desktop. */

export type EventoVoz =
    | { tipo: "estado"; valor: "conectando" | "ouvindo" | "processando" | "falando" | "encerrado" }
    | { tipo: "transcricao_parcial" | "transcricao_final"; texto: string }
    | { tipo: "resposta_parcial"; texto: string }
    | { tipo: "erro"; detalhe: string }
    // [145]: reconexão automática do STT (a conexão com a Together pode
    // cair sozinha) — não é erro, é um aviso informativo, sem interromper.
    | { tipo: "aviso"; detalhe: string }

// [151]: 1,1s era curto demais pra uma pausa natural (pensar, respirar,
// formular a frase) — cortava o usuário no meio da fala. Não é um limite de
// TEMPO PRA FALAR, é só quanto silêncio o sistema espera antes de assumir
// que a pessoa terminou. 2200ms dá bem mais folga, ainda sem deixar a
// resposta lenta demais depois que a pessoa realmente parou.
const SILENCIO_PARA_ENVIAR_MS = 2200
const LIMIAR_RMS = 0.02
const SAMPLE_RATE_SAIDA = 24000

/** Monta um cabeçalho WAV de verdade (44 bytes) na frente do PCM16 cru —
 *  formato idêntico ao que o teste isolado ([140]) provou tocar na máquina
 *  do usuário via `<audio>` comum. */
function pcm16ParaWav(pcm16: Uint8Array<ArrayBuffer>): Blob {
    const cabecalho = new ArrayBuffer(44)
    const v = new DataView(cabecalho)
    const escrever = (offset: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i)) }
    const bytesPorAmostra = 2
    const byteRate = SAMPLE_RATE_SAIDA * bytesPorAmostra
    escrever(0, "RIFF")
    v.setUint32(4, 36 + pcm16.byteLength, true)
    escrever(8, "WAVE")
    escrever(12, "fmt ")
    v.setUint32(16, 16, true)       // tamanho do bloco fmt
    v.setUint16(20, 1, true)        // PCM
    v.setUint16(22, 1, true)        // mono
    v.setUint32(24, SAMPLE_RATE_SAIDA, true)
    v.setUint32(28, byteRate, true)
    v.setUint16(32, bytesPorAmostra, true)
    v.setUint16(34, 16, true)       // bits por amostra
    escrever(36, "data")
    v.setUint32(40, pcm16.byteLength, true)
    return new Blob([cabecalho, pcm16], { type: "audio/wav" })
}

/** Fila de reprodução por FRASE via `<audio>` comum — acumula os pedaços
 *  PCM16 de uma frase até `sentence_end`, monta um WAV completo, e toca em
 *  sequência (espera `onended` antes da próxima) no mesmo elemento
 *  persistente. Perde o "sem gap dentro da frase" do agendamento manual,
 *  mas usa o único mecanismo comprovado funcionando na prática. */
class FilaAudio {
    private elemento: HTMLAudioElement
    private pedacosFraseAtual: Uint8Array<ArrayBuffer>[] = []
    private filaFrases: Blob[] = []
    private tocando = false
    // [149]: achado real — `response_done` chega assim que o BACKEND termina
    // de mandar texto+áudio, não quando o ÁUDIO termina de TOCAR (tocar tem
    // duração real, proporcional à fala). Sem isto, o "ouvindo" disparava
    // (e escondia o texto ao vivo) enquanto o Kokoro ainda estava falando.
    private aoEsvaziar: (() => void) | null = null

    constructor(elemento: HTMLAudioElement) {
        this.elemento = elemento
        this.elemento.onended = () => { this.tocando = false; this._tocarProxima() }
        this.elemento.onerror = () => { this.tocando = false; this._tocarProxima() }
    }

    async destravar(): Promise<void> {
        // [129]: mesmo truque de desbloqueio por gesto real já usado no
        // resto do projeto — WAV silencioso, tocado dentro do clique.
        try {
            this.elemento.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
            await this.elemento.play()
            this.elemento.pause()
            this.elemento.currentTime = 0
            console.log("[VTR] elemento <audio> de saída desbloqueado com sucesso")
        } catch (e) {
            console.error("[VTR] falha ao desbloquear o <audio> de saída:", e)
        }
    }

    enfileirarPedaco(pcm16Bruto: ArrayBuffer): void {
        // [137]: defensivo — o backend já alinha em pares de bytes na origem.
        const pcm16 = pcm16Bruto.byteLength % 2 !== 0 ? pcm16Bruto.slice(0, -1) : pcm16Bruto
        if (pcm16.byteLength) this.pedacosFraseAtual.push(new Uint8Array(pcm16))
    }

    /** [141]: o backend manda `sentence_end` depois dos pedaços de cada
     *  frase — é o gatilho pra fechar o WAV daquela frase e enfileirar. */
    fecharFrase(): void {
        if (!this.pedacosFraseAtual.length) return
        const total = this.pedacosFraseAtual.reduce((n, p) => n + p.byteLength, 0)
        const juntado: Uint8Array<ArrayBuffer> = new Uint8Array(total)
        let offset = 0
        for (const p of this.pedacosFraseAtual) { juntado.set(p, offset); offset += p.byteLength }
        this.pedacosFraseAtual = []
        const blob = pcm16ParaWav(juntado)
        console.log("[VTR] frase fechada:", { bytesPcm: total, duracaoAprox: (total / 2 / SAMPLE_RATE_SAIDA).toFixed(3) })
        this.filaFrases.push(blob)
        this._tocarProxima()
    }

    /** Diz se a fila ainda tem algo tocando ou esperando pra tocar. */
    estaOcupada(): boolean {
        return this.tocando || this.filaFrases.length > 0
    }

    /** Registra um aviso pra quando a fila esvaziar de verdade (nada
     *  tocando, nada esperando) — dispara uma única vez. Se já estiver
     *  vazia neste instante, quem chama deve conferir com `estaOcupada()`
     *  antes, em vez de confiar cegamente neste callback. */
    setAoEsvaziar(cb: (() => void) | null): void {
        this.aoEsvaziar = cb
    }

    private _tocarProxima(): void {
        if (this.tocando) return
        if (!this.filaFrases.length) {
            const cb = this.aoEsvaziar
            this.aoEsvaziar = null
            cb?.()
            return
        }
        const blob = this.filaFrases.shift()!
        const url = URL.createObjectURL(blob)
        this.tocando = true
        this.elemento.src = url
        this.elemento.play()
            .then(() => console.log("[VTR] <audio> tocando frase — bytes:", blob.size))
            .catch((e) => {
                console.error("[VTR] <audio>.play() falhou:", e?.name, e?.message)
                this.tocando = false
                this._tocarProxima()
            })
        // libera a memória do Blob assim que ele terminar (ou logo depois de
        // começar a tocar — o navegador já leu o que precisava do Blob).
        this.elemento.addEventListener("ended", () => URL.revokeObjectURL(url), { once: true })
    }

    fechar(): void {
        this.filaFrases = []
        this.pedacosFraseAtual = []
        this.aoEsvaziar = null
        this.elemento.pause()
        this.elemento.src = ""
    }
}

/** Downsample simples (decimação por vizinho mais próximo) do sample rate
 *  nativo do hardware (tipicamente 48000) pra 16000, que é o que o STT em
 *  tempo real da Together exige. Não é um resample de qualidade de estúdio,
 *  mas é suficiente pra fala — o teste real ([135]) confirmou transcrição
 *  correta com esse método. */
function paraPcm16_16k(float32: Float32Array, sampleRateOrigem: number): ArrayBuffer {
    const razao = sampleRateOrigem / 16000
    const tamanhoNovo = Math.floor(float32.length / razao)
    const saida = new Int16Array(tamanhoNovo)
    for (let i = 0; i < tamanhoNovo; i++) {
        const amostra = float32[Math.floor(i * razao)]
        saida[i] = Math.max(-32768, Math.min(32767, Math.round(amostra * 32768)))
    }
    return saida.buffer
}

export class VozTempoReal {
    private ws: WebSocket | null = null
    private ctxEntrada: AudioContext | null = null
    private stream: MediaStream | null = null
    private processor: ScriptProcessorNode | null = null
    private fila: FilaAudio | null = null
    private _elementoAudio: HTMLAudioElement | null = null
    private silencioDesde: number | null = null
    private jaComitou = false
    private encerrado = false
    // [155]: achado real — o microfone mandava áudio pro servidor O TEMPO
    // TODO, inclusive enquanto a IA estava falando. Sem fone, a voz da IA
    // sai pela caixa, o mic capta a própria resposta, o sistema "ouve a si
    // mesma" e entra num loop (exatamente o relato do usuário: "envia
    // palavras que o usuário não mandou, em sequência"). O mesmo problema
    // já tinha sido resolvido no OUTRO modo de voz (mãos-livres,
    // `Chat.tsx`/`TutorIA.tsx`, [096]: "nunca escuta o próprio áudio da
    // IA") — esta classe nasceu depois, separada, e não herdou a proteção.
    private estadoAtual: "conectando" | "ouvindo" | "processando" | "falando" | "encerrado" = "conectando"
    // [012]/[096]: este projeto roda com `erasableSyntaxOnly` — proíbe
    // parâmetro-propriedade no construtor, então os campos são declarados
    // e atribuídos explicitamente.
    private readonly conversationId: number
    private readonly onEvento: (e: EventoVoz) => void

    constructor(conversationId: number, onEvento: (e: EventoVoz) => void) {
        this.conversationId = conversationId
        this.onEvento = onEvento
    }

    /** [155]: único ponto que emite `estado` — sempre atualiza
     * `estadoAtual` junto, pra `_processarAudio` saber se pode mandar áudio. */
    private _estado(valor: "conectando" | "ouvindo" | "processando" | "falando" | "encerrado"): void {
        this.estadoAtual = valor
        this.onEvento({ tipo: "estado", valor })
    }

    async iniciar(): Promise<void> {
        this._estado("conectando")

        // [141]: elemento <audio> real, próprio deste módulo (isolado do
        // resto do app) — mecanismo comprovado funcionando na máquina do
        // usuário, no lugar do AudioContext cru que nunca produziu som
        // audível apesar de reportar "running" sem erro nenhum.
        const elementoAudio = document.createElement("audio")
        elementoAudio.hidden = true
        document.body.appendChild(elementoAudio)
        this._elementoAudio = elementoAudio
        this.fila = new FilaAudio(elementoAudio)
        await this.fila.destravar()  // [129]/[135]: destrava dentro do clique real que chamou iniciar()

        // [155]: a 2ª camada de defesa (echoCancellation/noiseSuppression
        // explícitos) foi REVERTIDA — o usuário reportou o "Tempo real"
        // inteiro parando de funcionar depois dela. Hipótese mais provável,
        // não confirmada ainda (sem microfone real aqui pra testar): o
        // processamento de eco/ruído pode ter deixado um piso de ruído/
        // artefato que nunca cai abaixo de `LIMIAR_RMS`, então o silêncio
        // nunca é detectado e o `commit` nunca dispara — pareceria
        // "travado", não só "com eco". A trava real do bug (não mandar
        // áudio fora do estado "ouvindo", logo abaixo) é lógica pura,
        // determinística, e fica — só a constraint de hardware saiu.
        this.stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        // [137]: rms sempre 0.0000 no teste real — precisa saber se a TRACK
        // em si já chega mutada/sem sinal (permissão do SO bloqueando por
        // baixo do pano, mesmo com a permissão do SITE concedida — comum no
        // Windows) ou se o problema é depois, no grafo do Web Audio.
        for (const track of this.stream.getAudioTracks()) {
            console.log("[VTR] audio track:", {
                label: track.label, enabled: track.enabled, muted: track.muted, readyState: track.readyState,
                settings: track.getSettings(),
            })
            track.onmute = () => console.warn("[VTR] track ficou MUTED em runtime")
            track.onunmute = () => console.log("[VTR] track ficou UNMUTED em runtime")
        }

        const protocolo = location.protocol === "https:" ? "wss:" : "ws:"
        this.ws = new WebSocket(`${protocolo}//${location.host}/ws/tutor-voz?conversation_id=${this.conversationId}`)
        this.ws.binaryType = "arraybuffer"

        await new Promise<void>((resolve, reject) => {
            if (!this.ws) return reject(new Error("sem WebSocket"))
            this.ws.onopen = () => resolve()
            this.ws.onerror = () => reject(new Error("Falha ao conectar ao servidor de voz."))
        })

        this.ws.onmessage = (ev) => {
            if (ev.data instanceof ArrayBuffer) {
                this._estado("falando")
                this.fila?.enfileirarPedaco(ev.data)
                return
            }
            const obj = JSON.parse(ev.data as string)
            if (obj.type === "transcript_delta") this.onEvento({ tipo: "transcricao_parcial", texto: obj.text })
            else if (obj.type === "transcript_final") {
                this.onEvento({ tipo: "transcricao_final", texto: obj.text })
                this._estado("processando")
            } else if (obj.type === "llm_delta") this.onEvento({ tipo: "resposta_parcial", texto: obj.text })
            // [141]: fim de UMA frase — fecha o WAV daquela frase e toca,
            // não espera a resposta inteira (a fila de <audio> continua
            // encadeando as próximas frases conforme chegam).
            else if (obj.type === "sentence_end") this.fila?.fecharFrase()
            else if (obj.type === "response_done") {
                // [149]: o backend terminou de MANDAR — o áudio pode ainda
                // estar TOCANDO (playback tem duração real). Só volta a
                // "ouvindo" (e só aí a bolha ao vivo é limpa/commitada) quando
                // a fila de reprodução esvaziar de verdade; sem áudio pendente
                // (resposta sem fala, ou já terminou de tocar), libera na hora.
                this.jaComitou = false
                if (this.fila?.estaOcupada()) {
                    this.fila.setAoEsvaziar(() => this._estado("ouvindo"))
                } else {
                    this._estado("ouvindo")
                }
            } else if (obj.type === "error") this.onEvento({ tipo: "erro", detalhe: obj.detail ?? "erro desconhecido" })
            // [145]: o backend reconectou a conexão STT->Together sozinho
            // depois dela cair — avisa sem tratar como falha da sessão.
            else if (obj.type === "info") this.onEvento({ tipo: "aviso", detalhe: obj.detail ?? "" })
        }
        this.ws.onclose = (ev) => {
            // [138]: motivo real do fechamento — antes era só um aviso genérico
            // "caiu", sem código nem razão nenhuma pra saber o porquê.
            console.log("[VTR] WebSocket fechou:", { code: ev.code, reason: ev.reason, wasClean: ev.wasClean })
            if (!this.encerrado) {
                const motivo = ev.reason ? ` (${ev.code}: ${ev.reason})` : ` (código ${ev.code})`
                this.onEvento({ tipo: "erro", detalhe: `Conexão de voz caiu${motivo}.` })
            }
        }
        this.ws.onerror = (ev) => console.error("[VTR] WebSocket erro:", ev)

        this.ctxEntrada = new AudioContext()
        // [136]: a essa altura já passamos por getUserMedia + handshake do
        // WebSocket (vários `await`) — fora da janela de gesto do usuário que
        // o Chrome exige pra nascer "running". Sem isto, o contexto nasce
        // "suspended" e onaudioprocess NUNCA dispara — o microfone parece
        // "ouvindo" na tela mas nada é processado. Achado real (não suposto):
        // era exatamente o sintoma relatado (botão liga, nada acontece).
        if (this.ctxEntrada.state === "suspended") await this.ctxEntrada.resume()
        console.log("[VTR] ctxEntrada state após resume:", this.ctxEntrada.state)

        const fonte = this.ctxEntrada.createMediaStreamSource(this.stream)
        // ScriptProcessorNode é deprecated mas universalmente suportado — sem
        // precisar carregar um AudioWorklet module à parte pra esta 1ª versão.
        this.processor = this.ctxEntrada.createScriptProcessor(4096, 1, 1)
        fonte.connect(this.processor)
        this.processor.connect(this.ctxEntrada.destination)
        this.processor.onaudioprocess = (e) => this._processarAudio(e)

        this._estado("ouvindo")
    }

    private _processarAudio(e: AudioProcessingEvent): void {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
        // [155]: NUNCA manda áudio do microfone pro servidor fora do estado
        // "ouvindo" — é isto que impede o sistema de captar a própria voz
        // (TTS tocando pela caixa) como se fosse fala do usuário. Reseta o
        // relógio de silêncio também, pra não computar como pausa o tempo
        // em que nem estava escutando de verdade.
        if (this.estadoAtual !== "ouvindo") {
            this.silencioDesde = null
            return
        }
        const float32 = e.inputBuffer.getChannelData(0)

        // [152]: `pico` ([137], só usado no log de diagnóstico que já
        // cumpriu o propósito — confirmar que o mic capturava sinal de
        // verdade, já confirmado pelo usuário) saiu do loop — um comparação
        // a menos por amostra, nas ~4096 amostras de CADA chamada (roda a
        // cada ~85ms, no MESMO thread principal da tela/render).
        let soma = 0
        for (let i = 0; i < float32.length; i++) soma += float32[i] * float32[i]
        const rms = Math.sqrt(soma / float32.length)

        const pcm16 = paraPcm16_16k(float32, this.ctxEntrada?.sampleRate ?? 48000)
        this.ws.send(pcm16)

        const agora = performance.now()
        if (rms > LIMIAR_RMS) {
            this.silencioDesde = null
        } else {
            if (this.silencioDesde == null) this.silencioDesde = agora
            if (!this.jaComitou && agora - this.silencioDesde >= SILENCIO_PARA_ENVIAR_MS) {
                this.jaComitou = true
                console.log("[VTR] silêncio detectado, mandando commit")
                this.ws.send(JSON.stringify({ type: "commit" }))
            }
        }
    }

    parar(): void {
        this.encerrado = true
        try { this.ws?.send(JSON.stringify({ type: "stop" })) } catch { /* já pode ter caído */ }
        this.ws?.close()
        this.processor?.disconnect()
        this.stream?.getTracks().forEach((t) => t.stop())
        void this.ctxEntrada?.close()
        this.fila?.fechar()
        this._elementoAudio?.remove()  // [141]: elemento próprio deste módulo, tira do DOM ao encerrar
        this._estado("encerrado")
    }
}
