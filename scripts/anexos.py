"""Bajador de anexos de Mercado Publico.

Que hace: recorre tu carpeta de licitaciones y, en cada una que guardaste desde
la web, baja los documentos oficiales (bases, anexos administrativos, tecnicos y
economicos) a

    <tu carpeta>\\<folio - titulo>\\anexos\\

No hace falta apretar nada en Mercado Publico: los archivos llegan solos.

Por que funciona, si antes no se podia: el icono "Ver adjuntos" de la ficha abre
una ventana protegida con reCAPTCHA, y por ahi un programa no pasa. Pero la misma
ficha trae ademas tres grillas propias -Administrativo, Tecnico y Economico- que
apuntan a VerAntecedentes.aspx, y esa pagina no esta protegida. Desde ahi cada
archivo se pide con un envio de formulario corriente.

Nunca borra ni sobrescribe nada tuyo: si un anexo ya esta bajado lo saltea, y no
toca notas.txt.

LIMITE IMPORTANTE, medido el 31-08-2026 contra licitaciones reales
-------------------------------------------------------------------
Esto NO baja todos los anexos, y no hay forma de que sepa cuantos le faltan.

Mercado Publico usa cuatro categorias: Administrativo, Tecnico, Economico y
"Otros". La ficha solo publica grillas para las tres primeras. Lo que este en
"Otros" es invisible desde aca, y ahi va a parar cosa importante: en la
licitacion 3134-72-LR26 las bases completas y dos ampliaciones de plazo de
cierre estaban todas en "Otros", y la ficha no mostraba ninguna grilla.

Medido:
    1422051-25-LE26   la ficha expone  9 de 10 archivos
    3134-72-LR26      la ficha expone  0 de  6 archivos

La lista completa vive solo en la ventana "Ver adjuntos", que esta detras de un
reCAPTCHA y por eso no se automatiza. Este programa es una ayuda que te ahorra
clics cuando funciona, NO un reemplazo de mirar la ficha. Cuando de verdad te
importe una licitacion, abre "Ver adjuntos" y compara.
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AJUSTES = RAIZ / "organizador.json"
REGISTRO = "_anexos.log"

MODULOS = "https://www.mercadopublico.cl/Procurement/Modules/"
FICHA = MODULOS + "RFB/DetailsAcquisition.aspx?idlicitacion="
NAVEGADOR = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")

ESPERA_SEG = 1.2      # pausa entre descargas, para no apurar al servidor
INTENTOS = 3
PROHIBIDOS = '<>:"/\\|?*'

# Marcas fijas de la ficha: existen siempre, tenga anexos o no. Nos dejan
# distinguir "esta licitacion no publico nada" de "Mercado Publico cambio la
# pagina y el script quedo ciego". Sin esto, lo segundo se ve igual que lo
# primero y te quedarias sin las bases creyendo que no existen.
MARCAS_FICHA = ('id="grvAdministrativo"', 'id="grvTecnico"',
                'id="grvEconomico"', 'imgAdjuntos')

# Se llena cuando algo huele a que el sitio cambio. Se avisa fuerte al final.
AVISOS = []


def log(mensaje):
    """Imprime sin morir si la consola no sabe escribir un acento."""
    try:
        print(mensaje, flush=True)
    except UnicodeEncodeError:
        print(mensaje.encode("ascii", "replace").decode("ascii"), flush=True)


def abrir_sesion():
    sesion = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(CookieJar()))
    sesion.addheaders = [("User-Agent", NAVEGADOR),
                         ("Accept-Language", "es-CL,es;q=0.9")]
    return sesion


def pedir(sesion, url, datos=None, espera=60):
    """Pide una pagina reintentando: la red se cae y el sitio a veces demora."""
    ultimo = None
    for intento in range(INTENTOS):
        try:
            peticion = urllib.request.Request(url, data=datos)
            if datos:
                peticion.add_header("Content-Type",
                                    "application/x-www-form-urlencoded")
            with sesion.open(peticion, timeout=espera) as r:
                return r.read(), dict(r.headers)
        except Exception as error:          # red, timeout, error del servidor
            ultimo = error
            if intento < INTENTOS - 1:
                time.sleep(2 * (intento + 1))
    raise ultimo


def limpiar_nombre(nombre):
    """Windows no acepta ciertos caracteres en los nombres de archivo."""
    limpio = "".join("_" if c in PROHIBIDOS else c for c in nombre)
    limpio = limpio.replace("\r", " ").replace("\n", " ").strip(" .")
    return limpio[:150] or "anexo"


def grillas_de_la_ficha(sesion, codigo):
    """Los enlaces VerAntecedentes que la ficha lleva adentro.

    Devuelve (situacion, enlaces), donde situacion es:
      "ok"          encontramos grillas, todo normal
      "sin anexos"  la ficha esta entera pero esta licitacion no publico nada
      "cambio"      la ficha ya no se parece a lo que el script sabe leer
    """
    pagina, _ = pedir(sesion, FICHA + urllib.parse.quote(codigo))
    texto = pagina.decode("utf-8", "replace")

    unicos = []
    for enlace in re.findall(r'VerAntecedentes\.aspx\?enc=[^"]+', texto):
        entero = MODULOS + "Attachment/" + html.unescape(enlace)
        if entero not in unicos:
            unicos.append(entero)
    if unicos:
        return "ok", unicos

    # No hay enlaces. Falta saber si es porque no hay anexos o porque el sitio
    # cambio: si las marcas fijas de la ficha siguen ahi, la ficha esta sana.
    presentes = sum(1 for marca in MARCAS_FICHA if marca in texto)
    if presentes >= 2:
        return "sin anexos", []
    return "cambio", []


def archivos_de_la_grilla(sesion, url):
    """Lee una grilla: devuelve el viewstate y un (nombre, control) por archivo."""
    pagina, _ = pedir(sesion, url)
    texto = pagina.decode("utf-8", "replace")

    def oculto(campo):
        m = re.search(r'id="' + campo + r'" value="([^"]*)"', texto)
        return html.unescape(m.group(1)) if m else ""

    estado = {"__VIEWSTATE": oculto("__VIEWSTATE"),
              "__VIEWSTATEGENERATOR": oculto("__VIEWSTATEGENERATOR"),
              "__EVENTVALIDATION": oculto("__EVENTVALIDATION")}

    filas = []
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", texto, re.S):
        boton = re.search(r"grdAttachment\$(ctl\d+)\$grdIbtnView", fila)
        if not boton:
            continue
        celdas = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                  for c in re.findall(r"<td[^>]*>(.*?)</td>", fila, re.S)]
        celdas = [c for c in celdas if c]
        nombre = celdas[0] if celdas else "anexo"
        filas.append((nombre, "grdAttachment$" + boton.group(1) + "$grdIbtnView"))

    # Una grilla que existe pero de la que no sabemos sacar ni una fila, o que
    # ya no trae viewstate, es senal de que la pagina cambio.
    if not filas or not estado["__VIEWSTATE"]:
        AVISOS.append("una grilla de anexos ya no se puede leer")
    return estado, filas


def bajar_archivo(sesion, url, estado, control):
    campos = dict(estado)
    campos[control + ".x"] = "10"
    campos[control + ".y"] = "10"
    campos = {k: v for k, v in campos.items() if v != ""}
    datos = urllib.parse.urlencode(campos).encode()
    contenido, cabeceras = pedir(sesion, url, datos)
    tipo = (cabeceras.get("Content-Type") or "").lower()
    if "text/html" in tipo:
        raise ValueError("el sitio devolvio una pagina, no el archivo")
    if not contenido:
        raise ValueError("el archivo llego vacio")
    return contenido


def bajar_licitacion(sesion, codigo, destino):
    """Baja todo lo que tenga la licitacion. Devuelve (nuevos, saltados, fallidos)."""
    situacion, grillas = grillas_de_la_ficha(sesion, codigo)
    if situacion == "cambio":
        log("   OJO: no reconozco la ficha de Mercado Publico")
        AVISOS.append("la ficha de " + codigo + " ya no se puede leer")
        return 0, 0, 0
    if situacion == "sin anexos":
        # OJO: "no hay grillas" NO significa "no hay anexos". Medido el 31-08-2026:
        # la licitacion 3134-72-LR26 no tiene ninguna grilla en la ficha y sin
        # embargo publica 6 archivos -las bases incluidas- en la categoria
        # "Otros", que la ficha no expone. Nunca digas que no hay anexos.
        log("   NO VEO ANEXOS AQUI -> revisala a mano, puede tener y no los muestro")
        AVISOS.append("en " + codigo + " no vi ninguna grilla: revisala a mano")
        return 0, 0, 0

    carpeta = destino / "anexos"
    carpeta.mkdir(exist_ok=True)
    nuevos = saltados = fallidos = 0
    vistos = set()

    for url in grillas:
        try:
            estado, filas = archivos_de_la_grilla(sesion, url)
        except Exception as error:
            log("   no pude leer una grilla: " + str(error)[:70])
            fallidos += 1
            continue

        for nombre, control in filas:
            if nombre in vistos:      # el mismo archivo aparece en dos grillas
                continue
            vistos.add(nombre)
            archivo = carpeta / limpiar_nombre(nombre)
            if archivo.exists() and archivo.stat().st_size > 0:
                log("   ya estaba   " + nombre)
                saltados += 1
                continue
            try:
                contenido = bajar_archivo(sesion, url, estado, control)
                archivo.write_bytes(contenido)
                log("   bajado      %s  (%d KB)" % (nombre, len(contenido) // 1024))
                nuevos += 1
            except Exception as error:
                log("   FALLO       %s  -> %s" % (nombre, str(error)[:60]))
                fallidos += 1
            time.sleep(ESPERA_SEG)
    return nuevos, saltados, fallidos


def leer_carpeta():
    if AJUSTES.exists():
        try:
            datos = json.loads(AJUSTES.read_text(encoding="utf-8"))
            carpeta = Path(datos.get("carpeta", ""))
            if carpeta.is_dir():
                return carpeta
        except (json.JSONDecodeError, OSError):
            pass
    log("No encuentro tu carpeta de licitaciones.")
    log("Abre primero el Organizador de anexos, que te la pregunta, o escribe")
    log("la ruta en " + str(AJUSTES))
    sys.exit(1)


def licitaciones_guardadas(carpeta):
    """Cada subcarpeta con datos.json es una licitacion que guardaste."""
    encontradas = []
    for sub in sorted(carpeta.iterdir()):
        if not sub.is_dir():
            continue
        ficha = sub / "datos.json"
        if not ficha.exists():
            continue
        try:
            codigo = json.loads(ficha.read_text(encoding="utf-8")).get("codigo")
        except (json.JSONDecodeError, OSError):
            codigo = None
        if not codigo:               # de repuesto: el folio va en el nombre
            m = re.match(r"([\w-]+?)\s+-\s", sub.name)
            codigo = m.group(1) if m else None
        if codigo:
            encontradas.append((codigo, sub))
    return encontradas


def main():
    carpeta = leer_carpeta()
    log("Carpeta: " + str(carpeta))
    pendientes = licitaciones_guardadas(carpeta)
    if not pendientes:
        log("")
        log("No hay licitaciones guardadas todavia.")
        log("Guarda una desde la web y vuelve a correr esto.")
        return 0

    log("Licitaciones guardadas: %d" % len(pendientes))
    log("")
    sesion = abrir_sesion()
    total_nuevos = total_saltados = total_fallidos = 0

    for codigo, destino in pendientes:
        log(destino.name)
        try:
            nuevos, saltados, fallidos = bajar_licitacion(sesion, codigo, destino)
        except Exception as error:
            log("   no pude abrir la ficha: " + str(error)[:80])
            nuevos = saltados = 0
            fallidos = 1
        total_nuevos += nuevos
        total_saltados += saltados
        total_fallidos += fallidos
        if nuevos or fallidos:
            marca = time.strftime("%Y-%m-%d %H:%M")
            try:
                with open(destino / REGISTRO, "a", encoding="utf-8") as registro:
                    registro.write("%s  nuevos=%d ya estaban=%d fallidos=%d\n"
                                   % (marca, nuevos, saltados, fallidos))
            except OSError:
                pass
        log("")

    log("-" * 52)
    log("Listo. Bajados %d, ya estaban %d, fallidos %d."
        % (total_nuevos, total_saltados, total_fallidos))
    if total_fallidos:
        log("Los fallidos casi siempre se arreglan corriendo esto de nuevo.")

    # Se avisa SIEMPRE, aunque todo haya salido bien. Es la unica forma de que
    # ella no confunda "bajo sin errores" con "los tengo todos".
    log("")
    log("ESTO NO ES LA LISTA COMPLETA.")
    log("Solo veo las categorias Administrativo, Tecnico y Economico.")
    log("Lo que el organismo suba como \"Otros\" -a veces las bases mismas-")
    log("no aparece aca. Si la licitacion te importa, abre \"Ver adjuntos\"")
    log("en la ficha y compara con lo que hay en la carpeta.")

    if AVISOS:
        log("")
        log("!" * 52)
        log("MERCADO PUBLICO PARECE HABER CAMBIADO SU PAGINA")
        log("")
        log("El script dejo de reconocer lo que antes leia sin problema.")
        log("NO des por hecho que esas licitaciones no tienen anexos:")
        log("revisalas a mano en el sitio y avisale a Claude.")
        log("")
        for aviso in sorted(set(AVISOS)):
            log("  - " + aviso)
        log("!" * 52)
        return 1

    return 1 if total_fallidos and not total_nuevos else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("")
        log("Cortado por ti.")
        sys.exit(0)
