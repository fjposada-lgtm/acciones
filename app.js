/* Panel de revision diaria.
 *
 * Solo lee archivos JSON generados por el flujo. No escribe nada, no llama a
 * ninguna API externa y no puede operar en Libertex.
 *
 * Si un dato no existe, se muestra "no disponible". Nunca se rellena con un
 * valor calculado ni supuesto.
 */

(function () {
  "use strict";

  var RUTA_ESTADO = "data/state/status.json";
  var RUTA_INDICE = "data/history/index.json";

  var NO_DISPONIBLE = "no disponible";

  // --------------------------------------------------------------- utilidades

  function $(id) {
    return document.getElementById(id);
  }

  /** Inserta texto de forma segura: nunca interpreta HTML de los datos. */
  function texto(elemento, valor) {
    elemento.textContent = valor === null || valor === undefined || valor === ""
      ? NO_DISPONIBLE
      : String(valor);
  }

  function crear(etiqueta, clase, contenido) {
    var nodo = document.createElement(etiqueta);
    if (clase) { nodo.className = clase; }
    if (contenido !== undefined && contenido !== null) {
      nodo.textContent = String(contenido);
    }
    return nodo;
  }

  function celdaND(fila, valor, clase) {
    var td = document.createElement("td");
    if (valor === null || valor === undefined || valor === "" || valor === "no_disponible") {
      td.className = "nd";
      td.textContent = NO_DISPONIBLE;
    } else {
      if (clase) { td.className = clase; }
      td.textContent = String(valor);
    }
    fila.appendChild(td);
    return td;
  }

  function numero(valor, moneda) {
    if (valor === null || valor === undefined) { return null; }
    var texto = Number(valor).toLocaleString("es-CL", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
    return moneda ? texto + " " + moneda : texto;
  }

  function fechaLegible(iso) {
    if (!iso) { return null; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return iso; }
    return d.toLocaleString("es-CL", {
      dateStyle: "medium",
      timeStyle: "short"
    });
  }

  function obtenerJSON(ruta) {
    return fetch(ruta, { cache: "no-store" }).then(function (r) {
      if (!r.ok) { return null; }
      return r.json().catch(function () { return null; });
    }).catch(function () { return null; });
  }

  function aviso(tipo, titulo, cuerpo) {
    var caja = crear("div", "aviso aviso--" + tipo);
    caja.appendChild(crear("p", "aviso__titulo", titulo));
    caja.appendChild(crear("p", null, cuerpo));
    $("avisos").appendChild(caja);
  }

  // --------------------------------------------------------------- estado

  var CLASE_ESTADO = {
    procesado: "chip--ok",
    sin_datos_nuevos: "chip--neutro",
    pendiente: "chip--aviso",
    datos_insuficientes: "chip--aviso",
    error: "chip--peligro",
    bloqueado_repo_publico: "chip--peligro"
  };

  function pintarEstado(estado) {
    var contenedor = $("chip-estado");
    contenedor.innerHTML = "";

    if (!estado) {
      contenedor.appendChild(crear("span", "chip chip--neutro", "Sin ejecuciones"));
      texto($("valor-estado"), "El sistema aun no se ha ejecutado");
      texto($("valor-fecha-datos"), null);
      texto($("valor-actualizado"), null);
      texto($("valor-correo"), null);
      return;
    }

    var clase = CLASE_ESTADO[estado.estado] || "chip--neutro";
    contenedor.appendChild(
      crear("span", "chip " + clase, estado.estado_legible || estado.estado)
    );

    texto($("valor-estado"), estado.estado_legible || estado.estado);
    texto($("valor-fecha-datos"), fechaLegible(estado.fecha_datos));
    texto($("valor-actualizado"), fechaLegible(estado.actualizado_en));
    texto($("detalle-estado"), estado.detalle || "");

    // El correo nunca se presenta como enviado sin confirmacion explicita.
    var correo = estado.correo;
    if (!correo) {
      texto($("valor-correo"), "correo no configurado");
    } else if (correo.enviado === true) {
      texto($("valor-correo"), "enviado a " + (correo.destinatario || NO_DISPONIBLE));
    } else if (correo.estado === "correo_no_configurado") {
      texto($("valor-correo"), "correo no configurado");
    } else {
      texto($("valor-correo"), "no enviado (" + (correo.estado || "desconocido") + ")");
    }

    if (estado.estado === "bloqueado_repo_publico") {
      aviso("peligro", "Procesamiento bloqueado: el repositorio es publico",
        estado.detalle || "No se procesaran capturas mientras el repositorio sea publico.");
    }
    if (estado.estado === "datos_insuficientes") {
      aviso("avisar", "La ultima captura no pudo usarse",
        estado.detalle || "Faltan campos clave o la imagen no es legible.");
    }
    if (estado.estado === "sin_datos_nuevos") {
      aviso("info", "Sin datos nuevos",
        estado.detalle || "No hay ninguna captura sin procesar en data/inbox/.");
    }
    if (correo && correo.estado === "correo_no_configurado") {
      aviso("info", "Correo no configurado",
        correo.detalle || "El informe quedo guardado en el repositorio; no se intento ningun envio.");
    }
    if (correo && correo.estado === "error_envio") {
      aviso("avisar", "El correo no se pudo enviar",
        (correo.detalle || "") + " El informe si quedo guardado en el repositorio.");
    }
  }

  // --------------------------------------------------------------- informe

  var CLASE_ATENCION = { alto: "chip--peligro", medio: "chip--aviso", bajo: "chip--ok" };

  function pintarInforme(reporte) {
    if (!reporte) { return; }

    $("informe-vacio").hidden = true;
    $("informe").hidden = false;

    if (reporte.demo) {
      aviso("avisar", "DATOS DE DEMOSTRACION",
        "Este informe usa datos de prueba y NO corresponde a la cuenta real.");
      var chipDemo = crear("span", "chip chip--demo", "DEMO");
      $("chip-estado").appendChild(chipDemo);
    }

    var analisis = reporte.analisis || {};
    var atencion = analisis.atencion || {};

    var chip = $("chip-atencion");
    if (atencion.nivel) {
      chip.hidden = false;
      chip.className = "chip " + (CLASE_ATENCION[atencion.nivel] || "chip--neutro");
      chip.textContent = "Atencion " + atencion.nivel;
    }

    var resumen = $("resumen-ejecutivo");
    resumen.innerHTML = "";
    resumen.appendChild(crear("p", null, reporte.resumen || NO_DISPONIBLE));

    if (analisis.desactualizada) {
      aviso("avisar", "Datos desactualizados",
        "La captura tiene " + analisis.antiguedad_horas + " horas. Los precios " +
        "no representan el mercado actual.");
    }

    // Moneda de referencia, tomada de los datos y no supuesta.
    var moneda = null;
    var cuenta = analisis.cuenta || {};
    Object.keys(cuenta).forEach(function (k) {
      if (!moneda && cuenta[k] && cuenta[k].moneda) { moneda = cuenta[k].moneda; }
    });

    // --- tabla de posiciones
    var cuerpo = document.querySelector("#tabla-posiciones tbody");
    cuerpo.innerHTML = "";

    var recomendaciones = {};
    (reporte.recomendaciones || []).forEach(function (r) {
      recomendaciones[r.instrumento] = r;
    });

    var extraidas = (reporte.datos_extraidos && reporte.datos_extraidos.posiciones) || [];

    (analisis.posiciones || []).forEach(function (p) {
      var origen = extraidas.filter(function (o) {
        return o.instrumento === p.instrumento;
      })[0] || {};

      var fila = document.createElement("tr");

      var th = document.createElement("th");
      th.scope = "row";
      th.textContent = p.instrumento;
      fila.appendChild(th);

      celdaND(fila, p.tipo_producto);
      celdaND(fila, p.direccion);
      celdaND(fila, p.apalancamiento === null || p.apalancamiento === undefined
        ? null : "x" + p.apalancamiento);
      celdaND(fila, origen.precio_entrada ? numero(origen.precio_entrada.valor) : null);
      celdaND(fila, origen.precio_actual ? numero(origen.precio_actual.valor) : null);

      var clase = null;
      if (typeof p.resultado === "number") {
        clase = p.resultado < 0 ? "neg" : "pos";
      }
      celdaND(fila, numero(p.resultado, moneda), clase);

      var rec = recomendaciones[p.instrumento];
      celdaND(fila, rec ? rec.categoria : null);

      cuerpo.appendChild(fila);
    });

    // --- hechos e interpretacion
    pintarLista($("lista-hechos"), reporte.hechos, "Sin hechos registrados.");
    pintarLista($("lista-interpretacion"), reporte.interpretacion, "Sin interpretacion registrada.");
    pintarLista($("lista-faltantes"), reporte.datos_faltantes,
      "Ninguno: todos los campos previstos se leyeron.");

    // --- recomendaciones detalladas
    var caja = $("recomendaciones");
    caja.innerHTML = "";
    (reporte.recomendaciones || []).forEach(function (r) {
      var bloque = crear("div", "rec");

      var cabecera = crear("div", "rec__cabecera");
      cabecera.appendChild(crear("span", "rec__instrumento", r.instrumento));
      cabecera.appendChild(crear("span", "chip", r.categoria));
      cabecera.appendChild(crear("span", "chip chip--neutro", "confianza " + (r.confianza || "?")));
      bloque.appendChild(cabecera);

      bloque.appendChild(campo("Motivo", r.motivo));
      bloque.appendChild(campo("Evidencia", r.evidencia));
      bloque.appendChild(campo("Datos que faltan",
        (r.datos_faltantes && r.datos_faltantes.length)
          ? r.datos_faltantes.join(", ")
          : "ninguno relevante"));

      caja.appendChild(bloque);
    });

    if (!(reporte.recomendaciones || []).length) {
      caja.appendChild(crear("p", "nd", "No se emitieron recomendaciones."));
    }

    // --- enlaces
    $("enlace-md").href = reporte.archivo_md || "#";
    $("enlace-json").href = reporte.archivo_json || "#";
  }

  function campo(etiqueta, valor) {
    var p = crear("p", "rec__campo");
    p.appendChild(crear("span", "rec__etiqueta", etiqueta));
    p.appendChild(document.createTextNode(valor || NO_DISPONIBLE));
    return p;
  }

  function pintarLista(contenedor, items, vacio) {
    contenedor.innerHTML = "";
    if (!items || !items.length) {
      contenedor.appendChild(crear("li", "nd", vacio));
      return;
    }
    items.forEach(function (item) {
      contenedor.appendChild(crear("li", null, item));
    });
  }

  // --------------------------------------------------------------- historial

  function pintarHistorial(indice) {
    var entradas = (indice && indice.reportes) || [];
    if (!entradas.length) { return; }

    $("historial-vacio").hidden = true;
    $("historial-caja").hidden = false;

    var cuerpo = $("historial-cuerpo");
    cuerpo.innerHTML = "";

    entradas.forEach(function (e) {
      var fila = document.createElement("tr");

      var th = document.createElement("th");
      th.scope = "row";
      th.textContent = fechaLegible(e.fecha_datos) || e.fecha || NO_DISPONIBLE;
      if (e.demo) {
        th.appendChild(document.createTextNode(" "));
        th.appendChild(crear("span", "chip chip--demo", "DEMO"));
      }
      fila.appendChild(th);

      celdaND(fila, (e.instrumentos || []).join(", "));
      celdaND(fila, e.nivel_atencion);

      var td = document.createElement("td");
      var enlace = crear("a", null, "Abrir");
      enlace.href = e.archivo_md;
      enlace.target = "_blank";
      enlace.rel = "noopener";
      td.appendChild(enlace);
      fila.appendChild(td);

      cuerpo.appendChild(fila);
    });
  }

  // --------------------------------------------------------------- arranque

  function iniciar() {
    if (location.protocol === "file:") {
      aviso("avisar", "Abre el panel con un servidor local",
        "Con file:// el navegador bloquea la lectura de los JSON. Ejecuta " +
        "python3 -m http.server 8000 en la carpeta del proyecto y abre " +
        "http://localhost:8000");
      return;
    }

    Promise.all([obtenerJSON(RUTA_ESTADO), obtenerJSON(RUTA_INDICE)])
      .then(function (resultados) {
        var estado = resultados[0];
        var indice = resultados[1];

        pintarEstado(estado);
        pintarHistorial(indice);

        var entradas = (indice && indice.reportes) || [];
        if (!entradas.length) { return null; }
        return obtenerJSON(entradas[0].archivo_json);
      })
      .then(function (reporte) {
        if (reporte) { pintarInforme(reporte); }
      })
      .catch(function (error) {
        aviso("peligro", "No se pudo cargar el panel", String(error));
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
