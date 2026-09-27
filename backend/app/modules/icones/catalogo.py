"""[128]: catálogo fixo dos "slots" de botão/aba que podem ganhar ícone
próprio — o cardápio do que aparece na aba Ícones. Adicionar um slot novo é
uma linha aqui, não migration nova (a escolha em si mora em `component_icons`,
uma tabela genérica chave→valor)."""

SLOTS: dict[str, dict[str, str]] = {
    # Menu lateral
    "menu.caderno": {"grupo": "Menu", "rotulo": "Caderno de questões"},
    "menu.chat": {"grupo": "Menu", "rotulo": "Chat de estudo"},
    "menu.tutor_ia": {"grupo": "Menu", "rotulo": "Tutor IA"},
    "menu.revisao": {"grupo": "Menu", "rotulo": "Revisão"},
    "menu.desempenho": {"grupo": "Menu", "rotulo": "Desempenho"},
    "menu.perfil": {"grupo": "Menu", "rotulo": "Perfil"},
    "menu.cadastro": {"grupo": "Menu", "rotulo": "Cadastro de questões"},
    "menu.ia": {"grupo": "Menu", "rotulo": "Cadastro de IA"},
    "menu.estat": {"grupo": "Menu", "rotulo": "Estatísticas"},
    "menu.rag": {"grupo": "Menu", "rotulo": "Biblioteca"},
    "menu.pagamentos": {"grupo": "Menu", "rotulo": "Pagamentos"},
    "menu.youtube": {"grupo": "Menu", "rotulo": "YouTube"},
    "menu.prompts": {"grupo": "Menu", "rotulo": "Prompts"},
    "menu.icones": {"grupo": "Menu", "rotulo": "Ícones"},
    # Chat de estudo — ações de estudo por questão
    "chat.explicar": {"grupo": "Chat de estudo", "rotulo": "Explicar"},
    "chat.aula": {"grupo": "Chat de estudo", "rotulo": "Mini-aula"},
    "chat.macete": {"grupo": "Chat de estudo", "rotulo": "Macete"},
    "chat.videos": {"grupo": "Chat de estudo", "rotulo": "Vídeos"},
    "chat.gemeas": {"grupo": "Chat de estudo", "rotulo": "Questões gêmeas"},
    "chat.passo_a_passo": {"grupo": "Chat de estudo", "rotulo": "Passo a passo narrado"},
    "chat.ler_questao": {"grupo": "Chat de estudo", "rotulo": "Ler questão"},
    # Compositor (Chat de estudo + Tutor IA)
    "compositor.anexar": {"grupo": "Compositor", "rotulo": "Anexar"},
    "compositor.acoes": {"grupo": "Compositor", "rotulo": "Abrir ferramentas"},
    "compositor.modo_voz": {"grupo": "Compositor", "rotulo": "Modo voz"},
    # [157]: desceram pra baixo do Enviar (Tutor IA) — persona/modelo/tempo
    # real saem de texto puro e ganham ícone, junto do modo_voz acima.
    "compositor.tempo_real": {"grupo": "Compositor", "rotulo": "Tempo real"},
    "compositor.persona": {"grupo": "Compositor", "rotulo": "Persona (professor/amigo)"},
    "compositor.modelo": {"grupo": "Compositor", "rotulo": "Escolher IA"},
    "compositor.enviar": {"grupo": "Compositor", "rotulo": "Enviar"},
    # [161]: chave celular/computador do cabeçalho — hoje é emoji cru (📱/🖥),
    # que rende de forma inconsistente entre SO/navegador (às vezes vira só
    # o texto alternativo). Vai pro mesmo sistema de ícone SVG do resto.
    "topo.modo_celular": {"grupo": "Cabeçalho", "rotulo": "Modo celular"},
    "topo.modo_computador": {"grupo": "Cabeçalho", "rotulo": "Modo computador/tablet"},
    # [162]: "ir ao topo" da conversa (hoje só no Tutor IA) — mesmo motivo
    # do [161], emoji cru (🔼) rendia quebrado em várias telas.
    "chat.ir_topo": {"grupo": "Tutor IA", "rotulo": "Ir para o topo"},
    "chat.ir_fim": {"grupo": "Tutor IA", "rotulo": "Ir para o final"},
    # [167]: menu de conversas virou colapsável (padrão assistentes de IA/
    # Gemini) — este é o ícone que abre/fecha o drawer, no topo da conversa
    # (Chat de estudo e Tutor IA).
    "chat.painel_toggle": {"grupo": "Chat de estudo", "rotulo": "Abrir/fechar conversas"},
}
