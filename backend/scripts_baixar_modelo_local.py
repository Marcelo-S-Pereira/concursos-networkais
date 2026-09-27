"""[171]: baixa os pesos de um modelo de embeddings local (ONNX int8) e testa.

Uso: python scripts_baixar_modelo_local.py [repo]   (padrão: Xenova/bge-m3)
Os arquivos vão para backend/modelos_locais/, que o .gitignore bloqueia."""

import sys
import time

from app.modules.ai_registry import embeddings_locais

repo = sys.argv[1] if len(sys.argv) > 1 else "Xenova/bge-m3"

if embeddings_locais.disponivel(repo):
    print(f"{repo}: já está em {embeddings_locais.PASTA_MODELOS}")
else:
    print(f"baixando {repo} ...")
    print("pasta:", embeddings_locais.baixar(repo))

inicio = time.time()
vetores, tokens = embeddings_locais.embed(repo, ["A capital do Brasil é Brasília.", "Qual é a capital do Brasil?"])
print(f"teste ok em {time.time() - inicio:.1f}s | dimensão {len(vetores[0])} | tokens {tokens}")
soma = sum(a * b for a, b in zip(vetores[0], vetores[1], strict=True))
print(f"similaridade entre as duas frases: {soma:.3f} (frases sobre o mesmo assunto devem passar de 0,7)")
