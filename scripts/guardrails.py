"""Barreras de seguridad del sistema.

Dos reglas duras:

1. Nunca se procesa ni se versiona una captura si el repositorio es publico.
2. El sistema solo analiza. No existe ninguna ruta de codigo que opere en
   Libertex, y este modulo documenta y verifica esa limitacion.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"


class VisibilityUnknown(Exception):
    """No se pudo comprobar si el repositorio es publico o privado."""


def _repo_slug() -> str | None:
    slug = os.environ.get("GITHUB_REPOSITORY")
    if slug and "/" in slug:
        return slug
    return None


def check_repo_visibility(slug: str | None = None, timeout: int = 10) -> dict:
    """Comprueba la visibilidad del repositorio.

    Devuelve ``{"visibility": "public"|"private", "checked": True, ...}``.
    Lanza :class:`VisibilityUnknown` si no se puede determinar, para que quien
    llame decida detenerse en lugar de asumir que es privado.
    """
    slug = slug or _repo_slug()
    if not slug:
        raise VisibilityUnknown(
            "No se conoce el repositorio (falta GITHUB_REPOSITORY)."
        )

    request = urllib.request.Request(
        f"{GITHUB_API}/repos/{slug}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "acciones-bot"},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and not token:
            # Sin token, un 404 significa "no visible publicamente", es decir
            # privado o inexistente. No es prueba suficiente de que sea privado.
            raise VisibilityUnknown(
                "El repositorio no es visible sin autenticacion (404). "
                "Podria ser privado o no existir; no se puede confirmar."
            ) from exc
        raise VisibilityUnknown(f"Error HTTP {exc.code} al consultar GitHub.") from exc
    except Exception as exc:  # red caida, DNS, etc.
        raise VisibilityUnknown(f"No se pudo consultar GitHub: {exc}") from exc

    visibility = payload.get("visibility") or (
        "private" if payload.get("private") else "public"
    )
    return {
        "checked": True,
        "repository": payload.get("full_name", slug),
        "visibility": visibility,
        "private": bool(payload.get("private")),
    }


def assert_safe_to_process(slug: str | None = None, allow_unknown: bool = False) -> dict:
    """Falla si el repositorio es publico o si la visibilidad es desconocida.

    ``allow_unknown`` solo deberia usarse en ejecuciones locales donde el
    operador ya sabe que el repositorio es privado.
    """
    try:
        info = check_repo_visibility(slug)
    except VisibilityUnknown as exc:
        if allow_unknown:
            return {
                "checked": False,
                "visibility": "desconocida",
                "private": None,
                "aviso": (
                    "No se pudo comprobar la visibilidad del repositorio: "
                    f"{exc} No subas capturas ni datos de posiciones hasta "
                    "confirmar manualmente que el repositorio es privado."
                ),
            }
        raise

    if not info["private"]:
        raise PermissionError(
            "BLOQUEADO: el repositorio "
            f"{info['repository']} es PUBLICO. No se procesaran capturas ni se "
            "guardaran datos financieros. Cambia el repositorio a privado en "
            "Settings > General > Danger Zone > Change repository visibility y "
            "vuelve a ejecutar. Recuerda que borrar una imagen despues no la "
            "elimina del historial de commits de Git."
        )
    return info
