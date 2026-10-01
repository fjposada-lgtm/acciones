"""Pruebas del flujo de error: correo sin configurar, repo publico, sin captura."""

from __future__ import annotations

import unittest
from unittest import mock

from scripts import cli, guardrails, notify


class ClienteSMTPFalso:
    """Doble de prueba: registra el mensaje en vez de enviarlo."""

    def __init__(self, rechazados=None, explota=False):
        self.rechazados = rechazados or {}
        self.explota = explota
        self.mensajes = []

    def send_message(self, mensaje):
        if self.explota:
            raise OSError("conexion rechazada")
        self.mensajes.append(mensaje)
        return self.rechazados


class TestCorreoNoConfigurado(unittest.TestCase):
    def test_sin_secretos_no_se_intenta_enviar(self):
        resultado = notify.enviar("asunto", "cuerpo", entorno={})
        self.assertEqual(resultado["estado"], "correo_no_configurado")
        self.assertFalse(resultado["enviado"])
        self.assertIsNone(resultado["destinatario"])
        self.assertIn("MAIL_TO", resultado["faltantes"])

    def test_el_detalle_dice_que_el_informe_quedo_guardado(self):
        resultado = notify.enviar("asunto", "cuerpo", entorno={})
        self.assertIn("quedo guardado", resultado["detalle"])
        self.assertNotIn("enviado correctamente", resultado["detalle"])

    def test_falta_un_solo_secreto_y_no_se_envia(self):
        entorno = {
            "MAIL_TO": "destino@example.com",
            "MAIL_FROM": "origen@example.com",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "usuario",
            # falta SMTP_PASSWORD
        }
        cliente = ClienteSMTPFalso()
        resultado = notify.enviar("asunto", "cuerpo", entorno=entorno, cliente_smtp=cliente)
        self.assertEqual(resultado["estado"], "correo_no_configurado")
        self.assertEqual(resultado["faltantes"], ["SMTP_PASSWORD"])
        self.assertEqual(cliente.mensajes, [])

    def test_valores_en_blanco_cuentan_como_faltantes(self):
        entorno = {
            "MAIL_TO": "   ",
            "MAIL_FROM": "origen@example.com",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "usuario",
            "SMTP_PASSWORD": "clave",
        }
        resultado = notify.enviar("asunto", "cuerpo", entorno=entorno)
        self.assertEqual(resultado["estado"], "correo_no_configurado")
        self.assertIn("MAIL_TO", resultado["faltantes"])


class TestCorreoConfigurado(unittest.TestCase):
    def _entorno(self):
        return {
            "MAIL_TO": "destino@example.com",
            "MAIL_FROM": "origen@example.com",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_USERNAME": "usuario",
            "SMTP_PASSWORD": "clave-secreta",
        }

    def test_envio_aceptado_se_reporta_como_enviado(self):
        cliente = ClienteSMTPFalso()
        resultado = notify.enviar("asunto", "cuerpo", entorno=self._entorno(), cliente_smtp=cliente)
        self.assertEqual(resultado["estado"], "enviado")
        self.assertTrue(resultado["enviado"])
        self.assertEqual(len(cliente.mensajes), 1)

    def test_destinatario_rechazado_no_cuenta_como_enviado(self):
        cliente = ClienteSMTPFalso(rechazados={"destino@example.com": (550, b"no existe")})
        resultado = notify.enviar("asunto", "cuerpo", entorno=self._entorno(), cliente_smtp=cliente)
        self.assertEqual(resultado["estado"], "error_envio")
        self.assertFalse(resultado["enviado"])

    def test_fallo_de_conexion_no_cuenta_como_enviado(self):
        cliente = ClienteSMTPFalso(explota=True)
        resultado = notify.enviar("asunto", "cuerpo", entorno=self._entorno(), cliente_smtp=cliente)
        self.assertEqual(resultado["estado"], "error_envio")
        self.assertFalse(resultado["enviado"])

    def test_la_contrasena_nunca_aparece_en_el_resultado(self):
        cliente = ClienteSMTPFalso(explota=True)
        resultado = notify.enviar("asunto", "cuerpo", entorno=self._entorno(), cliente_smtp=cliente)
        self.assertNotIn("clave-secreta", str(resultado))

    def test_la_configuracion_no_expone_la_contrasena_en_claro(self):
        config = notify.configuracion(self._entorno())
        self.assertTrue(config["configurado"])
        # El bloque publico no incluye la contrasena.
        publico = {k: v for k, v in config.items() if not k.startswith("_")}
        self.assertNotIn("clave-secreta", str(publico))


class TestVisibilidadDelRepositorio(unittest.TestCase):
    def test_repositorio_publico_bloquea_el_proceso(self):
        with mock.patch.object(
            guardrails,
            "check_repo_visibility",
            return_value={"checked": True, "repository": "x/y", "visibility": "public", "private": False},
        ):
            with self.assertRaises(PermissionError) as ctx:
                guardrails.assert_safe_to_process("x/y")
        self.assertIn("PUBLICO", str(ctx.exception))
        self.assertIn("privado", str(ctx.exception))

    def test_repositorio_privado_permite_continuar(self):
        with mock.patch.object(
            guardrails,
            "check_repo_visibility",
            return_value={"checked": True, "repository": "x/y", "visibility": "private", "private": True},
        ):
            info = guardrails.assert_safe_to_process("x/y")
        self.assertTrue(info["private"])

    def test_visibilidad_desconocida_falla_por_defecto(self):
        with mock.patch.object(
            guardrails, "check_repo_visibility", side_effect=guardrails.VisibilityUnknown("sin red")
        ):
            with self.assertRaises(guardrails.VisibilityUnknown):
                guardrails.assert_safe_to_process("x/y")

    def test_visibilidad_desconocida_avisa_si_se_permite(self):
        with mock.patch.object(
            guardrails, "check_repo_visibility", side_effect=guardrails.VisibilityUnknown("sin red")
        ):
            info = guardrails.assert_safe_to_process("x/y", allow_unknown=True)
        self.assertFalse(info["checked"])
        self.assertIn("No subas capturas", info["aviso"])

    def test_sin_repositorio_no_se_asume_privado(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(guardrails.VisibilityUnknown):
                guardrails.check_repo_visibility()


class TestVentanaHoraria(unittest.TestCase):
    def test_el_comando_informa_la_hora_de_santiago(self):
        parser = cli.build_parser()
        args = parser.parse_args(["ventana-horaria", "--hora-objetivo", "8"])
        codigo = args.func(args)
        self.assertEqual(codigo, 0)


if __name__ == "__main__":
    unittest.main()
