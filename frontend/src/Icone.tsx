import { createContext, type ReactNode, useCallback, useContext, useEffect, useState } from "react"
import { api, type IconesEstado } from "./api"
import { BIBLIOTECA_ICONES } from "./iconesBiblioteca"

/** [128]: contexto carregado uma vez no topo do app (Painel) — todo `Icone`
 * consome daqui, sem cada componente buscar `/icones` sozinho. */
const IconesContext = createContext<{ estado: IconesEstado; refrescar: () => void }>({
    estado: {}, refrescar: () => {},
})

export function IconesProvider({ children }: { children: ReactNode }) {
    const [estado, setEstado] = useState<IconesEstado>({})
    const carregar = useCallback(() => { api.icones().then(setEstado).catch(() => setEstado({})) }, [])
    useEffect(() => { carregar() }, [carregar])
    return <IconesContext.Provider value={{ estado, refrescar: carregar }}>{children}</IconesContext.Provider>
}

export function useIcones() {
    return useContext(IconesContext)
}

/** Sem escolha feita para o slot: mostra `textoPadrao` — exatamente o
 * comportamento de hoje, ninguém vê nada diferente até o admin escolher um
 * ícone na aba Ícones. Com escolha: ícone SÓ (sem o texto ao lado), com
 * `title=textoPadrao` como tooltip — no padrão dos chats de IA conhecidos. */
export default function Icone({ slot, textoPadrao }: { slot: string; textoPadrao: string }) {
    const { estado } = useIcones()
    const escolha = estado[slot]
    if (!escolha) return <>{textoPadrao}</>
    if (escolha.tipo === "upload") {
        return <img src={`/api/v1/icones/arquivo/${encodeURIComponent(slot)}`} alt={textoPadrao} title={textoPadrao} className="icone-custom" />
    }
    const miolo = BIBLIOTECA_ICONES[escolha.valor]
    if (!miolo) return <>{textoPadrao}</>
    return (
        <span title={textoPadrao} className="icone-custom-wrap">
            <svg
                xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
                fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                className="icone-custom" dangerouslySetInnerHTML={{ __html: miolo }}
            />
        </span>
    )
}
