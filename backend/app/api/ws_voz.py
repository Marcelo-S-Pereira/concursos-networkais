"""[135]: voz em tempo real do Tutor IA — WebSocket próprio, fora do prefixo
`/api/v1` (o nginx já reserva `location /ws/` com upgrade de conexão desde
o [011]; nunca tinha um endpoint Python do lado de dentro — este é o
primeiro). Aditivo: não toca em nenhuma rota REST existente.

Protocolo (cliente → servidor):
  - `{"type": "commit"}` — texto JSON, fim da fala do aluno (o cliente já
    detectou silêncio, mesma lógica RMS do mãos-livres existente).
  - frames binários — PCM16 16kHz mono, pedaços do microfone.
  - `{"type": "stop"}` — encerra a sessão.

Protocolo (servidor → cliente), tudo JSON exceto os frames binários:
  - `{"type": "transcript_delta"|"transcript_final", "text": ...}`
  - `{"type": "llm_delta", "text": ...}` (pedaço da resposta em texto)
  - frames binários — PCM16 24kHz mono, a fala da resposta, em pedaços por
    frase (o cliente agenda e toca via Web Audio API, sem esperar a
    resposta inteira).
  - `{"type": "response_done"}` / `{"type": "error", "detail": ...}`

Simplificações desta 1ª versão, registradas com honestidade (não escondidas):
sem retry/fallback dentro de um turno (usa só a conexão ativa de cada
categoria — se falhar, dá erro, não cai pra próxima da cadeia como o
REST faz); sem a fila de admissão (`fila.vaga`) da [126] (é um
context manager síncrono, não pensado pra sessão assíncrona de longa
duração — entra depois, com uma versão assíncrona dela)."""

import asyncio
import contextlib
import json
import re

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ChatMessage, Conversation, User
from app.db.session import SessionLocal
from app.modules.ai_registry import limites
from app.modules.ai_registry.orcamento import diario_excedido
from app.modules.ai_registry.resolver import cadeia_para_categoria
from app.modules.ai_registry.servico import VOZES_PADRAO, _com_escolhida
from app.modules.chat.chat import _material_selecionado
from app.modules.chat.voz_streaming import SessaoSTT, chamar_chat_streaming, falar_streaming
from app.modules.creditos import acesso_diario
from app.modules.prompts import prompts
from app.modules.rag.rag import contexto_biblioteca

router = APIRouter()

_QUEBRA_FRASE = re.compile(r"(?<=[.!?:])\s+")


async def _montar_sistema(db: Session, conversa: Conversation) -> str:
    """Mesma lógica de `chat.responder()` pro modo tutor — reusa as mesmas
    peças (prompt do banco, material selecionado, persona), sem tocar na
    função síncrona original."""
    persona_chave = "chat_persona_amigo" if conversa.persona == "amigo" else "chat_persona_professor"
    sistema = prompts.buscar(db, "chat_sistema_tutor") + "\n\n" + prompts.buscar(db, persona_chave)
    sistema += "\n\n" + prompts.buscar(db, "chat_modo_voz_addendum")
    material = _material_selecionado(db, conversa)
    if material:
        sistema += "\n\n" + material
    return sistema


def _historico(db: Session, conversation_id: int) -> list[dict]:
    linhas = db.execute(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.id)
    ).scalars()
    return [{"role": m.role, "content": m.conteudo} for m in linhas][-20:]


async def _reconectar_stt(websocket: WebSocket, sessao_velha: SessaoSTT, conn_stt) -> SessaoSTT | None:
    """[145]: achado real em produção (log do serviço) — a conexão WebSocket
    do backend com a Together (STT em tempo real) cai sozinha depois de um
    tempo (3 quedas reais medidas, todas entre 309-316s de conexão, indício
    forte de limite de duração de sessão do lado da Together — não
    confirmado 100% qual é a causa exata, mas o EFEITO é real e mensurável).
    Antes, essa queda não era tratada em lugar nenhum: a exceção subia crua
    e derrubava a sessão de voz INTEIRA (WebSocket do navegador incluso) sem
    nenhum aviso — o aluno só via tudo parar de responder, sem explicação.
    Agora: reconecta transparente numa sessão nova (mesma conexão de IA já
    resolvida) e avisa o cliente com clareza. O áudio que estava em trânsito
    no exato momento da queda pode se perder (o turno em andamento não é
    recuperado) — aceitável: é melhor pedir pro aluno falar de novo do que a
    sessão inteira morrer calada."""
    with contextlib.suppress(Exception):
        await sessao_velha.fechar()
    try:
        nova = SessaoSTT(conn_stt, idioma="pt")
        await nova.conectar()
    except Exception as e:  # noqa: BLE001 — sem STT novo, a sessão de voz não tem como continuar
        await websocket.send_json({"type": "error", "detail": f"A conexão de voz caiu e não reconectou: {e}"})
        return None
    await websocket.send_json({
        "type": "info",
        "detail": "A conexão de voz renovou automaticamente. Se sua última fala não foi ouvida, fale de novo.",
    })
    return nova


@router.websocket("/ws/tutor-voz")
async def tutor_voz_ws(websocket: WebSocket, conversation_id: int):
    db = SessionLocal()
    try:
        user_id = websocket.session.get("user_id")
        user = db.get(User, user_id) if user_id else None
        if not user:
            await websocket.close(code=4401, reason="Não autenticado.")
            return

        conversa = db.get(Conversation, conversation_id)
        if not conversa or conversa.user_id != user.id or conversa.modo != "tutor":
            await websocket.close(code=4404, reason="Conversa não encontrada.")
            return

        # [079]: só o dono escapa dos limites rolantes — mesmo critério de
        # `chat.py::_isento`, vitalício continua com ritmo limitado.
        if motivo := limites.bloqueio(db, user.id, isento=user.role == "superadmin"):
            await websocket.close(code=4429, reason=motivo)
            return
        if motivo := acesso_diario.abrir(db, user):
            await websocket.close(code=4402, reason=motivo)
            return
        if diario_excedido(db):
            await websocket.close(code=4402, reason="Orçamento diário de IA atingido.")
            return

        cadeia_stt = _com_escolhida(
            db, cadeia_para_categoria(db, "transcricao"), "transcricao", conversa.modelo_transcricao_id,
        )
        cadeia_llm = _com_escolhida(db, cadeia_para_categoria(db, "texto"), "texto", conversa.modelo_texto_id)
        cadeia_tts = _com_escolhida(db, cadeia_para_categoria(db, "voz"), "voz", conversa.modelo_voz_id)
        if not cadeia_stt or not cadeia_llm or not cadeia_tts:
            await websocket.close(code=4400, reason="Falta conexão de IA (texto/voz/transcrição).")
            return
        conn_stt, conn_llm, conn_tts = cadeia_stt[0], cadeia_llm[0], cadeia_tts[0]
        # [151]: voz do Kokoro escolhida pelo aluno pra esta conversa (mesmo
        # campo que o "Modo voz" REST já usa) — None cai no padrão de sempre.
        voz = conversa.voz_escolhida or VOZES_PADRAO.get((conn_tts.modelo or "").lower(), "alloy")

        await websocket.accept()

        sessao_stt = SessaoSTT(conn_stt, idioma="pt")
        try:
            await sessao_stt.conectar()
        except Exception as e:  # noqa: BLE001 — sessão inteira depende disso, erro claro ao cliente
            await websocket.send_json({"type": "error", "detail": f"Falha ao conectar STT: {e}"})
            await websocket.close()
            return

        try:
            while True:
                msg = await websocket.receive()
                # [147]: achado real em produção (log do serviço, durante o
                # restart do [146]) — `receive()` cru devolve
                # `{"type": "websocket.disconnect", ...}` num desconecte real
                # (rede caindo, aba fechando, reconexão do cliente), sem
                # "bytes" nem "text". Sem checar isso, o código caía no
                # `continue` de baixo e chamava `receive()` de novo — e o
                # Starlette levanta `RuntimeError` ao chamar receive() depois
                # de já ter entregue um disconnect. Isso derrubava a
                # coroutine da sessão INTEIRA sem nenhum aviso ao cliente,
                # de forma silenciosa — não só durante restart do servidor,
                # em QUALQUER desconexão real do WebSocket do navegador.
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes") is not None:
                    # [145]: a conexão STT->Together pode ter caído sozinha
                    # (ver `_reconectar_stt`) — reconecta e descarta só este
                    # pedaço perdido, sem derrubar a sessão de voz inteira.
                    try:
                        await sessao_stt.mandar_audio(msg["bytes"])
                    except websockets.exceptions.ConnectionClosed:
                        nova = await _reconectar_stt(websocket, sessao_stt, conn_stt)
                        if nova is None:
                            break
                        sessao_stt = nova
                    continue
                if msg.get("text") is None:
                    continue
                dados = json.loads(msg["text"])
                tipo = dados.get("type")

                if tipo == "commit":
                    try:
                        await sessao_stt.commit()
                        transcript_final = None
                        # [150]: achado real, mais grave que o [146] cobria —
                        # `sessao_stt.eventos()` é um `async for` cru sobre o
                        # WebSocket com a Together; se o commit não tem fala
                        # de verdade (ruído/silêncio baixo, testado com
                        # áudio real), a Together às vezes NÃO manda nenhum
                        # evento terminal (nem `.completed`, nem `error`) —
                        # o loop trava pra sempre. Como é a MESMA coroutine
                        # que depois volta a `websocket.receive()` pra ler
                        # áudio novo, travar aqui trava a sessão INTEIRA —
                        # o microfone do cliente continua mandando bytes,
                        # mas nada mais é processado, sem erro nenhum. Timeout
                        # generoso (turnos reais respondem em segundos)
                        # tratado como "sem transcrição", não como falha.
                        async with asyncio.timeout(12):
                            async for ev in sessao_stt.eventos():
                                if "delta" in ev:
                                    await websocket.send_json({"type": "transcript_delta", "text": ev["delta"]})
                                t = ev.get("type", "")
                                if t.endswith(".completed"):
                                    transcript_final = ev.get("transcript", "")
                                    break
                                if t == "error":
                                    await websocket.send_json({"type": "error", "detail": json.dumps(ev)[:300]})
                                    break
                    except TimeoutError:
                        pass
                    except websockets.exceptions.ConnectionClosed:
                        # o turno em andamento se perde (a Together não tem
                        # mais o áudio commitado) — o aluno só fala de novo.
                        nova = await _reconectar_stt(websocket, sessao_stt, conn_stt)
                        if nova is None:
                            break
                        sessao_stt = nova
                        # [150]: o cliente já mandou o "commit" — sem mandar
                        # algum aviso de fim de turno aqui, o frontend nunca
                        # reseta a trava que impede o PRÓXIMO commit (ver
                        # comentário completo abaixo), e a sessão fica surda
                        # pro resto da conversa.
                        await websocket.send_json({"type": "response_done"})
                        continue
                    # [150]: achado real — comit disparado por ruído/silêncio
                    # (transcript vazio/só espaço) ou por erro do STT (loop
                    # acima sai sem `.completed`) nunca mandava NENHUM evento
                    # de volta — nem erro, nem response_done. O frontend usa
                    # exatamente o `response_done` pra destravar o PRÓXIMO
                    # commit (`jaComitou=false`, [136]/[149]); sem ele, a
                    # sessão parece ter "caído" depois do 1º turno real, mas
                    # na verdade só ficou travada esperando um evento que
                    # nunca chegava — o microfone continuava mandando áudio
                    # pro servidor o tempo todo, só nunca mais disparava
                    # commit nenhum. [146] já cobria o caso de NÃO persistir
                    # transcrição vazia; isto aqui cobre o caso de sempre
                    # avisar o cliente que o turno (mesmo vazio) terminou.
                    if transcript_final and transcript_final.strip():
                        await websocket.send_json({"type": "transcript_final", "text": transcript_final})
                        await _processar_turno(websocket, db, conversa, conn_llm, conn_tts, voz, transcript_final)
                    else:
                        await websocket.send_json({"type": "response_done"})

                elif tipo == "stop":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await sessao_stt.fechar()
    finally:
        db.close()


async def _processar_turno(
    websocket: WebSocket, db: Session, conversa: Conversation, conn_llm, conn_tts, voz: str, texto_usuario: str,
) -> None:
    """Um turno completo: LLM em streaming → corta em frases → TTS em
    streaming por frase → manda tudo pro cliente conforme chega, sem esperar
    a resposta inteira."""
    sistema = await _montar_sistema(db, conversa)
    biblioteca = contexto_biblioteca(db, texto_usuario, uso="tutor", k=8, doc_ids=conversa.rag_doc_ids or None)
    if biblioteca:
        sistema += "\n\n" + biblioteca
    mensagens = [
        {"role": "system", "content": sistema},
        *_historico(db, conversa.id),
        {"role": "user", "content": texto_usuario},
    ]

    resposta_completa = ""
    buffer = ""
    try:
        async for delta in chamar_chat_streaming(conn_llm, mensagens, max_tokens=800):
            resposta_completa += delta
            buffer += delta
            await websocket.send_json({"type": "llm_delta", "text": delta})
            partes = _QUEBRA_FRASE.split(buffer)
            while len(partes) > 1:
                frase = partes.pop(0).strip()
                if frase:
                    await _falar_frase(websocket, conn_tts, voz, frase)
                buffer = partes[0] if partes else ""
                partes = [buffer]
        if buffer.strip():
            await _falar_frase(websocket, conn_tts, voz, buffer.strip())
    except Exception as e:  # noqa: BLE001 — turno isolado; sessão continua de pé pro próximo
        await websocket.send_json({"type": "error", "detail": f"Falha na resposta: {e}"})

    db.add(ChatMessage(conversation_id=conversa.id, role="user", conteudo=texto_usuario))
    if resposta_completa:
        db.add(ChatMessage(conversation_id=conversa.id, role="assistant", conteudo=resposta_completa))
    db.commit()
    await websocket.send_json({"type": "response_done"})


async def _falar_frase(websocket: WebSocket, conn_tts, voz: str, frase: str) -> None:
    async for pedaco_pcm in falar_streaming(conn_tts, frase, voz):
        await websocket.send_bytes(pedaco_pcm)
    await websocket.send_json({"type": "sentence_end"})
