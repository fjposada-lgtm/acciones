"""Esquema de los datos extraidos de una captura y su validacion.

La extraccion la produce Claude leyendo la imagen; este modulo comprueba de
forma determinista que lo entregado sea utilizable. Ningun valor se calcula ni
se infiere aqui: lo que no viene legible queda como ``None`` y se registra en
``datos_faltantes``.
"""

from __future__ import annotations

from . import common

# Campos de una posicion que el extractor puede entregar.
CAMPOS_POSICION = (
    "instrumento",
    "tipo_producto",
    "direccion",
    "tamano",
    "monto",
    "apalancamiento",
    "precio_entrada",
    "precio_actual",
    "resultado",
    "margen",
    "stop_loss",
    "take_profit",
    "costos",
    "abierta_en",
)

TIPOS_PRODUCTO = ("CFD", "accion", "no_disponible")
DIRECCIONES = ("compra", "venta", "no_disponible")
TIPOS_RESULTADO = ("realizada", "no_realizada", "no_disponible")

# Para que una posicion sea analizable necesitamos el instrumento y al menos
# uno de estos campos con valor legible.
CAMPOS_MINIMOS_UTILES = ("direccion", "tamano", "monto", "resultado", "precio_actual")

CAMPOS_CUENTA = ("saldo", "patrimonio", "margen_usado", "margen_libre", "resultado_total")


class ValidationError(Exception):
    """La extraccion no cumple el esquema."""


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _magnitude(value, campo, errores):
    """Normaliza una magnitud con forma {"valor": x, "moneda": "USD"} o None."""
    if value is None:
        return None
    if not isinstance(value, dict):
        errores.append(campo + ": se esperaba un objeto con 'valor' y 'moneda'.")
        return None
    valor = value.get("valor")
    if valor is None:
        return None
    if not _is_number(valor):
        errores.append(campo + ": 'valor' debe ser numerico, llego " + repr(valor))
        return None
    salida = {"valor": float(valor), "moneda": value.get("moneda")}
    if "tipo" in value:
        tipo = value.get("tipo")
        if tipo not in TIPOS_RESULTADO:
            errores.append(
                campo + ": 'tipo' debe ser uno de " + str(TIPOS_RESULTADO)
                + ", llego " + repr(tipo)
            )
        salida["tipo"] = tipo
    return salida


def validar_extraccion(datos):
    """Valida la extraccion y devuelve un informe de validacion determinista."""
    errores = []
    avisos = []
    faltantes = []

    if not isinstance(datos, dict):
        raise ValidationError("La extraccion debe ser un objeto JSON.")

    if datos.get("schema_version") != common.SCHEMA_VERSION:
        errores.append(
            "schema_version debe ser " + str(common.SCHEMA_VERSION)
            + ", llego " + repr(datos.get("schema_version"))
        )

    # ---- legibilidad de la imagen
    calidad = datos.get("calidad_imagen") or {}
    if calidad.get("legible") is not True:
        errores.append(
            "La captura se marco como no legible: "
            + str(calidad.get("notas") or "sin detalle")
        )

    # ---- fuente
    fuente = datos.get("fuente") or {}
    if not fuente.get("archivo"):
        errores.append("Falta 'fuente.archivo' (ruta de la captura).")
    if not fuente.get("sha256"):
        errores.append("Falta 'fuente.sha256'.")

    # ---- fecha de los datos
    fecha, nota = common.parse_visible_datetime(fuente.get("fecha_visible"))
    origen_fecha = "captura" if fecha else None
    if fecha is None:
        nombre = (fuente.get("archivo") or "").rsplit("/", 1)[-1]
        fecha = common.datetime_from_filename(nombre)
        if fecha is not None:
            origen_fecha = "nombre_archivo"
            avisos.append(
                "La captura no mostraba fecha legible; se uso la fecha del "
                "nombre del archivo. La confianza temporal es menor."
            )
    if fecha is None:
        errores.append(
            "No hay fecha utilizable: la captura no muestra fecha legible y el "
            "nombre del archivo no sigue la convencion YYYY-MM-DD."
        )
        faltantes.append("fecha de los datos")
    elif origen_fecha == "captura" and nota not in ("ok", "fecha no disponible"):
        avisos.append(nota)

    antiguedad_horas = None
    desactualizada = False
    if fecha is not None:
        fecha = common.to_santiago(fecha)
        delta = common.now_santiago() - fecha
        antiguedad_horas = round(delta.total_seconds() / 3600, 2)
        if antiguedad_horas < -2:
            errores.append(
                "La fecha de la captura esta en el futuro (" + fecha.isoformat()
                + "); no se puede usar."
            )
        elif antiguedad_horas > common.MAX_CAPTURE_AGE_HOURS:
            desactualizada = True
            avisos.append(
                "La captura tiene " + str(antiguedad_horas) + " horas de "
                "antiguedad (limite " + str(common.MAX_CAPTURE_AGE_HOURS)
                + " h). Los precios NO se pueden presentar como actuales."
            )

    # ---- posiciones
    posiciones_in = datos.get("posiciones")
    if posiciones_in is None:
        posiciones_in = []
    if not isinstance(posiciones_in, list):
        raise ValidationError("'posiciones' debe ser una lista.")

    posiciones = []
    for indice, cruda in enumerate(posiciones_in):
        etiqueta = "posiciones[" + str(indice) + "]"
        if not isinstance(cruda, dict):
            errores.append(etiqueta + ": se esperaba un objeto.")
            continue

        instrumento = cruda.get("instrumento")
        if not instrumento or not isinstance(instrumento, str):
            errores.append(etiqueta + ": falta el nombre del instrumento.")
            continue

        tipo_producto = cruda.get("tipo_producto") or "no_disponible"
        if tipo_producto not in TIPOS_PRODUCTO:
            errores.append(
                etiqueta + ": 'tipo_producto' debe ser uno de " + str(TIPOS_PRODUCTO)
            )
            tipo_producto = "no_disponible"

        direccion = cruda.get("direccion") or "no_disponible"
        if direccion not in DIRECCIONES:
            errores.append(
                etiqueta + ": 'direccion' debe ser una de " + str(DIRECCIONES)
            )
            direccion = "no_disponible"

        apal = cruda.get("apalancamiento")
        if apal is not None and not _is_number(apal):
            errores.append(etiqueta + ": 'apalancamiento' debe ser numerico.")
            apal = None

        posicion = {
            "instrumento": instrumento.strip(),
            "tipo_producto": tipo_producto,
            "direccion": direccion,
            "tamano": _magnitude(cruda.get("tamano"), etiqueta + ".tamano", errores),
            "monto": _magnitude(cruda.get("monto"), etiqueta + ".monto", errores),
            "apalancamiento": apal,
            "precio_entrada": _magnitude(
                cruda.get("precio_entrada"), etiqueta + ".precio_entrada", errores
            ),
            "precio_actual": _magnitude(
                cruda.get("precio_actual"), etiqueta + ".precio_actual", errores
            ),
            "resultado": _magnitude(
                cruda.get("resultado"), etiqueta + ".resultado", errores
            ),
            "margen": _magnitude(cruda.get("margen"), etiqueta + ".margen", errores),
            "stop_loss": _magnitude(
                cruda.get("stop_loss"), etiqueta + ".stop_loss", errores
            ),
            "take_profit": _magnitude(
                cruda.get("take_profit"), etiqueta + ".take_profit", errores
            ),
            "costos": _magnitude(cruda.get("costos"), etiqueta + ".costos", errores),
            "abierta_en": cruda.get("abierta_en"),
        }

        # Lo ilegible queda como "no disponible"; nunca se calcula ni se supone.
        sin_datos = [
            campo
            for campo in CAMPOS_POSICION
            if campo != "instrumento"
            and posicion.get(campo) in (None, "no_disponible")
        ]
        posicion["datos_faltantes"] = sin_datos
        for campo in sin_datos:
            faltantes.append(posicion["instrumento"] + ": " + campo)

        utiles = [
            c
            for c in CAMPOS_MINIMOS_UTILES
            if posicion.get(c) not in (None, "no_disponible")
        ]
        posicion["suficiente"] = bool(utiles)
        if not utiles:
            avisos.append(
                posicion["instrumento"] + ": solo se pudo leer el nombre; sin "
                "datos suficientes para analizar esta posicion."
            )
        posiciones.append(posicion)

    # ---- cuenta
    cuenta_in = datos.get("cuenta") or {}
    cuenta = {}
    for campo in CAMPOS_CUENTA:
        cuenta[campo] = _magnitude(cuenta_in.get(campo), "cuenta." + campo, errores)
        if cuenta[campo] is None:
            faltantes.append("cuenta: " + campo)

    hay_posiciones_utiles = any(p["suficiente"] for p in posiciones)
    hay_cuenta = any(v is not None for v in cuenta.values())
    if not hay_posiciones_utiles and not hay_cuenta:
        errores.append(
            "La captura no aporta ni una posicion analizable ni datos de cuenta."
        )

    normalizados = {
        "schema_version": common.SCHEMA_VERSION,
        "fuente": {
            "tipo": fuente.get("tipo", "captura_pantalla"),
            "archivo": fuente.get("archivo"),
            "sha256": fuente.get("sha256"),
            "fecha_visible": fuente.get("fecha_visible"),
            "plataforma": fuente.get("plataforma", "Libertex"),
        },
        "cuenta": cuenta,
        "posiciones": posiciones,
        "notas_extraccion": datos.get("notas_extraccion"),
    }

    valida = not errores
    return {
        "valida": valida,
        "estado": "procesado" if valida else "datos_insuficientes",
        "errores": errores,
        "avisos": avisos,
        "datos_faltantes": sorted(set(faltantes)),
        "datos": normalizados,
        "fecha_datos": fecha.isoformat() if fecha else None,
        "origen_fecha": origen_fecha,
        "desactualizada": desactualizada,
        "antiguedad_horas": antiguedad_horas,
    }
