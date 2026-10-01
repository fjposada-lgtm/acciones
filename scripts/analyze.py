"""Calculos deterministas sobre los datos ya extraidos y validados.

Todo lo que se pueda calcular con aritmetica se calcula aqui, en codigo
auditable, y no lo redacta un modelo. Claude solo recibe este resultado para
escribir el informe.

Regla transversal: si falta un dato, el calculo que depende de el devuelve
``None`` y se anota en ``datos_faltantes``. Nunca se estima.
"""

from __future__ import annotations

from . import common

# Umbrales de apalancamiento. Son convenciones del proyecto, no reglas de
# mercado, y se documentan en el informe como interpretacion.
APALANCAMIENTO_MEDIO = 5
APALANCAMIENTO_ALTO = 10

# Porcentaje del valor nocional total en un solo instrumento a partir del cual
# se senala concentracion.
CONCENTRACION_ALTA = 0.40

# Uso de margen sobre patrimonio a partir del cual se senala tension.
MARGEN_TENSO = 0.50


def _valor(magnitud):
    """Devuelve el numero de una magnitud, o None si no esta disponible."""
    if isinstance(magnitud, dict):
        return magnitud.get("valor")
    return None


def _nocional(posicion):
    """Valor nocional = tamano x precio de entrada, si ambos son legibles.

    Si solo hay 'monto' se usa ese valor. Si no hay nada, devuelve None.
    """
    tamano = _valor(posicion.get("tamano"))
    precio = _valor(posicion.get("precio_entrada"))
    if tamano is not None and precio is not None:
        return abs(tamano * precio)
    monto = _valor(posicion.get("monto"))
    if monto is not None:
        return abs(monto)
    return None


def analizar_posicion(posicion):
    """Metricas y banderas de una posicion. Solo aritmetica."""
    banderas = []
    faltantes = list(posicion.get("datos_faltantes", []))

    nocional = _nocional(posicion)
    margen = _valor(posicion.get("margen"))
    resultado = _valor(posicion.get("resultado"))
    apal = posicion.get("apalancamiento")

    resultado_pct_margen = None
    if resultado is not None and margen not in (None, 0):
        resultado_pct_margen = round(100.0 * resultado / margen, 2)

    variacion_precio_pct = None
    entrada = _valor(posicion.get("precio_entrada"))
    actual = _valor(posicion.get("precio_actual"))
    if entrada not in (None, 0) and actual is not None:
        variacion_precio_pct = round(100.0 * (actual - entrada) / entrada, 2)

    if apal is not None:
        if apal >= APALANCAMIENTO_ALTO:
            banderas.append(
                "apalancamiento_alto: multiplicador x" + str(apal)
                + " (>= x" + str(APALANCAMIENTO_ALTO) + ")"
            )
        elif apal >= APALANCAMIENTO_MEDIO:
            banderas.append(
                "apalancamiento_medio: multiplicador x" + str(apal)
                + " (>= x" + str(APALANCAMIENTO_MEDIO) + ")"
            )
    else:
        banderas.append("apalancamiento_desconocido: no se pudo leer en la captura")

    if posicion.get("stop_loss") is None:
        banderas.append("sin_stop_loss_visible: no se leyo un stop loss")

    if resultado is not None and resultado < 0:
        banderas.append("resultado_negativo")

    if posicion.get("tipo_producto") == "CFD":
        banderas.append(
            "producto_cfd: contrato por diferencia, no implica propiedad del activo"
        )
    elif posicion.get("tipo_producto") == "no_disponible":
        banderas.append(
            "tipo_producto_desconocido: no se puede afirmar si es CFD o accion"
        )

    if not posicion.get("suficiente"):
        banderas.append("datos_insuficientes_para_analizar")

    return {
        "instrumento": posicion["instrumento"],
        "tipo_producto": posicion.get("tipo_producto"),
        "direccion": posicion.get("direccion"),
        "nocional": nocional,
        "margen": margen,
        "resultado": resultado,
        "tipo_resultado": (posicion.get("resultado") or {}).get("tipo")
        if isinstance(posicion.get("resultado"), dict)
        else None,
        "resultado_pct_margen": resultado_pct_margen,
        "variacion_precio_pct": variacion_precio_pct,
        "apalancamiento": apal,
        "banderas": banderas,
        "datos_faltantes": faltantes,
        "suficiente": bool(posicion.get("suficiente")),
    }


def calcular_concentracion(posiciones_analizadas):
    """Reparto del nocional entre instrumentos, si hay datos suficientes."""
    con_nocional = [p for p in posiciones_analizadas if p["nocional"] is not None]
    total = sum(p["nocional"] for p in con_nocional)
    if not con_nocional or total <= 0:
        return {
            "calculable": False,
            "motivo": (
                "No se pudo calcular el nocional de ninguna posicion "
                "(faltan tamano/precio o monto)."
            ),
            "total_nocional": None,
            "por_instrumento": [],
            "cobertura": (
                str(len(con_nocional)) + "/" + str(len(posiciones_analizadas))
            ),
        }

    reparto = {}
    for p in con_nocional:
        reparto[p["instrumento"]] = reparto.get(p["instrumento"], 0.0) + p["nocional"]

    por_instrumento = [
        {
            "instrumento": nombre,
            "nocional": round(valor, 2),
            "porcentaje": round(100.0 * valor / total, 2),
            "concentrado": (valor / total) >= CONCENTRACION_ALTA,
        }
        for nombre, valor in sorted(reparto.items(), key=lambda kv: -kv[1])
    ]
    return {
        "calculable": True,
        "motivo": None,
        "total_nocional": round(total, 2),
        "por_instrumento": por_instrumento,
        "cobertura": str(len(con_nocional)) + "/" + str(len(posiciones_analizadas)),
        "parcial": len(con_nocional) < len(posiciones_analizadas),
    }


def calcular_margen(cuenta):
    """Uso de margen sobre patrimonio, si ambos valores son legibles."""
    usado = _valor(cuenta.get("margen_usado"))
    patrimonio = _valor(cuenta.get("patrimonio"))
    if usado is None or patrimonio in (None, 0):
        return {
            "calculable": False,
            "motivo": "Faltan 'margen_usado' o 'patrimonio' en la captura.",
            "uso_pct": None,
            "tenso": None,
        }
    uso = usado / patrimonio
    return {
        "calculable": True,
        "motivo": None,
        "uso_pct": round(100.0 * uso, 2),
        "tenso": uso >= MARGEN_TENSO,
    }


def comparar_con_anterior(posiciones_analizadas, reporte_anterior):
    """Diferencias frente al ultimo informe valido."""
    if not reporte_anterior:
        return {
            "hay_anterior": False,
            "fecha_anterior": None,
            "nuevas": [],
            "cerradas": [],
            "cambios": [],
            "nota": "No existe un informe valido anterior con el cual comparar.",
        }

    previas = {}
    for p in reporte_anterior.get("analisis", {}).get("posiciones", []):
        previas[p["instrumento"]] = p

    actuales = {p["instrumento"]: p for p in posiciones_analizadas}

    nuevas = sorted(set(actuales) - set(previas))
    cerradas = sorted(set(previas) - set(actuales))

    cambios = []
    for nombre in sorted(set(actuales) & set(previas)):
        ahora, antes = actuales[nombre], previas[nombre]
        delta_resultado = None
        if ahora["resultado"] is not None and antes.get("resultado") is not None:
            delta_resultado = round(ahora["resultado"] - antes["resultado"], 2)
        cambios.append(
            {
                "instrumento": nombre,
                "resultado_antes": antes.get("resultado"),
                "resultado_ahora": ahora["resultado"],
                "delta_resultado": delta_resultado,
                "comparable": delta_resultado is not None,
            }
        )

    return {
        "hay_anterior": True,
        "fecha_anterior": reporte_anterior.get("fecha_datos"),
        "nuevas": nuevas,
        "cerradas": cerradas,
        "cambios": cambios,
        "nota": None,
    }


def nivel_atencion(posiciones_analizadas, margen, concentracion, desactualizada):
    """Nivel de atencion global, por reglas explicitas y auditables."""
    motivos = []
    puntos = 0

    for p in posiciones_analizadas:
        for bandera in p["banderas"]:
            if bandera.startswith("apalancamiento_alto"):
                puntos += 2
                motivos.append(p["instrumento"] + ": apalancamiento alto")
            elif bandera.startswith("apalancamiento_medio"):
                puntos += 1
                motivos.append(p["instrumento"] + ": apalancamiento medio")
            elif bandera == "resultado_negativo":
                puntos += 1
                motivos.append(p["instrumento"] + ": resultado negativo")
            elif bandera.startswith("sin_stop_loss_visible"):
                puntos += 1
                motivos.append(p["instrumento"] + ": sin stop loss visible")

    if margen.get("tenso"):
        puntos += 2
        motivos.append("Uso de margen sobre patrimonio igual o superior al 50%")

    for item in concentracion.get("por_instrumento", []):
        if item["concentrado"]:
            puntos += 1
            motivos.append(
                "Concentracion en " + item["instrumento"]
                + " (" + str(item["porcentaje"]) + "% del nocional)"
            )

    if desactualizada:
        puntos += 1
        motivos.append("Los datos de la captura estan desactualizados")

    if puntos >= 5:
        nivel = "alto"
    elif puntos >= 2:
        nivel = "medio"
    else:
        nivel = "bajo"

    return {"nivel": nivel, "puntos": puntos, "motivos": sorted(set(motivos))}


def analizar(validacion, reporte_anterior=None):
    """Punto de entrada: convierte una validacion en metricas deterministas."""
    datos = validacion["datos"]
    posiciones = [analizar_posicion(p) for p in datos["posiciones"]]
    concentracion = calcular_concentracion(posiciones)
    margen = calcular_margen(datos["cuenta"])
    comparacion = comparar_con_anterior(posiciones, reporte_anterior)
    atencion = nivel_atencion(
        posiciones, margen, concentracion, validacion["desactualizada"]
    )

    resultados = [p["resultado"] for p in posiciones if p["resultado"] is not None]
    resultado_total_posiciones = round(sum(resultados), 2) if resultados else None

    return {
        "schema_version": common.SCHEMA_VERSION,
        "generado_en": common.now_santiago().isoformat(),
        "fecha_datos": validacion["fecha_datos"],
        "origen_fecha": validacion["origen_fecha"],
        "desactualizada": validacion["desactualizada"],
        "antiguedad_horas": validacion["antiguedad_horas"],
        "fuente": datos["fuente"],
        "cuenta": datos["cuenta"],
        "posiciones": posiciones,
        "resultado_total_posiciones": resultado_total_posiciones,
        "cobertura_resultado": str(len(resultados)) + "/" + str(len(posiciones)),
        "concentracion": concentracion,
        "margen": margen,
        "comparacion": comparacion,
        "atencion": atencion,
        "datos_faltantes": validacion["datos_faltantes"],
        "avisos": validacion["avisos"],
    }
