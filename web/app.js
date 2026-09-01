/* Radar de licitaciones - lee los JSON que deja scripts/actualizar.py */

const CLAVE_GUARDADO = "radar-licitaciones-filtros";
const FICHA_MP = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion=";

const el = (id) => document.getElementById(id);
const controles = {
  texto: el("texto"),
  estado: el("estado"),
  region: el("region"),
  dias: el("dias"),
  montoMin: el("montoMin"),
  montoMax: el("montoMax"),
  soloNuevas: el("soloNuevas"),
  verDescartadas: el("verDescartadas"),
  soloFavoritas: el("soloFavoritas"),
};

let licitaciones = [];
let codigosNuevas = new Set();
let descartadas = new Set();

const CLAVE_DESCARTADAS = "radar-licitaciones-descartadas";
const CLAVE_FAVORITAS = "radar-licitaciones-favoritas";

let favoritas = new Set();

function leerFavoritas() {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_FAVORITAS) || "[]"));
  } catch (e) {
    return new Set();
  }
}

function guardarFavoritas() {
  try {
    localStorage.setItem(CLAVE_FAVORITAS, JSON.stringify([...favoritas]));
  } catch (e) {
    /* modo privado: no se puede guardar */
  }
  const cuenta = el("cuentaFavoritas");
  if (cuenta) cuenta.textContent = favoritas.size;
}

function alternarFavorita(codigo) {
  const ahoraGusta = !favoritas.has(codigo);
  if (ahoraGusta) favoritas.add(codigo);
  else favoritas.delete(codigo);
  guardarFavoritas();
  pintar();
}

function leerDescartadas() {
  try {
    return new Set(JSON.parse(localStorage.getItem(CLAVE_DESCARTADAS) || "[]"));
  } catch (e) {
    return new Set();
  }
}

function guardarDescartadas() {
  try {
    localStorage.setItem(CLAVE_DESCARTADAS, JSON.stringify([...descartadas]));
  } catch (e) {
    /* modo privado: no se puede guardar */
  }
  const cuenta = el("cuentaDescartadas");
  if (cuenta) cuenta.textContent = descartadas.size;
}

function descartar(codigo) {
  descartadas.add(codigo);
  if (favoritas.delete(codigo)) guardarFavoritas();
  guardarDescartadas();
  pintar();
}

function devolver(codigo) {
  descartadas.delete(codigo);
  guardarDescartadas();
  pintar();
}

const sinTildes = (t) =>
  (t || "").toString().normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

const pesos = (n) =>
  n === null || n === undefined || isNaN(n)
    ? null
    : "$" + Math.round(n).toLocaleString("es-CL");

function aFecha(valor) {
  if (!valor) return null;
  const f = new Date(valor);
  return isNaN(f.getTime()) ? null : f;
}

function fechaCorta(valor) {
  const f = aFecha(valor);
  if (!f) return "sin fecha";
  return f.toLocaleDateString("es-CL", { day: "2-digit", month: "short", year: "numeric" });
}

function diasHasta(valor) {
  const f = aFecha(valor);
  if (!f) return null;
  const hoy = new Date();
  return Math.ceil((f - hoy) / 86400000);
}

async function cargarJSON(ruta) {
  const respuesta = await fetch(ruta, { cache: "no-cache" });
  if (!respuesta.ok) throw new Error(ruta + " -> " + respuesta.status);
  return respuesta.json();
}

async function cargarTodo() {
  const [indice, vigentes, nuevas] = await Promise.all([
    cargarJSON("datos/indice.json"),
    cargarJSON("datos/vigentes.json"),
    cargarJSON("datos/nuevas.json").catch(() => []),
  ]);

  licitaciones = (vigentes || []).filter((lic) => lic && lic.codigo);
  codigosNuevas = new Set((nuevas || []).map((l) => l.codigo));

  const momento = aFecha(indice.actualizado);
  el("resumen").textContent =
    licitaciones.length +
    " licitaciones vigentes · " +
    (codigosNuevas.size === 0
      ? "ninguna nueva hoy"
      : codigosNuevas.size + (codigosNuevas.size === 1 ? " nueva hoy" : " nuevas hoy")) +
    " · actualizado el " +
    (momento
      ? momento.toLocaleDateString("es-CL", { day: "2-digit", month: "long" }) +
        " a las " +
        momento.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })
      : "?");

  descartadas = leerDescartadas();
  favoritas = leerFavoritas();
  const vivos = new Set(licitaciones.map((l) => l.codigo));
  for (const codigo of [...descartadas]) {
    if (!vivos.has(codigo)) descartadas.delete(codigo);  // ya cerro: no ocupa espacio
  }
  for (const codigo of [...favoritas]) {
    if (!vivos.has(codigo)) favoritas.delete(codigo);
  }
  guardarDescartadas();
  guardarFavoritas();

  poblarSelect(controles.estado, licitaciones.map((l) => l.estado));
  poblarSelect(controles.region, licitaciones.map((l) => l.region));
}

function poblarSelect(select, valores) {
  const unicos = [...new Set(valores.filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "es")
  );
  for (const valor of unicos) {
    const opcion = document.createElement("option");
    opcion.value = valor;
    opcion.textContent = valor;
    select.appendChild(opcion);
  }
}

function filtrar() {
  const texto = sinTildes(controles.texto.value.trim());
  const estado = controles.estado.value;
  const region = controles.region.value;
  const dias = parseInt(controles.dias.value, 10);
  const soloNuevas = controles.soloNuevas.checked;
  const min = parseFloat(controles.montoMin.value);
  const max = parseFloat(controles.montoMax.value);

  let desde = null;
  if (dias > 0) {
    desde = new Date();
    desde.setHours(0, 0, 0, 0);
    desde.setDate(desde.getDate() - (dias - 1));
  }

  const verDescartadas = controles.verDescartadas.checked;
  const soloFavoritas = controles.soloFavoritas.checked;

  return licitaciones.filter((lic) => {
    if (verDescartadas !== descartadas.has(lic.codigo)) return false;
    if (soloFavoritas && !favoritas.has(lic.codigo)) return false;
    if (soloNuevas && !codigosNuevas.has(lic.codigo)) return false;
    if (estado && lic.estado !== estado) return false;
    if (region && lic.region !== region) return false;

    if (desde) {
      const publicada = aFecha(lic.publicacion) || aFecha(lic.dia);
      if (!publicada || publicada < desde) return false;
    }

    if (!isNaN(min) && (lic.monto === null || lic.monto < min)) return false;
    if (!isNaN(max) && lic.monto !== null && lic.monto > max) return false;

    if (texto) {
      const bolsa = sinTildes(
        [lic.nombre, lic.descripcion, lic.organismo, lic.unidad, lic.codigo,
         (lic.categorias || []).join(" ")].join(" ")
      );
      if (!texto.split(/\s+/).every((palabra) => bolsa.includes(palabra))) return false;
    }

    return true;
  });
}

function ordenar(lista) {
  /* El orden es siempre por fecha de cierre, y nada mas. Las que tienen like NO
     suben al principio a proposito: si la ficha salta de lugar al apretar el
     boton, pierdes de vista donde ibas leyendo. El like es una marca, no un
     orden. Para verlas juntas esta la casilla "Solo mis likes". */
  return lista.slice().sort((a, b) => {
    const fa = aFecha(a.cierre);
    const fb = aFecha(b.cierre);
    if (fa && fb) return fa - fb;
    if (fa) return -1;
    if (fb) return 1;
    return 0;
  });
}

function cantidadTexto(item) {
  if (item.cantidad === null || item.cantidad === undefined || item.cantidad === "") return "";
  return (item.cantidad + " " + (item.unidad || "")).trim();
}

function filasRequerimientos(lic) {
  const r = lic.requerimientos || {};
  const filas = [];
  const fecha = (v) => {
    const f = aFecha(v);
    return f ? f.toLocaleDateString("es-CL", { day: "2-digit", month: "short" }) : null;
  };

  const items = r.items || [];
  if (items.length) {
    const trozos = items.slice(0, 4).map((it) => {
      const nombre = it.producto || it.categoria || "(sin nombre)";
      const cantidad = cantidadTexto(it);
      return (cantidad ? cantidad + " · " : "") + nombre;
    });
    const resto = (r.items_total || items.length) - Math.min(items.length, 4);
    if (resto > 0) trozos.push("y " + resto + (resto === 1 ? " ítem más" : " ítems más"));
    filas.push(["Qué piden", trozos.join(" · ")]);
  }

  const visita = fecha(r.visita_terreno);
  if (visita) filas.push(["Visita a terreno", visita + (r.direccion_visita ? " — " + r.direccion_visita : "")]);

  const antecedentes = fecha(r.entrega_antecedentes);
  const fisico = fecha(r.soporte_fisico);
  if (antecedentes || fisico) {
    const partes = [];
    if (antecedentes) partes.push("antecedentes hasta el " + antecedentes);
    if (fisico) partes.push("soporte físico hasta el " + fisico + (r.direccion_entrega ? " en " + r.direccion_entrega : ""));
    filas.push(["Entregas", partes.join("; ")]);
  }

  const respuestas = fecha(r.respuestas);
  const tecnica = fecha(r.apertura_tecnica);
  if (respuestas || tecnica) {
    const partes = [];
    if (respuestas) partes.push("respuestas el " + respuestas);
    if (tecnica) partes.push("apertura técnica el " + tecnica);
    filas.push(["Hitos", partes.join("; ")]);
  }

  const contrato = [];
  if (r.duracion) contrato.push("dura " + r.duracion);
  if (r.renovable === true) contrato.push("renovable");
  if (r.modalidad_pago) contrato.push(r.modalidad_pago);
  if (contrato.length) filas.push(["Contrato", contrato.join(", ")]);

  const proceso = [];
  if (r.etapas) proceso.push(r.etapas + (r.etapas === 1 ? " etapa" : " etapas"));
  if (r.obras === true) proceso.push("contrato de obras");
  if (r.financiamiento) proceso.push(r.financiamiento.toLowerCase());
  if (proceso.length) filas.push(["Proceso", proceso.join(", ")]);

  if (r.contacto) {
    filas.push(["Contraparte", r.contacto + (r.contacto_email ? " · " + r.contacto_email : "")]);
  }

  if (r.prohibiciones) filas.push(["Prohibiciones", r.prohibiciones]);

  if (!lic.monto && r.monto_nota) filas.push(["Sobre el monto", r.monto_nota]);

  if (r.reclamos_comprador > 0) {
    filas.push(["Reclamos al organismo", r.reclamos_comprador + " por atraso en pagos, últimos 12 meses"]);
  }

  return filas;
}

function cuadroRequerimientos(lic) {
  const filas = filasRequerimientos(lic);
  if (!filas.length) return null;

  const caja = document.createElement("details");
  caja.className = "requerimientos";

  const titulo = document.createElement("summary");
  titulo.textContent = "Requerimientos técnicos";
  caja.appendChild(titulo);

  const tabla = document.createElement("dl");
  for (const [etiqueta, valor] of filas) {
    const dt = document.createElement("dt");
    dt.textContent = etiqueta;
    const dd = document.createElement("dd");
    dd.textContent = valor;
    tabla.appendChild(dt);
    tabla.appendChild(dd);
  }
  caja.appendChild(tabla);
  return caja;
}

function tarjeta(lic) {
  const restan = diasHasta(lic.cierre);
  const urgente = restan !== null && restan >= 0 && restan <= 3;

  const nodo = document.createElement("article");
  nodo.dataset.codigo = lic.codigo;
  nodo.className = "ficha" + (urgente ? " cierra-pronto" : "") +
    (descartadas.has(lic.codigo) ? " descartada" : "") +
    (favoritas.has(lic.codigo) ? " favorita" : "");

  const titulo = document.createElement("h2");
  const enlace = document.createElement("a");
  enlace.href = FICHA_MP + encodeURIComponent(lic.codigo);
  enlace.target = "_blank";
  enlace.rel = "noopener";
  enlace.textContent = lic.nombre || "(sin nombre)";
  titulo.appendChild(enlace);
  nodo.appendChild(titulo);

  const meta = document.createElement("p");
  meta.className = "meta";
  const partes = [
    ["Organismo", lic.organismo],
    ["Región", lic.region],
    ["Publicada", fechaCorta(lic.publicacion || lic.dia)],
    ["Cierra", fechaCorta(lic.cierre)],
  ];
  for (const [rotulo, valor] of partes) {
    if (!valor) continue;
    const trozo = document.createElement("span");
    trozo.innerHTML = rotulo + ": <strong></strong>";
    trozo.querySelector("strong").textContent = valor;
    meta.appendChild(trozo);
  }
  nodo.appendChild(meta);

  if (lic.descripcion) {
    const desc = document.createElement("p");
    desc.className = "descripcion";
    desc.textContent = lic.descripcion;
    nodo.appendChild(desc);
  }

  const etiquetas = document.createElement("div");
  etiquetas.className = "etiquetas";

  const agregar = (texto, clase) => {
    const e = document.createElement("span");
    e.className = "etiqueta " + (clase || "");
    e.textContent = texto;
    etiquetas.appendChild(e);
  };

  if (codigosNuevas.has(lic.codigo)) agregar("NUEVA", "nueva");
  if (lic.estado) agregar(lic.estado);
  const monto = pesos(lic.monto);
  if (monto) agregar(monto + (lic.moneda && lic.moneda !== "CLP" ? " " + lic.moneda : ""), "monto");
  if (restan !== null) {
    if (restan < 0) agregar("cerrada hace " + Math.abs(restan) + " días", "plazo");
    else if (restan === 0) agregar("cierra hoy", "urgente");
    else agregar("cierra en " + restan + (restan === 1 ? " día" : " días"), urgente ? "urgente" : "plazo");
  }
  if (lic.tipo) agregar(lic.tipo);
  agregar(lic.codigo, "codigo");

  nodo.appendChild(etiquetas);

  const cuadro = cuadroRequerimientos(lic);
  if (cuadro) nodo.appendChild(cuadro);

  const acciones = document.createElement("div");
  acciones.className = "acciones";
  const bases = document.createElement("a");
  bases.className = "boton-bases";
  bases.href = FICHA_MP + encodeURIComponent(lic.codigo);
  bases.target = "_blank";
  bases.rel = "noopener";
  bases.textContent = "⬇ Bases administrativas y técnicas";
  acciones.appendChild(bases);

  if (!descartadas.has(lic.codigo)) {
    const estrella = document.createElement("button");
    estrella.type = "button";
    const esFavorita = favoritas.has(lic.codigo);
    estrella.className = "boton-favorita" + (esFavorita ? " activa" : "");
    estrella.textContent = esFavorita ? "♥ Like" : "♡ Like";
    estrella.title = esFavorita
      ? "Quitarle el like"
      : "Marcarla. Se queda donde esta; para verlas juntas usa «Solo mis likes»";
    estrella.addEventListener("click", () => alternarFavorita(lic.codigo));
    acciones.appendChild(estrella);
  }

  // el boton de guardar aparece solo en las que tienen corazon
  if (favoritas.has(lic.codigo) && typeof guardarUna === "function" && HAY_SOPORTE) {
    const guardar = document.createElement("button");
    guardar.type = "button";
    guardar.className = "boton-guardar-uno";
    guardar.textContent = "⬇ Guardar y abrir anexos";
    guardar.title = "Crea su carpeta y abre la ficha para que descargues los anexos";
    guardar.addEventListener("click", async () => {
      guardar.disabled = true;
      guardar.textContent = "Guardando…";
      try {
        await guardarUna(lic.codigo);
        if (typeof abrirBases === "function") abrirBases(lic.codigo);
        guardar.textContent = "✓ Guardada";
        guardar.classList.add("hecho");
        setTimeout(() => {
          guardar.textContent = "⬇ Guardar y abrir anexos";
          guardar.classList.remove("hecho");
          guardar.disabled = false;
        }, 4000);
      } catch (e) {
        guardar.textContent = "⬇ Guardar y abrir anexos";
        guardar.disabled = false;
      }
    });
    acciones.appendChild(guardar);
  }

  const boton = document.createElement("button");
  boton.type = "button";
  if (descartadas.has(lic.codigo)) {
    boton.className = "boton-devolver";
    boton.textContent = "↩ Devolver a la lista";
    boton.addEventListener("click", () => devolver(lic.codigo));
  } else {
    boton.className = "boton-descartar";
    boton.textContent = "✕ Eliminar";
    boton.title = "La saca del listado en este navegador. Se puede devolver.";
    boton.addEventListener("click", () => descartar(lic.codigo));
  }
  acciones.appendChild(boton);

  nodo.appendChild(acciones);

  return nodo;
}

function pintar() {
  const resultado = ordenar(filtrar());
  const lista = el("lista");
  lista.replaceChildren(...resultado.map(tarjeta));

  const viendoDescartadas = controles.verDescartadas.checked;
  const universo = licitaciones.length - (viendoDescartadas ? 0 : descartadas.size);
  if (viendoDescartadas) {
    el("conteo").textContent =
      resultado.length + (resultado.length === 1 ? " eliminada" : " eliminadas") +
      (resultado.length === descartadas.size ? "" : " de " + descartadas.size);
  } else {
    el("conteo").textContent =
      (resultado.length === universo
        ? resultado.length + " licitaciones"
        : resultado.length + " de " + universo + " licitaciones") +
      (descartadas.size
        ? " · " + descartadas.size + " eliminada" + (descartadas.size === 1 ? "" : "s")
        : "");
  }
  el("avisoDescartadas").classList.toggle("oculto", !viendoDescartadas);

  el("vacio").classList.toggle("oculto", resultado.length > 0);
  guardarFiltros();
  if (typeof refrescarBoton === "function") refrescarBoton();
}

function guardarFiltros() {
  const estado = {};
  for (const [nombre, control] of Object.entries(controles)) {
    // la vista de descartadas nunca se recuerda: al volver siempre se ve la lista normal
    if (nombre === "verDescartadas") continue;
    estado[nombre] = control.type === "checkbox" ? control.checked : control.value;
  }
  try {
    localStorage.setItem(CLAVE_GUARDADO, JSON.stringify(estado));
  } catch (e) {
    /* modo privado: seguimos sin guardar */
  }
}

function recuperarFiltros() {
  try {
    const guardado = JSON.parse(localStorage.getItem(CLAVE_GUARDADO) || "{}");
    for (const [nombre, valor] of Object.entries(guardado)) {
      const control = controles[nombre];
      if (!control || valor === undefined || nombre === "verDescartadas") continue;
      if (control.type === "checkbox") control.checked = Boolean(valor);
      else control.value = valor;
    }
  } catch (e) {
    /* nada guardado o ilegible */
  }
}

function conectar() {
  let temporizador;
  for (const control of Object.values(controles)) {
    const evento =
      control.tagName === "SELECT" || control.type === "checkbox" ? "change" : "input";
    control.addEventListener(evento, () => {
      clearTimeout(temporizador);
      temporizador = setTimeout(pintar, evento === "input" ? 180 : 0);
    });
  }
  el("restaurarTodas").addEventListener("click", () => {
    descartadas.clear();
    guardarDescartadas();
    controles.verDescartadas.checked = false;
    controles.soloFavoritas.checked = false;
    pintar();
  });

  el("limpiar").addEventListener("click", () => {
    controles.texto.value = "";
    controles.estado.value = "";
    controles.region.value = "";
    controles.dias.value = "0";
    controles.montoMin.value = "";
    controles.montoMax.value = "";
    controles.soloNuevas.checked = false;
    controles.verDescartadas.checked = false;
    controles.soloFavoritas.checked = false;
    pintar();
  });
}

(async function iniciar() {
  try {
    await cargarTodo();
    if (typeof prepararGuardado === "function") await prepararGuardado();
    recuperarFiltros();
    conectar();
    pintar();
  } catch (error) {
    el("resumen").textContent = "no pude leer los datos";
    el("conteo").textContent = "";
    el("vacio").classList.remove("oculto");
    el("vacio").textContent =
      "Todavía no hay datos guardados. Ejecuta el radar una vez (doble clic en «Abrir radar») y vuelve a cargar esta página. Detalle técnico: " +
      error.message;
  }
})();
