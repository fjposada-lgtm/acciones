"""Envio opcional del informe por correo.

Reglas:

- Nada esta escrito en el codigo: destinatario, servidor y credenciales salen
  de variables de entorno alimentadas por GitHub Secrets.
- Si falta cualquier valor, no se intenta el envio y el estado queda como
  ``correo_no_configurado``. Nunca se afirma que el informe fue enviado.
- Solo se considera enviado cuando el servidor SMTP acepta el mensaje sin
  destinatarios rechazados.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

# Variables necesarias para habilitar el envio.
VARIABLES_REQUERIDAS = (
    "MAIL_TO",
    "MAIL_FROM",
    "SMTP_HOST",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
)

VARIABLES_OPCIONALES = {
    "SMTP_PORT": "587",
    "SMTP_SECURITY": "starttls",  # starttls | ssl | none
}


def configuracion(entorno=None):
    """Lee la configuracion de correo y dice si esta completa.

    Nunca devuelve el valor de la contrasena, solo si esta presente.
    """
    entorno = entorno if entorno is not None else os.environ
    faltantes = [
        nombre
        for nombre in VARIABLES_REQUERIDAS
        if not (entorno.get(nombre) or "").strip()
    ]
    valores = {
        nombre: (entorno.get(nombre) or "").strip() for nombre in VARIABLES_REQUERIDAS
    }
    for nombre, por_defecto in VARIABLES_OPCIONALES.items():
        valores[nombre] = (entorno.get(nombre) or por_defecto).strip()

    return {
        "configurado": not faltantes,
        "faltantes": faltantes,
        "destinatario": valores["MAIL_TO"] or None,
        "remitente": valores["MAIL_FROM"] or None,
        "servidor": valores["SMTP_HOST"] or None,
        "puerto": valores["SMTP_PORT"],
        "seguridad": valores["SMTP_SECURITY"],
        "_valores": valores,
    }


def _mensaje(config, asunto, cuerpo):
    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = config["remitente"]
    mensaje["To"] = config["destinatario"]
    mensaje.set_content(cuerpo)
    return mensaje


def enviar(asunto, cuerpo, entorno=None, cliente_smtp=None):
    """Intenta enviar el informe. Devuelve el resultado, sin excepciones.

    ``cliente_smtp`` permite inyectar un doble en las pruebas; en produccion se
    usa :mod:`smtplib`.
    """
    config = configuracion(entorno)

    if not config["configurado"]:
        return {
            "estado": "correo_no_configurado",
            "enviado": False,
            "destinatario": None,
            "detalle": (
                "Faltan secretos de correo: " + ", ".join(config["faltantes"])
                + ". El informe quedo guardado en el repositorio; no se intento "
                "ningun envio."
            ),
            "faltantes": config["faltantes"],
        }

    valores = config["_valores"]
    try:
        if cliente_smtp is not None:
            servidor = cliente_smtp
            rechazados = servidor.send_message(_mensaje(config, asunto, cuerpo))
        else:
            puerto = int(valores["SMTP_PORT"])
            contexto = ssl.create_default_context()
            if valores["SMTP_SECURITY"] == "ssl":
                with smtplib.SMTP_SSL(valores["SMTP_HOST"], puerto, context=contexto, timeout=30) as servidor:
                    servidor.login(valores["SMTP_USERNAME"], valores["SMTP_PASSWORD"])
                    rechazados = servidor.send_message(_mensaje(config, asunto, cuerpo))
            else:
                with smtplib.SMTP(valores["SMTP_HOST"], puerto, timeout=30) as servidor:
                    if valores["SMTP_SECURITY"] != "none":
                        servidor.starttls(context=contexto)
                    servidor.login(valores["SMTP_USERNAME"], valores["SMTP_PASSWORD"])
                    rechazados = servidor.send_message(_mensaje(config, asunto, cuerpo))
    except Exception as exc:
        # El mensaje de error nunca debe incluir la contrasena.
        return {
            "estado": "error_envio",
            "enviado": False,
            "destinatario": config["destinatario"],
            "detalle": "Fallo el envio: " + type(exc).__name__ + ": " + str(exc),
            "faltantes": [],
        }

    if rechazados:
        return {
            "estado": "error_envio",
            "enviado": False,
            "destinatario": config["destinatario"],
            "detalle": "El servidor rechazo destinatarios: " + str(list(rechazados)),
            "faltantes": [],
        }

    return {
        "estado": "enviado",
        "enviado": True,
        "destinatario": config["destinatario"],
        "detalle": "El servidor SMTP acepto el mensaje.",
        "faltantes": [],
    }
