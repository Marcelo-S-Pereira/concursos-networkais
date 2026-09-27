"""[171]: embeddings que rodam na própria ambiente de execucao (ONNX int8, CPU), sem API.

Existe porque a Together deixou de ter qualquer modelo de embeddings serverless.
Os pesos ficam em `backend/modelos_locais/` (fora do git). Pooling por família:
e5 usa média com máscara, o resto (bge-m3) usa o token CLS; sempre normalizado,
então distância de cosseno no pgvector funciona direto."""

import os
import threading
from pathlib import Path

import numpy as np

PASTA_MODELOS = Path(__file__).resolve().parents[3] / "modelos_locais"
ARQUIVO_ONNX = "onnx/model_quantized.onnx"
ARQUIVO_TOKENIZER = "tokenizer.json"
LOTE = 8
MAX_TOKENS = 512


class ModeloLocalIndisponivel(Exception):
    pass


def _pasta(repo: str) -> Path:
    return PASTA_MODELOS / repo.replace("/", "__")


def disponivel(repo: str) -> bool:
    pasta = _pasta(repo)
    return (pasta / ARQUIVO_ONNX).is_file() and (pasta / ARQUIVO_TOKENIZER).is_file()


def baixar(repo: str) -> Path:
    from huggingface_hub import hf_hub_download

    pasta = _pasta(repo)
    for arquivo in (ARQUIVO_ONNX, ARQUIVO_TOKENIZER):
        hf_hub_download(repo, arquivo, local_dir=pasta)
    return pasta


def _pooling(repo: str) -> str:
    return "media" if "e5" in repo.lower() else "cls"


class _Motor:
    def __init__(self, repo: str):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        pasta = _pasta(repo)
        self.pooling = _pooling(repo)
        self.tok = Tokenizer.from_file(str(pasta / ARQUIVO_TOKENIZER))
        self.tok.enable_truncation(max_length=MAX_TOKENS)
        self.tok.enable_padding()
        opcoes = ort.SessionOptions()
        opcoes.intra_op_num_threads = int(os.environ.get("EMBEDDINGS_THREADS", "2"))
        opcoes.log_severity_level = 3
        self.sess = ort.InferenceSession(str(pasta / ARQUIVO_ONNX), opcoes, providers=["CPUExecutionProvider"])
        self.entradas = {i.name for i in self.sess.get_inputs()}

    def _lote(self, frases: list[str]) -> tuple[np.ndarray, int]:
        enc = self.tok.encode_batch(frases)
        ids = np.array([e.ids for e in enc], dtype=np.int64)
        mascara = np.array([e.attention_mask for e in enc], dtype=np.int64)
        entrada = {"input_ids": ids, "attention_mask": mascara}
        if "token_type_ids" in self.entradas:
            entrada["token_type_ids"] = np.zeros_like(ids)
        oculto = self.sess.run(None, entrada)[0]
        if self.pooling == "media":
            m = mascara[..., None].astype(np.float32)
            vetor = (oculto * m).sum(1) / m.sum(1)
        else:
            vetor = oculto[:, 0]
        return vetor / np.linalg.norm(vetor, axis=1, keepdims=True), int(mascara.sum())

    def embed(self, textos: list[str]) -> tuple[list[list[float]], int]:
        # ordena por tamanho pra reduzir preenchimento; devolve na ordem original
        ordem = sorted(range(len(textos)), key=lambda i: len(textos[i]))
        saida: list[list[float]] = [[] for _ in textos]
        tokens = 0
        for ini in range(0, len(ordem), LOTE):
            idx = ordem[ini : ini + LOTE]
            vetores, n = self._lote([textos[i] for i in idx])
            tokens += n
            for k, i in enumerate(idx):
                saida[i] = vetores[k].tolist()
        return saida, tokens


_motores: dict[str, _Motor] = {}
_trava = threading.Lock()


def _motor(repo: str) -> _Motor:
    with _trava:
        if repo not in _motores:
            if not disponivel(repo):
                raise ModeloLocalIndisponivel(
                    f'O modelo local "{repo}" não está na ambiente de execucao. Baixe com: '
                    f"python scripts_baixar_modelo_local.py {repo}"
                )
            _motores[repo] = _Motor(repo)
        return _motores[repo]


def carregar(repo: str) -> None:
    """Carrega o modelo agora (e não na primeira busca)."""
    _motor(repo)


def embed(repo: str, textos: list[str]) -> tuple[list[list[float]], int]:
    """Devolve (vetores na ordem de `textos`, total de tokens processados)."""
    return _motor(repo).embed(textos)
