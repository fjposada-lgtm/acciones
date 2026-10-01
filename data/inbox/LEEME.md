# Bandeja de entrada de capturas

Aquí se deja la captura de pantalla de Libertex que se quiere analizar.

## ⚠️ Antes de subir nada

**El repositorio debe ser privado.** Una captura de las posiciones es un dato
financiero personal.

Y algo que suele pasarse por alto:

> **Borrar la imagen después NO la elimina del repositorio.** Git guarda todos
> los commits anteriores. Una imagen subida a un repositorio público queda en
> el historial —y posiblemente en cachés y réplicas de terceros— aunque se
> borre el archivo al día siguiente. La única forma de quitarla de verdad es
> reescribir el historial, y ni siquiera eso garantiza que nadie la haya copiado.

El workflow comprueba la visibilidad del repositorio **antes** de procesar
cualquier cosa y se detiene si es público. Esa comprobación protege el
procesamiento, pero **no puede impedir que subas la imagen**: eso depende de ti.

## Cómo agregar una captura desde GitHub

1. Entra al repositorio en github.com.
2. Navega a la carpeta `data/inbox/`.
3. Pulsa **Add file → Upload files**.
4. Arrastra la captura.
5. Pulsa **Commit changes**.

Al confirmar el commit, el workflow *Revisión diaria de operaciones* arranca
solo y genera el informe.

## Nombre del archivo

Formato recomendado:

```
2026-10-01_libertex.png
2026-10-01T09-30_libertex.png
```

La fecha del nombre se usa **solo como respaldo**, cuando la captura no muestra
una fecha legible. En ese caso el informe lo advierte y baja la confianza.

Si la captura **sí** muestra la fecha y hora de Libertex, mucho mejor: el
sistema prefiere ese dato. Procura que el reloj de la plataforma quede visible.

## Qué debe verse en la captura

Cuanto más de esto sea legible, mejor será el informe:

- Nombre o ticker del instrumento.
- Tipo de producto (CFD o acción), si la plataforma lo indica.
- Dirección (compra o venta).
- Tamaño o monto de la operación.
- Apalancamiento o multiplicador.
- Precio de entrada y precio actual.
- Ganancia o pérdida.
- Margen, stop loss, take profit y costos.
- Saldo, patrimonio y margen de la cuenta.
- **Fecha y hora** que muestre Libertex.

Lo que no se lea con claridad queda como «no disponible». **El sistema nunca
estima un valor que no pudo leer.**

## Formatos aceptados

`.png`, `.jpg`, `.jpeg`, `.webp`

## Capturas repetidas

Se identifican por el SHA-256 de su contenido. Subir dos veces la misma imagen
—aunque le cambies el nombre— no genera un segundo informe.

## Antigüedad

Una captura de más de **36 horas** se marca como desactualizada: el informe
igual se genera, pero advierte que los precios no representan el mercado
actual. El umbral se ajusta con la variable `MAX_CAPTURE_AGE_HOURS`.
