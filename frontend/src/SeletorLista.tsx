export type ItemSelecao = { id: number; label: string; sublabel?: string; desabilitado?: boolean; titulo?: string }

/** Lista de validação em list view: cada item numa linha própria, com
 * checkbox alinhado e rolagem quando há muitos itens — usada pra escolher
 * cadernos/fontes de conhecimento no Chat de estudo e no Tutor IA. Existia
 * antes como `.rag-uso` (pensado só pros 3 checkboxes curtos "Usar em:" da
 * Biblioteca), que colidia em especificidade CSS com `.chat-box-corpo label`
 * (mesma especificidade, ordem de declaração decidia — o resultado real era
 * o checkbox empilhado sozinho, texto solto embaixo, nada alinhado). Esta
 * lista usa um seletor descendente de 2 classes (`.lista-selecao
 * .lista-selecao-item`), que tem especificidade maior que qualquer regra de
 * `label` sozinha — não depende de ordem no arquivo pra vencer. */
export default function SeletorLista({ itens, selecionados, aoAlternar, vazio }: {
    itens: ItemSelecao[]
    selecionados: Set<number>
    aoAlternar: (id: number) => void
    vazio?: string
}) {
    if (!itens.length) return <p className="dica">{vazio ?? "Nada disponível ainda."}</p>
    return (
        <div className="lista-selecao" role="list">
            {itens.map((it) => (
                <label key={it.id} className="lista-selecao-item" title={it.titulo}>
                    <input type="checkbox" checked={selecionados.has(it.id)} disabled={it.desabilitado}
                        onChange={() => aoAlternar(it.id)} />
                    <span className="lista-selecao-texto">
                        <span>{it.label}</span>
                        {it.sublabel && <span className="dica lista-selecao-sub">{it.sublabel}</span>}
                    </span>
                </label>
            ))}
        </div>
    )
}
