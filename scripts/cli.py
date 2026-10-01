"""Interfaz de linea de comandos del sistema.

Uso general::

    python -m scripts.cli <comando> [opciones]

Comandos:

``check-repo``        Comprueba que el repositorio sea privado.
``scan``              Busca la captura nueva mas reciente sin procesar.
``validate``          Valida la extraccion producida por Claude.
``analyze``           Calcula metricas deterministas sobre lo validado.
``finalize``          Une analisis y narrativa, guarda informe e historial.
``notify``            Envia el informe por correo si esta configurado.
``status``            Muestra y guarda el estado actual del proceso.
``ventana-horaria``   Indica si es la hora de la revision diaria en Chile.

Ningun comando opera en Libertex. El sistema solo lee y analiza.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import analyze as analyze_mod
from . import common, guardrails, inbox, notify
from . import report as report_mod
from . import schema as schema_mod


def _salida(payload, archivo=None):
    """Imprime el resultado y, opcionalmente, lo guarda."""
    texto = json.dumps(payload, ensure_ascii=False, indent=2)
    print(texto)
    if archivo:
        common.write_json(Path(archivo), payload)
    return payload


def guardar_estado(estado, detalle, extra=None):
    """Escribe data/state/status.json, que es lo que lee el panel."""
    payload = {
        "schema_version": common.SCHEMA_VERSION,
        "estado": estado,
        "estado_legible": common.ESTADOS.get(estado, estado),
        "detalle": detalle,
        "actualizado_en": common.now_santiago().isoformat(),
    }
    if extra:
        payload.update(extra)
    common.write_json(common.STATUS_FILE, payload)
    return payload


# ------------------------------------------------------------------ comandos

def cmd_check_repo(args):
    try:
        info = guardrails.assert_safe_to_process(
            slug=args.repo, allow_unknown=args.allow_unknown
        )
    except PermissionError as exc:
        guardar_estado("bloqueado_repo_publico", str(exc))
        _salida({"ok": False, "estado": "bloqueado_repo_publico", "detalle": str(exc)})
        return 2
    except guardrails.VisibilityUnknown as exc:
        detalle = (
            "No se pudo comprobar la visibilidad del repositorio: " + str(exc)
            + " No subas capturas hasta confirmar manualmente que es privado."
        )
        guardar_estado("error", detalle)
        _salida({"ok": False, "estado": "error", "detalle": detalle})
        return 2
    _salida({"ok": True, **info})
    return 0


def cmd_scan(args):
    resultado = inbox.detectar_pendiente(args.inbox, args.registro)
    common.write_json(common.PENDING_FILE, resultado)

    if resultado["estado"] == "sin_datos_nuevos":
        guardar_estado("sin_datos_nuevos", resultado["motivo"],
                       {"duplicadas": len(resultado["duplicadas"])})
    else:
        guardar_estado("pendiente", resultado["motivo"],
                       {"captura": resultado["captura"]["archivo"]})

    _salida(resultado)
    # Codigo 0 siempre: "sin datos nuevos" no es un fallo del sistema.
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write("estado=" + resultado["estado"] + "\n")
            fh.write("hay_captura=" + ("true" if resultado["captura"] else "false") + "\n")
            if resultado["captura"]:
                fh.write("archivo=" + resultado["captura"]["archivo"] + "\n")
                fh.write("sha256=" + resultado["captura"]["sha256"] + "\n")
    return 0


def cmd_validate(args):
    datos = common.read_json(Path(args.extraccion), default=None)
    if datos is None:
        detalle = "No se pudo leer la extraccion en " + args.extraccion
        guardar_estado("error", detalle)
        _salida({"ok": False, "estado": "error", "detalle": detalle})
        return 2

    try:
        validacion = schema_mod.validar_extraccion(datos)
    except schema_mod.ValidationError as exc:
        detalle = "Extraccion invalida: " + str(exc)
        guardar_estado("datos_insuficientes", detalle)
        _salida({"ok": False, "estado": "datos_insuficientes", "detalle": detalle})
        return 3

    common.write_json(Path(args.salida), validacion)
    if not validacion["valida"]:
        guardar_estado(
            "datos_insuficientes",
            "La captura no pasa la validacion.",
            {"errores": validacion["errores"]},
        )
        _salida({"ok": False, "estado": "datos_insuficientes",
                 "errores": validacion["errores"], "avisos": validacion["avisos"]})
        return 3

    _salida({"ok": True, "estado": "validado", "avisos": validacion["avisos"],
             "desactualizada": validacion["desactualizada"],
             "datos_faltantes": validacion["datos_faltantes"]})
    return 0


def cmd_analyze(args):
    validacion = common.read_json(Path(args.validacion), default=None)
    if not validacion or not validacion.get("valida"):
        detalle = "No hay una validacion valida en " + args.validacion
        guardar_estado("datos_insuficientes", detalle)
        _salida({"ok": False, "detalle": detalle})
        return 3

    anterior = report_mod.ultimo_reporte_valido()
    analisis = analyze_mod.analizar(validacion, anterior)
    common.write_json(Path(args.salida), analisis)
    _salida({"ok": True, "nivel_atencion": analisis["atencion"]["nivel"],
             "posiciones": len(analisis["posiciones"]),
             "hay_anterior": analisis["comparacion"]["hay_anterior"]})
    return 0


def cmd_finalize(args):
    analisis = common.read_json(Path(args.analisis), default=None)
    narrativa = common.read_json(Path(args.narrativa), default=None)
    validacion = common.read_json(Path(args.validacion), default=None)

    if not analisis or not narrativa or not validacion:
        detalle = "Faltan archivos de entrada para construir el informe."
        guardar_estado("error", detalle)
        _salida({"ok": False, "detalle": detalle})
        return 2

    try:
        reporte = report_mod.construir_reporte(analisis, narrativa, validacion)
    except report_mod.NarrativaInvalida as exc:
        detalle = "La narrativa no cumple el contrato: " + str(exc)
        guardar_estado("error", detalle)
        _salida({"ok": False, "detalle": detalle})
        return 4

    guardado = report_mod.guardar(reporte)
    report_mod.actualizar_indice(guardado["reporte"])

    sha = analisis["fuente"].get("sha256")
    if sha:
        inbox.marcar_procesada(
            sha,
            {
                "archivo": analisis["fuente"].get("archivo"),
                "fecha_proceso": common.now_santiago().isoformat(),
                "reporte": guardado["reporte"]["archivo_json"],
            },
        )

    guardar_estado(
        "procesado",
        "Informe generado correctamente.",
        {
            "reporte_md": guardado["reporte"]["archivo_md"],
            "reporte_json": guardado["reporte"]["archivo_json"],
            "fecha_datos": reporte["fecha_datos"],
            "nivel_atencion": analisis["atencion"]["nivel"],
            "desactualizada": analisis["desactualizada"],
        },
    )
    _salida({"ok": True, "md": guardado["reporte"]["archivo_md"],
             "json": guardado["reporte"]["archivo_json"]})
    return 0


def cmd_notify(args):
    reporte = common.read_json(Path(args.reporte), default=None)
    if not reporte:
        _salida({"ok": False, "detalle": "No se pudo leer el informe."})
        return 2

    cuerpo = Path(common.ROOT / reporte["archivo_md"]).read_text(encoding="utf-8")
    asunto = "Informe diario de operaciones - " + reporte["fecha"]
    resultado = notify.enviar(asunto, cuerpo)

    estado_actual = common.read_json(common.STATUS_FILE, default={}) or {}
    estado_actual["correo"] = {
        "estado": resultado["estado"],
        "enviado": resultado["enviado"],
        "detalle": resultado["detalle"],
        "destinatario": resultado["destinatario"],
    }
    common.write_json(common.STATUS_FILE, estado_actual)

    _salida(resultado)
    # Que el correo no este configurado no debe hacer fallar el flujo.
    return 0 if resultado["estado"] != "error_envio" else 1


def cmd_status(args):
    estado = common.read_json(common.STATUS_FILE, default=None)
    if estado is None:
        estado = guardar_estado("sin_datos_nuevos", "El sistema aun no ha procesado ninguna captura.")
    _salida(estado)
    return 0


def cmd_ventana_horaria(args):
    """Comprueba si la hora local de Santiago esta dentro de la ventana diaria.

    GitHub Actions programa el cron en UTC y Chile cambia de horario dos veces
    al ano, asi que el workflow dispara en dos horas UTC distintas y es este
    comando el que decide cual corresponde hoy.
    """
    ahora = common.now_santiago()
    dentro = args.hora_objetivo <= ahora.hour < (args.hora_objetivo + args.tolerancia)
    payload = {
        "hora_santiago": ahora.isoformat(),
        "hora_local": ahora.hour,
        "hora_objetivo": args.hora_objetivo,
        "tolerancia_horas": args.tolerancia,
        "dentro_de_ventana": dentro,
        "zoneinfo_disponible": common.santiago_tz() is not None,
    }
    _salida(payload)
    if args.github_output:
        with open(args.github_output, "a", encoding="utf-8") as fh:
            fh.write("dentro_de_ventana=" + ("true" if dentro else "false") + "\n")
    return 0


# ------------------------------------------------------------------ parser

def build_parser():
    parser = argparse.ArgumentParser(
        prog="python -m scripts.cli",
        description="Revision diaria de operaciones de Libertex (solo analisis).",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("check-repo", help="Comprueba que el repositorio sea privado.")
    p.add_argument("--repo", default=None, help="owner/repo. Por defecto GITHUB_REPOSITORY.")
    p.add_argument("--allow-unknown", action="store_true",
                   help="No falla si la visibilidad no se puede comprobar.")
    p.set_defaults(func=cmd_check_repo)

    p = sub.add_parser("scan", help="Busca la captura nueva mas reciente.")
    p.add_argument("--inbox", default=None)
    p.add_argument("--registro", default=None)
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("validate", help="Valida la extraccion.")
    p.add_argument("--extraccion", required=True)
    p.add_argument("--salida", default=str(common.STATE_DIR / "validacion.json"))
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("analyze", help="Calcula metricas deterministas.")
    p.add_argument("--validacion", default=str(common.STATE_DIR / "validacion.json"))
    p.add_argument("--salida", default=str(common.ANALYSIS_FILE))
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("finalize", help="Construye y guarda el informe.")
    p.add_argument("--analisis", default=str(common.ANALYSIS_FILE))
    p.add_argument("--narrativa", default=str(common.NARRATIVE_FILE))
    p.add_argument("--validacion", default=str(common.STATE_DIR / "validacion.json"))
    p.set_defaults(func=cmd_finalize)

    p = sub.add_parser("notify", help="Envia el informe por correo si esta configurado.")
    p.add_argument("--reporte", required=True)
    p.set_defaults(func=cmd_notify)

    p = sub.add_parser("status", help="Muestra el estado actual.")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("ventana-horaria", help="Indica si corresponde la revision diaria.")
    p.add_argument("--hora-objetivo", type=int, default=8)
    p.add_argument("--tolerancia", type=int, default=1)
    p.add_argument("--github-output", default=None)
    p.set_defaults(func=cmd_ventana_horaria)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
