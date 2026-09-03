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
        headers: { "Content-Type": "application/json" },
        ...init,
    })
    if (!res.ok) {
        const corpo = await res.json().catch(() => null)
        const detalhe = corpo?.detail
        // O FastAPI devolve lista de erros quando a validação do schema falha.
        const mensagem = Array.isArray(detalhe) ? (detalhe[0]?.msg ?? "Dados inválidos.") : (detalhe ?? `Erro ${res.status}`)
        throw new ApiError(res.status, mensagem)
    }
    return res.status === 204 ? (undefined as T) : res.json()
}

export type DadosCadastro = { nome: string; email: string; cpf: string; telefone: string }

export type Choice = { letra: string; texto: string }
export type Questao = {
    id: number; numero: number; pagina: number; disciplina: string; enunciado: string
    gabarito: string | null; tem_figura: boolean; confianca: number; aviso: string
    revisada: boolean; descartada: boolean; alternativas: Choice[]
}
export type Exame = { id: number; banca: string; orgao: string; cargo: string; ano: number | null; total: number; revisar: number }
export type ResultadoSimulado = { total: number; respondidas: number; acertos: number; resultado: Record<number, boolean> }
export type ConexaoIA = {
    id: number; nome: string; endpoint: string; modelo: string; categoria: string
    tipo_deploy: string; ativa: boolean; ordem_fallback: number | null
    max_tokens: number; temperatura: number
    context_window_tokens: number | null; rate_limit_rpm: number | null
    preco_entrada_por_milhao: number | null; preco_saida_por_milhao: number | null
    moeda: string; chave_mascarada: string
}
export type ConexaoInput = {
    nome: string; endpoint: string; api_key: string; modelo: string; categoria: string
    tipo_deploy?: string; max_tokens?: number; temperatura?: number
    context_window_tokens?: number | null; rate_limit_rpm?: number | null
    preco_entrada_por_milhao?: number | null; preco_saida_por_milhao?: number | null
    moeda?: string
}
export type PatchQuestao = Partial<{
    enunciado: string; gabarito: string; disciplina: string
    alternativas: Record<string, string>; revisada: boolean; descartada: boolean
}>

export const api = {
    exames: () => pedir<Exame[]>("/exames"),
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
    transcreverIA: (qid: number) => pedir<{ enunciado: string; alternativas: Record<string, string> }>(`/exames/questoes/${qid}/transcrever`, { method: "POST" }),
    restaurarFigura: (qid: number) => pedir<{ ok: boolean }>(`/exames/questoes/${qid}/figura/restaurar`, { method: "POST" }),
    corrigir: (examId: number, respostas: Record<number, string>) =>
        pedir<ResultadoSimulado>(`/exames/${examId}/corrigir`, { method: "POST", body: JSON.stringify({ respostas }) }),

    conexoesIA: () => pedir<ConexaoIA[]>("/ai/conexoes"),
    criarConexao: (d: ConexaoInput) => pedir<ConexaoIA>("/ai/conexoes", { method: "POST", body: JSON.stringify(d) }),
    editarConexao: (id: number, d: ConexaoInput) => pedir<ConexaoIA>(`/ai/conexoes/${id}`, { method: "PATCH", body: JSON.stringify(d) }),
    apagarConexao: (id: number) => pedir<void>(`/ai/conexoes/${id}`, { method: "DELETE" }),
    ativarConexao: (id: number) => pedir<ConexaoIA[]>(`/ai/conexoes/${id}/ativar`, { method: "POST" }),
    fallbackConexao: (id: number, ordem: number | null) => pedir<ConexaoIA[]>(`/ai/conexoes/${id}/fallback`, { method: "POST", body: JSON.stringify({ ordem }) }),
    revelarChave: (id: number) => pedir<{ api_key: string }>(`/ai/conexoes/${id}/revelar`),
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
