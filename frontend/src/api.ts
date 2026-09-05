export type Health = { status: "ok" | "degraded"; database?: boolean; pgvector?: string | null }

export type Usuario = {
    id: number
    nome: string
    email: string
    cpf: string
    telefone: string
    role: string
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
    enunciado_col2: string; gabarito: string | null; tem_figura: boolean; modo_exibicao: string; confianca: number; aviso: string
    revisada: boolean; descartada: boolean; alternativas: Choice[]
}
export type Exame = { id: number; banca: string; orgao: string; cargo: string; ano: number | null; total: number; revisar: number }
export type ResultadoSimulado = { total: number; respondidas: number; acertos: number; percentual_bruto: number; resultado: Record<number, boolean>; por_enfase: EnfaseDesempenho[] }
export type Classificacao = {
    nota_ponderada: number; nota_corte: number | null; vagas: number | null
    eliminado: boolean; motivos: string[]
    por_disciplina: Record<string, { acertos: number; total: number; peso: number }>
    por_fase: { fase: string; pontos: number; total: number; percentual: number; minimo_pct: number | null }[]
}
export type RegrasEditalT = { pesos: Record<string, number>; minimos: Record<string, number>; nota_corte: number | null; vagas: number | null; fases?: Record<string, string>; minimo_pct_fase?: Record<string, number>; materias_sem_zero?: string[] }
export type SimRun = { simulation_id: number; started_at: string; deadline_at: string; duration_seconds: number; question_count: number; status: string }
export type EnfaseDesempenho = { enfase: string; acertos: number; total: number; percentual: number; mastery: string; amostra: number; historico_pct?: number | null; delta?: number | null; delta_rotulo?: string; amostra_historico?: number | null }
export type StatEnfase = { id: number; banca: string; orgao: string; cargo: string; ano: number | null; enfase: string; amostra: number | null; acerto_pct: number | null; fonte: string; tipo_fonte: string; status: string }
export type StatEnfaseInput = Omit<StatEnfase, "id">
export type SimResultado = { acertos: number; total: number; respondidas: number; em_branco: number; percentual_bruto: number; encerrado_no_prazo: boolean; resultado: Record<number, boolean>; por_enfase: EnfaseDesempenho[]; classificacao?: Classificacao | null }
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
export type PatchQuestao = Partial<{
    enunciado: string; gabarito: string; disciplina: string
    alternativas: Record<string, string>; revisada: boolean; descartada: boolean; modo_exibicao: string; enunciado_col2: string
}>

export const api = {
    exames: () => pedir<Exame[]>("/exames"),
    importarCaderno: async (form: FormData) => {
        const res = await fetch(`/api/v1/exames/importar`, { method: "POST", credentials: "include", body: form })
        if (!res.ok) { const c = await res.json().catch(() => null); throw new Error(c?.detail ?? "Falha ao importar") }
        return res.json() as Promise<Exame>
    },
    obterRegras: (examId: number) => pedir<RegrasEditalT | null>(`/exames/${examId}/regras`),
    gravarRegras: (examId: number, r: RegrasEditalT) => pedir<RegrasEditalT>(`/exames/${examId}/regras`, { method: "PUT", body: JSON.stringify(r) }),
    apagarCaderno: (examId: number) => pedir<void>(`/exames/${examId}`, { method: "DELETE" }),
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
    revisaoDevidas: () => pedir<Questao[]>("/revisao"),
    responderRevisao: (qid: number, letra: string) => pedir<{ acertou: boolean }>(`/revisao/${qid}/responder`, { method: "POST", body: JSON.stringify({ letra }) }),
    gerarGemeas: (qid: number) => pedir<GemeaT[]>(`/exames/questoes/${qid}/gemeas`, { method: "POST" }),
    responderGemea: (twinId: number, letra: string) => pedir<{ acertou: boolean; gabarito: string }>(`/exames/gemeas/${twinId}/responder`, { method: "POST", body: JSON.stringify({ letra }) }),
    explicarIA: (qid: number, student_answer: string | null) =>
        pedir<Explicacao>(`/exames/questoes/${qid}/explicar`, { method: "POST", body: JSON.stringify({ student_answer }) }),
    transcreverIA: (qid: number) => pedir<{ enunciado: string; alternativas: Record<string, string> }>(`/exames/questoes/${qid}/transcrever`, { method: "POST" }),
    restaurarFigura: (qid: number) => pedir<{ ok: boolean }>(`/exames/questoes/${qid}/figura/restaurar`, { method: "POST" }),
    corrigir: (examId: number, respostas: Record<number, string>) =>
        pedir<ResultadoSimulado>(`/exames/${examId}/corrigir`, { method: "POST", body: JSON.stringify({ respostas }) }),
    estatEnfase: () => pedir<StatEnfase[]>("/estatisticas/enfase"),
    criarEstat: (d: StatEnfaseInput) => pedir<StatEnfase>("/estatisticas/enfase", { method: "POST", body: JSON.stringify(d) }),
    editarEstat: (id: number, d: StatEnfaseInput) => pedir<StatEnfase>(`/estatisticas/enfase/${id}`, { method: "PATCH", body: JSON.stringify(d) }),
    apagarEstat: (id: number) => pedir<void>(`/estatisticas/enfase/${id}`, { method: "DELETE" }),
    iniciarSimulado: (examId: number, duration_seconds: number) =>
        pedir<SimRun>(`/simulado/iniciar`, { method: "POST", body: JSON.stringify({ exam_id: examId, duration_seconds }) }),
    entregarSimulado: (runId: number, respostas: Record<number, string>) =>
        pedir<SimResultado>(`/simulado/${runId}/entregar`, { method: "POST", body: JSON.stringify({ respostas }) }),

    conexoesIA: () => pedir<ConexaoIA[]>("/ai/conexoes"),
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
    logout: () => pedir<void>("/auth/logout", { method: "POST" }),
    health: () => pedir<Health>("/health"),
}
