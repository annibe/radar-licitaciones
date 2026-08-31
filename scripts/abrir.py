"""Abre el radar en el navegador.

Es lo que ejecuta el acceso directo "Abrir radar":
  1. actualiza los datos consultando la API de Mercado Publico,
  2. levanta un servidor local en 127.0.0.1:8766,
  3. abre la pagina en el navegador y se queda escuchando.

Para cerrarlo, cierra esta ventana negra o pulsa Ctrl+C.
"""

import subprocess
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web"
PUERTO_PREFERIDO = 8790


class Silencioso(SimpleHTTPRequestHandler):
    """Sirve la carpeta web sin llenar la pantalla de lineas de log."""

    def log_message(self, formato, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def actualizar():
    print("Buscando licitaciones nuevas en Mercado Publico...")
    print("(la primera vez puede tardar varios minutos)")
    print("")
    resultado = subprocess.run([sys.executable, str(RAIZ / "scripts" / "actualizar.py")])
    if resultado.returncode != 0:
        print("")
        print("No pude actualizar los datos. Abro igual la pagina con lo que haya guardado.")
    print("")


def levantar():
    """Busca un puerto libre: en este equipo conviven otras apps locales."""
    for puerto in range(PUERTO_PREFERIDO, PUERTO_PREFERIDO + 20):
        try:
            return ThreadingHTTPServer(
                ("127.0.0.1", puerto), partial(Silencioso, directory=str(WEB))
            )
        except OSError:
            continue
    print("No encontre ningun puerto libre entre " + str(PUERTO_PREFERIDO) +
          " y " + str(PUERTO_PREFERIDO + 19) + ".")
    sys.exit(1)


def main():
    actualizar()

    servidor = levantar()
    DIRECCION = "http://127.0.0.1:" + str(servidor.server_address[1]) + "/"
    print("Radar abierto en " + DIRECCION)
    print("Deja esta ventana abierta mientras lo uses. Para cerrarlo: Ctrl+C.")
    threading.Timer(1.0, lambda: webbrowser.open(DIRECCION)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Radar cerrado.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
