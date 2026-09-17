import { useEffect, useState } from "react"
import { api, type Usuario } from "./api"
import { AcessoForm } from "./Acesso"

/** [154]/[155]: landing pública — só o que existe de verdade. As imagens e o
 * vídeo em `/landing/*` são CAPTURA REAL da tela (conta de teste descartável,
 * conversas reais com chamada de IA de verdade), não mockup nem imagem de
 * banco — apagados os dados de teste depois de capturar, as imagens ficam. */
type Recurso = { titulo: string; pontos: string[]; imagem?: string; alt?: string }

const RECURSOS_PRINCIPAIS: Recurso[] = [
    {
        titulo: "Tutor IA",
        imagem: "/landing/tutor-ia.png",
        alt: "Tela real do Tutor IA respondendo sobre firewall, com persona professor selecionada",
        pontos: [
            "Converse por texto ou por voz (aperta-e-segura, mãos-livres ou tempo real, com transcrição ao vivo) com um tutor especialista no assunto que você escolher.",
            "Ele estuda os documentos que VOCÊ indicar — edital, apostila em PDF ou Markdown, até a transcrição de um vídeo do YouTube que você escolheu — e explica com base neles, citando o material quando ajuda.",
            "Escolha o tom: professor (estruturado, técnico) ou amigo (leve, direto).",
            "Peça mini-aula, macete de memorização, ou sugestões de vídeo — sempre a partir do que você pediu, nunca empurrado sem pedir.",
        ],
    },
    {
        titulo: "Chat de estudo por questão",
        imagem: "/landing/chat-estudo.png",
        alt: "Tela real do Chat de estudo com dicas de preparação para o caderno Transpetro Dutos e Terminais",
        pontos: [
            "Ligado direto ao seu caderno de questões — escolha um ou vários cadernos, e até fontes específicas da biblioteca, pra conversa focar no que interessa.",
            "Por questão: explica por que a alternativa certa é certa (e por que as outras parecem certas e não são), dá mini-aula do conceito, ensina o macete, e gera questões gêmeas por IA pra você praticar a mesma habilidade em outro contexto.",
            "Regra de ouro: o gabarito NUNCA aparece pra você nem pro tutor antes de você responder — nem em pergunta solta, nem por acidente.",
            "Modo automático: depois de responder, o tutor oferece mini-aula → macete → gêmeas, um passo de cada vez, sempre perguntando antes — nunca decide sozinho por você.",
        ],
    },
    {
        titulo: "Simulado cronometrado",
        imagem: "/landing/simulado.png",
        alt: "Tela real de um simulado com o texto da prova Transpetro Dutos e Terminais e o cartão-resposta ao lado",
        pontos: [
            "Cartão-resposta realista — você escolhe o tamanho do campo da bolha, marca com o mouse/dedo, e marcar fora do círculo ou em dobro anula a questão, igual na prova de papel.",
            "O tempo é controlado pelo SERVIDOR, não pelo navegador — ninguém consegue burlar o relógio.",
            "Correção automática e, quando o edital tem regra de eliminação/nota de corte cadastrada, classificação estimada — sempre o backend decidindo o que é certo, nunca o LLM.",
            "Ao terminar, vê o desempenho por disciplina/ênfase na hora, e cada questão errada já entra sozinha na agenda de revisão.",
        ],
    },
]

const RECURSOS_SECUNDARIOS: Recurso[] = [
    {
        titulo: "Revisão espaçada",
        pontos: [
            "Toda questão que você errar — no simulado OU no chat de estudo — entra sozinha numa agenda de revisão com intervalos crescentes (1, 3, 7, 15, 30 dias).",
            "Você não precisa organizar nada: abre a aba Revisão e responde só o que está vencendo hoje.",
        ],
    },
    {
        titulo: "Desempenho e Mastery",
        pontos: [
            "Painel com XP, nível, sequência de dias seguidos de estudo, e o quanto você domina cada disciplina.",
            "Tudo somado entre o que você respondeu no Simulado E no Chat de estudo — nenhuma das duas fontes fica de fora da conta.",
        ],
    },
    {
        titulo: "Biblioteca de conhecimento (RAG)",
        pontos: [
            "Uma base de referência que alimenta o Tutor e o Chat — você escolhe exatamente quais documentos valem pra cada conversa.",
            "Pode contribuir com material próprio (PDF, Markdown, transcrição de vídeo) — entra na biblioteca com o seu nome.",
        ],
    },
]

function ContadorBeta() {
    const [beta, setBeta] = useState<{ vagas_total: number; vagas_usadas: number; vagas_restantes: number } | null>(null)
    useEffect(() => { api.betaStatus().then(setBeta).catch(() => setBeta(null)) }, [])
    if (!beta) return null
    if (beta.vagas_restantes <= 0) {
        return <p className="beta-contador">As {beta.vagas_total} vagas gratuitas do BETA 1 já foram todas ocupadas.</p>
    }
    return (
        <p className="beta-contador">
            <strong>{beta.vagas_restantes}</strong> de {beta.vagas_total} vagas gratuitas do BETA 1 ainda disponíveis
        </p>
    )
}

function CartaoRecurso({ r, invertido }: { r: Recurso; invertido?: boolean }) {
    return (
        <article className={`landing-showcase ${invertido ? "invertido" : ""}`}>
            {r.imagem && (
                <div className="landing-showcase-img">
                    <img src={r.imagem} alt={r.alt ?? r.titulo} loading="lazy" />
                </div>
            )}
            <div className="landing-showcase-texto">
                <h3>{r.titulo}</h3>
                <ul>
                    {r.pontos.map((p) => <li key={p}>{p}</li>)}
                </ul>
            </div>
        </article>
    )
}

export default function Landing({ aoEntrar }: { aoEntrar: (u: Usuario) => void }) {
    return (
        <main className="tela landing">
            <header className="landing-hero">
                <div className="landing-hero-texto">
                    <span className="badge-beta">BETA 1</span>
                    <h1>ConcurseiroIA</h1>
                    <p className="landing-slogan">
                        Tutor de IA, chat de estudo por questão, simulado cronometrado e revisão espaçada —
                        hoje especializado no processo seletivo Transpetro (PSP/Terra), com mais editais a caminho.
                    </p>
                    <ContadorBeta />
                    <p className="landing-beta-explica">
                        Os primeiros 30 cadastros entram grátis, com 155 créditos do mês já na conta —
                        automático, sem precisar pedir nada.
                    </p>
                </div>
                <div className="landing-hero-form">
                    <div className="cartao-acesso">
                        <AcessoForm aoEntrar={aoEntrar} />
                    </div>
                </div>
            </header>

            <section className="landing-video" aria-label="Vídeo de uso real">
                <h2>Veja funcionando de verdade</h2>
                <p className="landing-video-legenda">Gravação real da plataforma — sem edição, sem encenação.</p>
                <video controls preload="metadata" src="/landing/demo.webm">
                    Seu navegador não suporta vídeo — veja as imagens abaixo.
                </video>
            </section>

            <section className="landing-recursos" aria-label="Recursos principais">
                {RECURSOS_PRINCIPAIS.map((r, i) => <CartaoRecurso key={r.titulo} r={r} invertido={i % 2 === 1} />)}
            </section>

            <section className="landing-recursos-sec" aria-label="Outros recursos">
                <h2>E mais</h2>
                <div className="landing-grid">
                    {RECURSOS_SECUNDARIOS.map((r) => (
                        <article key={r.titulo} className="landing-card">
                            <h3>{r.titulo}</h3>
                            <ul>{r.pontos.map((p) => <li key={p}>{p}</li>)}</ul>
                        </article>
                    ))}
                </div>
            </section>

            <footer className="landing-footer">
                <p>ConcurseiroIA — parte do <a href="https://networkais.com" rel="noopener">networkais.com</a>.</p>
            </footer>
        </main>
    )
}
