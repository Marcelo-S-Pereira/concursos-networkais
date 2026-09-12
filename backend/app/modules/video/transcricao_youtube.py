"""Transcrição de vídeo do YouTube pra "sub-RAG" ([109]) — o link que o
usuário escolheu MANUALMENTE (não busca automática, que fica pra depois).

Pipeline real: yt-dlp baixa o áudio (ffmpeg extrai/converte), o mesmo STT
(Whisper via Together, [095]) transcreve. Nenhuma simulação.

ACHADO REAL ao construir isto (testado com um vídeo público real, não
suposto): o YouTube bloqueia extração/download vindo do IP desta ambiente de execucao —
"Sign in to confirm you're not a bot" — mesmo tentativa de só pegar
legenda, sem baixar mídia nenhuma. É o bloqueio de bot do YouTube contra IP
de datacenter, documentado e conhecido, não um bug daqui. Só se resolve com
cookies de uma conta real logada (risco de ToS/conta) ou proxy residencial
(custo/infra nova) — decisão do usuário, não resolvida por código. Por isso
este módulo é REAL (não finge sucesso) — hoje ele vai propagar o erro
verdadeiro do YouTube; se o bloqueio for resolvido depois, começa a
funcionar sem tocar neste código de novo.
"""

import re
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.modules.ai_registry import servico

DURACAO_MAXIMA_S = 20 * 60  # 20 min — teto pra não estourar custo/tempo de STT
_RE_YOUTUBE = re.compile(r"(youtube\.com/watch\?v=|youtube\.com/shorts/|youtu\.be/)")


class VideoError(Exception):
    """Erro real do vídeo (URL inválida, vídeo longo demais, ou — hoje, quase
    sempre — o bloqueio de bot do YouTube). Nunca mascarado."""


def transcrever_link(db: Session, url: str, *, user_id: int, origem: str = "tutor_video") -> dict:
    """Baixa o áudio do vídeo e transcreve. Devolve {"titulo": str, "texto": str}.

    Lança VideoError com o motivo REAL em qualquer falha — nunca finge sucesso."""
    import yt_dlp

    if not _RE_YOUTUBE.search(url):
        raise VideoError("Isso não parece um link do YouTube.")

    with tempfile.TemporaryDirectory(prefix="tutor_video_") as tmp:
        saida = str(Path(tmp) / "audio.%(ext)s")
        opts_info = {"quiet": True, "no_warnings": True, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001 — repassa o motivo real do yt-dlp, nunca inventa outro
            raise VideoError(f"Não consegui acessar o vídeo: {e}") from e

        duracao = info.get("duration") or 0
        if duracao > DURACAO_MAXIMA_S:
            raise VideoError(f"Vídeo longo demais ({duracao // 60} min) — o limite é {DURACAO_MAXIMA_S // 60} min.")
        titulo = info.get("title") or "Vídeo do YouTube"

        opts_download = {
            "format": "worstaudio/worst",
            "outtmpl": saida,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "64"}],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts_download) as ydl:
                ydl.download([url])
        except Exception as e:  # noqa: BLE001 — idem
            raise VideoError(f"Não consegui baixar o áudio do vídeo: {e}") from e

        arquivos = list(Path(tmp).glob("audio.*"))
        if not arquivos:
            raise VideoError("O download não gerou arquivo de áudio.")
        audio_bytes = arquivos[0].read_bytes()

    resultado = servico.transcrever_audio(db, audio_bytes, "video.mp3", origem=origem, user_id=user_id)
    texto = (resultado.get("texto") or "").strip()
    if not texto:
        raise VideoError("A transcrição voltou vazia.")
    return {"titulo": titulo, "texto": texto}
