"""Pruebas del analisis, la narrativa y la escritura del historial."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import analyze, common, report, schema
from tests import fixtures


def _analisis_base():
    validacion = schema.validar_extraccion(fixtures.extraccion_valida())
    assert validacion["valida"], validacion["errores"]
    return validacion, analyze.analizar(validacion, None)


class TestAnalisis(unittest.TestCase):
    def test_calculos_deterministas(self):
        _, analisis = _analisis_base()
        posicion = analisis["posiciones"][0]
        # resultado -20 sobre margen 400 = -5%
        self.assertEqual(posicion["resultado_pct_margen"], -5.0)
        # precio 200 -> 198 = -1%
        self.assertEqual(posicion["variacion_precio_pct"], -1.0)
        # nocional = 10 x 200
        self.assertEqual(posicion["nocional"], 2000.0)

    def test_sin_margen_no_se_calcula_porcentaje(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["margen"] = None
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        self.assertIsNone(analisis["posiciones"][0]["resultado_pct_margen"])

    def test_margen_cero_no_divide_por_cero(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["margen"] = {"valor": 0.0, "moneda": "USD"}
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        self.assertIsNone(analisis["posiciones"][0]["resultado_pct_margen"])

    def test_bandera_de_cfd_y_de_falta_de_stop_loss(self):
        _, analisis = _analisis_base()
        banderas = analisis["posiciones"][0]["banderas"]
        self.assertTrue(any(b.startswith("producto_cfd") for b in banderas))
        self.assertTrue(any(b.startswith("sin_stop_loss_visible") for b in banderas))

    def test_apalancamiento_alto_sube_el_nivel_de_atencion(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["apalancamiento"] = 20
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        self.assertIn(analisis["atencion"]["nivel"], ("medio", "alto"))
        self.assertTrue(any("apalancamiento alto" in m for m in analisis["atencion"]["motivos"]))

    def test_concentracion_no_calculable_sin_tamanos(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["tamano"] = None
        datos["posiciones"][0]["monto"] = None
        datos["posiciones"][0]["precio_entrada"] = None
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        self.assertFalse(analisis["concentracion"]["calculable"])
        self.assertIsNotNone(analisis["concentracion"]["motivo"])

    def test_margen_de_cuenta_se_calcula(self):
        _, analisis = _analisis_base()
        # 200 usado sobre 980 de patrimonio
        self.assertAlmostEqual(analisis["margen"]["uso_pct"], 20.41, places=1)
        self.assertFalse(analisis["margen"]["tenso"])

    def test_sin_informe_anterior_no_hay_comparacion(self):
        _, analisis = _analisis_base()
        self.assertFalse(analisis["comparacion"]["hay_anterior"])
        self.assertIsNotNone(analisis["comparacion"]["nota"])

    def test_comparacion_detecta_nuevas_y_cerradas(self):
        _, analisis = _analisis_base()
        anterior = {
            "fecha_datos": "2026-09-30T09:00:00-03:00",
            "analisis": {"posiciones": [{"instrumento": "TSLA", "resultado": 5.0}]},
        }
        nuevo = analyze.analizar(_analisis_base()[0], anterior)
        self.assertIn("AAPL", nuevo["comparacion"]["nuevas"])
        self.assertIn("TSLA", nuevo["comparacion"]["cerradas"])
        del analisis

    def test_comparacion_calcula_la_diferencia_de_resultado(self):
        validacion, _ = _analisis_base()
        anterior = {
            "fecha_datos": "2026-09-30T09:00:00-03:00",
            "analisis": {"posiciones": [{"instrumento": "AAPL", "resultado": -50.0}]},
        }
        analisis = analyze.analizar(validacion, anterior)
        cambio = analisis["comparacion"]["cambios"][0]
        self.assertEqual(cambio["delta_resultado"], 30.0)
        self.assertTrue(cambio["comparable"])

    def test_comparacion_no_inventa_diferencia_si_falta_un_lado(self):
        validacion, _ = _analisis_base()
        anterior = {
            "fecha_datos": "2026-09-30T09:00:00-03:00",
            "analisis": {"posiciones": [{"instrumento": "AAPL", "resultado": None}]},
        }
        analisis = analyze.analizar(validacion, anterior)
        cambio = analisis["comparacion"]["cambios"][0]
        self.assertIsNone(cambio["delta_resultado"])
        self.assertFalse(cambio["comparable"])


class TestNarrativa(unittest.TestCase):
    def test_narrativa_valida_pasa(self):
        _, analisis = _analisis_base()
        resultado = report.validar_narrativa(fixtures.narrativa_valida(), analisis)
        self.assertEqual(resultado["sin_recomendacion"], [])

    def test_categoria_no_permitida_se_rechaza(self):
        _, analisis = _analisis_base()
        narrativa = fixtures.narrativa_valida()
        narrativa["recomendaciones"][0]["categoria"] = "Comprar ya"
        with self.assertRaises(report.NarrativaInvalida):
            report.validar_narrativa(narrativa, analisis)

    def test_recomendacion_sobre_instrumento_inexistente_se_rechaza(self):
        _, analisis = _analisis_base()
        narrativa = fixtures.narrativa_valida(instrumento="NVDA")
        with self.assertRaises(report.NarrativaInvalida):
            report.validar_narrativa(narrativa, analisis)

    def test_falta_de_confianza_se_rechaza(self):
        _, analisis = _analisis_base()
        narrativa = fixtures.narrativa_valida()
        del narrativa["recomendaciones"][0]["confianza"]
        with self.assertRaises(report.NarrativaInvalida):
            report.validar_narrativa(narrativa, analisis)

    def test_falta_una_seccion_se_rechaza(self):
        _, analisis = _analisis_base()
        narrativa = fixtures.narrativa_valida()
        del narrativa["conclusion"]
        with self.assertRaises(report.NarrativaInvalida):
            report.validar_narrativa(narrativa, analisis)


class TestEscrituraHistorial(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.json_dir = self.dir / "data" / "reports"
        self.md_dir = self.dir / "reports"
        self.indice = self.dir / "index.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _reporte(self):
        validacion, analisis = _analisis_base()
        return report.construir_reporte(analisis, fixtures.narrativa_valida(), validacion)

    def test_guarda_json_y_markdown(self):
        guardado = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        self.assertTrue(guardado["json"].exists())
        self.assertTrue(guardado["md"].exists())
        texto = guardado["md"].read_text(encoding="utf-8")
        self.assertIn("## HECHOS", texto)
        self.assertIn("## INTERPRETACION", texto)
        self.assertIn("Informe diario de operaciones", texto)

    def test_no_sobrescribe_un_informe_del_mismo_dia(self):
        primero = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        segundo = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        self.assertNotEqual(primero["json"], segundo["json"])
        self.assertNotEqual(primero["md"], segundo["md"])
        self.assertTrue(primero["json"].exists())
        self.assertEqual(len(list(self.json_dir.glob("*.json"))), 2)

    def test_el_markdown_marca_los_cfd(self):
        guardado = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        texto = guardado["md"].read_text(encoding="utf-8")
        self.assertIn("contratos por diferencia", texto)
        self.assertNotIn("acciones en propiedad", texto)

    def test_el_markdown_muestra_no_disponible_en_vez_de_inventar(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["precio_actual"] = None
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        reporte = report.construir_reporte(analisis, fixtures.narrativa_valida(), validacion)
        guardado = report.guardar(reporte, self.json_dir, self.md_dir)
        texto = guardado["md"].read_text(encoding="utf-8")
        self.assertIn("no disponible", texto)

    def test_el_markdown_advierte_datos_desactualizados(self):
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = fixtures.fecha_reciente_iso(
            common.MAX_CAPTURE_AGE_HOURS + 20
        )
        validacion = schema.validar_extraccion(datos)
        analisis = analyze.analizar(validacion, None)
        reporte = report.construir_reporte(analisis, fixtures.narrativa_valida(), validacion)
        guardado = report.guardar(reporte, self.json_dir, self.md_dir)
        texto = guardado["md"].read_text(encoding="utf-8")
        self.assertIn("ADVERTENCIA", texto)
        self.assertIn("no representan el mercado actual", texto)

    def test_el_indice_acumula_sin_perder_entradas(self):
        primero = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        report.actualizar_indice(primero["reporte"], self.indice)
        segundo = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        indice = report.actualizar_indice(segundo["reporte"], self.indice)
        self.assertEqual(indice["total"], 2)
        archivos = {r["archivo_json"] for r in indice["reportes"]}
        self.assertEqual(len(archivos), 2)

    def test_el_indice_no_duplica_el_mismo_archivo(self):
        guardado = report.guardar(self._reporte(), self.json_dir, self.md_dir)
        report.actualizar_indice(guardado["reporte"], self.indice)
        indice = report.actualizar_indice(guardado["reporte"], self.indice)
        self.assertEqual(indice["total"], 1)

    def test_el_reporte_no_se_marca_como_demo(self):
        reporte = self._reporte()
        self.assertFalse(reporte["demo"])


if __name__ == "__main__":
    unittest.main()
