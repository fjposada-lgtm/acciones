"""Datos de apoyo para las pruebas.

Son valores inventados a proposito, usados solo para ejercitar el codigo. Nunca
se escriben en data/reports ni en reports/.
"""

from __future__ import annotations

import copy

from scripts import common


def fecha_reciente_iso(horas_atras=1):
    import datetime as dt

    return (common.now_santiago() - dt.timedelta(hours=horas_atras)).isoformat()


def extraccion_valida(**overrides):
    """Extraccion completa y legible, fechada hace una hora."""
    base = {
        "schema_version": 1,
        "fuente": {
            "tipo": "captura_pantalla",
            "archivo": "data/inbox/2026-10-01T09-00_libertex.png",
            "sha256": "a" * 64,
            "fecha_visible": fecha_reciente_iso(1),
            "plataforma": "Libertex",
        },
        "calidad_imagen": {"legible": True, "notas": "Texto nitido."},
        "cuenta": {
            "saldo": {"valor": 1000.0, "moneda": "USD"},
            "patrimonio": {"valor": 980.0, "moneda": "USD"},
            "margen_usado": {"valor": 200.0, "moneda": "USD"},
            "margen_libre": {"valor": 780.0, "moneda": "USD"},
            "resultado_total": {"valor": -20.0, "moneda": "USD", "tipo": "no_realizada"},
        },
        "posiciones": [
            {
                "instrumento": "AAPL",
                "tipo_producto": "CFD",
                "direccion": "compra",
                "tamano": {"valor": 10, "moneda": None},
                "monto": {"valor": 2000.0, "moneda": "USD"},
                "apalancamiento": 5,
                "precio_entrada": {"valor": 200.0, "moneda": "USD"},
                "precio_actual": {"valor": 198.0, "moneda": "USD"},
                "resultado": {"valor": -20.0, "moneda": "USD", "tipo": "no_realizada"},
                "margen": {"valor": 400.0, "moneda": "USD"},
                "stop_loss": None,
                "take_profit": {"valor": 215.0, "moneda": "USD"},
                "costos": {"valor": -1.2, "moneda": "USD"},
                "abierta_en": "2026-09-28",
            }
        ],
        "notas_extraccion": None,
    }
    datos = copy.deepcopy(base)
    datos.update(copy.deepcopy(overrides))
    return datos


def narrativa_valida(instrumento="AAPL"):
    return {
        "resumen_ejecutivo": "La cuenta muestra una posicion abierta con resultado negativo leve.",
        "hechos": ["La captura muestra 1 posicion abierta."],
        "interpretacion": ["El uso de margen deja holgura."],
        "recomendaciones": [
            {
                "instrumento": instrumento,
                "categoria": "Revisar",
                "motivo": "No se leyo stop loss y el resultado es negativo.",
                "evidencia": "analisis.posiciones[0]: resultado -20,0 USD.",
                "confianza": "media",
                "datos_faltantes": ["stop_loss"],
            }
        ],
        "conclusion": "Revisar personalmente si corresponde fijar un stop loss.",
    }
