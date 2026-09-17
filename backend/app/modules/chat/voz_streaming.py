"""[135]: voz em tempo real (Tutor IA, desktop) — streaming de verdade em
LLM, TTS e STT, os 3 confirmados com chamada real à Together antes de
escrever esta linha (não suposição):

- LLM `/chat/completions` com `stream: true` entrega tokens incrementais
  (SSE), formato OpenAI padrão.
- TTS `/audio/speech` com `stream: true` entrega áudio em PCM16 mono 24kHz
  (NÃO o mp3 pedido em `response_format` — a API ignora isso em streaming),
  em eventos SSE `conversation.item.audio_output.delta` com o áudio em
  base64 no campo `delta`.
- STT não streama pelo REST `/audio/transcriptions` (testado, só devolve
  `[DONE]`) — precisa do WebSocket Realtime
  (`wss://.../v1/realtime?model=...&input_audio_format=pcm_s16le_16000`,
  mesmo protocolo da Realtime API da OpenAI), que devolve
  `conversation.item.input_audio_transcription.delta/.completed`. Testado
  real com `nvidia/parakeet-tdt-0.6b-v3` (streaming, português correto sem
  configuração) e `openai/whisper-large-v3` (streaming, mas veio em inglês
  sem configurar idioma).

Tudo aqui é ADITIVO — não toca em `cliente.chamar_chat/falar/transcrever`
nem em `servico.conversar/falar_texto/transcrever_audio` nem em
`chat.responder/responder_e_falar`, que o mobile e o resto do app usam hoje
sem streaming. Zero risco pro que já funciona.
"""

import base64
import json
from collections.abc import AsyncIterator

import httpx
import websockets

from app.core.crypto import decifrar_ia
from app.db.models import AiConnection

TIMEOUT_S = 60.0


async def chamar_chat_streaming(
    conn: AiConnection, mensagens: list[dict], *, max_tokens: int | None = None,
) -> AsyncIterator[str]:
    """Gera o texto da resposta em pedaços (tokens/palavras), conforme o LLM
    escreve — não espera a resposta inteira terminar."""
    if conn.endpoint.startswith("local://"):
        raise RuntimeError(f'"{conn.nome}" é um modelo local — sem streaming ligado ainda.')
    chave = decifrar_ia(conn.api_key_cifrada)
    corpo = {
        "model": conn.modelo, "messages": mensagens, "stream": True,
        "max_tokens": max_tokens or conn.max_tokens, "temperature": conn.temperatura,
    }
    url = conn.endpoint.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client, client.stream(
        "POST", url, headers={"Authorization": f"Bearer {chave}"}, json=corpo,
    ) as r:
        if r.status_code != 200:
            corpo_erro = (await r.aread())[:300]
            raise RuntimeError(f'"{conn.nome}" (streaming) respondeu {r.status_code}: {corpo_erro}')
        async for linha in r.aiter_lines():
            if not linha or not linha.startswith("data:"):
                continue
            dado = linha[len("data:"):].strip()
            if dado == "[DONE]":
                break
            try:
                obj = json.loads(dado)
            except json.JSONDecodeError:
                continue
            delta = (obj.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
            if delta:
                yield delta


async def falar_streaming(conn: AiConnection, texto: str, voz: str) -> AsyncIterator[bytes]:
    """Gera os bytes de áudio (PCM16 mono 24kHz cru — confirmado real) em
    pedaços, conforme o Kokoro sintetiza — não espera a fala inteira ficar
    pronta pra começar a entregar."""
    if conn.endpoint.startswith("local://"):
        raise RuntimeError(f'"{conn.nome}" é um modelo local — sem streaming ligado ainda.')
    chave = decifrar_ia(conn.api_key_cifrada)
    corpo = {"model": conn.modelo, "input": texto, "voice": voz, "response_format": "mp3", "stream": True}
    url = conn.endpoint.rstrip("/") + "/audio/speech"
    # [137]: achado real em produção — os deltas de áudio da Together não
    # vêm alinhados em número par de bytes (PCM16 = 2 bytes/amostra); o
    # front quebrava com "byte length of Int16Array should be a multiple of
    # 2" na hora de tocar. Corrigido aqui, na origem: guarda 1 byte
    # sobressalente entre pedaços e só solta quando fecha um par — assim
    # NENHUM consumidor (hoje só o front, futuros também) precisa se
    # preocupar com alinhamento.
    sobra = b""
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as client, client.stream(
        "POST", url, headers={"Authorization": f"Bearer {chave}"}, json=corpo,
    ) as r:
        if r.status_code != 200:
            corpo_erro = (await r.aread())[:300]
            raise RuntimeError(f'"{conn.nome}" (TTS streaming) respondeu {r.status_code}: {corpo_erro}')
        async for linha in r.aiter_lines():
            if not linha or not linha.startswith("data:"):
                continue
            dado = linha[len("data:"):].strip()
            if dado == "[DONE]":
                break
            try:
                obj = json.loads(dado)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "conversation.item.audio_output.delta" and "delta" in obj:
                pedaco = sobra + base64.b64decode(obj["delta"])
                if len(pedaco) % 2 != 0:
                    sobra = pedaco[-1:]
                    pedaco = pedaco[:-1]
                else:
                    sobra = b""
                if pedaco:
                    yield pedaco
    # sobra de 1 byte no fim (amostra cortada ao meio) — descarta; é
    # inaudível e mais seguro que inventar um byte pra completar.


class SessaoSTT:
    """Uma sessão de transcrição em tempo real contra o WebSocket Realtime da
    Together — um objeto por sessão de voz do Tutor IA. `input_audio_format`
    fixo em PCM16 16kHz mono porque é o que o endpoint exige (documentado, e
    confirmado no teste real)."""

    def __init__(self, conn: AiConnection, idioma: str = "pt"):
        if conn.endpoint.startswith("local://"):
            raise RuntimeError(f'"{conn.nome}" é um modelo local — sem streaming ligado ainda.')
        self._chave = decifrar_ia(conn.api_key_cifrada)
        # `conn.endpoint` já termina em "/v1" (ex: https://api.together.xyz/v1)
        # — só troca o esquema e acrescenta "/realtime", sem duplicar "/v1".
        base = conn.endpoint.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")
        # [135]: `language` vai na URL — testado real que `session.update`
        # depois de conectar é ignorado em silêncio (sem erro, sem efeito;
        # o Whisper seguia respondendo em inglês). Já na URL funciona.
        self._url = f"{base}/realtime?model={conn.modelo}&input_audio_format=pcm_s16le_16000&language={idioma}"
        self._ws: websockets.ClientConnection | None = None

    async def conectar(self) -> None:
        self._ws = await websockets.connect(
            self._url,
            additional_headers={"Authorization": f"Bearer {self._chave}", "OpenAI-Beta": "realtime=v1"},
        )

    async def mandar_audio(self, pcm16_16k_mono: bytes) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": base64.b64encode(pcm16_16k_mono).decode(),
        }))

    async def commit(self) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def eventos(self) -> AsyncIterator[dict]:
        assert self._ws is not None
        async for msg in self._ws:
            yield json.loads(msg)

    async def fechar(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
