export type Health = { status: "ok" | "degraded"; database?: boolean; pgvector?: string | null }

export type Usuario = {
    id: number
    nome: string
    email: string
    cpf: string
    telefone: string
    role: string
    tem_senha: boolean
    senha_habilitada: boolean
    senha_prompt_dispensado: boolean
}

// Campos declarados explicitamente: o TypeScript deste projeto roda com
// erasableSyntaxOnly, que proíbe parâmetro-propriedade no construtor.
export class ApiError extends Error {
    status: number

    constructor(status: number, mensagem: string) {
        super(mensagem)
        this.status = status
    }
}

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
    const res = await fetch(`/api/v1${caminho}`, {
        credentials: "include",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        ...init,
    })
    if (!res.ok) {
        const corpo = await res.json().catch(() => null)
        const detalhe = corpo?.detail
        // O FastAPI devolve lista de erros quando a validação do schema falha.
        let mensagem: string
        if (Array.isArray(detalhe)) {
            const e = detalhe[0]
            const campo = Array.isArray(e?.loc) ? e.loc[e.loc.length - 1] : ""
            mensagem = campo ? `Campo "${campo}": ${e?.msg ?? "inválido"}` : (e?.msg ?? "Dados inválidos.")
        } else {
            mensagem = detalhe ?? `Erro ${res.status}`
        }
        throw new ApiError(res.status, mensagem)
    }
    return res.status === 204 ? (undefined as T) : res.json()
}

export type DadosCadastro = { nome: string; email: string; cpf: string; telefone: string }

export type Choice = { letra: string; texto: string }
export type Questao = {
    id: number; numero: number; pagina: number; disciplina: string; enunciado: string
    enunciado_col2: string; pergunta: string; gabarito: string | null; tem_figura: boolean; modo_exibicao: string; confianca: number; aviso: string
    revisada: boolean; descartada: boolean; alternativas: Choice[]
}
// [153]: só a rota de Revisão devolve isto — "simulado" ou "chat" (de onde veio o erro)
export type QuestaoRevisao = Questao & { origem: "simulado" | "chat" }
export type Exame = { id: number; banca: string; orgao: string; cargo: string; ano: number | null; total: number; revisar: number; excluido_em?: string | null }
export type TempoEnfase = { enfase: string; amostra: number; mediana_s: number; media_s: number; p75_s: number }
export type MasteryEnfase = { enfase: string; acertos: number; total: number; percentual: number; mastery: string; amostra: number }
export type DificuldadeEnfase = { enfase: string; tentativas: number; erros: number; erro_pct: number; dificuldade: string }
export type Gamificacao = { xp: number; nivel: number; xp_no_nivel: number; xp_para_proximo: number; acertos: number; simulados: number; revisoes: number; streak_dias: number }
export type DesempenhoResumo = {
    mastery: MasteryEnfase[]
    dificuldade: DificuldadeEnfase[]
    macete: { com_macete: number; revisoes_avaliadas: number; acerto_pos_macete_pct: number | null; observacao: string }
    gamificacao: Gamificacao
}
export type AdminOverview = { usuarios: number; simulados_feitos: number; cadernos: number; questoes: number }
export type RecursoConcedido = { feature: string; nome: string; limite_diario: number; usado_hoje: number }
export type UsuarioAdmin = {
    id: number; nome: string; email: string; role: string; saldo: number; vitalicio: boolean
    simulados: number; recursos: RecursoConcedido[]
    mesmo_cpf_dono: boolean; comprado: number; doado: number
}
export type RecursoCatalogo = Record<string, { nome: string; unidade: string; custo_unidade_api: number }>
export type MeuRecurso = { liberado: boolean; limite_diario: number | null; usado_hoje: number }
export type YoutubeUso = { buscas_hoje: number; unidades_hoje: number; cota_diaria_unidades: number; pct: number }
export type Conversa = {
    id: number; exam_id: number | null; exam_ids: number[]; titulo: string
    modo: "chat" | "tutor"; persona: "professor" | "amigo"; modo_questao: "normal" | "random"; rag_doc_ids: number[]
    modelo_texto_id: number | null; modelo_visao_id: number | null
    modelo_voz_id: number | null; modelo_transcricao_id: number | null; modo_voz: boolean
    voz_escolhida: string | null
}
export type VozKokoro = { id: string; rotulo: string }
export type DocTutor = {
    id: number; titulo: string; descricao: string; indexado: boolean
    tentativas_indexacao: number; enviado_por: string | null
}
export type DocChat = { id: number; titulo: string; descricao: string; indexado: boolean; tentativas_indexacao: number }
export type ModeloOpcao = { id: number; nome: string; modelo: string; ativa: boolean }
export type ModelosChat = { texto: ModeloOpcao[]; visao: ModeloOpcao[]; voz: ModeloOpcao[]; transcricao: ModeloOpcao[] }
export type EditarConversaIn = {
    titulo?: string
    persona?: "professor" | "amigo"
    rag_doc_ids?: number[]
    modelo_texto_id?: number | null; modelo_visao_id?: number | null
    modelo_voz_id?: number | null; modelo_transcricao_id?: number | null
    modo_voz?: boolean
    voz_escolhida?: string | null
    limpar_voz?: boolean
}
export type ChatMsg = { role: string; conteudo: string; question_id: number | null }
export type JanelaUso = { usadas: number; limite: number; restam: number | null; reinicia_em?: string | null; libera_em?: string | null }
export type LimitesUso = { isento: boolean; janela_sessao_h: number; janela_semana_d: number; sessao: JanelaUso; semana: JanelaUso; bloqueado: boolean }
export type LimitesConfig = { sessao_msgs: number; semana_msgs: number; janela_sessao_h: number; janela_semana_d: number }
export type Orcamento = {
    orcamento_mensal_usd: number; orcamento_diario_usd: number
    gasto_hoje_usd: number; gasto_mes_usd: number
    pct_dia: number; pct_mes: number; projecao_mes_usd: number; diario_excedido: boolean
}
export type Dinheiro = { usd: number; brl: number }
export type UsoTotais = {
    chamadas: number; falhas: number; tokens_in: number; tokens_out: number
    stt_seg: number; tts_chars: number; custo: Dinheiro
}
export type UsoDist = { n: number; p50: number | Dinheiro | null; p90: number | Dinheiro | null; max: number | Dinheiro | null }
export type UsoFerramenta = UsoTotais & {
    ferramenta: string; acoes: number; acoes_falhas: number
    custo_por_acao_clientes: { n: number; p50: Dinheiro | null; p90: Dinheiro | null; max: Dinheiro | null }
}
export type UsoUsuario = {
    user_id: number | null; nome: string; email: string | null; sem_limites: boolean
    total: UsoTotais; dias_ativos: number
    por_ferramenta: (UsoTotais & { ferramenta: string; acoes: number })[]
}
export type ConsumoResumo = {
    dias: number; desde: string; cotacao: { usd_brl: number; fonte: string }; total: Dinheiro
    ferramentas: UsoFerramenta[]; usuarios: UsoUsuario[]
    distribuicao_clientes: {
        usuarios_com_uso: number
        custo_por_usuario_dia: { n: number; p50: Dinheiro | null; p90: Dinheiro | null; max: Dinheiro | null }
        acoes_por_usuario_dia: { n: number; p50: number | null; p90: number | null; max: number | null }
    }
    notas: string[]
}
export type FilaEstado = {
    max_concorrente: number; cpu_pct_max: number; mem_pct_max: number; disco_pct_max: number; timeout_espera_s: number
    em_voo: number; esperando: number; cpu_pct: number; memoria_pct: number | null; disco_pct: number | null
}
export type FilaHistoricoLinha = {
    quando: string; cpu_pct: number | null; memoria_pct: number | null; disco_pct: number | null
    em_voo: number; esperando: number; max_concorrente: number
    admitidas: number; rejeitadas: number; espera_media_ms: number | null
}
export type IconeEscolha = { tipo: "biblioteca" | "upload"; valor: string }
export type IconesEstado = Record<string, IconeEscolha>
export type IconeCatalogoLinha = { slot: string; grupo: string; rotulo: string; atual: IconeEscolha | null }
export type CreditosResumo = {
    saldo: number; total_ganho: number; total_gasto: number
    extrato: { delta: number; tipo: string; descricao: string; quando: string | null }[]
    acesso_livre: boolean
}
export type PlataformaPagamento = { id: number; titulo: string; provedor: string; public_key: string; ativa: boolean; token_mascarado: string }
export type PlataformaPagamentoInput = { titulo: string; provedor: string; access_token: string; public_key: string }
export type ConfigPagamento = { preco_reais: number; creditos_por_compra: number }
export type EstadoHoje = { isento: boolean; aberto: boolean; abriu_em: string | null; fecha_em: string | null }
export type ResumoSemana = { isento: boolean; usado: number; alvo: number }
export type MinhaPorta = { hoje: EstadoHoje; semana: ResumoSemana }
export type YoutubeStatus = { configurada: boolean; chave_mascarada: string | null }
export type VideoResultado = { video_id: string; titulo: string; canal: string; miniatura: string; url: string }
export type SaudeVPS = {
    cpus: number; load_1min: number; load_por_cpu: number
    memoria_pct: number | null; disco_pct: number | null; conexoes_db: number | null
    status: "ok" | "atencao" | "critico"; motivos: string[]; cadastros_bloqueados: boolean
}
export type ResultadoSimulado = { total: number; respondidas: number; acertos: number; percentual_bruto: number; resultado: Record<number, boolean>; por_enfase: EnfaseDesempenho[]; tempo_por_enfase?: TempoEnfase[]; tempo_alvo_s?: number | null }
export type Classificacao = {
    nota_ponderada: number; nota_corte: number | null; vagas: number | null
    eliminado: boolean; motivos: string[]
    por_disciplina: Record<string, { acertos: number; total: number; peso: number }>
    por_fase: { fase: string; pontos: number; total: number; percentual: number; minimo_pct: number | null }[]
    ranking?: {
        status: string; candidato_pct?: number; publico_pct?: number; delta_pp?: number
        percentil_estimado?: number; posicao_estimada?: number | null; total_inscritos?: number | null
        vagas?: number | null; situacao?: string | null; confianca?: string; enfases_sem_dado?: string[]; observacao?: string
    }
}
export type RegrasEditalT = { pesos: Record<string, number>; minimos: Record<string, number>; nota_corte: number | null; vagas: number | null; total_inscritos?: number | null; fases?: Record<string, string>; minimo_pct_fase?: Record<string, number>; materias_sem_zero?: string[] }
export type SimRun = { simulation_id: number; started_at: string; deadline_at: string; duration_seconds: number; question_count: number; status: string }
export type EnfaseDesempenho = { enfase: string; acertos: number; total: number; percentual: number; mastery: string; amostra: number; historico_pct?: number | null; delta?: number | null; delta_rotulo?: string; amostra_historico?: number | null }
export type StatEnfase = { id: number; exam_id: number | null; disciplina: string; banca: string; orgao: string; cargo: string; ano: number | null; enfase: string; amostra: number | null; acerto_pct: number | null; fonte: string; tipo_fonte: string; status: string }
export type StatEnfaseInput = Omit<StatEnfase, "id">
export type TemaComStat = { id: number; nome: string; stat: StatEnfase | null }
export type EstruturaEstat = { exam_id: number; cargo: string; disciplinas: { disciplina: string; temas: TemaComStat[] }[] }
export type SimResultado = { acertos: number; total: number; respondidas: number; em_branco: number; percentual_bruto: number; encerrado_no_prazo: boolean; resultado: Record<number, boolean>; por_enfase: EnfaseDesempenho[]; classificacao?: Classificacao | null; tempo_por_enfase?: TempoEnfase[]; tempo_alvo_s?: number | null }
export type GemeaT = { id: number; enunciado: string; alternativas: Record<string, string> }
export type Explicacao = {
    correct: boolean; error_type: string; diagnosis: string; mini_lesson: string
    review_recommendation: string
    memory_trick: { memory_hook: string; rapid_rule: string; steps: string[]; applies_when: string; warning: string }
}
export type Plataforma = {
    id: number; titulo: string; endpoint: string; chave_mascarada: string; qtd_modelos: number
}
export type PlataformaInput = { titulo: string; endpoint: string; api_key: string }
export type RagDoc = {
    id: number; titulo: string; descricao: string; colecao: string; chunk_count: number; indexado: boolean; erro: string | null
    uso_chat: boolean; uso_tutor: boolean; uso_simulado: boolean; enviado_por: string | null; tentativas_indexacao: number; chunks_prontos: number
}
export type ConexaoIA = {
    id: number; platform_id: number; plataforma_titulo: string
    nome: string; modelo: string; categoria: string
    tipo_deploy: string; ativa: boolean; ordem_fallback: number | null
    max_tokens: number; temperatura: number
    context_window_tokens: number | null; rate_limit_rpm: number | null
    preco_entrada_por_milhao: number | null; preco_saida_por_milhao: number | null
    moeda: string
}
export type ConexaoInput = {
    platform_id: number; nome: string; modelo: string; categoria: string
    tipo_deploy?: string; max_tokens?: number; temperatura?: number
    context_window_tokens?: number | null; rate_limit_rpm?: number | null
    preco_entrada_por_milhao?: number | null; preco_saida_por_milhao?: number | null
    moeda?: string
}
export type UsoConexao = {
    connection_id: number
    requisicoes: number; erros: number
    prompt_tokens: number; completion_tokens: number; total_tokens: number
    segundos_uso: number; horas_uso: number
    unidades: Record<string, number>
    tem_preco: boolean
    preco: { input: number; output: number; por_minuto: number | null; moeda: string } | null
    custo_usd: number | null; custo_brl: number | null
    gasto_min_usd: number | null; gasto_min_brl: number | null
    gasto_hora_usd: number | null; gasto_hora_brl: number | null
    gasto_dia_usd: number | null; gasto_dia_brl: number | null
    gasto_mes_usd: number | null; gasto_mes_brl: number | null
    ultimos_erros: { quando: string | null; origem: string; erro: string | null }[]
}
export type UsoResumo = {
    cotacao_usd_brl: number; fonte_cotacao: string; por_conexao: UsoConexao[]
}
export type PromptItem = { chave: string; nome: string; onde_usado: string; como_funciona: string; texto: string }
export type PatchQuestao = Partial<{
    enunciado: string; gabarito: string; disciplina: string
    alternativas: Record<string, string>; revisada: boolean; descartada: boolean; modo_exibicao: string; enunciado_col2: string; pergunta: string
}>

export const api = {
    exames: () => pedir<Exame[]>("/exames"),
    importarCaderno: async (form: FormData) => {
        const res = await fetch(`/api/v1/exames/importar`, { method: "POST", credentials: "include", body: form })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao importar") }
        return res.json() as Promise<Exame>
    },
    obterRegras: (examId: number) => pedir<RegrasEditalT | null>(`/exames/${examId}/regras`),
    aferirLLM: (examId: number) => pedir<{ similaridade_pct: number; cenarios: number; checagens: number; veredito: string }>(`/exames/${examId}/aferir-llm`, { method: "POST" }),
    gravarRegras: (examId: number, r: RegrasEditalT) => pedir<RegrasEditalT>(`/exames/${examId}/regras`, { method: "PUT", body: JSON.stringify(r) }),
    editarCaderno: (examId: number, dados: { banca?: string; orgao?: string; cargo?: string; ano?: number | null }) =>
        pedir<Exame>(`/exames/${examId}`, { method: "PATCH", body: JSON.stringify(dados) }),
    apagarCaderno: (examId: number) => pedir<void>(`/exames/${examId}`, { method: "DELETE" }),
    lixeiraCadernos: () => pedir<Exame[]>("/exames/lixeira"),
    restaurarCaderno: (examId: number) => pedir<Exame>(`/exames/${examId}/restaurar`, { method: "POST" }),
    apagarCadernoPermanente: (examId: number) => pedir<void>(`/exames/${examId}/permanente`, { method: "DELETE" }),
    questoes: (examId: number) => pedir<Questao[]>(`/exames/${examId}/questoes`),
    editarQuestao: (qid: number, dados: PatchQuestao) =>
        pedir<Questao>(`/exames/questoes/${qid}`, { method: "PATCH", body: JSON.stringify(dados) }),
    figuraUrl: (qid: number) => `/api/v1/exames/questoes/${qid}/figura`,
    salvarFigura: async (qid: number, blob: Blob) => {
        const fd = new FormData()
        fd.append("arquivo", blob, "recorte.png")
        const res = await fetch(`/api/v1/exames/questoes/${qid}/figura`, { method: "POST", credentials: "include", body: fd })
        if (!res.ok) throw new Error("Falha ao salvar recorte")
        return res.json()
    },
    paginaImagemUrl: (examId: number, n: number) => `/api/v1/exames/${examId}/pagina/${n}/imagem`,
    paginaTexto: async (examId: number, n: number) => {
        const res = await fetch(`/api/v1/exames/${examId}/pagina/${n}/texto`, { credentials: "include" })
        return res.ok ? res.text() : ""
    },
    revisaoDevidas: () => pedir<QuestaoRevisao[]>("/revisao"),
    responderRevisao: (qid: number, letra: string) => pedir<{ acertou: boolean }>(`/revisao/${qid}/responder`, { method: "POST", body: JSON.stringify({ letra }) }),
    gerarGemeas: (qid: number) => pedir<GemeaT[]>(`/exames/questoes/${qid}/gemeas`, { method: "POST" }),
    responderGemea: (twinId: number, letra: string) => pedir<{ acertou: boolean; gabarito: string }>(`/exames/gemeas/${twinId}/responder`, { method: "POST", body: JSON.stringify({ letra }) }),
    explicarIA: (qid: number, student_answer: string | null) =>
        pedir<Explicacao>(`/exames/questoes/${qid}/explicar`, { method: "POST", body: JSON.stringify({ student_answer }) }),
    passoAPasso: (qid: number, student_answer: string | null) =>
        pedir<{ passos: string[] }>(`/exames/questoes/${qid}/passo-a-passo`, { method: "POST", body: JSON.stringify({ student_answer }) }),
    falarPasso: (qid: number, texto: string) =>
        pedir<{ audio_b64: string }>(`/exames/questoes/${qid}/passo-a-passo/falar`, { method: "POST", body: JSON.stringify({ texto }) }),
    transcreverIA: (qid: number) => pedir<{ enunciado: string; alternativas: Record<string, string> }>(`/exames/questoes/${qid}/transcrever`, { method: "POST" }),
    restaurarFigura: (qid: number) => pedir<{ ok: boolean }>(`/exames/questoes/${qid}/figura/restaurar`, { method: "POST" }),
    corrigir: (examId: number, respostas: Record<number, string>, tempos?: Record<number, number>) =>
        pedir<ResultadoSimulado>(`/exames/${examId}/corrigir`, { method: "POST", body: JSON.stringify({ respostas, tempos }) }),
    desempenho: () => pedir<DesempenhoResumo>("/desempenho"),
    adminOverview: () => pedir<AdminOverview>("/admin/overview"),
    adminUsuarios: () => pedir<UsuarioAdmin[]>("/admin/usuarios"),
    recursosCatalogo: () => pedir<RecursoCatalogo>("/admin/recursos/catalogo"),
    concederRecurso: (email: string, feature: string, limite_diario: number) =>
        pedir<{ ok: boolean }>("/admin/recursos/conceder", { method: "POST", body: JSON.stringify({ email, feature, limite_diario }) }),
    revogarRecurso: (email: string, feature: string) =>
        pedir<{ ok: boolean }>("/admin/recursos/revogar", { method: "POST", body: JSON.stringify({ email, feature }) }),
    adminYoutubeUso: () => pedir<YoutubeUso>("/admin/youtube/uso"),
    chatRecursos: () => pedir<Record<string, MeuRecurso>>("/chat/recursos"),
    adminVitalicio: (email: string, vitalicio: boolean) =>
        pedir<{ email: string; vitalicio: boolean }>("/admin/vitalicio", { method: "POST", body: JSON.stringify({ email, vitalicio }) }),
    campanhaPrevia: (alvo: string, limite: number) =>
        pedir<{ quantos: number; exemplos: string[] }>(`/admin/campanha/previa?alvo=${alvo}&limite=${limite}`),
    aplicarCampanha: (alvo: string, quantidade: number, motivo: string, limite: number) =>
        pedir<{ beneficiados: number }>("/admin/campanha", { method: "POST", body: JSON.stringify({ alvo, quantidade, motivo, limite }) }),
    meusCreditos: () => pedir<CreditosResumo>("/creditos"),
    minhaPorta: () => pedir<MinhaPorta>("/creditos/porta"),
    creditosComprar: () => pedir<{ init_point: string; creditos: number; preco_reais: number }>("/creditos/comprar", { method: "POST" }),
    chatConversas: (modo: "chat" | "tutor" = "chat") => pedir<Conversa[]>(`/chat/conversas?modo=${modo}`),
    chatCriarConversa: (exam_ids: number[], titulo: string, extra?: { modo?: "chat" | "tutor"; persona?: "professor" | "amigo"; modo_questao?: "normal" | "random"; rag_doc_ids?: number[]; modo_voz?: boolean; voz_escolhida?: string | null }) =>
        pedir<Conversa>("/chat/conversas", { method: "POST", body: JSON.stringify({ exam_ids, titulo, ...extra }) }),
    chatMensagens: (cid: number) => pedir<Conversa & { mensagens: ChatMsg[] }>(`/chat/conversas/${cid}`),
    chatModelos: () => pedir<ModelosChat>("/chat/modelos"),
    chatVozes: () => pedir<VozKokoro[]>("/chat/vozes"),
    chatEditarConversa: (cid: number, d: EditarConversaIn) =>
        pedir<Conversa>(`/chat/conversas/${cid}`, { method: "PATCH", body: JSON.stringify(d) }),
    chatDocumentosRag: () => pedir<DocChat[]>("/chat/documentos-rag"),
    chatQuestaoAleatoria: (cid: number) =>
        pedir<{ question_id: number; conteudo: string }>(`/chat/conversas/${cid}/questao-aleatoria`, { method: "POST" }),
    chatEnviar: (cid: number, texto: string, question_id: number | null, imagem_b64?: string | null) => pedir<{ resposta: string; saldo: number; limites: LimitesUso }>(`/chat/conversas/${cid}/mensagem`, { method: "POST", body: JSON.stringify({ texto, question_id, imagem_b64: imagem_b64 ?? null }) }),
    // [123]: mesma resposta de chatEnviar, mas TAMBÉM fala (TTS) — pro modo
    // carro falar de volta mesmo quando o aluno digita em vez de usar o mic.
    // [133]: `audio_url` (URL servida) foi tentada e REVERTIDA — a Cloudflare
    // cacheava a resposta e servia sem checar sessão (vazamento real). Voltou
    // pra `audio_b64` (o que já funcionava no celular).
    chatEnviarFalado: (cid: number, texto: string, question_id: number | null) =>
        pedir<{ resposta: string; audio_b64: string; saldo: number; limites: LimitesUso }>(
            `/chat/conversas/${cid}/mensagem-falada`, { method: "POST", body: JSON.stringify({ texto, question_id }) }),
    chatEnviarAudio: async (cid: number, blob: Blob, question_id: number | null) => {
        const fd = new FormData()
        fd.append("file", blob, "pergunta.webm")
        if (question_id != null) fd.append("question_id", String(question_id))
        const res = await fetch(`/api/v1/chat/conversas/${cid}/audio`, { method: "POST", credentials: "include", body: fd })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? `Erro ${res.status}`) }
        return res.json() as Promise<{ transcricao: string; resposta: string; audio_b64: string; saldo: number; limites: LimitesUso }>
    },
    // Cartões impressos no chat sem IA — texto vem do servidor, nunca do cliente.
    chatLerQuestao: (cid: number, qid: number) => pedir<{ conteudo: string }>(`/chat/conversas/${cid}/questao/${qid}`, { method: "POST" }),
    chatLerGemea: (cid: number, twinId: number, ordem: "A" | "B") => pedir<{ conteudo: string }>(`/chat/conversas/${cid}/gemea/${twinId}?ordem=${ordem}`, { method: "POST" }),
    chatResponderGemea: (cid: number, twinId: number, letra: string) => pedir<{ acertou: boolean; gabarito: string; conteudo: string }>(`/chat/conversas/${cid}/gemea/${twinId}/responder`, { method: "POST", body: JSON.stringify({ letra }) }),
    chatFechamento: (cid: number, qid: number, letraPrincipal: string, gemeaAOk: boolean, gemeaBOk: boolean) =>
        pedir<{ conteudo: string }>(`/chat/conversas/${cid}/questao/${qid}/fechamento`, {
            method: "POST", body: JSON.stringify({ letra_principal: letraPrincipal, gemea_a_ok: gemeaAOk, gemea_b_ok: gemeaBOk }),
        }),
    chatApagar: (cid: number) => pedir<void>(`/chat/conversas/${cid}`, { method: "DELETE" }),
    chatLimites: () => pedir<LimitesUso>("/chat/limites"),
    adminUsoResumo: (dias: number) => pedir<ConsumoResumo>(`/admin/uso/resumo?dias=${dias}`),
    adminOrcamento: () => pedir<Orcamento>("/admin/orcamento"),
    salvarOrcamento: (mensal_usd: number, diario_usd: number | null) =>
        pedir<Orcamento>("/admin/orcamento", { method: "POST", body: JSON.stringify({ mensal_usd, diario_usd }) }),
    adminLimites: () => pedir<LimitesConfig>("/admin/limites"),
    salvarLimites: (sessao_msgs: number, semana_msgs: number) =>
        pedir<LimitesConfig>("/admin/limites", { method: "POST", body: JSON.stringify({ sessao_msgs, semana_msgs }) }),
    adminFila: () => pedir<FilaEstado>("/admin/fila"),
    salvarFila: (dados: Omit<FilaEstado, "em_voo" | "esperando" | "cpu_pct" | "memoria_pct" | "disco_pct">) =>
        pedir<FilaEstado>("/admin/fila", { method: "POST", body: JSON.stringify(dados) }),
    adminFilaHistorico: (dias: number) => pedir<FilaHistoricoLinha[]>(`/admin/fila/historico?dias=${dias}`),
    icones: () => pedir<IconesEstado>("/icones"),
    iconesCatalogo: () => pedir<IconeCatalogoLinha[]>("/icones/admin/catalogo"),
    iconesEscolherBiblioteca: (slot: string, nome_icone: string) =>
        pedir<IconeCatalogoLinha[]>(`/icones/admin/${encodeURIComponent(slot)}`, { method: "PUT", body: JSON.stringify({ nome_icone }) }),
    iconesEnviarUpload: async (slot: string, arquivo: File) => {
        const fd = new FormData(); fd.append("arquivo", arquivo)
        const res = await fetch(`/api/v1/icones/admin/${encodeURIComponent(slot)}/upload`, { method: "POST", credentials: "include", body: fd })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao enviar") }
        return res.json() as Promise<IconeCatalogoLinha[]>
    },
    iconesRemover: (slot: string) => pedir<IconeCatalogoLinha[]>(`/icones/admin/${encodeURIComponent(slot)}`, { method: "DELETE" }),
    enviarFeedback: (ferramenta: "chat" | "tutor_ia" | "simulado", estrelas: number | null, texto: string | null) =>
        pedir<{ ok: boolean }>("/feedback", { method: "POST", body: JSON.stringify({ ferramenta, estrelas, texto }) }),
    betaStatus: () => pedir<{ vagas_total: number; vagas_usadas: number; vagas_restantes: number }>("/auth/beta"),
    adminCreditar: (email: string, creditos: number, motivo: string) =>
        pedir<{ ok: boolean; saldo: number }>("/admin/creditar", { method: "POST", body: JSON.stringify({ email, creditos, motivo }) }),
    pagPlataformas: () => pedir<PlataformaPagamento[]>("/pagamentos"),
    criarPagPlataforma: (d: PlataformaPagamentoInput) => pedir<PlataformaPagamento>("/pagamentos", { method: "POST", body: JSON.stringify(d) }),
    editarPagPlataforma: (id: number, d: PlataformaPagamentoInput) => pedir<PlataformaPagamento>(`/pagamentos/${id}`, { method: "PATCH", body: JSON.stringify(d) }),
    apagarPagPlataforma: (id: number) => pedir<void>(`/pagamentos/${id}`, { method: "DELETE" }),
    ativarPagPlataforma: (id: number) => pedir<PlataformaPagamento[]>(`/pagamentos/${id}/ativar`, { method: "POST" }),
    revelarPagToken: (id: number) => pedir<{ access_token: string }>(`/pagamentos/${id}/revelar`),
    testarPagPlataforma: (id: number) => pedir<{ ok: boolean | null; mensagem: string }>(`/pagamentos/${id}/testar`, { method: "POST" }),
    pagConfig: () => pedir<ConfigPagamento>("/pagamentos/config"),
    salvarPagConfig: (d: ConfigPagamento) => pedir<ConfigPagamento>("/pagamentos/config", { method: "PUT", body: JSON.stringify(d) }),
    adminYoutube: () => pedir<YoutubeStatus>("/admin/youtube"),
    salvarYoutube: (chave: string) => pedir<YoutubeStatus>("/admin/youtube", { method: "PUT", body: JSON.stringify({ chave }) }),
    apagarYoutube: () => pedir<void>("/admin/youtube", { method: "DELETE" }),
    testarYoutube: () => pedir<{ ok: boolean; mensagem: string }>("/admin/youtube/testar", { method: "POST" }),
    chatVideos: (termo: string) => pedir<{ resultados: VideoResultado[] }>("/chat/videos", { method: "POST", body: JSON.stringify({ termo }) }),
    tutorDocumentos: () => pedir<DocTutor[]>("/tutor/documentos"),
    tutorEnviarArquivos: async (arquivos: File[], conversationId: number | null) => {
        const fd = new FormData()
        arquivos.forEach((a) => fd.append("arquivos", a))
        if (conversationId != null) fd.append("conversation_id", String(conversationId))
        const res = await fetch("/api/v1/tutor/documentos/arquivo", { method: "POST", credentials: "include", body: fd })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao enviar o(s) arquivo(s)") }
        return res.json() as Promise<{ id: number; titulo: string; descricao: string; chunk_count: number }[]>
    },
    tutorEnviarVideo: (url: string, conversationId: number | null) =>
        pedir<{ id: number; titulo: string; descricao: string; chunk_count: number }>(
            "/tutor/documentos/video", { method: "POST", body: JSON.stringify({ url, conversation_id: conversationId }) },
        ),
    tutorVideoInfo: (url: string) =>
        pedir<{ titulo: string | null; duracao_s: number | null }>(`/tutor/video-info?url=${encodeURIComponent(url)}`),
    tutorEnviarVideoAudio: async (blob: Blob, url: string, conversationId: number | null) => {
        const fd = new FormData()
        fd.append("file", blob, "video.webm")
        fd.append("url", url)
        if (conversationId != null) fd.append("conversation_id", String(conversationId))
        const res = await fetch("/api/v1/tutor/documentos/video-audio", { method: "POST", credentials: "include", body: fd })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao transcrever o áudio") }
        return res.json() as Promise<{ id: number; titulo: string; descricao: string; chunk_count: number }>
    },
    adminSaude: () => pedir<SaudeVPS>("/admin/saude"),
    adminBloquearCadastros: (bloqueado: boolean) =>
        pedir<{ cadastros_bloqueados: boolean }>("/admin/cadastros", { method: "POST", body: JSON.stringify({ bloqueado }) }),
    estatEstrutura: (examId: number) => pedir<EstruturaEstat>(`/estatisticas/enfase/estrutura?exam_id=${examId}`),
    estatExtrairTemas: (examId: number) => pedir<{ criados: number; disciplinas: string[] }>(`/estatisticas/enfase/temas/extrair?exam_id=${examId}`, { method: "POST" }),
    estatAddTema: (examId: number, disciplina: string, nome: string) => pedir<{ id: number; disciplina: string; nome: string }>("/estatisticas/enfase/temas", { method: "POST", body: JSON.stringify({ exam_id: examId, disciplina, nome }) }),
    estatDelTema: (id: number) => pedir<void>(`/estatisticas/enfase/temas/${id}`, { method: "DELETE" }),
    upsertEstatTema: (d: StatEnfaseInput) => pedir<StatEnfase>("/estatisticas/enfase/por-tema", { method: "PUT", body: JSON.stringify(d) }),
    apagarEstat: (id: number) => pedir<void>(`/estatisticas/enfase/${id}`, { method: "DELETE" }),
    iniciarSimulado: (examId: number, duration_seconds: number) =>
        pedir<SimRun>(`/simulado/iniciar`, { method: "POST", body: JSON.stringify({ exam_id: examId, duration_seconds }) }),
    entregarSimulado: (runId: number, respostas: Record<number, string>, tempos?: Record<number, number>) =>
        pedir<SimResultado>(`/simulado/${runId}/entregar`, { method: "POST", body: JSON.stringify({ respostas, tempos }) }),

    ragDocs: () => pedir<RagDoc[]>("/rag/documentos"),
    ragImportar: async (fd: FormData) => {
        const res = await fetch(`/api/v1/rag/documentos/importar`, { method: "POST", credentials: "include", body: fd })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao importar") }
        return res.json() as Promise<RagDoc>
    },
    ragReindexar: (id: number) => pedir<RagDoc>(`/rag/documentos/${id}/reindexar`, { method: "POST" }),
    ragClassificar: (id: number, uso_chat: boolean, uso_tutor: boolean, uso_simulado: boolean) =>
        pedir<RagDoc>(`/rag/documentos/${id}`, { method: "PATCH", body: JSON.stringify({ uso_chat, uso_tutor, uso_simulado }) }),
    ragEditarMeta: (id: number, titulo: string, descricao: string) =>
        pedir<RagDoc>(`/rag/documentos/${id}`, { method: "PATCH", body: JSON.stringify({ titulo, descricao }) }),
    ragApagar: (id: number) => pedir<void>(`/rag/documentos/${id}`, { method: "DELETE" }),
    ragBuscar: (consulta: string) => pedir<{ resultados: { titulo: string; chunk: number; conteudo: string }[] }>("/rag/buscar", { method: "POST", body: JSON.stringify({ consulta }) }),
    ragPerguntar: (pergunta: string) => pedir<{ resposta: string; trechos: { titulo: string; chunk: number; conteudo: string }[] }>("/rag/perguntar", { method: "POST", body: JSON.stringify({ pergunta }) }),
    prompts: () => pedir<PromptItem[]>("/prompts"),
    editarPrompt: (chave: string, texto: string) =>
        pedir<PromptItem>(`/prompts/${encodeURIComponent(chave)}`, { method: "PUT", body: JSON.stringify({ texto }) }),
    catalogoPlataformas: () => pedir<{ nome: string; endpoint: string }[]>("/ai/catalogo/plataformas"),
    catalogoModelos: (plataforma: string, categoria: string) =>
        pedir<{ id: number; model_id: string; rotulo: string; dim: number | null; padrao: boolean }[]>(`/ai/catalogo/modelos?plataforma=${encodeURIComponent(plataforma)}&categoria=${categoria}`),
    sincronizarCatalogo: (platformId: number) => pedir<{ plataforma: string; modelos_no_provedor: number; novos_no_catalogo: number }>(`/ai/catalogo/sincronizar/${platformId}`, { method: "POST" }),
    conexoesIA: () => pedir<ConexaoIA[]>("/ai/conexoes"),
    usoConexoes: () => pedir<UsoResumo>("/ai/conexoes/uso"),
    criarConexao: (d: ConexaoInput) => pedir<ConexaoIA>("/ai/conexoes", { method: "POST", body: JSON.stringify(d) }),
    editarConexao: (id: number, d: ConexaoInput) => pedir<ConexaoIA>(`/ai/conexoes/${id}`, { method: "PATCH", body: JSON.stringify(d) }),
    apagarConexao: (id: number) => pedir<void>(`/ai/conexoes/${id}`, { method: "DELETE" }),
    ativarConexao: (id: number) => pedir<ConexaoIA[]>(`/ai/conexoes/${id}/ativar`, { method: "POST" }),
    fallbackConexao: (id: number, ordem: number | null) => pedir<ConexaoIA[]>(`/ai/conexoes/${id}/fallback`, { method: "POST", body: JSON.stringify({ ordem }) }),
    plataformas: () => pedir<Plataforma[]>("/ai/plataformas"),
    criarPlataforma: (d: PlataformaInput) => pedir<Plataforma>("/ai/plataformas", { method: "POST", body: JSON.stringify(d) }),
    editarPlataforma: (id: number, d: PlataformaInput) => pedir<Plataforma>(`/ai/plataformas/${id}`, { method: "PATCH", body: JSON.stringify(d) }),
    apagarPlataforma: (id: number) => pedir<void>(`/ai/plataformas/${id}`, { method: "DELETE" }),
    revelarChave: (id: number) => pedir<{ api_key: string }>(`/ai/plataformas/${id}/revelar`),
    testarConexao: (id: number) => pedir<{ ok: boolean | null; resposta?: string; dimensao?: number }>(`/ai/conexoes/${id}/testar`, { method: "POST" }),
    me: () => pedir<Usuario>("/auth/me"),
    cadastrar: (d: DadosCadastro) => pedir<{ mensagem: string }>("/auth/cadastro", { method: "POST", body: JSON.stringify(d) }),
    solicitarCodigo: (email: string) =>
        pedir<{ mensagem: string }>("/auth/login/solicitar", { method: "POST", body: JSON.stringify({ email }) }),
    verificarCodigo: (email: string, codigo: string) =>
        pedir<Usuario>("/auth/login/verificar", { method: "POST", body: JSON.stringify({ email, codigo }) }),
    entrarComSenha: (email: string, senha: string) =>
        pedir<Usuario>("/auth/login/senha", { method: "POST", body: JSON.stringify({ email, senha }) }),
    cadastrarSenha: (senha: string) => pedir<Usuario>("/auth/senha/cadastrar", { method: "POST", body: JSON.stringify({ senha }) }),
    alternarSenha: (habilitada: boolean) => pedir<Usuario>("/auth/senha/alternar", { method: "POST", body: JSON.stringify({ habilitada }) }),
    dispensarPromptSenha: () => pedir<Usuario>("/auth/senha/dispensar-prompt", { method: "POST" }),
    logout: () => pedir<void>("/auth/logout", { method: "POST" }),
    health: () => pedir<Health>("/health"),
}
