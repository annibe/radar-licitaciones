/* Guardar en OneDrive las licitaciones marcadas con corazon.

   Usa la API de acceso a archivos de Chrome/Edge: pides la carpeta UNA vez,
   el navegador recuerda el permiso, y desde ahi la pagina puede escribir dentro.
   Nada sale del equipo: no hay servidor de por medio.

   Estructura que deja:
     <carpeta que elijas>\
        LEEME.txt
        1057426-88-LP26 - Consultoria estructura documental\
           ficha.html      todos los datos, para leer o imprimir a PDF
           datos.json      lo mismo en crudo
           bases.url       acceso directo a la ficha oficial
           notas.txt       para escribir (nunca se sobrescribe)
*/

const HAY_SOPORTE = typeof window.showDirectoryPicker === "function";
const BD = "radar-licitaciones";
const ALMACEN = "carpetas";

let carpeta = null;   // FileSystemDirectoryHandle

/* ---------- recordar la carpeta entre visitas ---------- */

function abrirBD() {
  return new Promise((resolve, reject) => {
    const pedido = indexedDB.open(BD, 1);
    pedido.onupgradeneeded = () => pedido.result.createObjectStore(ALMACEN);
    pedido.onsuccess = () => resolve(pedido.result);
    pedido.onerror = () => reject(pedido.error);
  });
}

async function recordar(handle) {
  try {
    const bd = await abrirBD();
    await new Promise((resolve, reject) => {
      const tx = bd.transaction(ALMACEN, "readwrite");
      tx.objectStore(ALMACEN).put(handle, "principal");
      tx.oncomplete = resolve;
      tx.onerror = () => reject(tx.error);
    });
  } catch (e) {
    /* si no se puede recordar, la pedimos de nuevo la proxima vez */
  }
}

async function recuperar() {
  try {
    const bd = await abrirBD();
    return await new Promise((resolve, reject) => {
      const tx = bd.transaction(ALMACEN, "readonly");
      const p = tx.objectStore(ALMACEN).get("principal");
      p.onsuccess = () => resolve(p.result || null);
      p.onerror = () => reject(p.error);
    });
  } catch (e) {
    return null;
  }
}

async function tienePermiso(handle, pedirlo) {
  if (!handle) return false;
  const opciones = { mode: "readwrite" };
  if ((await handle.queryPermission(opciones)) === "granted") return true;
  if (!pedirlo) return false;
  return (await handle.requestPermission(opciones)) === "granted";
}

/* ---------- nombres de carpeta que Windows acepte ---------- */

function limpiarNombre(texto, largo) {
  return (texto || "")
    .replace(/[\\/:*?"<>|]/g, " ")      // prohibidos en Windows
    .replace(/[\x00-\x1f]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, largo)
    .replace(/[. ]+$/, "");             // Windows no admite punto ni espacio al final
}

function nombreCarpeta(lic) {
  const folio = limpiarNombre(lic.codigo, 30) || "sin-folio";
  const titulo = limpiarNombre(lic.nombre, 70);
  return titulo ? folio + " - " + titulo : folio;
}

/* ---------- lo que se escribe dentro ---------- */

function textoPlano(lic) {
  const r = lic.requerimientos || {};
  const lineas = [];
  const agregar = (etiqueta, valor) => { if (valor) lineas.push(etiqueta + ": " + valor); };
  agregar("Licitacion", lic.nombre);
  agregar("Folio", lic.codigo);
  agregar("Organismo", lic.organismo);
  agregar("Unidad", lic.unidad);
  agregar("Region", lic.region);
  agregar("Estado", lic.estado);
  agregar("Publicada", fechaCorta(lic.publicacion));
  agregar("Cierra", fechaCorta(lic.cierre));
  agregar("Monto estimado", pesos(lic.monto) || "no informado");
  agregar("Contraparte", r.contacto);
  lineas.push("");
  lineas.push("Bases oficiales: " + FICHA_MP + lic.codigo);
  return lineas.join("\r\n");
}

function fichaHTML(lic) {
  const escapar = (t) => String(t == null ? "" : t)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const filas = filasRequerimientos(lic)
    .map(([e, v]) => "<tr><th>" + escapar(e) + "</th><td>" + escapar(v) + "</td></tr>")
    .join("");
  const datos = [
    ["Folio", lic.codigo], ["Estado", lic.estado], ["Organismo", lic.organismo],
    ["Unidad de compra", lic.unidad], ["Region", lic.region], ["Comuna", lic.comuna],
    ["Publicada", fechaCorta(lic.publicacion)], ["Cierra", fechaCorta(lic.cierre)],
    ["Monto estimado", pesos(lic.monto) || "no informado"], ["Tipo", lic.tipo],
    ["Categorias", (lic.categorias || []).join(", ")],
  ].filter(([, v]) => v)
   .map(([e, v]) => "<tr><th>" + escapar(e) + "</th><td>" + escapar(v) + "</td></tr>")
   .join("");

  return `<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<title>${escapar(lic.codigo)} - ${escapar(lic.nombre)}</title>
<style>
 body{font:15px/1.55 "Segoe UI",system-ui,sans-serif;color:#1b2436;max-width:820px;margin:32px auto;padding:0 22px}
 h1{font-size:21px;line-height:1.3;margin:0 0 4px}
 .folio{color:#5a657a;font-size:14px;margin:0 0 22px}
 h2{font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:#16307e;margin:28px 0 8px}
 table{border-collapse:collapse;width:100%}
 th{text-align:left;font-weight:600;color:#5a657a;padding:6px 14px 6px 0;vertical-align:top;width:190px}
 td{padding:6px 0;vertical-align:top}
 tr+tr th,tr+tr td{border-top:1px solid #eef1f6}
 .desc{background:#f7f9fd;border:1px solid #e2e8f4;border-radius:9px;padding:14px 16px;white-space:pre-wrap}
 a.boton{display:inline-block;margin-top:26px;background:#1f4fd8;color:#fff;padding:11px 20px;
   border-radius:8px;text-decoration:none;font-weight:600}
 footer{margin-top:34px;padding-top:14px;border-top:1px solid #e6eaf2;color:#8a94a6;font-size:12px}
 @media print{a.boton{display:none}}
</style></head><body>
<h1>${escapar(lic.nombre)}</h1>
<p class="folio">${escapar(lic.codigo)}</p>
<h2>Datos de la licitacion</h2>
<table>${datos}</table>
${filas ? '<h2>Requerimientos tecnicos</h2><table>' + filas + "</table>" : ""}
${lic.descripcion ? '<h2>Descripcion</h2><div class="desc">' + escapar(lic.descripcion) + "</div>" : ""}
<a class="boton" href="${FICHA_MP + encodeURIComponent(lic.codigo)}">Abrir las bases en Mercado Publico</a>
<footer>Guardado el ${new Date().toLocaleString("es-CL")} desde el radar de licitaciones.
Los datos vienen de la API de ChileCompra; el monto es referencial.</footer>
</body></html>`;
}

const LEEME = `CARPETA DE LICITACIONES
=======================

Cada subcarpeta es una licitacion de Mercado Publico que estamos siguiendo.
Que exista la carpeta significa que la licitacion esta en juego.

Dentro de cada una:
  ficha.html   Todos los datos y los requerimientos tecnicos. Se abre en el
               navegador; para dejarla en PDF, Ctrl+P y "Guardar como PDF".
  datos.json   Lo mismo en crudo, por si se necesita procesar.
  bases.url    Acceso directo a la ficha oficial, donde estan las bases
               administrativas y tecnicas y los anexos para descargar.
  notas.txt    Para escribir. Este archivo NUNCA se sobrescribe.

Para trabajar en equipo: que cada persona escriba en el notas.txt de la
licitacion que le toca. Como son archivos distintos, no se pisan entre si.

Esta carpeta la genera el radar de licitaciones.
`;

/* ---------- guardar ---------- */

async function escribir(dir, nombre, contenido, soloSiNoExiste) {
  if (soloSiNoExiste) {
    try {
      await dir.getFileHandle(nombre);
      return false;                       // ya existe: no lo tocamos
    } catch (e) {
      /* no existe, seguimos */
    }
  }
  const archivo = await dir.getFileHandle(nombre, { create: true });
  const flujo = await archivo.createWritable();
  await flujo.write(contenido);
  await flujo.close();
  return true;
}

function dondeEstoy() {
  return carpeta && carpeta.name ? '"' + carpeta.name + '"' : "tu carpeta";
}


function avisar(texto, tono) {
  const caja = el("avisoGuardar");
  if (!caja) return;
  caja.textContent = texto;
  caja.className = "aviso-guardar" + (tono ? " " + tono : "");
  caja.classList.remove("oculto");
}

async function elegirCarpeta() {
  const elegida = await window.showDirectoryPicker({ mode: "readwrite", id: "radar" });
  carpeta = elegida;
  await recordar(elegida);
  await escribir(carpeta, "LEEME.txt", LEEME, true);
  avisar("Carpeta conectada: " + dondeEstoy() + ". Ya puedes guardar.", "ok");
  refrescarBoton();
}

async function guardar() {
  return guardarLicitaciones(licitaciones.filter((l) => favoritas.has(l.codigo)));
}


async function guardarUna(codigo) {
  const lic = licitaciones.find((l) => l.codigo === codigo);
  if (lic) await guardarLicitaciones([lic]);
}


async function guardarLicitaciones(marcadas) {
  if (!marcadas.length) {
    avisar("Primero marca con el corazon las licitaciones que quieras guardar.", "");
    return;
  }

  if (!carpeta) carpeta = await recuperar();
  if (!carpeta) { await elegirCarpeta(); }
  if (!(await tienePermiso(carpeta, true))) {
    avisar("Necesito tu permiso para escribir en la carpeta.", "error");
    return;
  }

  avisar("Guardando " + marcadas.length + "...", "");
  let nuevas = 0, actualizadas = 0;
  try {
    await escribir(carpeta, "LEEME.txt", LEEME, true);
    for (const lic of marcadas) {
      const dir = await carpeta.getDirectoryHandle(nombreCarpeta(lic), { create: true });
      const eraNueva = await escribir(dir, "notas.txt",
        "NOTAS - " + lic.nombre + "\r\n" + "=".repeat(40) + "\r\n\r\n" + textoPlano(lic) + "\r\n\r\n",
        true);
      await escribir(dir, "ficha.html", fichaHTML(lic));
      await escribir(dir, "datos.json", JSON.stringify(lic, null, 1));
      await escribir(dir, "bases.url",
        "[InternetShortcut]\r\nURL=" + FICHA_MP + encodeURIComponent(lic.codigo) + "\r\n");
      if (eraNueva) nuevas++; else actualizadas++;
    }
    const partes = [];
    if (nuevas) partes.push(nuevas + (nuevas === 1 ? " carpeta nueva" : " carpetas nuevas"));
    if (actualizadas) {
      partes.push(actualizadas + (actualizadas === 1 ? " actualizada" : " actualizadas"));
    }
    if (marcadas.length === 1) await dejarMarca(marcadas[0]);
    avisar("Listo: " + partes.join(" y ") + " en " + dondeEstoy() +
      ". Tus notas no se tocaron.", "ok");
  } catch (error) {
    avisar("No pude terminar de guardar: " + error.message, "error");
  }
}

async function dejarMarca(lic) {
  /* Le dice al organizador local en que carpeta archivar lo que se descargue
     ahora. Solo lo escribe el equipo que esta guardando, y se pisa cada vez:
     es una nota adhesiva, no un registro compartido. */
  try {
    await escribir(carpeta, "_ultima-descarga.json", JSON.stringify({
      codigo: lic.codigo,
      carpeta: nombreCarpeta(lic),
      nombre: lic.nombre,
      momento: new Date().toISOString(),
    }, null, 1));
  } catch (e) {
    /* si no se puede, el organizador simplemente no sabra donde archivar */
  }
}


function abrirBases(codigo) {
  window.open(FICHA_MP + encodeURIComponent(codigo), "_blank", "noopener");
}


function refrescarBoton() {
  const boton = el("guardarSeleccionadas");
  if (!boton) return;
  const cuantas = licitaciones.filter((l) => favoritas.has(l.codigo)).length;
  boton.textContent = cuantas
    ? "Guardar " + cuantas + (cuantas === 1 ? " licitación" : " licitaciones") + " en mi carpeta"
    : "Guardar en mi carpeta";
  boton.disabled = !cuantas;
}

async function prepararGuardado() {
  const zona = el("zonaGuardar");
  if (!zona) return;
  if (!HAY_SOPORTE) {
    zona.innerHTML = '<p class="aviso-guardar">Para guardar las licitaciones en una ' +
      "carpeta de tu computador, abre esta página en Chrome o Edge de escritorio.</p>";
    return;
  }
  el("guardarSeleccionadas").addEventListener("click", guardar);
  el("cambiarCarpeta").addEventListener("click", () => elegirCarpeta().catch(() => {}));

  carpeta = await recuperar();
  if (carpeta && (await tienePermiso(carpeta, false))) {
    avisar("Carpeta conectada: " + dondeEstoy() + ".", "ok");
  } else if (carpeta) {
    avisar("Carpeta " + dondeEstoy() + ": al guardar te pedirá permiso una vez.", "");
  }
  refrescarBoton();
}
