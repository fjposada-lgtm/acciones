"""Pruebas de validacion: imagenes ilegibles, campos faltantes y fechas."""

from __future__ import annotations

import datetime as dt
import unittest

from scripts import common, schema
from tests import fixtures


class TestImagenIlegible(unittest.TestCase):
    def test_imagen_marcada_ilegible_no_pasa(self):
        datos = fixtures.extraccion_valida()
        datos["calidad_imagen"] = {"legible": False, "notas": "Foto borrosa."}
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertEqual(resultado["estado"], "datos_insuficientes")
        self.assertTrue(any("no legible" in e for e in resultado["errores"]))

    def test_falta_bloque_calidad_no_pasa(self):
        datos = fixtures.extraccion_valida()
        del datos["calidad_imagen"]
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])

    def test_captura_sin_posiciones_ni_cuenta_no_pasa(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"] = []
        datos["cuenta"] = {}
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertTrue(
            any("ni una posicion analizable" in e for e in resultado["errores"])
        )


class TestCamposFaltantes(unittest.TestCase):
    def test_campos_ilegibles_quedan_como_no_disponibles(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["precio_actual"] = None
        datos["posiciones"][0]["margen"] = None
        resultado = schema.validar_extraccion(datos)
        self.assertTrue(resultado["valida"])
        posicion = resultado["datos"]["posiciones"][0]
        self.assertIsNone(posicion["precio_actual"])
        self.assertIsNone(posicion["margen"])
        self.assertIn("precio_actual", posicion["datos_faltantes"])
        self.assertIn("margen", posicion["datos_faltantes"])

    def test_no_se_inventa_el_resultado_a_partir_de_precios(self):
        """Si falta el resultado, no debe aparecer calculado desde los precios."""
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["resultado"] = None
        resultado = schema.validar_extraccion(datos)
        posicion = resultado["datos"]["posiciones"][0]
        self.assertIsNone(posicion["resultado"])
        self.assertIn("resultado", posicion["datos_faltantes"])

    def test_posicion_solo_con_nombre_se_marca_insuficiente(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0] = {"instrumento": "TSLA"}
        resultado = schema.validar_extraccion(datos)
        posicion = resultado["datos"]["posiciones"][0]
        self.assertFalse(posicion["suficiente"])
        self.assertTrue(any("solo se pudo leer el nombre" in a for a in resultado["avisos"]))

    def test_posicion_sin_instrumento_es_error(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["instrumento"] = None
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])

    def test_valor_no_numerico_es_error_y_no_se_convierte(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["margen"] = {"valor": "400 USD", "moneda": "USD"}
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertIsNone(resultado["datos"]["posiciones"][0]["margen"])

    def test_direccion_invalida_no_se_adivina(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["direccion"] = "long"
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertEqual(
            resultado["datos"]["posiciones"][0]["direccion"], "no_disponible"
        )

    def test_cfd_no_se_convierte_en_accion(self):
        datos = fixtures.extraccion_valida()
        resultado = schema.validar_extraccion(datos)
        self.assertEqual(resultado["datos"]["posiciones"][0]["tipo_producto"], "CFD")

    def test_producto_desconocido_queda_no_disponible(self):
        datos = fixtures.extraccion_valida()
        datos["posiciones"][0]["tipo_producto"] = None
        resultado = schema.validar_extraccion(datos)
        self.assertEqual(
            resultado["datos"]["posiciones"][0]["tipo_producto"], "no_disponible"
        )


class TestFechas(unittest.TestCase):
    def test_captura_reciente_no_esta_desactualizada(self):
        resultado = schema.validar_extraccion(fixtures.extraccion_valida())
        self.assertTrue(resultado["valida"])
        self.assertFalse(resultado["desactualizada"])
        self.assertEqual(resultado["origen_fecha"], "captura")

    def test_captura_antigua_se_marca_desactualizada(self):
        horas = common.MAX_CAPTURE_AGE_HOURS + 10
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = fixtures.fecha_reciente_iso(horas)
        resultado = schema.validar_extraccion(datos)
        self.assertTrue(resultado["valida"], resultado["errores"])
        self.assertTrue(resultado["desactualizada"])
        self.assertTrue(any("desactualiz" in a or "antiguedad" in a for a in resultado["avisos"]))

    def test_fecha_en_el_futuro_es_error(self):
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = fixtures.fecha_reciente_iso(-48)
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertTrue(any("futuro" in e for e in resultado["errores"]))

    def test_sin_fecha_visible_usa_el_nombre_del_archivo(self):
        hoy = common.now_santiago().date().isoformat()
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = None
        datos["fuente"]["archivo"] = "data/inbox/" + hoy + "_libertex.png"
        resultado = schema.validar_extraccion(datos)
        self.assertTrue(resultado["valida"], resultado["errores"])
        self.assertEqual(resultado["origen_fecha"], "nombre_archivo")
        self.assertTrue(any("nombre del archivo" in a for a in resultado["avisos"]))

    def test_sin_fecha_en_ningun_lado_es_error(self):
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = None
        datos["fuente"]["archivo"] = "data/inbox/captura.png"
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertTrue(any("fecha utilizable" in e for e in resultado["errores"]))
        self.assertIn("fecha de los datos", resultado["datos_faltantes"])

    def test_fecha_ilegible_no_se_adivina(self):
        datos = fixtures.extraccion_valida()
        datos["fuente"]["fecha_visible"] = "ayer por la tarde"
        datos["fuente"]["archivo"] = "data/inbox/captura.png"
        resultado = schema.validar_extraccion(datos)
        self.assertFalse(resultado["valida"])
        self.assertIsNone(resultado["fecha_datos"])

    def test_formato_dia_mes_ano_se_interpreta(self):
        momento, nota = common.parse_visible_datetime("01/10/2026 14:32")
        self.assertIsNotNone(momento)
        self.assertEqual((momento.day, momento.month, momento.year), (1, 10, 2026))
        del nota

    def test_fecha_del_nombre_de_archivo_con_hora(self):
        momento = common.datetime_from_filename("2026-10-01T09-30_libertex.png")
        self.assertIsNotNone(momento)
        self.assertEqual((momento.hour, momento.minute), (9, 30))


class TestHusoHorario(unittest.TestCase):
    def test_hay_hora_de_santiago(self):
        ahora = common.now_santiago()
        self.assertIsNotNone(ahora.tzinfo)
        desfase = ahora.utcoffset()
        self.assertIn(desfase, (dt.timedelta(hours=-3), dt.timedelta(hours=-4)))

    def test_respaldo_sin_zoneinfo_da_un_desfase_chileno(self):
        enero = dt.datetime(2026, 1, 15)
        julio = dt.datetime(2026, 7, 15)
        self.assertEqual(common._chile_offset_fallback(enero), dt.timedelta(hours=-3))
        self.assertEqual(common._chile_offset_fallback(julio), dt.timedelta(hours=-4))


if __name__ == "__main__":
    unittest.main()
