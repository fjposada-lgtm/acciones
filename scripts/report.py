"""Ensamblado del informe diario y escritura del historial.

Claude entrega la narrativa como JSON; el formato Markdown lo arma este modulo
para que todos los informes se vean igual y para que ningun numero del informe
provenga de texto libre: las cifras salen siempre del analisis determinista.
"""

from __future__ import annotations

from pathlib import Path

from . import common

CLAVES_NARRATIVA = (
    "resumen_ejecutivo",
    "hechos",
    "interpretacion",
    "recomendaciones",
    "conclusion",
)


class NarrativaInvalida(Exception):
    """La narrativa entregada por Claude no cumple el contrato."""


def validar_narrativa(narrativa, analisis):
    """Comprueba la narrativa antes de publicarla.

    Verifica que esten todas las secciones, que cada recomendacion use una
    categoria permitida y que no se recomiende sobre instrumentos que no
    aparecen en los datos extraidos.
    """
    if not isinstance(narrativa, dict):
        raise NarrativaInvalida("La narrativa debe ser un objeto JSON.")

    faltan = [k for k in CLAVES_NARRATIVA if k not in narrativa]
    if faltan:
        raise NarrativaInvalida("Faltan secciones en la narrativa: " + ", ".join(faltan))

    for clave in ("hechos", "interpretacion", "recomendaciones"):
        if not isinstance(narrativa[clave], list):
            raise NarrativaInvalida("'" + clave + "' debe ser una lista.")

    instrumentos = {p["instrumento"] for p in analisis["posiciones"]}
    vistos = set()
    for rec in narrativa["recomendaciones"]:
        if not isinstance(rec, dict):
            raise NarrativaInvalida("Cada recomendacion debe ser un objeto.")
        instrumento = rec.get("instrumento")
        if instrumento not in instrumentos:
            raise NarrativaInvalida(
                "Recomendacion sobre un instrumento que no esta en los datos "
                "extraidos: " + repr(instrumento)
            )
        categoria = rec.get("categoria")
        if categoria not in common.CATEGORIAS_RECOMENDACION:
            raise NarrativaInvalida(
                "Categoria no permitida para " + str(instrumento) + ": "
                + repr(categoria) + ". Debe ser una de "
                + str(common.CATEGORIAS_RECOMENDACION)
            )
        if not rec.get("motivo"):
            raise NarrativaInvalida("Falta 'motivo' en la recomendacion de " + str(instrumento))
        if rec.get("confianza") not in ("alta", "media", "baja"):
            raise NarrativaInvalida(
                "Falta 'confianza' (alta/media/baja) en la recomendacion de "
                + str(instrumento)
            )
        vistos.add(instrumento)

    sin_recomendacion = sorted(instrumentos - vistos)
    return {"sin_recomendacion": sin_recomendacion}


def _fmt(valor, moneda=None, sufijo=""):
    if valor is None:
        return "no disponible"
    texto = "{:,.2f}".format(valor)
    if moneda:
        texto = texto + " " + moneda
    return texto + sufijo


def _moneda_principal(analisis):
    """Moneda a mostrar, tomada de la cuenta y si no de la primera posicion."""
    for campo in (analisis.get("cuenta") or {}).values():
        if isinstance(campo, dict) and campo.get("moneda"):
            return campo["moneda"]
    for posicion in analisis.get("posiciones", []):
        for clave in ("resultado", "margen"):
            magnitud = posicion.get(clave)
            if isinstance(magnitud, dict) and magnitud.get("moneda"):
                return magnitud["moneda"]
    return None


def ruta_disponible(directorio, fecha_iso, extension):
    """Devuelve una ruta libre; nunca sobrescribe un informe existente."""
    directorio = Path(directorio)
    base = directorio / (fecha_iso + extension)
    if not base.exists():
        return base
    contador = 2
    while True:
        alternativa = directorio / (fecha_iso + "-" + str(contador) + extension)
        if not alternativa.exists():
            return alternativa
        contador += 1


def render_markdown(reporte):
    """Genera el informe en espanol a partir del reporte estructurado."""
    analisis = reporte["analisis"]
    narrativa = reporte["narrativa"]
    moneda = _moneda_principal(analisis)

    lineas = []
    add = lineas.append

    add("# Informe diario de operaciones - " + reporte["fecha"])
    add("")
    add("> Este informe es **apoyo a una decision humana**, no una orden ejecutable.")
    add("> El sistema solo lee y analiza: nunca abre, cierra ni modifica operaciones.")
    add("")

    # --- metadatos
    add("## Datos del informe")
    add("")
    add("| Campo | Valor |")
    add("| --- | --- |")
    add("| Fecha y hora de los datos | " + (analisis["fecha_datos"] or "no disponible") + " |")
    add("| Origen de la fecha | " + str(analisis["origen_fecha"] or "no disponible") + " |")
    add("| Antiguedad de la captura | " + (
        str(analisis["antiguedad_horas"]) + " h" if analisis["antiguedad_horas"] is not None else "no disponible"
    ) + " |")
    add("| Fuente | " + str(analisis["fuente"].get("tipo")) + " (" + str(analisis["fuente"].get("plataforma")) + ") |")
    add("| Archivo de origen | `" + str(analisis["fuente"].get("archivo")) + "` |")
    add("| SHA-256 de la captura | `" + str(analisis["fuente"].get("sha256")) + "` |")
    add("| Informe generado | " + reporte["generado_en"] + " |")
    add("| Nivel de atencion | **" + analisis["atencion"]["nivel"].upper() + "** |")
    add("")

    if analisis["desactualizada"]:
        add("> **ADVERTENCIA:** los datos de esta captura estan desactualizados "
            "(" + str(analisis["antiguedad_horas"]) + " h). Los precios no "
            "representan el mercado actual.")
        add("")

    # --- 1. resumen
    add("## 1. Resumen ejecutivo")
    add("")
    add(narrativa["resumen_ejecutivo"])
    add("")
    if analisis["atencion"]["motivos"]:
        add("Motivos del nivel de atencion (calculados por reglas del sistema):")
        add("")
        for motivo in analisis["atencion"]["motivos"]:
            add("- " + motivo)
        add("")

    # --- 2. posiciones
    add("## 2. Operaciones")
    add("")
    if not analisis["posiciones"]:
        add("No se leyo ninguna posicion en la captura.")
        add("")
    else:
        add("| Instrumento | Producto | Direccion | Apalanc. | Entrada | Actual | Resultado | Margen |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for p in analisis["posiciones"]:
            origen = next(
                (o for o in reporte["datos_extraidos"]["posiciones"]
                 if o["instrumento"] == p["instrumento"]),
                {},
            )
            entrada = (origen.get("precio_entrada") or {}).get("valor")
            actual = (origen.get("precio_actual") or {}).get("valor")
            add(
                "| " + p["instrumento"]
                + " | " + str(p["tipo_producto"])
                + " | " + str(p["direccion"])
                + " | " + ("x" + str(p["apalancamiento"]) if p["apalancamiento"] is not None else "no disponible")
                + " | " + _fmt(entrada)
                + " | " + _fmt(actual)
                + " | " + _fmt(p["resultado"], moneda)
                + " | " + _fmt(p["margen"], moneda)
                + " |"
            )
        add("")
        add("Resultado sumado de las posiciones legibles: "
            + _fmt(analisis["resultado_total_posiciones"], moneda)
            + " (cobertura " + analisis["cobertura_resultado"] + " posiciones).")
        add("")
        tipos = {p["tipo_producto"] for p in analisis["posiciones"]}
        if "CFD" in tipos:
            add("> Las posiciones marcadas como **CFD** son contratos por diferencia: "
                "no implican propiedad del activo subyacente.")
            add("")
        if "no_disponible" in tipos:
            add("> En las posiciones con producto `no_disponible` la captura no "
                "permitio determinar si se trata de un CFD o de una accion en "
                "propiedad. No se asume ninguna de las dos.")
            add("")

    # --- 3. cambios
    add("## 3. Cambios frente al informe anterior")
    add("")
    comp = analisis["comparacion"]
    if not comp["hay_anterior"]:
        add(comp["nota"])
        add("")
    else:
        add("Informe anterior: " + str(comp["fecha_anterior"]))
        add("")
        add("- Posiciones nuevas: " + (", ".join(comp["nuevas"]) if comp["nuevas"] else "ninguna"))
        add("- Posiciones que ya no aparecen: " + (", ".join(comp["cerradas"]) if comp["cerradas"] else "ninguna"))
        add("")
        comparables = [c for c in comp["cambios"] if c["comparable"]]
        if comparables:
            add("| Instrumento | Resultado anterior | Resultado actual | Diferencia |")
            add("| --- | --- | --- | --- |")
            for c in comparables:
                add(
                    "| " + c["instrumento"]
                    + " | " + _fmt(c["resultado_antes"], moneda)
                    + " | " + _fmt(c["resultado_ahora"], moneda)
                    + " | " + _fmt(c["delta_resultado"], moneda) + " |"
                )
            add("")
        no_comparables = [c["instrumento"] for c in comp["cambios"] if not c["comparable"]]
        if no_comparables:
            add("Sin comparacion posible por datos faltantes: " + ", ".join(no_comparables) + ".")
            add("")

    # --- 4. riesgos
    add("## 4. Riesgos observables")
    add("")
    margen = analisis["margen"]
    if margen["calculable"]:
        add("- Uso de margen sobre patrimonio: **" + str(margen["uso_pct"]) + "%**"
            + (" (tension alta)" if margen["tenso"] else ""))
    else:
        add("- Uso de margen: no calculable. " + str(margen["motivo"]))

    conc = analisis["concentracion"]
    if conc["calculable"]:
        detalle = ", ".join(
            i["instrumento"] + " " + str(i["porcentaje"]) + "%"
            for i in conc["por_instrumento"]
        )
        add("- Concentracion por nocional (" + conc["cobertura"] + " posiciones): " + detalle)
        if conc.get("parcial"):
            add("  - Calculo parcial: algunas posiciones no tenian tamano ni monto legibles.")
    else:
        add("- Concentracion: no calculable. " + str(conc["motivo"]))

    apalancadas = [
        p["instrumento"] + " (x" + str(p["apalancamiento"]) + ")"
        for p in analisis["posiciones"]
        if p["apalancamiento"] is not None
    ]
    if apalancadas:
        add("- Apalancamiento leido: " + ", ".join(apalancadas))
    sin_apal = [p["instrumento"] for p in analisis["posiciones"] if p["apalancamiento"] is None]
    if sin_apal:
        add("- Apalancamiento no legible en: " + ", ".join(sin_apal))
    add("")

    # --- 5 y 6. recomendaciones
    add("## 5. Recomendaciones por operacion")
    add("")
    add("Categorias posibles: **Mantener**, **Revisar**, **No operar**. "
        "Ninguna es una instruccion de ejecucion.")
    add("")
    for rec in narrativa["recomendaciones"]:
        add("### " + rec["instrumento"] + " - " + rec["categoria"])
        add("")
        add("- **Motivo:** " + rec["motivo"])
        add("- **Evidencia utilizada:** " + str(rec.get("evidencia") or "no indicada"))
        add("- **Nivel de confianza:** " + rec["confianza"])
        faltan = rec.get("datos_faltantes") or []
        add("- **Datos que faltan:** " + (", ".join(faltan) if faltan else "ninguno relevante"))
        add("")

    if reporte.get("sin_recomendacion"):
        add("Sin recomendacion emitida (datos insuficientes): "
            + ", ".join(reporte["sin_recomendacion"]) + ".")
        add("")

    # --- hechos vs interpretacion
    add("## HECHOS")
    add("")
    add("Afirmaciones respaldadas directamente por la captura o por calculo sobre ella.")
    add("")
    for hecho in narrativa["hechos"]:
        add("- " + hecho)
    add("")

    add("## INTERPRETACION")
    add("")
    add("Lectura del analista. No son hechos observados en la captura.")
    add("")
    for idea in narrativa["interpretacion"]:
        add("- " + idea)
    add("")

    # --- 7. conclusion
    add("## 7. Conclusion y revision personal")
    add("")
    add(narrativa["conclusion"])
    add("")

    # --- datos faltantes
    add("## Datos faltantes en esta captura")
    add("")
    if analisis["datos_faltantes"]:
        for item in analisis["datos_faltantes"]:
            add("- " + item)
    else:
        add("- Ninguno: todos los campos previstos se leyeron.")
    add("")

    if analisis["avisos"]:
        add("## Avisos de validacion")
        add("")
        for aviso in analisis["avisos"]:
            add("- " + aviso)
        add("")

    add("---")
    add("")
    add("Generado automaticamente por el sistema de revision diaria. "
        "No constituye asesoria financiera ni promesa de rentabilidad.")
    add("")

    return "\n".join(lineas)


def construir_reporte(analisis, narrativa, extra_validacion):
    """Combina analisis determinista y narrativa en el reporte estructurado."""
    comprobacion = validar_narrativa(narrativa, analisis)
    fecha_datos = analisis["fecha_datos"]
    fecha = fecha_datos.split("T")[0] if fecha_datos else common.now_santiago().date().isoformat()

    return {
        "schema_version": common.SCHEMA_VERSION,
        "fecha": fecha,
        "fecha_datos": fecha_datos,
        "hora_datos": fecha_datos.split("T")[1] if fecha_datos and "T" in fecha_datos else None,
        "generado_en": common.now_santiago().isoformat(),
        "estado": "procesado",
        "fuente": analisis["fuente"],
        "instrumentos": [p["instrumento"] for p in analisis["posiciones"]],
        "datos_extraidos": extra_validacion["datos"],
        "analisis": analisis,
        "narrativa": narrativa,
        "resumen": narrativa["resumen_ejecutivo"],
        "hechos": narrativa["hechos"],
        "interpretacion": narrativa["interpretacion"],
        "recomendaciones": narrativa["recomendaciones"],
        "datos_faltantes": analisis["datos_faltantes"],
        "sin_recomendacion": comprobacion["sin_recomendacion"],
        "demo": False,
    }


def guardar(reporte, json_dir=None, md_dir=None):
    """Escribe el reporte sin sobrescribir ninguno anterior."""
    json_dir = Path(json_dir) if json_dir else common.REPORTS_JSON_DIR
    md_dir = Path(md_dir) if md_dir else common.REPORTS_MD_DIR
    json_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    ruta_json = ruta_disponible(json_dir, reporte["fecha"], ".json")
    # El Markdown reutiliza el mismo nombre base para que el par sea evidente.
    ruta_md = md_dir / (ruta_json.stem + ".md")
    if ruta_md.exists():
        ruta_md = ruta_disponible(md_dir, ruta_json.stem, ".md")

    reporte = dict(reporte)
    reporte["archivo_json"] = common.rel(ruta_json)
    reporte["archivo_md"] = common.rel(ruta_md)

    common.write_json(ruta_json, reporte)
    common.write_text(ruta_md, render_markdown(reporte))
    return {"json": ruta_json, "md": ruta_md, "reporte": reporte}


def actualizar_indice(reporte, indice_path=None):
    """Agrega el informe al indice del historial, en orden descendente."""
    indice_path = Path(indice_path) if indice_path else common.HISTORY_INDEX
    indice = common.read_json(indice_path, default=None)
    if not isinstance(indice, dict) or not isinstance(indice.get("reportes"), list):
        indice = {"schema_version": common.SCHEMA_VERSION, "reportes": []}

    entrada = {
        "fecha": reporte["fecha"],
        "fecha_datos": reporte["fecha_datos"],
        "generado_en": reporte["generado_en"],
        "archivo_json": reporte["archivo_json"],
        "archivo_md": reporte["archivo_md"],
        "instrumentos": reporte["instrumentos"],
        "nivel_atencion": reporte["analisis"]["atencion"]["nivel"],
        "sha256_captura": reporte["fuente"].get("sha256"),
        "demo": reporte.get("demo", False),
    }

    # Reemplaza solo la entrada del mismo archivo; nunca borra otras.
    indice["reportes"] = [
        r for r in indice["reportes"] if r.get("archivo_json") != entrada["archivo_json"]
    ]
    indice["reportes"].append(entrada)
    indice["reportes"].sort(key=lambda r: (r.get("fecha_datos") or "", r.get("generado_en") or ""), reverse=True)
    indice["actualizado_en"] = common.now_santiago().isoformat()
    indice["total"] = len(indice["reportes"])

    common.write_json(indice_path, indice)
    return indice


def ultimo_reporte_valido(indice_path=None):
    """Devuelve el contenido del ultimo informe valido, si existe."""
    indice_path = Path(indice_path) if indice_path else common.HISTORY_INDEX
    indice = common.read_json(indice_path, default=None)
    if not isinstance(indice, dict):
        return None
    for entrada in indice.get("reportes", []):
        if entrada.get("demo"):
            continue
        datos = common.read_json(common.ROOT / entrada["archivo_json"], default=None)
        if datos:
            return datos
    return None
