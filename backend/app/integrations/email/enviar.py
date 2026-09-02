"""Envio do código de login por SMTP (Gmail com App Password).

Sem SMTP configurado, o código vai para o log do serviço em vez de ser enviado -
permite desenvolver antes de a credencial existir. O código NUNCA volta na
resposta HTTP: isso anularia o propósito de exigir acesso ao e-mail.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

log = logging.getLogger("concursos.email")

MINUTOS_VALIDADE = 10


def _corpo_html(nome: str, codigo: str) -> str:
    return f"""
    <html>
      <body style="font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif; color:#16181d;">
        <h2 style="color:#12805c; margin-bottom:4px;">Seu código de acesso</h2>
        <p>Olá, {nome}. Use o código abaixo para entrar no APP Concursos:</p>
        <div style="background:#f3f4f6; padding:16px 20px; border-radius:8px; display:inline-block;
                    font-size:28px; font-weight:700; letter-spacing:6px; color:#111827;">{codigo}</div>
        <p style="font-size:12px; color:#6b7280; margin-top:20px;">
          Vale por {MINUTOS_VALIDADE} minutos e só pode ser usado uma vez.<br>
          Se não foi você quem pediu, ignore este e-mail.
        </p>
      </body>
    </html>
    """


def enviar_codigo(destino: str, nome: str, codigo: str) -> bool:
    s = get_settings()
    if not s.smtp_user or not s.smtp_password:
        # Sem credencial: registra no log para o desenvolvimento seguir.
        log.warning("SMTP não configurado. Código de %s: %s", destino, codigo)
        return False

    mensagem = MIMEMultipart("alternative")
    mensagem["From"] = s.smtp_from or s.smtp_user
    mensagem["To"] = destino
    mensagem["Subject"] = f"{codigo} é o seu código do APP Concursos"
    mensagem.attach(MIMEText(_corpo_html(nome, codigo), "html", "utf-8"))

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as servidor:
            servidor.starttls()
            servidor.login(s.smtp_user, s.smtp_password)
            servidor.sendmail(s.smtp_user, destino, mensagem.as_string())
        log.info("Código enviado para %s", destino)
        return True
    except Exception as erro:
        # Nunca deixar o erro de SMTP subir para o usuário com detalhe de
        # servidor/credencial; a rota responde igual em sucesso e falha.
        log.error("Falha ao enviar e-mail para %s: %s", destino, erro)
        return False
