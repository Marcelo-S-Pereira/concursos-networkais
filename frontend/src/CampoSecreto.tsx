import { useState } from "react"

/**
 * Campo de senha/chave com olho de ver/esconder.
 *
 * Regra do projeto: TODO campo de segredo (chave de API, senha, token) usa este
 * componente — assim nenhum nasce sem o olho por esquecimento.
 *
 * `aoRevelar` é opcional e serve para o caso de edição, em que o campo vem vazio
 * de propósito (em branco = mantém o segredo atual): ao clicar no olho com o
 * campo vazio, busca o valor real no backend e o mostra em claro. Sem ele, o
 * olho apenas alterna entre `password` e `text` no que foi digitado.
 */
export default function CampoSecreto({
    valor, aoMudar, placeholder, aoRevelar, autoComplete = "off",
}: {
    valor: string
    aoMudar: (v: string) => void
    placeholder?: string
    aoRevelar?: () => Promise<string>
    autoComplete?: string
}) {
    const [vendo, setVendo] = useState(false)
    const [buscando, setBuscando] = useState(false)
    const [erro, setErro] = useState<string | null>(null)

    async function alternar() {
        if (vendo) {
            setVendo(false)
            return
        }
        if (aoRevelar && !valor) {
            setBuscando(true)
            setErro(null)
            try {
                aoMudar(await aoRevelar())
            } catch (e) {
                setErro(e instanceof Error ? e.message : "Não foi possível revelar")
                return
            } finally {
                setBuscando(false)
            }
        }
        setVendo(true)
    }

    return (
        <>
            <span className="campo-chave">
                <input
                    type={vendo ? "text" : "password"}
                    value={valor}
                    onChange={(e) => aoMudar(e.target.value)}
                    placeholder={placeholder}
                    autoComplete={autoComplete}
                    spellCheck={false}
                />
                <button
                    type="button"
                    className="olho"
                    onClick={alternar}
                    disabled={buscando}
                    aria-label={vendo ? "Ocultar" : "Mostrar"}
                    title={vendo ? "Ocultar" : "Mostrar"}
                >
                    {buscando ? "…" : vendo ? "🙈" : "👁"}
                </button>
            </span>
            {erro && <span className="falha">{erro}</span>}
        </>
    )
}
