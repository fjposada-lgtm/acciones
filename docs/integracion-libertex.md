# Entrada de datos desde Libertex: lo que se investigó y lo que se implementó

Fecha de la investigación: **1 de octubre de 2026**.

## Resumen

**No se encontró una API REST oficial y pública documentada para clientes
retail de Libertex.** Por eso la primera versión de este sistema lee una
**captura de pantalla**, con la limitación declarada abiertamente.

**La lectura de una captura de pantalla NO es una integración oficial de
Libertex.** Es una transcripción visual hecha por un modelo, con los errores
que eso implica. El sistema está construido para que esa limitación sea visible
en cada informe, no para disimularla.

## Qué se buscó

| Búsqueda | Resultado |
| --- | --- |
| API REST pública documentada para clientes retail | No encontrada |
| Portal de desarrolladores de Libertex | No encontrado |
| Exportación autorizada de datos de la cuenta | **Sí existe** (ver abajo) |

Fuentes consultadas: el sitio y centro de ayuda de Libertex, su página de
plataformas y la documentación de MetaTrader.

## Lo que sí existe: exportación oficial autorizada

Según el centro de ayuda de Libertex, la cuenta ofrece exportación de datos por
dos vías, ambas autorizadas y usando las credenciales propias del titular:

1. **Descarga CSV desde la plataforma.** En la sección *Closed trades* hay un
   botón de descarga que entrega los datos en `.csv`. En la versión de
   escritorio, los informes están en el menú del usuario, opción *Reports*.

2. **Extracto de MetaTrader 4/5**, para las cuentas que operan con MetaTrader.
   En MT4: pestaña *Account History* → clic derecho → *Save as Report* (`.htm`).
   En MT5: pestaña *History* → clic derecho → *Report* → *HTML*.

**Limitación importante de ambas:** cubren operaciones **cerradas**. Para la
foto de las **posiciones abiertas** —que es lo que interesa en la revisión
diaria— la captura de pantalla sigue siendo, por ahora, la vía disponible.

## Lo que NO se hizo, deliberadamente

El sistema **no** hace nada de esto, y no debe añadirse:

- Inventar o adivinar endpoints de API.
- Usar interfaces internas o APIs no documentadas de Libertex.
- Guardar o usar contraseñas, cookies o tokens de sesión de Libertex.
- Automatizar el inicio de sesión o raspar la web de Libertex.
- Abrir, cerrar o modificar operaciones; hacer depósitos o retiros.

Varias de estas prácticas, además de ser frágiles, infringen el acuerdo de
cliente de Libertex.

## Ruta de migración recomendada

La entrada está aislada a propósito en [`scripts/inbox.py`](../scripts/inbox.py)
y en el paso de extracción del workflow. El resto del sistema —validación,
análisis, informe, panel— consume el JSON normalizado que define
[`scripts/schema.py`](../scripts/schema.py) y no sabe de dónde salió.

Para migrar a la exportación oficial cuando convenga:

1. Escribir un lector de CSV que produzca el mismo JSON del esquema versión 1.
2. Registrarlo como una fuente alternativa con `fuente.tipo = "csv_libertex"`.
3. No hace falta tocar `schema.py`, `analyze.py`, `report.py` ni el panel.

Si en el futuro Libertex publica una API oficial para clientes retail,
**verifica la documentación antes de implementarla** y usa únicamente
credenciales emitidas para ese fin, guardadas como GitHub Secrets.

## Fuentes

- [Libertex — Plataforma de trading](https://libertex.com/platforms/libertex)
- [Centro de ayuda de Libertex — informes de transacciones](https://cs.libertex.org/en/articles/9399022-how-can-i-view-libertex-transaction-reports)
- [MetaTrader 4 — History Center](https://www.metatrader4.com/en/trading-platform/help/service/history_center)
- [Libertex — Acuerdo de cliente (PDF)](https://libertex.org/sites/default/files/2023-08/2023.08.07.%20Client%20agreement%20EN.pdf)
