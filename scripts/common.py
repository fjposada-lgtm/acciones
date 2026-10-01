"""Utilidades compartidas: rutas, fechas, E/S de JSON y hashing.

Todo el proyecto usa unicamente la libreria estandar de Python para que no haya
que instalar dependencias ni en local ni en GitHub Actions.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from pathlib import Path

# ---------------------------------------------------------------- rutas

ROOT = Path(__file__).resolve().parent.parent

INBOX_DIR = ROOT / "data" / "inbox"
EXTRACTED_DIR = ROOT / "data" / "extracted"
REPORTS_JSON_DIR = ROOT / "data" / "reports"
HISTORY_DIR = ROOT / "data" / "history"
STATE_DIR = ROOT / "data" / "state"
REPORTS_MD_DIR = ROOT / "reports"

HISTORY_INDEX = HISTORY_DIR / "index.json"
PROCESSED_REGISTRY = HISTORY_DIR / "processed.json"
STATUS_FILE = STATE_DIR / "status.json"
PENDING_FILE = STATE_DIR / "pending.json"
ANALYSIS_FILE = STATE_DIR / "analysis.json"
NARRATIVE_FILE = STATE_DIR / "narrative.json"

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}

# Antiguedad maxima de una captura para considerarla vigente.
MAX_CAPTURE_AGE_HOURS = int(os.environ.get("MAX_CAPTURE_AGE_HOURS", "36"))

SCHEMA_VERSION = 1

# Estados posibles del proceso. El panel los muestra tal cual.
ESTADOS = {
    "sin_datos_nuevos": "Sin datos nuevos",
    "pendiente": "Captura pendiente de procesar",
    "procesado": "Procesado",
    "datos_insuficientes": "Datos insuficientes",
    "error": "Error",
    "bloqueado_repo_publico": "Bloqueado: el repositorio es publico",
}

CATEGORIAS_RECOMENDACION = ("Mantener", "Revisar", "No operar")


# ---------------------------------------------------------------- fechas

def _chile_offset_fallback(naive_utc: _dt.datetime) -> _dt.timedelta:
    """Aproxima el huso de Chile continental sin la base de datos tz.

    Regla vigente desde 2023: horario de verano (UTC-3) desde el primer sabado
    de septiembre hasta el primer sabado de abril; el resto del ano UTC-4.
    Solo se usa como respaldo cuando ``zoneinfo`` no tiene datos (p. ej. en
    Windows sin el paquete ``tzdata``); en GitHub Actions nunca se usa.
    """

    def first_saturday(year: int, month: int) -> _dt.date:
        d = _dt.date(year, month, 1)
        return d + _dt.timedelta(days=(5 - d.weekday()) % 7)

    year = naive_utc.year
    dst_start = first_saturday(year, 9)
    dst_end = first_saturday(year, 4)
    today = naive_utc.date()
    in_dst = today >= dst_start or today < dst_end
    return _dt.timedelta(hours=-3 if in_dst else -4)


def santiago_tz():
    """Devuelve la zona horaria de Santiago, o ``None`` si hay que aproximar."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Santiago")
    except Exception:
        return None


def now_santiago() -> _dt.datetime:
    """Hora actual en America/Santiago."""
    tz = santiago_tz()
    now_utc = _dt.datetime.now(_dt.timezone.utc)
    if tz is not None:
        return now_utc.astimezone(tz)
    offset = _chile_offset_fallback(now_utc.replace(tzinfo=None))
    return now_utc.astimezone(_dt.timezone(offset))


def to_santiago(moment: _dt.datetime) -> _dt.datetime:
    """Convierte un datetime con tz a hora de Santiago."""
    if moment.tzinfo is None:
        raise ValueError("se requiere un datetime con zona horaria")
    tz = santiago_tz()
    if tz is not None:
        return moment.astimezone(tz)
    offset = _chile_offset_fallback(moment.astimezone(_dt.timezone.utc).replace(tzinfo=None))
    return moment.astimezone(_dt.timezone(offset))


_DATE_PATTERNS = (
    # ISO con o sin zona: 2026-10-01T14:32:00-03:00
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?"), "iso"),
    # 01/10/2026 14:32  o  01-10-2026 14:32
    (re.compile(r"^(\d{2})[/-](\d{2})[/-](\d{4})[ T](\d{2}):(\d{2})"), "dmy"),
    # Solo fecha ISO
    (re.compile(r"^(\d{4})-(\d{2})-(\d{2})$"), "iso_date"),
)


def parse_visible_datetime(text: str | None):
    """Interpreta una fecha/hora leida en la captura.

    Devuelve ``(datetime | None, nota)``. Si el texto no se puede interpretar
    con seguridad devuelve ``None`` en lugar de adivinar.
    """
    if not text or not isinstance(text, str):
        return None, "fecha no disponible"
    raw = text.strip()
    try:
        parsed = _dt.datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now_santiago().tzinfo)
            return parsed, "fecha sin zona horaria; se asumio hora de Santiago"
        return parsed, "ok"
    except ValueError:
        pass

    for pattern, kind in _DATE_PATTERNS:
        m = pattern.match(raw)
        if not m:
            continue
        tzinfo = now_santiago().tzinfo
        if kind == "iso":
            y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
            s = int(m.group(6) or 0)
        elif kind == "dmy":
            d, mo, y, h, mi = (int(m.group(i)) for i in range(1, 6))
            s = 0
        else:
            y, mo, d = (int(m.group(i)) for i in range(1, 4))
            h = mi = s = 0
        try:
            return _dt.datetime(y, mo, d, h, mi, s, tzinfo=tzinfo), "fecha sin zona horaria; se asumio hora de Santiago"
        except ValueError:
            return None, f"fecha ilegible: {raw!r}"
    return None, f"fecha ilegible: {raw!r}"


_FILENAME_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T_](\d{2})-(\d{2}))?")


def datetime_from_filename(name: str):
    """Extrae una fecha del nombre del archivo (convencion YYYY-MM-DD[THH-MM])."""
    m = _FILENAME_DATE.search(name)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h = int(m.group(4) or 0)
    mi = int(m.group(5) or 0)
    try:
        return _dt.datetime(y, mo, d, h, mi, tzinfo=now_santiago().tzinfo)
    except ValueError:
        return None


# ---------------------------------------------------------------- E/S

def read_json(path: Path, default=None):
    """Lee un JSON; devuelve ``default`` si no existe o esta corrupto."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload) -> None:
    """Escribe un JSON con formato estable y salto de linea final."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def sha256_file(path: Path) -> str:
    """Hash del contenido del archivo, usado para detectar capturas repetidas."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def rel(path: Path) -> str:
    """Ruta relativa a la raiz del repo, con separadores POSIX."""
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()
