"""Radar de licitaciones de Mercado Publico.

Cada ejecucion:
  1. barre TODAS las licitaciones vigentes (abiertas) de Mercado Publico,
  2. se queda con las que calzan con los filtros de config.json,
  3. compara con la foto anterior y marca cuales son nuevas,
  4. deja el resultado en web/datos/ para la web y para el correo.

Como la foto se reconstruye entera en cada corrida, la base solo contiene
licitaciones vigentes: las que cierran desaparecen solas.

Uso:
    py scripts/actualizar.py

El ticket sale de la variable de entorno MP_TICKET o de ~/.mp_ticket
"""

import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.json"
DATOS = RAIZ / "web" / "datos"
VIGENTES = DATOS / "vigentes.json"
NUEVAS = DATOS / "nuevas.json"
INDICE = DATOS / "indice.json"
API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
ZONA_CHILE = timezone(timedelta(hours=-4))

ESTADOS = {
    "5": "Publicada", "6": "Cerrada", "7": "Desierta",
    "8": "Adjudicada", "18": "Revocada", "19": "Suspendida",
}

# Tablas de codigos del diccionario oficial de la API
MODALIDAD_PAGO = {
    1: "pago a 30 días", 2: "pago a 30, 60 y 90 días", 3: "pago al día",
    4: "pago anual", 5: "pago bimensual", 6: "pago contra entrega conforme",
    7: "pagos mensuales", 8: "pago por estado de avance", 9: "pago trimestral",
    10: "pago a 60 días",
}
UNIDAD_TIEMPO = {1: "horas", 2: "días", 3: "semanas", 4: "meses", 5: "años"}
ESTIMACION = {1: "presupuesto disponible", 2: "precio referencial",
              3: "monto no estimable"}


def log(mensaje):
    print(mensaje, flush=True)


def leer_ticket():
    """El ticket vive FUERA de la carpeta del proyecto, para no subirlo nunca a GitHub."""
    ticket = os.environ.get("MP_TICKET", "").strip()
    if ticket:
        return ticket
    for archivo in (Path.home() / ".mp_ticket", RAIZ / "ticket.txt"):
        if archivo.exists():
            ticket = archivo.read_text(encoding="utf-8").strip()
            if ticket:
                return ticket
    log(
        "ERROR: no encuentro el ticket de la API.\n"
        "  - En tu computador: el ticket va en el archivo " + str(Path.home() / ".mp_ticket") + "\n"
        "    (solo el ticket dentro, sin comillas ni espacios).\n"
        "  - En GitHub: guardalo como secreto MP_TICKET."
    )
    sys.exit(1)


def leer_config():
    with CONFIG.open(encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("palabras_clave", [])
    cfg.setdefault("excluir_palabras", [])
    cfg.setdefault("monto_min_clp", 0)
    cfg.setdefault("monto_max_clp", None)
    cfg.setdefault("regiones", [])
    cfg.setdefault("pausa_entre_consultas_seg", 0.5)
    cfg.setdefault("max_detalles_por_corrida", 600)
    cfg.setdefault("refrescar_detalle_cada_dias", 7)
    return cfg


def normalizar(texto):
    """Minusculas y sin tildes, para comparar sin sorpresas."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFD", str(texto))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return texto.lower()


def consultar(params, ticket, intentos=4, pausa=0.5):
    """Una llamada a la API, con reintentos: el servicio devuelve 500 cuando se satura."""
    params = dict(params)
    params["ticket"] = ticket
    url = API + "?" + urllib.parse.urlencode(params)
    visible = url.replace(ticket, "***")
    for intento in range(1, intentos + 1):
        try:
            peticion = urllib.request.Request(
                url, headers={"User-Agent": "radar-licitaciones/1.0"}
            )
            with urllib.request.urlopen(peticion, timeout=60) as respuesta:
                crudo = respuesta.read().decode("utf-8-sig", errors="replace")
            return json.loads(crudo)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            codigo = getattr(error, "code", "sin respuesta")
            if intento == intentos:
                log("  ! fallo definitivo (" + str(codigo) + ") en " + visible)
                return None
            espera = pausa * (2 ** intento)
            log("  . reintento " + str(intento) + " tras " + str(codigo) +
                ", espero " + format(espera, ".1f") + "s")
            time.sleep(espera)
        except json.JSONDecodeError:
            if intento == intentos:
                log("  ! respuesta ilegible en " + visible)
                return None
            time.sleep(pausa * (2 ** intento))
    return None


def compilar(palabras):
    """Convierte cada palabra clave en un patron que respeta los limites de palabra.

    Sin esto, "ia" calzaria dentro de vigilancia, farmacia o consultoria. Las palabras
    de mas de 3 letras aceptan derivados: "digital" encuentra digitales y
    digitalizacion; "plataforma", plataformas.
    """
    patrones = []
    for palabra in palabras:
        limpia = normalizar(palabra).strip()
        if not limpia:
            continue
        cuerpo = r"\s+".join(re.escape(parte) for parte in limpia.split())
        patron = r"\b" + cuerpo + (r"\b" if len(limpia) <= 3 else "")
        patrones.append(re.compile(patron))
    return patrones


def calza_palabras(texto, claves, excluidas):
    if excluidas and any(patron.search(texto) for patron in excluidas):
        return False
    if not claves:
        return True
    return any(patron.search(texto) for patron in claves)


def si_no(valor):
    """La API mezcla 1/0, "1"/"0" y true/false para lo mismo."""
    if valor in (None, "", "null"):
        return None
    if isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if texto in ("1", "true", "si", "sí"):
        return True
    if texto in ("0", "false", "no"):
        return False
    return None


def entero(valor):
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def duracion_texto(detalle):
    valor = entero(detalle.get("TiempoDuracionContrato"))
    if not valor:
        return None
    unidad = UNIDAD_TIEMPO.get(entero(detalle.get("UnidadTiempoDuracionContrato")), "")
    return (str(valor) + " " + unidad).strip()


def requerimientos(detalle, items):
    """El cuadro resumen: que piden, que exigen y bajo que condiciones."""
    fechas = detalle.get("Fechas") or {}
    lista = []
    for item in items[:15]:
        lista.append({
            "producto": (item.get("NombreProducto") or "").strip(),
            "categoria": (item.get("Categoria") or "").strip(),
            "cantidad": item.get("Cantidad"),
            "unidad": (item.get("UnidadMedida") or "").strip(),
            "detalle": (item.get("Descripcion") or "").strip()[:400],
        })
    return {
        "items": lista,
        "items_total": ((detalle.get("Items") or {}).get("Cantidad")) or len(items),
        "etapas": entero(detalle.get("Etapas")),
        "toma_razon": si_no(detalle.get("TomaRazon")),
        "visita_terreno": fechas.get("FechaVisitaTerreno"),
        "direccion_visita": (detalle.get("DireccionVisita") or "").strip(),
        "entrega_antecedentes": fechas.get("FechaEntregaAntecedentes"),
        "soporte_fisico": fechas.get("FechaSoporteFisico"),
        "direccion_entrega": (detalle.get("DireccionEntrega") or "").strip(),
        "apertura_tecnica": fechas.get("FechaActoAperturaTecnica"),
        "apertura_economica": fechas.get("FechaActoAperturaEconomica"),
        "respuestas": fechas.get("FechaPubRespuestas"),
        "estimada_adjudicacion": fechas.get("FechaEstimadaAdjudicacion"),
        "duracion": duracion_texto(detalle),
        "renovable": si_no(detalle.get("EsRenovable")),
        "prohibiciones": (detalle.get("ProhibicionContratacion") or "").strip()[:300],
        "extension_plazo": si_no(detalle.get("ExtensionPlazo")),
        "modalidad_pago": MODALIDAD_PAGO.get(entero(detalle.get("Modalidad"))),
        "estimacion": ESTIMACION.get(entero(detalle.get("Estimacion"))),
        "monto_nota": (detalle.get("JustificacionMontoEstimado") or "").strip()[:300],
        "financiamiento": (detalle.get("FuenteFinanciamiento") or "").strip(),
        "obras": si_no(detalle.get("Obras")),
        "reclamos_comprador": entero(detalle.get("CantidadReclamos")),
        "contacto": (detalle.get("NombreResponsableContrato") or "").strip(),
        "contacto_email": (detalle.get("EmailResponsableContrato") or "").strip(),
        "contacto_fono": (detalle.get("FonoResponsableContrato") or "").strip(),
    }


def limpiar(detalle):
    """Se queda solo con los campos que la web y el correo necesitan."""
    comprador = detalle.get("Comprador") or {}
    fechas = detalle.get("Fechas") or {}
    items = ((detalle.get("Items") or {}).get("Listado")) or []
    categorias = sorted({
        (item.get("Categoria") or "").strip()
        for item in items
        if (item.get("Categoria") or "").strip()
    })
    codigo_estado = str(detalle.get("CodigoEstado") or "")
    monto = detalle.get("MontoEstimado")
    try:
        monto = float(monto) if monto not in (None, "") else None
    except (TypeError, ValueError):
        monto = None
    return {
        "codigo": detalle.get("CodigoExterno"),
        "nombre": (detalle.get("Nombre") or "").strip(),
        "descripcion": (detalle.get("Descripcion") or "").strip()[:1200],
        "estado": detalle.get("Estado") or ESTADOS.get(codigo_estado, codigo_estado),
        "codigo_estado": codigo_estado,
        "tipo": detalle.get("Tipo"),
        # ojo: estas fechas viven dentro de "Fechas", no en la raiz
        "publicacion": fechas.get("FechaPublicacion") or fechas.get("FechaCreacion"),
        "cierre": fechas.get("FechaCierre") or detalle.get("FechaCierre"),
        "monto": monto,
        "moneda": detalle.get("Moneda"),
        "organismo": comprador.get("NombreOrganismo"),
        "unidad": comprador.get("NombreUnidad"),
        "region": comprador.get("RegionUnidad"),
        "comuna": comprador.get("ComunaUnidad"),
        "categorias": categorias[:8],
        "requerimientos": requerimientos(detalle, items),
    }


def pasa_filtros_finales(ficha, cfg):
    minimo = cfg.get("monto_min_clp") or 0
    maximo = cfg.get("monto_max_clp")
    monto = ficha.get("monto")
    if monto is not None:
        if minimo and monto < minimo:
            return False
        if maximo and monto > maximo:
            return False
    regiones = [normalizar(r) for r in cfg.get("regiones") or []]
    if regiones:
        region = normalizar(ficha.get("region"))
        if not any(r in region for r in regiones):
            return False
    return True


def cargar_foto_anterior():
    """La foto de la corrida pasada: codigo -> ficha guardada."""
    if not VIGENTES.exists():
        return {}
    try:
        fichas = json.loads(VIGENTES.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {f["codigo"]: f for f in fichas if f.get("codigo")}


def hay_que_refrescar(ficha, hoy, cada_dias):
    """Reusa el detalle guardado: ahorra consultas a la API."""
    visto = ficha.get("actualizado")
    if not visto:
        return True
    try:
        return (hoy - datetime.strptime(visto, "%Y-%m-%d").date()).days >= cada_dias
    except ValueError:
        return True


def main():
    cfg = leer_config()
    ticket = leer_ticket()
    DATOS.mkdir(parents=True, exist_ok=True)

    hoy = datetime.now(ZONA_CHILE).date()
    pausa = cfg["pausa_entre_consultas_seg"]
    claves = compilar(cfg["palabras_clave"])
    excluidas = compilar(cfg["excluir_palabras"])

    log("Radar de licitaciones - " + hoy.strftime("%d-%m-%Y") + " (hora de Chile)")
    log("Palabras clave: " + (", ".join(cfg["palabras_clave"]) or "(todas)"))

    anterior = cargar_foto_anterior()
    primera_vez = not anterior
    log("Foto anterior: " + (str(len(anterior)) + " licitaciones" if anterior else "no hay, esta es la primera carga"))

    log("\nBarriendo las licitaciones vigentes en Mercado Publico...")
    respuesta = consultar({"estado": "activas"}, ticket, pausa=pausa)
    listado = (respuesta or {}).get("Listado") or []
    if not listado:
        log("La API no devolvio licitaciones vigentes. Dejo la foto anterior intacta.")
        sys.exit(1)
    log("  vigentes en total: " + str(len(listado)))

    candidatas = []
    vistos = set()
    for fila in listado:
        codigo = fila.get("CodigoExterno")
        if not codigo or codigo in vistos:
            continue
        vistos.add(codigo)
        if calza_palabras(normalizar(fila.get("Nombre")), claves, excluidas):
            candidatas.append(codigo)
    log("  calzan por nombre: " + str(len(candidatas)))

    reusadas = [c for c in candidatas
                if c in anterior and not hay_que_refrescar(anterior[c], hoy, cfg["refrescar_detalle_cada_dias"])]
    por_consultar = [c for c in candidatas if c not in reusadas]
    log("  detalle reutilizado de la foto anterior: " + str(len(reusadas)))

    tope = cfg["max_detalles_por_corrida"]
    if len(por_consultar) > tope:
        log("  (corto en " + str(tope) + " consultas para no gastar la cuota diaria)")
        por_consultar = por_consultar[:tope]

    fichas = []
    for codigo in reusadas:
        fichas.append(anterior[codigo])

    log("  consultando el detalle de " + str(len(por_consultar)) + " licitaciones...")
    for numero, codigo in enumerate(por_consultar, 1):
        time.sleep(pausa)
        datos = consultar({"codigo": codigo}, ticket, pausa=pausa)
        detalle = ((datos or {}).get("Listado") or [None])[0]
        if not detalle:
            continue
        ficha = limpiar(detalle)
        if not pasa_filtros_finales(ficha, cfg):
            continue
        previa = anterior.get(codigo)
        ficha["visto"] = (previa or {}).get("visto") or hoy.isoformat()
        ficha["actualizado"] = hoy.isoformat()
        fichas.append(ficha)
        if numero % 25 == 0:
            log("    " + str(numero) + "/" + str(len(por_consultar)))

    fichas = [f for f in fichas if pasa_filtros_finales(f, cfg)]
    nuevas = [] if primera_vez else [f for f in fichas if f["codigo"] not in anterior]

    fichas.sort(key=lambda f: f.get("cierre") or "9999")
    VIGENTES.write_text(json.dumps(fichas, ensure_ascii=False, indent=1), encoding="utf-8")
    NUEVAS.write_text(json.dumps(nuevas, ensure_ascii=False, indent=1), encoding="utf-8")

    cerradas = [c for c in anterior if c not in {f["codigo"] for f in fichas}]
    INDICE.write_text(json.dumps({
        "actualizado": datetime.now(ZONA_CHILE).isoformat(timespec="seconds"),
        "vigentes": len(fichas),
        "nuevas": len(nuevas),
        "salieron": len(cerradas),
        "primera_carga": primera_vez,
        "filtros": {
            "palabras_clave": cfg["palabras_clave"],
            "excluir_palabras": cfg["excluir_palabras"],
            "monto_min_clp": cfg["monto_min_clp"],
            "monto_max_clp": cfg["monto_max_clp"],
            "regiones": cfg["regiones"],
        },
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log("")
    log("Vigentes que calzan: " + str(len(fichas)))
    if primera_vez:
        log("Primera carga: no marco ninguna como nueva. Desde manana solo aviso los cambios.")
    else:
        log("Nuevas desde la corrida anterior: " + str(len(nuevas)))
        log("Salieron de la lista (cerraron o cambiaron de estado): " + str(len(cerradas)))


if __name__ == "__main__":
    main()
