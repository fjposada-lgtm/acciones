"""Gestion de la bandeja de entrada de capturas.

Una captura se identifica por el SHA-256 de su contenido, no por su nombre.
Asi, volver a subir la misma imagen con otro nombre se detecta como duplicada
y no genera un segundo informe.
"""

from __future__ import annotations

from pathlib import Path

from . import common


def listar_capturas(inbox=None):
    """Devuelve las imagenes de la bandeja, de mas reciente a mas antigua.

    El orden usa la fecha del nombre del archivo cuando existe y, si no, la
    fecha de modificacion. El nombre se usa como desempate estable.
    """
    inbox = Path(inbox) if inbox else common.INBOX_DIR
    if not inbox.is_dir():
        return []

    archivos = [
        ruta
        for ruta in inbox.iterdir()
        if ruta.is_file() and ruta.suffix.lower() in common.IMAGE_SUFFIXES
    ]

    def clave(ruta):
        del_nombre = common.datetime_from_filename(ruta.name)
        if del_nombre is not None:
            marca = del_nombre.timestamp()
        else:
            marca = ruta.stat().st_mtime
        return (marca, ruta.name)

    return sorted(archivos, key=clave, reverse=True)


def cargar_registro(ruta=None):
    """Lee el registro de capturas ya procesadas."""
    ruta = Path(ruta) if ruta else common.PROCESSED_REGISTRY
    registro = common.read_json(ruta, default=None)
    if not isinstance(registro, dict) or "procesadas" not in registro:
        return {"schema_version": common.SCHEMA_VERSION, "procesadas": {}}
    return registro


def ya_procesada(sha256, registro=None):
    registro = registro if registro is not None else cargar_registro()
    return sha256 in registro.get("procesadas", {})


def marcar_procesada(sha256, info, ruta=None):
    """Registra una captura como procesada. Es idempotente."""
    ruta = Path(ruta) if ruta else common.PROCESSED_REGISTRY
    registro = cargar_registro(ruta)
    registro["procesadas"][sha256] = info
    common.write_json(ruta, registro)
    return registro


def detectar_pendiente(inbox=None, registro_path=None):
    """Busca la captura mas reciente que todavia no ha sido procesada.

    Devuelve un diccionario con ``estado`` igual a ``pendiente`` o
    ``sin_datos_nuevos``. Nunca inventa una captura.
    """
    capturas = listar_capturas(inbox)
    registro = cargar_registro(registro_path)

    if not capturas:
        return {
            "estado": "sin_datos_nuevos",
            "motivo": "La carpeta data/inbox/ no tiene ninguna imagen.",
            "captura": None,
            "duplicadas": [],
        }

    duplicadas = []
    for ruta in capturas:
        sha = common.sha256_file(ruta)
        if ya_procesada(sha, registro):
            duplicadas.append(
                {
                    "archivo": common.rel(ruta),
                    "sha256": sha,
                    "procesada_en": registro["procesadas"][sha].get("fecha_proceso"),
                }
            )
            continue
        return {
            "estado": "pendiente",
            "motivo": "Hay una captura nueva por procesar.",
            "captura": {
                "archivo": common.rel(ruta),
                "sha256": sha,
                "bytes": ruta.stat().st_size,
                "fecha_nombre": (
                    common.datetime_from_filename(ruta.name).isoformat()
                    if common.datetime_from_filename(ruta.name)
                    else None
                ),
            },
            "duplicadas": duplicadas,
        }

    return {
        "estado": "sin_datos_nuevos",
        "motivo": (
            "Todas las capturas de la bandeja ya fueron procesadas ("
            + str(len(duplicadas))
            + " duplicada(s)). No se genera un informe nuevo."
        ),
        "captura": None,
        "duplicadas": duplicadas,
    }
