import { useEffect, useRef } from "react"

// Editor rico "tipo Word" leve: contentEditable + barra de ferramentas.
// Guarda o conteúdo como HTML. Usa execCommand (amplo suporte) para formatar.
// Sobrescrito/subscrito são essenciais para química/matemática de concurso.

type Cmd = { icone: string; titulo: string; cmd: string; valor?: string }

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

    // injeta o valor inicial sem quebrar o cursor a cada tecla
    useEffect(() => {
        if (ref.current && ref.current.innerHTML !== valor) {
            ref.current.innerHTML = valor
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    function aplicar(cmd: string, valorCmd?: string) {
        ref.current?.focus()
        document.execCommand(cmd, false, valorCmd)
        aoMudar(ref.current?.innerHTML ?? "")
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
            </div>
            <div
                ref={ref}
                className="rich-area"
                contentEditable
                suppressContentEditableWarning
                style={{ minHeight: `${minRows * 1.6}em` }}
                onInput={() => aoMudar(ref.current?.innerHTML ?? "")}
            />
        </div>
    )
}
