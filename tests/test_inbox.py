"""Pruebas de la bandeja: deteccion de capturas nuevas y duplicadas."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import common, inbox


class TestBandeja(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.inbox = self.dir / "inbox"
        self.inbox.mkdir()
        self.registro = self.dir / "processed.json"

    def tearDown(self):
        self._tmp.cleanup()

    def _crear(self, nombre, contenido=b"imagen-falsa"):
        ruta = self.inbox / nombre
        ruta.write_bytes(contenido)
        return ruta

    def test_bandeja_vacia_da_sin_datos_nuevos(self):
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "sin_datos_nuevos")
        self.assertIsNone(resultado["captura"])

    def test_detecta_una_captura_nueva(self):
        self._crear("2026-10-01_libertex.png")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "pendiente")
        self.assertTrue(resultado["captura"]["archivo"].endswith("2026-10-01_libertex.png"))

    def test_ignora_archivos_que_no_son_imagen(self):
        self._crear("notas.txt")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "sin_datos_nuevos")

    def test_elige_la_captura_mas_reciente_por_nombre(self):
        self._crear("2026-09-30_libertex.png", b"vieja")
        self._crear("2026-10-01_libertex.png", b"nueva")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertTrue(resultado["captura"]["archivo"].endswith("2026-10-01_libertex.png"))

    def test_captura_ya_procesada_no_se_repite(self):
        ruta = self._crear("2026-10-01_libertex.png")
        sha = common.sha256_file(ruta)
        inbox.marcar_procesada(sha, {"fecha_proceso": "2026-10-01T08:00:00-03:00"}, self.registro)
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "sin_datos_nuevos")
        self.assertEqual(len(resultado["duplicadas"]), 1)

    def test_misma_imagen_con_otro_nombre_es_duplicada(self):
        """El duplicado se detecta por contenido, no por nombre de archivo."""
        ruta = self._crear("2026-10-01_libertex.png", b"contenido-identico")
        sha = common.sha256_file(ruta)
        inbox.marcar_procesada(sha, {"fecha_proceso": "x"}, self.registro)
        self._crear("2026-10-02_otra-copia.png", b"contenido-identico")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "sin_datos_nuevos")

    def test_captura_nueva_junto_a_una_procesada(self):
        vieja = self._crear("2026-09-30_libertex.png", b"vieja")
        inbox.marcar_procesada(common.sha256_file(vieja), {"fecha_proceso": "x"}, self.registro)
        self._crear("2026-10-01_libertex.png", b"nueva")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "pendiente")
        self.assertTrue(resultado["captura"]["archivo"].endswith("2026-10-01_libertex.png"))

    def test_marcar_procesada_es_idempotente(self):
        ruta = self._crear("2026-10-01_libertex.png")
        sha = common.sha256_file(ruta)
        inbox.marcar_procesada(sha, {"fecha_proceso": "a"}, self.registro)
        registro = inbox.marcar_procesada(sha, {"fecha_proceso": "b"}, self.registro)
        self.assertEqual(len(registro["procesadas"]), 1)

    def test_registro_corrupto_no_rompe_la_deteccion(self):
        self.registro.write_text("{no es json", encoding="utf-8")
        self._crear("2026-10-01_libertex.png")
        resultado = inbox.detectar_pendiente(self.inbox, self.registro)
        self.assertEqual(resultado["estado"], "pendiente")


if __name__ == "__main__":
    unittest.main()
