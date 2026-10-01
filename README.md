# acciones — revisión diaria de operaciones de Libertex

Sistema que revisa a diario las operaciones de Libertex de Francisco a partir
de una captura de pantalla, guarda el historial, genera recomendaciones y
entrega un informe diario en español.

> **El sistema solo analiza y recomienda.** No abre, cierra ni modifica
> operaciones, y no hace depósitos ni retiros. No existe ninguna ruta de código
> que pueda hacerlo.

---

## ⚠️ Estado actual: hay que hacer dos cosas antes de usarlo

| # | Acción | Estado |
| --- | --- | --- |
| 1 | **Hacer privado el repositorio** | ❌ Pendiente — hoy es **público** |
| 2 | **Configurar el secreto `CLAUDE_CODE_OAUTH_TOKEN`** | ❌ Pendiente |

Mientras el repositorio sea público, el workflow **se detiene solo** y no
procesa ninguna captura. Es deliberado.

### 1. Hacer privado el repositorio

`Settings` → `General` → abajo del todo, `Danger Zone` → `Change repository
visibility` → **Make private**.

> **No subas ninguna captura antes de hacer esto.** Borrarla después no la
> elimina del historial de Git.

### 2. Configurar el token de Claude

Ver [Configuración de Claude](#configuración-de-claude) más abajo.

---

## Cómo funciona

```
data/inbox/captura.png
        │
        ├─ 0. Barrera: ¿el repositorio es privado?  ── si es público, se detiene
        │
        ├─ 1. Detección de captura nueva        (Python, por SHA-256)
        │
        ├─ 2. Extracción                        (Claude lee la imagen → JSON)
        │
        ├─ 3. Validación                        (Python: legible, fecha, campos)
        │
        ├─ 4. Cálculos                          (Python: margen, concentración, deltas)
        │
        ├─ 5. Redacción                         (Claude escribe sobre lo ya validado)
        │
        ├─ 6. Informe                           (Python arma el .md y el .json)
        │
        ├─ 7. Historial                         (sin sobrescribir nada anterior)
        │
        └─ 8. Correo                            (opcional; si no hay secretos, no se envía)
```

El reparto es intencional: **Claude lee y redacta; el código calcula y valida.**
Ninguna cifra del informe sale de texto libre generado por un modelo.

---

## Instalación

No hay dependencias que instalar. Todo usa la librería estándar de Python 3.11+.

```bash
git clone https://github.com/fjposada-lgtm/acciones.git
cd acciones
python3 --version   # debe ser 3.11 o superior
```

En **GitHub Actions no hay que instalar nada**: el runner ya trae Python.

En **Windows**, si `python` abre la Microsoft Store, instala Python desde
[python.org](https://www.python.org/downloads/) o con `winget install Python.Python.3.12`.

---

## Uso

### Subir una captura

Ver la guía detallada en [`data/inbox/LEEME.md`](data/inbox/LEEME.md).

Resumen: en github.com, entra a `data/inbox/`, pulsa **Add file → Upload
files**, arrastra la imagen y confirma el commit. El workflow arranca solo.

Nombra el archivo como `2026-10-01_libertex.png`. Si la captura muestra la
fecha y hora de Libertex, mejor: el sistema prefiere ese dato y el nombre queda
solo como respaldo.

### Ejecución manual

En GitHub: pestaña **Actions** → **Revisión diaria de operaciones** → **Run
workflow**.

En local, paso a paso:

```bash
export GITHUB_REPOSITORY=fjposada-lgtm/acciones

python3 -m scripts.cli check-repo                  # falla si el repo es público
python3 -m scripts.cli scan                        # busca captura nueva
# (aquí Claude genera data/extracted/<sha>.json)
python3 -m scripts.cli validate --extraccion data/extracted/<sha>.json
python3 -m scripts.cli analyze
# (aquí Claude genera data/state/narrativa.json)
python3 -m scripts.cli finalize
python3 -m scripts.cli notify --reporte data/reports/2026-10-01.json
```

`python3 -m scripts.cli --help` lista todos los comandos.

### Ver el panel

El panel lee archivos JSON, así que necesita un servidor HTTP. Abrir
`index.html` con doble clic **no funciona**: el navegador bloquea `file://`.

```bash
python3 -m http.server 8000
# abrir http://localhost:8000
```

El panel muestra el informe más reciente, la fecha y hora de los datos, el
estado del proceso, las alertas y el historial completo. Se ve bien en
computador y en móvil.

---

## Horario de la revisión diaria

La revisión programada corre a las **08:00 de `America/Santiago`**.

### Cómo se resuelve el cambio de hora de Chile

El cron de GitHub Actions **siempre se interpreta en UTC** y no entiende de
horario de verano. Chile cambia de huso dos veces al año:

| Período | Huso | 08:00 en Chile equivale a |
| --- | --- | --- |
| Horario de verano (≈ septiembre → abril) | UTC−3 | **11:00 UTC** |
| Horario estándar (≈ abril → septiembre) | UTC−4 | **12:00 UTC** |

La solución tiene dos partes:

1. El workflow programa **ambas** horas: `0 11 * * *` y `0 12 * * *`.
2. El primer paso ejecuta `python -m scripts.cli ventana-horaria`, que consulta
   la hora real en Santiago con `zoneinfo` (que sí conoce las reglas chilenas,
   incluidos los cambios de fecha que decrete el gobierno). **La ejecución que
   no corresponde al huso de hoy se detiene de inmediato** y no genera informe.

Así siempre corre exactamente una vez al día, sin depender de que yo adivine
las fechas del cambio de hora.

> GitHub Actions puede retrasar los cron de alta demanda unos minutos. La
> tolerancia por defecto es de 1 hora (`--tolerancia`).

---

## Configuración de Claude

El sistema usa **Claude Code con tu suscripción existente**, mediante
autenticación OAuth. **No usa la API de Claude Console, no requiere API key de
pago y no habilita créditos ni recarga automática.**

### Generar el token

En tu computador, con Claude Code instalado y con tu sesión iniciada:

```bash
claude setup-token
```

El comando abre el flujo OAuth oficial en el navegador y, al terminar, imprime
un token que empieza por `sco-at-`.

### Guardarlo en GitHub Secrets

1. `Settings` → `Secrets and variables` → `Actions`.
2. **New repository secret**.
3. Nombre: `CLAUDE_CODE_OAUTH_TOKEN`
4. Valor: el token generado.

> **Nunca** pegues el token en un archivo del repositorio, en un comentario ni
> en un log. Los secretos de GitHub se enmascaran automáticamente en la salida
> de Actions.

El token caduca. Cuando el workflow falle con un error de autenticación,
vuelve a ejecutar `claude setup-token` y actualiza el secreto.

### Si no puedes configurar la autenticación por suscripción

El sistema **no cae automáticamente a una alternativa de pago**: eso está
descartado por diseño. Si el OAuth no se puede configurar:

- El workflow fallará en el paso de extracción con un error de autenticación.
- Todo lo demás —detección, validación, cálculos, informe, historial, panel—
  **funciona igual sin Claude**, siempre que alguien produzca a mano los
  archivos `data/extracted/<sha>.json` y `data/state/narrativa.json` siguiendo
  los formatos de [`prompts/extraer.md`](prompts/extraer.md) y
  [`prompts/redactar.md`](prompts/redactar.md).
- La ruta local es la de la sección [Ejecución manual](#ejecución-manual), con
  Claude Code corriendo en tu máquina con tu sesión normal, sin cobros.

---

## Configuración opcional del correo

El envío por correo está **desactivado hasta que tú lo configures**. No hay
ningún destinatario escrito en el código.

Si faltan secretos, el sistema **no intenta enviar nada**: guarda el informe,
muestra «correo no configurado» en el panel y lo dice en el log. **Nunca
informa que el correo fue enviado si no hubo confirmación del servidor SMTP.**

Para habilitarlo, agrega estos secretos en `Settings` → `Secrets and variables`
→ `Actions`:

| Secreto | Obligatorio | Ejemplo | Para qué |
| --- | --- | --- | --- |
| `MAIL_TO` | Sí | `francisco@ejemplo.cl` | Destinatario del informe |
| `MAIL_FROM` | Sí | `informes@ejemplo.cl` | Remitente |
| `SMTP_HOST` | Sí | `smtp.gmail.com` | Servidor SMTP |
| `SMTP_USERNAME` | Sí | `informes@ejemplo.cl` | Usuario SMTP |
| `SMTP_PASSWORD` | Sí | *(contraseña de aplicación)* | Contraseña SMTP |
| `SMTP_PORT` | No | `587` (por defecto) | Puerto |
| `SMTP_SECURITY` | No | `starttls` (por defecto), `ssl` o `none` | Cifrado |

Con Gmail hace falta una **contraseña de aplicación**, no la contraseña normal
de la cuenta.

Los cinco primeros son obligatorios: si falta **uno solo**, no se intenta el
envío.

---

## Privacidad

- **El repositorio debe ser privado.** Las capturas y los informes contienen
  posiciones, montos y resultados. El workflow se bloquea si detecta que el
  repositorio es público.
- **Borrar un archivo no lo borra del historial de Git.** Una imagen subida a
  un repositorio público queda en los commits anteriores aunque la elimines
  después.
- **Nunca se guardan contraseñas, cookies ni tokens** en archivos versionados
  ni en logs. Los secretos van en GitHub Secrets y GitHub los enmascara.
- **El sistema no usa credenciales de Libertex.** No inicia sesión, no raspa la
  web y no toca APIs internas.
- **Permisos mínimos en Actions:** el workflow de revisión solo pide
  `contents: write` (para guardar el informe). El de pruebas solo
  `contents: read`.
- Se guarda únicamente lo necesario para el análisis y la comparación entre
  días.

---

## Limitaciones

Conviene tenerlas presentes al leer cualquier informe:

1. **La lectura de capturas no es una integración oficial de Libertex.** Es
   transcripción visual hecha por un modelo y puede equivocarse. Ver
   [`docs/integracion-libertex.md`](docs/integracion-libertex.md).
2. **Solo se lee lo que está visible.** Lo que no se vea en la imagen no existe
   para el sistema; aparece como «no disponible» y nunca se estima.
3. **Los datos son del momento de la captura, no del momento del informe.** Si
   la captura tiene más de 36 horas, el informe lo advierte y no presenta los
   precios como actuales.
4. **Las recomendaciones son apoyo a una decisión humana**, no órdenes
   ejecutables, y se limitan a tres categorías: *Mantener*, *Revisar*,
   *No operar*.
5. **No hay promesas de rentabilidad** ni metas diarias de ganancia, y el
   sistema nunca sugiere subir el apalancamiento.
6. **Los CFD no son acciones en propiedad.** El sistema los distingue y, cuando
   no puede determinar el tipo de producto, lo dice en vez de suponerlo.
7. **No es asesoría financiera.**

---

## Pruebas

```bash
python3 -m unittest discover -s tests -v
```

Cubren: imágenes ilegibles, campos faltantes, fechas de captura y detección de
datos desactualizados, extracción sin valores inventados, detección de capturas
duplicadas, escritura del historial sin sobrescribir informes, y el flujo de
error cuando falta autenticación de correo o no hay captura nueva.

Se ejecutan solas en cada push mediante
[`.github/workflows/pruebas.yml`](.github/workflows/pruebas.yml).

---

## Estructura del proyecto

```
.github/workflows/
  revision-diaria.yml     Flujo principal (manual, por captura nueva y diario)
  pruebas.yml             Pruebas automáticas

scripts/
  common.py               Rutas, fechas, huso de Chile, E/S, hashing
  guardrails.py           Barrera de visibilidad del repositorio
  inbox.py                Detección de capturas nuevas y duplicadas
  schema.py               Esquema y validación de la extracción
  analyze.py              Cálculos deterministas (margen, concentración, deltas)
  report.py               Armado del informe e historial
  notify.py               Envío opcional por correo
  cli.py                  Interfaz de línea de comandos

prompts/
  extraer.md              Instrucciones de extracción (solo leer la imagen)
  redactar.md             Instrucciones de redacción (solo datos validados)

data/
  inbox/                  Capturas por procesar  ← aquí va la imagen
  extracted/              JSON crudo de cada captura
  reports/YYYY-MM-DD.json Datos estructurados de cada informe
  history/index.json      Índice del historial que lee el panel
  history/processed.json  Registro de capturas ya procesadas (SHA-256)
  state/                  Estado del proceso y archivos intermedios

reports/YYYY-MM-DD.md     Informe en español

index.html, styles.css, app.js    Panel

docs/integracion-libertex.md      Investigación sobre la API de Libertex
tests/                            Pruebas
```

---

## Qué contiene cada informe

1. Resumen ejecutivo y nivel de atención.
2. Tabla por operación con los datos disponibles.
3. Cambios frente al último informe válido.
4. Riesgos observables: apalancamiento, margen y concentración.
5. Recomendación por operación: *Mantener*, *Revisar* o *No operar*.
6. Motivo, evidencia, nivel de confianza y datos faltantes de cada una.
7. Conclusión con lo que conviene revisar personalmente.

Con los **HECHOS** y la **INTERPRETACIÓN** en secciones separadas, siempre.
