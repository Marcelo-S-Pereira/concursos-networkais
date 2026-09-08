import { type ClipboardEvent, useEffect, useRef } from "react"

// Editor rico "tipo Word" leve: contentEditable + barra de ferramentas.
// Guarda o conteúdo como HTML. Usa execCommand (amplo suporte) para formatar.
// Sobrescrito/subscrito são essenciais para química/matemática de concurso.

type Cmd = { icone: string; titulo: string; cmd: string; valor?: string }

function escaparHtml(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// "Reflow": tira as quebras de linha automáticas (do PDF), junta as linhas de um
// parágrafo num parágrafo corrido e desfaz a hifenização de fim de linha. Sem
// isso, o texto colado tem quebra manual em cada linha e o justify não estica.
export function reflowarTexto(texto: string): string {
    const s = texto.replace(/([A-Za-zÀ-ÿ])-[ \t]*\r?\n[ \t]*([a-zà-ÿ])/g, "$1$2")  // "utiliza-\nção" → "utilização"
    const paragrafos = s
        .split(/\r?\n[ \t]*\r?\n+/)  // linha em branco separa parágrafos
        .map((p) => p.replace(/[ \t]*\r?\n[ \t]*/g, " ").replace(/[ \t]{2,}/g, " ").trim())  // quebra simples vira espaço
        .filter(Boolean)
    return paragrafos.map((p) => `<div>${escaparHtml(p)}</div>`).join("")
}

const COMANDOS: Cmd[] = [
    { icone: "B", titulo: "Negrito", cmd: "bold" },
    { icone: "I", titulo: "Itálico", cmd: "italic" },
    { icone: "U", titulo: "Sublinhado", cmd: "underline" },
    { icone: "x²", titulo: "Sobrescrito", cmd: "superscript" },
    { icone: "x₂", titulo: "Subscrito", cmd: "subscript" },
    { icone: "•", titulo: "Lista", cmd: "insertUnorderedList" },
    { icone: "⌫", titulo: "Limpar formatação", cmd: "removeFormat" },
]

export default function RichText({
    valor, aoMudar, minRows = 2,
}: {
    valor: string
    aoMudar: (html: string) => void
    minRows?: number
}) {
    const ref = useRef<HTMLDivElement>(null)
    const selRef = useRef<Range | null>(null)

    // injeta o valor inicial sem quebrar o cursor a cada tecla
    useEffect(() => {
        if (ref.current && ref.current.innerHTML !== valor) {
            ref.current.innerHTML = valor
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    // guarda a seleção atual — o seletor/botão da barra rouba o foco e a perderia
    function lembrarSelecao() {
        const s = window.getSelection()
        if (s && s.rangeCount && ref.current && ref.current.contains(s.anchorNode)) {
            selRef.current = s.getRangeAt(0).cloneRange()
        }
    }

    function aplicar(cmd: string, valorCmd?: string) {
        ref.current?.focus()
        const s = window.getSelection()
        if (selRef.current && s) { s.removeAllRanges(); s.addRange(selRef.current) }  // restaura a seleção
        document.execCommand(cmd, false, valorCmd)
        aoMudar(ref.current?.innerHTML ?? "")
        lembrarSelecao()
    }

    // cola: já entra com reflow (tira as quebras de linha do PDF)
    function aoColar(e: ClipboardEvent<HTMLDivElement>) {
        const txt = e.clipboardData.getData("text/plain")
        if (!txt) return
        e.preventDefault()
        document.execCommand("insertHTML", false, reflowarTexto(txt))
        aoMudar(ref.current?.innerHTML ?? "")
    }

    // Alinhamento NÃO usa execCommand (falha quando o texto é um bloco só/linhas soltas).
    // JUSTIFICAR, como no Word, também JUNTA as linhas (tira as quebras do PDF) antes de
    // justificar — senão cada linha tem quebra manual e o justify não estica. Persiste no
    // HTML e o DOMPurify preserva o text-align.
    function alinhar(align: "left" | "center" | "right" | "justify") {
        const el = ref.current
        if (!el) return
        if (align === "justify") {
            const texto = el.innerText || el.textContent || ""  // innerText tem as quebras; textContent é fallback
            el.innerHTML = `<div style="text-align: justify;">${reflowarTexto(texto)}</div>`
            aoMudar(el.innerHTML)
            return
        }
        const unico = el.children.length === 1 ? (el.firstElementChild as HTMLElement | null) : null
        if (unico && unico.tagName === "DIV" && unico.style.textAlign) {
            unico.style.textAlign = align
        } else {
            const wrap = document.createElement("div")
            wrap.style.textAlign = align
            while (el.firstChild) wrap.appendChild(el.firstChild)
            el.appendChild(wrap)
        }
        aoMudar(el.innerHTML)
    }

    return (
        <div className="rich">
            <div className="rich-barra">
                {COMANDOS.map((c) => (
                    <button key={c.cmd} type="button" title={c.titulo} onMouseDown={(e) => e.preventDefault()} onClick={() => aplicar(c.cmd)}>
                        {c.icone}
                    </button>
                ))}
                <select
                    title="Tamanho da fonte"
                    onMouseDown={(e) => e.stopPropagation()}
                    onChange={(e) => { aplicar("fontSize", e.target.value); e.target.selectedIndex = 0 }}
                    defaultValue=""
                >
                    <option value="" disabled>fonte</option>
                    <option value="2">pequena</option>
                    <option value="3">normal</option>
                    <option value="5">grande</option>
                    <option value="6">título</option>
                </select>
                <select
                    title="Alinhamento do texto (aplica no texto todo)"
                    onMouseDown={(e) => e.stopPropagation()}
                    onChange={(e) => { alinhar(e.target.value as "left" | "center" | "right" | "justify"); e.target.selectedIndex = 0 }}
                    defaultValue=""
                >
                    <option value="" disabled>alinhar</option>
                    <option value="left">à esquerda</option>
                    <option value="center">centralizar</option>
                    <option value="right">à direita</option>
                    <option value="justify">justificar</option>
                </select>
            </div>
            <div
                ref={ref}
                className="rich-area"
                contentEditable
                suppressContentEditableWarning
                style={{ minHeight: `${minRows * 1.6}em` }}
                onInput={() => aoMudar(ref.current?.innerHTML ?? "")}
                onMouseUp={lembrarSelecao}
                onKeyUp={lembrarSelecao}
                onPaste={aoColar}
            />
        </div>
    )
}
