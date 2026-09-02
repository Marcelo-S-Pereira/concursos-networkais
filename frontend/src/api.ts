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
    id: number; numero: number; disciplina: string; enunciado: string
    gabarito: string | null; tem_figura: boolean; confianca: number; aviso: string
    revisada: boolean; descartada: boolean; alternativas: Choice[]
}
export type Exame = { id: number; banca: string; orgao: string; cargo: string; ano: number | null; total: number; revisar: number }
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
    me: () => pedir<Usuario>("/auth/me"),
    cadastrar: (d: DadosCadastro) => pedir<{ mensagem: string }>("/auth/cadastro", { method: "POST", body: JSON.stringify(d) }),
    solicitarCodigo: (email: string) =>
        pedir<{ mensagem: string }>("/auth/login/solicitar", { method: "POST", body: JSON.stringify({ email }) }),
    verificarCodigo: (email: string, codigo: string) =>
        pedir<Usuario>("/auth/login/verificar", { method: "POST", body: JSON.stringify({ email, codigo }) }),
    logout: () => pedir<void>("/auth/logout", { method: "POST" }),
    health: () => pedir<Health>("/health"),
}
