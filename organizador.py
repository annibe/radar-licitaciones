"""Organizador de anexos descargados.

Que hace: vigila tu carpeta de Descargas. Cuando bajas los anexos de una
licitacion desde Mercado Publico, los mueve solos a

    <tu carpeta compartida>\\<folio - titulo>\\anexos\\

Como sabe a cual licitacion pertenecen: la pagina web deja una nota
(_ultima-descarga.json) cada vez que aprietas "Guardar y abrir anexos". Todo lo
que descargues en los minutos siguientes se archiva en esa licitacion.

No toca internet ni el sitio de ChileCompra: solo mueve archivos de una carpeta
a otra en tu computador.

Se cierra con Ctrl+C o cerrando la ventana.
"""

import json
import re
import zipfile
import hashlib
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
AJUSTES = RAIZ / "organizador.json"
DESCARGAS = Path.home() / "Downloads"
MARCA = "_ultima-descarga.json"
REGISTRO = "_organizador.log"

# extensiones que valen la pena archivar
UTILES = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".7z",
          ".jpg", ".jpeg", ".png", ".txt", ".rtf", ".odt", ".ods", ".dwg"}
# archivos a medio bajar
EN_CURSO = {".crdownload", ".part", ".tmp", ".partial"}

# solo se archivan descargas que vengan de estos dominios
DOMINIOS = ("mercadopublico.cl", "chilecompra.cl")

INTENTOS_MAX = 45         # ~3 minutos: los PDF grandes tardan en pasar el antivirus
VENTANA_MINUTOS = 120     # cuanto rato despues de la marca seguimos archivando.
                          # Generoso a proposito: el validador de origen ya impide
                          # que se archive algo que no venga de Mercado Publico.
PAUSA_SEG = 4


def log(mensaje):
    print(mensaje, flush=True)


def elegir_carpeta():
    """Primera vez: le pedimos la carpeta compartida con un dialogo normal."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError:
        log("No puedo abrir el selector de carpetas. Escribe la ruta en " + str(AJUSTES))
        return None

    raiz = tk.Tk()
    raiz.withdraw()
    messagebox.showinfo(
        "Organizador de anexos",
        "Elige la carpeta donde el radar guarda las licitaciones.\n\n"
        "Es la misma que elegiste en la web, por ejemplo:\n"
        "OneDrive\\Licitaciones",
    )
    elegida = filedialog.askdirectory(title="Carpeta de licitaciones")
    raiz.destroy()
    return Path(elegida) if elegida else None


def leer_ajustes():
    if AJUSTES.exists():
        try:
            datos = json.loads(AJUSTES.read_text(encoding="utf-8"))
            carpeta = Path(datos.get("carpeta", ""))
            if carpeta.is_dir():
                return carpeta
        except (json.JSONDecodeError, OSError):
            pass
    carpeta = elegir_carpeta()
    if not carpeta or not carpeta.is_dir():
        log("Sin carpeta no puedo trabajar. Cierro.")
        sys.exit(1)
    AJUSTES.write_text(json.dumps({"carpeta": str(carpeta)}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return carpeta


def leer_marca(compartida):
    archivo = compartida / MARCA
    if not archivo.exists():
        return None
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        momento = datetime.fromisoformat(datos["momento"].replace("Z", "+00:00"))
        datos["desde"] = momento.timestamp()
        return datos
    except (json.JSONDecodeError, OSError, KeyError, ValueError):
        return None


def origen(archivo):
    """De donde se bajo el archivo.

    Windows marca cada descarga con un flujo alterno llamado Zone.Identifier, y
    Chrome escribe ahi la direccion de origen. Es lo que nos permite archivar solo
    lo que viene de Mercado Publico y no tu factura de la luz.
    Devuelve el dominio, o None si el archivo no tiene marca (no se descargo).
    """
    try:
        with open(str(archivo) + ":Zone.Identifier", "r",
                  encoding="utf-8", errors="replace") as f:
            zona = f.read()
    except OSError:
        return None
    for clave in ("HostUrl", "ReferrerUrl"):
        m = re.search(clave + r"=(\S+)", zona)
        if m:
            return re.sub(r"^https?://", "", m.group(1)).split("/")[0].lower()
    return None


def viene_de_mercado_publico(archivo):
    dominio = origen(archivo)
    if not dominio:
        return False, "no parece una descarga"
    if any(d in dominio for d in DOMINIOS):
        return True, dominio
    return False, dominio


def esta_completo(archivo):
    """Evita mover algo que todavia se esta descargando.

    Que el tamano deje de crecer no alcanza: Chrome mantiene el archivo abierto
    un rato despues de terminar, y mover en ese momento revienta con
    "WinError 32: el archivo esta siendo utilizado por otro proceso", dejando
    una copia a medias. Abrirlo en modo escritura falla mientras otro proceso lo
    tenga tomado, asi que eso nos sirve de prueba: si abre, es nuestro.
    """
    if archivo.suffix.lower() in EN_CURSO:
        return False
    try:
        tam = archivo.stat().st_size
        time.sleep(1.2)
        if tam == 0 or tam != archivo.stat().st_size:
            return False
        with open(archivo, "r+b"):
            pass
        return True
    except OSError:
        return False


def firma(archivo):
    """Huella del contenido de un archivo."""
    resumen = hashlib.md5()
    with open(archivo, "rb") as f:
        for trozo in iter(lambda: f.read(65536), b""):
            resumen.update(trozo)
    return resumen.hexdigest()


def ya_archivado(destino, archivo):
    """Si en la carpeta ya hay un archivo con el mismo contenido.

    Un solo clic en la lupa de Mercado Publico a veces dispara la descarga
    varias veces, y Chrome le va poniendo "(1)", "(2)"... Sin esta comprobacion
    la carpeta termina con tres copias identicas y nombres distintos. Comparamos
    primero por tamano, que es barato, y solo calculamos la huella si coincide.
    """
    if not destino.is_dir():
        return False
    try:
        tam = archivo.stat().st_size
        iguales = [f for f in destino.iterdir()
                   if f.is_file() and f.stat().st_size == tam]
        if not iguales:
            return False
        mia = firma(archivo)
        return any(firma(otro) == mia for otro in iguales)
    except OSError:
        return False


def sin_sufijo_de_copia(nombre):
    """Chrome renombra a "archivo (1).pdf" cuando ya bajaste ese archivo antes.

    Ese sufijo no dice nada del documento y ensucia la carpeta, asi que lo
    sacamos al archivar. Si el nombre limpio ya esta ocupado, nombre_libre se
    encarga de desempatar.
    """
    return re.sub(r"\s*\(\d+\)(?=\.[A-Za-z0-9]+$)", "", nombre)


def nombre_libre(destino, nombre):
    nombre = sin_sufijo_de_copia(nombre)
    candidato = destino / nombre
    if not candidato.exists():
        return candidato
    tronco, sufijo = candidato.stem, candidato.suffix
    for numero in range(2, 100):
        otro = destino / (tronco + " (" + str(numero) + ")" + sufijo)
        if not otro.exists():
            return otro
    return destino / (tronco + " " + str(int(time.time())) + sufijo)


def descomprimir(archivo, destino):
    """Si Mercado Publico entrego un ZIP, lo abrimos en la carpeta.

    La descarga masiva ("Seleccionar Todos" + el codigo de la imagen) entrega un
    solo comprimido con todos los anexos. Guardar el ZIP tal cual obligaria a
    abrirlo a mano cada vez, asi que lo dejamos ya descomprimido.
    Devuelve la lista de archivos extraidos, o None si no era un ZIP legible.
    """
    if archivo.suffix.lower() != ".zip":
        return None
    try:
        with zipfile.ZipFile(archivo) as z:
            nombres = [n for n in z.namelist() if not n.endswith("/")]
            sacados = []
            for nombre in nombres:
                # nos quedamos solo con el nombre, sin rutas raras dentro del zip
                limpio = Path(nombre.replace("\\", "/")).name
                if not limpio:
                    continue
                final = nombre_libre(destino, limpio)
                with z.open(nombre) as dentro, open(final, "wb") as fuera:
                    shutil.copyfileobj(dentro, fuera)
                sacados.append(final)
            return sacados
    except (zipfile.BadZipFile, OSError):
        return None


def archivar(archivo, destino):
    """Deja el archivo en la carpeta de la licitacion.

    En Windows "mover" es copiar y luego borrar. Con archivos grandes el
    navegador o el antivirus suelen tener tomado el original justo en ese
    momento: la copia se hace, el borrado falla, y si eso se trata como fracaso
    el programa vuelve a intentarlo y termina duplicando el archivo una y otra
    vez. Aqui separamos las dos cosas: si la copia quedo, el archivo esta a
    salvo; el original se borra despues, cuando lo suelten.

    Devuelve (destino_final, hay_que_borrar_el_original).
    """
    final = nombre_libre(destino, archivo.name)
    parcial = final.with_name(final.name + ".parcial")
    shutil.copy2(str(archivo), str(parcial))
    parcial.replace(final)
    try:
        archivo.unlink()
        return final, False
    except OSError:
        return final, True


def anotar(compartida, linea):
    try:
        with (compartida / REGISTRO).open("a", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d-%m-%Y %H:%M") + "  " + linea + "\n")
    except OSError:
        pass


def main():
    compartida = leer_ajustes()
    log("Organizador de anexos en marcha.")
    log("  Vigilando:  " + str(DESCARGAS))
    log("  Archivando: " + str(compartida))
    log("")
    log("Deja esta ventana abierta mientras descargas los anexos.")
    log("Para cerrarlo: Ctrl+C o cierra la ventana.")
    log("")

    if not DESCARGAS.is_dir():
        log("No encuentro tu carpeta de Descargas en " + str(DESCARGAS))
        sys.exit(1)

    ya_vistos = {a.name for a in DESCARGAS.iterdir() if a.is_file()}
    marca_anterior = None
    esperando = {}
    por_borrar = set()

    while True:
        time.sleep(PAUSA_SEG)
        marca = leer_marca(compartida)
        if not marca:
            continue

        if marca.get("momento") != (marca_anterior or {}).get("momento"):
            marca_anterior = marca
            log("Ahora archivando en: " + marca["carpeta"])
            # lo que ya estaba antes de la marca no nos interesa
            ya_vistos = {a.name for a in DESCARGAS.iterdir() if a.is_file()}

        if datetime.now().timestamp() - marca["desde"] > VENTANA_MINUTOS * 60:
            continue

        for original in list(por_borrar):
            try:
                original.unlink()
                por_borrar.discard(original)
                log("  ya lo solto el navegador, saque el original de Descargas")
            except FileNotFoundError:
                por_borrar.discard(original)
            except OSError:
                pass                      # sigue tomado; lo intentamos de nuevo

        destino = compartida / marca["carpeta"] / "anexos"
        for archivo in DESCARGAS.iterdir():
            if not archivo.is_file() or archivo.name in ya_vistos:
                continue
            if archivo.suffix.lower() not in UTILES:
                continue
            valido, de_donde = viene_de_mercado_publico(archivo)
            if not valido:
                ya_vistos.add(archivo.name)      # no volvemos a mirarlo
                log("  ignorado, " + de_donde + ": " + archivo.name)
                continue
            if not esta_completo(archivo):
                intentos = esperando.get(archivo.name, 0) + 1
                esperando[archivo.name] = intentos
                if intentos == 3:
                    log("  esperando a que el navegador lo suelte: " + archivo.name)
                elif intentos > INTENTOS_MAX:
                    ya_vistos.add(archivo.name)
                    log("  me rindo con " + archivo.name + ": sigue ocupado.")
                    anotar(compartida, "NO ARCHIVADO (ocupado): " + archivo.name)
                continue
            if ya_archivado(destino, archivo):
                ya_vistos.add(archivo.name)
                log("  repetido, ya lo tienes archivado: " + archivo.name)
                log("    lo dejo en Descargas; borralo tu si quieres")
                continue
            destino.mkdir(parents=True, exist_ok=True)
            try:
                sacados = descomprimir(archivo, destino)
                if sacados is not None:
                    ya_vistos.add(archivo.name)
                    esperando.pop(archivo.name, None)
                    log("  descomprimido: " + str(len(sacados)) + " archivos de " + archivo.name)
                    for s in sacados:
                        log("     " + s.name[:60])
                        anotar(compartida, marca["carpeta"] + "  <-  " + s.name)
                    try:
                        archivo.unlink()
                    except OSError:
                        por_borrar.add(archivo)
                    continue

                final, pendiente = archivar(archivo, destino)
                if pendiente:
                    por_borrar.add(archivo)
                ya_vistos.add(archivo.name)
                esperando.pop(archivo.name, None)
                log("  archivado: " + final.name)
                anotar(compartida, marca["carpeta"] + "  <-  " + final.name)
            except (OSError, shutil.Error) as error:
                # sin este tope, un archivo trabado se reintenta cada 4 segundos
                # para siempre y llena la pantalla de la misma linea
                intentos = esperando.get(archivo.name, 0) + 1
                esperando[archivo.name] = intentos
                if intentos == 1:
                    log("  ocupado, reintentando: " + archivo.name)
                elif intentos > INTENTOS_MAX:
                    ya_vistos.add(archivo.name)
                    log("  me rindo con " + archivo.name + ". Muevelo a mano a:")
                    log("    " + str(destino))
                    anotar(compartida, "NO ARCHIVADO (ocupado): " + archivo.name)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("")
        log("Organizador detenido.")
