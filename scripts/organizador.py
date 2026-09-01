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

VENTANA_MINUTOS = 25      # cuanto rato despues de la marca seguimos archivando
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
    """Evita mover algo que todavia se esta descargando."""
    if archivo.suffix.lower() in EN_CURSO:
        return False
    try:
        tam = archivo.stat().st_size
        time.sleep(1.2)
        return tam == archivo.stat().st_size and tam > 0
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


def nombre_libre(destino, nombre):
    candidato = destino / nombre
    if not candidato.exists():
        return candidato
    tronco, sufijo = candidato.stem, candidato.suffix
    for numero in range(2, 100):
        otro = destino / (tronco + " (" + str(numero) + ")" + sufijo)
        if not otro.exists():
            return otro
    return destino / (tronco + " " + str(int(time.time())) + sufijo)


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
                continue
            if ya_archivado(destino, archivo):
                ya_vistos.add(archivo.name)
                log("  repetido, ya lo tienes archivado: " + archivo.name)
                log("    lo dejo en Descargas; borralo tu si quieres")
                continue
            destino.mkdir(parents=True, exist_ok=True)
            try:
                final = nombre_libre(destino, archivo.name)
                shutil.move(str(archivo), str(final))
                ya_vistos.add(archivo.name)
                log("  archivado: " + final.name)
                anotar(compartida, marca["carpeta"] + "  <-  " + final.name)
            except (OSError, shutil.Error) as error:
                log("  no pude mover " + archivo.name + ": " + str(error))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("")
        log("Organizador detenido.")
