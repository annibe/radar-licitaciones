"""Arma el Excel y manda el correo diario con el resumen de licitaciones.

Se ejecuta despues de actualizar.py:
    py scripts/enviar_correo.py                (arma el Excel y envia)
    py scripts/enviar_correo.py --solo-excel   (solo arma el Excel, no envia)

Las claves del correo NO viven en esta carpeta:
  - en tu computador, en el archivo  C:\\Users\\<tu usuario>\\.mp_correo  (formato JSON)
  - en GitHub, como secretos CORREO_USUARIO y CORREO_CLAVE
"""

import argparse
import csv
import json
import os
import smtplib
import ssl
import sys
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

import excel

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "web" / "datos"
DESCARGAS = RAIZ / "web" / "descargas"
CONFIG = RAIZ / "config.json"
ZONA_CHILE = timezone(timedelta(hours=-4))

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

COLUMNAS = [
    ("Código", 16), ("Nombre", 52), ("Estado", 13), ("Organismo", 34),
    ("Unidad de compra", 28), ("Región", 24), ("Comuna", 16),
    ("Publicada", 17), ("Cierra", 17), ("Días para cierre", 9),
    ("Monto estimado", 16), ("Moneda", 8), ("Tipo", 7),
    ("Categorías", 30),
    ("Qué piden", 46), ("Visita a terreno", 15), ("Entrega antecedentes", 16),
    ("Duración contrato", 15), ("Renovable", 10), ("Prohibiciones", 34),
    ("Contraparte", 26),
    ("Descripción", 60), ("Bases", 16),
]

COLUMNAS_ITEMS = [
    ("Código licitación", 16), ("Licitación", 46), ("N°", 5),
    ("Producto o servicio", 40), ("Categoría", 30),
    ("Cantidad", 10), ("Unidad", 12), ("Detalle del requerimiento", 70),
]

FICHA_MP = "https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion="


def log(mensaje):
    print(mensaje, flush=True)


def leer_config():
    with CONFIG.open(encoding="utf-8") as f:
        cfg = json.load(f)
    correo = cfg.get("correo") or {}
    correo.setdefault("activo", True)
    correo.setdefault("para", "")
    correo.setdefault("asunto", "Radar de licitaciones - {fecha}")
    correo.setdefault("url_web", "")
    correo.setdefault("servidor", "smtp.gmail.com")
    correo.setdefault("puerto", 465)
    correo.setdefault("maximo_en_el_correo", 15)
    correo.setdefault("enviar_aunque_no_haya_nada", False)
    cfg["correo"] = correo
    return cfg


def leer_credenciales():
    usuario = os.environ.get("CORREO_USUARIO", "").strip()
    clave = os.environ.get("CORREO_CLAVE", "").strip()
    if usuario and clave:
        return usuario, clave
    archivo = Path.home() / ".mp_correo"
    if archivo.exists():
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            return datos.get("usuario", "").strip(), datos.get("clave", "").strip()
        except json.JSONDecodeError:
            log("El archivo .mp_correo esta mal escrito (no es JSON valido).")
    return "", ""


def cargar(nombre):
    archivo = DATOS / nombre
    if not archivo.exists():
        return None
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def aFecha(valor):
    if not valor:
        return None
    texto = str(valor).replace("Z", "").split(".")[0]
    for formato in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            continue
    return None


def dias_para_cierre(ficha, hoy):
    cierre = aFecha(ficha.get("cierre"))
    if not cierre:
        return None
    return (cierre.date() - hoy).days


def resumen_items(ficha, tope=3):
    r = ficha.get("requerimientos") or {}
    items = r.get("items") or []
    if not items:
        return ""
    trozos = []
    for item in items[:tope]:
        nombre = item.get("producto") or item.get("categoria") or ""
        cantidad = cantidad_texto(item)
        trozos.append((cantidad + " · " if cantidad else "") + nombre)
    resto = (r.get("items_total") or len(items)) - len(items[:tope])
    if resto > 0:
        trozos.append("y %d más" % resto)
    return " · ".join(trozos)


def si_no_texto(valor):
    if valor is True:
        return "Sí"
    if valor is False:
        return "No"
    return ""


def fila_excel(ficha, hoy):
    restan = dias_para_cierre(ficha, hoy)
    r = ficha.get("requerimientos") or {}
    return [
        ficha.get("codigo"),
        (ficha.get("nombre"), excel.AJUSTADO),
        ficha.get("estado"),
        ficha.get("organismo"),
        ficha.get("unidad"),
        ficha.get("region"),
        ficha.get("comuna"),
        (aFecha(ficha.get("publicacion")), excel.FECHA),
        (aFecha(ficha.get("cierre")), excel.FECHA),
        restan,
        (ficha.get("monto"), excel.MONEDA),
        ficha.get("moneda"),
        ficha.get("tipo"),
        (", ".join(ficha.get("categorias") or []), excel.AJUSTADO),
        (resumen_items(ficha), excel.AJUSTADO),
        (aFecha(r.get("visita_terreno")), excel.FECHA),
        (aFecha(r.get("entrega_antecedentes")), excel.FECHA),
        r.get("duracion"),
        si_no_texto(r.get("renovable")),
        (r.get("prohibiciones"), excel.AJUSTADO),
        r.get("contacto"),
        (ficha.get("descripcion"), excel.AJUSTADO),
        ('=HYPERLINK("%s%s","descargar bases")' % (FICHA_MP, ficha.get("codigo")), excel.ENLACE),
    ]


def filas_items(fichas, hoy):
    """Una fila por item solicitado: el requerimiento tecnico en detalle."""
    filas = []
    for ficha in ordenar(fichas, hoy):
        for numero, item in enumerate((ficha.get("requerimientos") or {}).get("items") or [], 1):
            filas.append([
                ficha.get("codigo"),
                (ficha.get("nombre"), excel.AJUSTADO),
                numero,
                (item.get("producto"), excel.AJUSTADO),
                (item.get("categoria"), excel.AJUSTADO),
                item.get("cantidad"),
                item.get("unidad"),
                (item.get("detalle"), excel.AJUSTADO),
            ])
    return filas


def armar_excel(nuevas, vigentes, hoy):
    DESCARGAS.mkdir(parents=True, exist_ok=True)
    anchos = [ancho for _, ancho in COLUMNAS]
    encabezado = [(titulo, excel.ENCABEZADO) for titulo, _ in COLUMNAS]

    hoja_nuevas = excel.Hoja("Nuevas de hoy", anchos)
    hoja_nuevas.agregar(encabezado)
    for ficha in ordenar(nuevas, hoy):
        hoja_nuevas.agregar(fila_excel(ficha, hoy))

    hoja_vigentes = excel.Hoja("Vigentes", anchos)
    hoja_vigentes.agregar(encabezado)
    for ficha in ordenar(vigentes, hoy):
        hoja_vigentes.agregar(fila_excel(ficha, hoy))

    hoja_items = excel.Hoja("Requerimientos", [ancho for _, ancho in COLUMNAS_ITEMS])
    hoja_items.agregar([(titulo, excel.ENCABEZADO) for titulo, _ in COLUMNAS_ITEMS])
    for fila in filas_items(vigentes, hoy):
        hoja_items.agregar(fila)

    ruta = DESCARGAS / "licitaciones.xlsx"
    excel.escribir(ruta, [hoja_nuevas, hoja_vigentes, hoja_items])
    log("Excel listo: " + str(ruta) + " (" + str(len(nuevas)) + " nuevas, " +
        str(len(vigentes)) + " vigentes)")
    armar_csv(vigentes, hoy)
    return ruta


def armar_csv(todas, hoy):
    """Misma base, en CSV, para quien prefiera abrirla en otra herramienta."""
    ruta = DESCARGAS / "licitaciones.csv"
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        escritor.writerow([titulo for titulo, _ in COLUMNAS])
        for ficha in ordenar(todas, hoy):
            fila = []
            for celda in fila_excel(ficha, hoy):
                valor = celda[0] if isinstance(celda, tuple) else celda
                if isinstance(valor, (datetime, date)):
                    valor = valor.strftime("%d-%m-%Y %H:%M")
                elif isinstance(valor, str) and valor.startswith('=HYPERLINK('):
                    valor = FICHA_MP + (ficha.get("codigo") or "")
                fila.append("" if valor is None else valor)
            escritor.writerow(fila)
    log("CSV listo: " + str(ruta))
    return ruta


def fecha_corta(valor):
    f = aFecha(valor)
    return f.strftime("%d-%m-%Y") if f else None


def cantidad_texto(item):
    cantidad = item.get("cantidad")
    if cantidad in (None, ""):
        return ""
    try:
        numero = float(cantidad)
        cantidad = int(numero) if numero.is_integer() else numero
    except (TypeError, ValueError):
        pass
    return (str(cantidad) + " " + (item.get("unidad") or "")).strip()


def filas_requerimientos(ficha):
    """El cuadro resumen: pares (etiqueta, valor), saltandose lo que venga vacio."""
    r = ficha.get("requerimientos") or {}
    filas = []

    items = r.get("items") or []
    if items:
        trozos = []
        for item in items[:4]:
            nombre = item.get("producto") or item.get("categoria") or "(sin nombre)"
            cantidad = cantidad_texto(item)
            trozos.append((cantidad + " · " if cantidad else "") + nombre)
        resto = (r.get("items_total") or len(items)) - len(items[:4])
        if resto > 0:
            trozos.append("y %d ítem%s más" % (resto, "" if resto == 1 else "s"))
        filas.append(("Qué piden", " · ".join(trozos)))

    visita = fecha_corta(r.get("visita_terreno"))
    if visita:
        direccion = r.get("direccion_visita")
        filas.append(("Visita a terreno", visita + (" — " + direccion if direccion else "")))

    antecedentes = fecha_corta(r.get("entrega_antecedentes"))
    fisico = fecha_corta(r.get("soporte_fisico"))
    if antecedentes or fisico:
        partes = []
        if antecedentes:
            partes.append("antecedentes hasta el " + antecedentes)
        if fisico:
            partes.append("soporte físico hasta el " + fisico +
                          (" en " + r["direccion_entrega"] if r.get("direccion_entrega") else ""))
        filas.append(("Entregas", "; ".join(partes)))

    respuestas = fecha_corta(r.get("respuestas"))
    tecnica = fecha_corta(r.get("apertura_tecnica"))
    if respuestas or tecnica:
        partes = []
        if respuestas:
            partes.append("respuestas el " + respuestas)
        if tecnica:
            partes.append("apertura técnica el " + tecnica)
        filas.append(("Hitos", "; ".join(partes)))

    contrato = []
    if r.get("duracion"):
        contrato.append("dura " + r["duracion"])
    if r.get("renovable") is True:
        contrato.append("renovable")
    if r.get("modalidad_pago"):
        contrato.append(r["modalidad_pago"])
    if contrato:
        filas.append(("Contrato", ", ".join(contrato)))

    proceso = []
    if r.get("etapas"):
        proceso.append(str(r["etapas"]) + (" etapa" if r["etapas"] == 1 else " etapas"))
    if r.get("obras") is True:
        proceso.append("es contrato de obras")
    if r.get("financiamiento"):
        proceso.append("financia: " + str(r["financiamiento"]))
    if proceso:
        filas.append(("Proceso", ", ".join(proceso)))

    if r.get("contacto"):
        contacto = r["contacto"]
        if r.get("contacto_email"):
            contacto += " · " + r["contacto_email"]
        filas.append(("Contraparte", contacto))

    if r.get("prohibiciones"):
        filas.append(("Prohibiciones", r["prohibiciones"]))

    if not ficha.get("monto") and r.get("monto_nota"):
        filas.append(("Sobre el monto", r["monto_nota"]))

    reclamos = r.get("reclamos_comprador")
    if reclamos:
        filas.append(("Reclamos al organismo",
                      str(reclamos) + " por atraso en pagos, últimos 12 meses"))

    return filas


def ordenar(fichas, hoy):
    def clave(ficha):
        restan = dias_para_cierre(ficha, hoy)
        return (restan is None, restan if restan is not None else 0)
    return sorted(fichas, key=clave)


def pesos(monto):
    if monto is None:
        return "monto no informado"
    return "$" + format(int(round(monto)), ",d").replace(",", ".")


def cuadro_html(ficha, escapar):
    """Cuadro resumen de requerimientos tecnicos, en tabla para que Outlook no lo rompa."""
    filas = filas_requerimientos(ficha)
    if not filas:
        return ""
    celdas = "".join("""
      <tr>
        <td style="padding:3px 10px 3px 0;color:#5a657a;font-size:12px;white-space:nowrap;
            vertical-align:top;">{etiqueta}</td>
        <td style="padding:3px 0;font-size:12px;color:#26324a;vertical-align:top;">{valor}</td>
      </tr>""".format(etiqueta=escapar(etiqueta), valor=escapar(valor))
        for etiqueta, valor in filas)

    return """
    <table style="width:100%;margin-top:11px;background:#f7f9fd;border:1px solid #e2e8f4;
           border-radius:8px;border-collapse:separate;" cellpadding="0" cellspacing="0">
      <tr><td style="padding:11px 13px 4px;">
        <div style="font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
             color:#16307e;">Requerimientos técnicos</div>
      </td></tr>
      <tr><td style="padding:0 13px 11px;">
        <table style="width:100%;border-collapse:collapse;">CELDAS_AQUI</table>
      </td></tr>
    </table>""".replace("CELDAS_AQUI", celdas)


def cuerpo_html(nuevas, vigentes, hoy, cfg, primera_carga=False):
    correo = cfg["correo"]
    tope = correo["maximo_en_el_correo"]
    protagonistas = vigentes if primera_carga else nuevas
    destacadas = ordenar(protagonistas, hoy)[:tope]
    cierran_pronto = [f for f in vigentes
                      if (dias_para_cierre(f, hoy) or 99) <= 3
                      and (dias_para_cierre(f, hoy) or -1) >= 0]

    def escapar(texto):
        return (str(texto or "")
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    filas = []
    for ficha in destacadas:
        restan = dias_para_cierre(ficha, hoy)
        if restan is None:
            plazo, color = "sin fecha de cierre", "#5a657a"
        elif restan < 0:
            plazo, color = "cerrada", "#8a94a6"
        elif restan == 0:
            plazo, color = "cierra HOY", "#c8451f"
        elif restan <= 3:
            plazo, color = "cierra en %d día%s" % (restan, "" if restan == 1 else "s"), "#c8451f"
        else:
            plazo, color = "cierra en %d días" % restan, "#0f7a53"

        filas.append("""
        <tr>
          <td style="padding:14px 16px;border-bottom:1px solid #e6eaf2;">
            <a href="{enlace}" style="color:#16307e;font-weight:600;font-size:15px;text-decoration:none;">{nombre}</a>
            <div style="color:#5a657a;font-size:13px;margin-top:4px;">{organismo} · {region}</div>
            <div style="margin-top:7px;font-size:13px;">
              <span style="color:{color};font-weight:600;">{plazo}</span>
              <span style="color:#8a94a6;"> · </span>
              <span style="color:#0f7a53;font-weight:600;">{monto}</span>
              <span style="color:#8a94a6;"> · {codigo}</span>
            </div>
            {cuadro}
            <div style="margin-top:10px;">
              <a href="{enlace}" style="display:inline-block;background:#eaf0ff;color:#16307e;
                 border:1px solid #c9d8ff;padding:7px 13px;border-radius:7px;text-decoration:none;
                 font-size:13px;font-weight:600;">&#11015; Bases administrativas y técnicas</a>
            </div>
          </td>
        </tr>""".format(
            cuadro=cuadro_html(ficha, escapar),
            enlace=FICHA_MP + escapar(ficha.get("codigo")),
            nombre=escapar(ficha.get("nombre")),
            organismo=escapar(ficha.get("organismo")),
            region=escapar(ficha.get("region")),
            color=color, plazo=plazo,
            monto=pesos(ficha.get("monto")),
            codigo=escapar(ficha.get("codigo")),
        ))

    resto = len(protagonistas) - len(destacadas)
    nota_resto = ""
    if resto > 0:
        nota_resto = ('<p style="color:#5a657a;font-size:14px;margin:14px 16px 0;">'
                      "Y otras %d en el Excel adjunto.</p>" % resto)

    boton_web = ""
    if correo.get("url_web"):
        boton_web = (
            '<p style="margin:22px 0 0;"><a href="%s" '
            'style="background:#1f4fd8;color:#fff;padding:11px 20px;border-radius:8px;'
            'text-decoration:none;font-weight:600;font-size:14px;">Ver el radar completo</a></p>'
            % correo["url_web"]
        )

    fecha_larga = "%d de %s" % (hoy.day, MESES[hoy.month - 1])

    return """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#f4f6fa;font-family:'Segoe UI',Arial,sans-serif;color:#1b2436;">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;">

  <div style="background:linear-gradient(120deg,#16307e,#1f4fd8);color:#fff;border-radius:12px 12px 0 0;padding:22px 20px;">
    <h1 style="margin:0;font-size:21px;">Radar de licitaciones</h1>
    <p style="margin:6px 0 0;opacity:.9;font-size:14px;">Mercado Público · {fecha}</p>
  </div>

  <div style="background:#fff;border:1px solid #e6eaf2;border-top:none;border-radius:0 0 12px 12px;padding:20px;">
    <p style="margin:0 0 4px;font-size:16px;">
      <strong style="font-size:26px;color:#1f4fd8;">{titular}</strong> {frase}
    </p>
    <p style="margin:0;color:#5a657a;font-size:14px;">
      {cantidad_vigentes} vigentes en tu radar · {cantidad_pronto} cierran en los próximos 3 días.
    </p>

    <table style="width:100%;border-collapse:collapse;margin-top:18px;">{filas}</table>
    {nota_resto}
    {boton_web}

    <p style="margin:24px 0 0;padding-top:16px;border-top:1px solid #e6eaf2;color:#5a657a;font-size:13px;">
      El Excel adjunto trae tres hojas: <strong>Nuevas de hoy</strong>, <strong>Vigentes</strong> y
      <strong>Requerimientos</strong> (un ítem solicitado por fila), con los filtros de Excel listos
      para usar. El monto es referencial: manda lo que diga la ficha oficial.
    </p>
  </div>

</div></body></html>""".format(
        fecha=fecha_larga,
        titular=len(protagonistas),
        frase=("licitaciones vigentes calzan con tus filtros. Desde mañana te aviso solo las nuevas."
               if primera_carga else
               ("licitación nueva desde ayer." if len(protagonistas) == 1
                else "licitaciones nuevas desde ayer.")),
        cantidad_pronto=len(cierran_pronto),
        cantidad_vigentes=len(vigentes),
        filas="".join(filas) or
        '<tr><td style="padding:16px;color:#5a657a;font-size:14px;">'
        "Hoy no apareció ninguna licitación nueva que calce con tus filtros.</td></tr>",
        nota_resto=nota_resto,
        boton_web=boton_web,
    )


def cuerpo_texto(nuevas, hoy):
    lineas = ["Radar de licitaciones - " + hoy.strftime("%d-%m-%Y"), ""]
    lineas.append(str(len(nuevas)) + " licitaciones nuevas que calzan con tus filtros.")
    lineas.append("")
    for ficha in ordenar(nuevas, hoy)[:20]:
        restan = dias_para_cierre(ficha, hoy)
        lineas.append("- " + (ficha.get("nombre") or ""))
        lineas.append("  " + (ficha.get("organismo") or "") +
                      " | " + pesos(ficha.get("monto")) +
                      (" | cierra en %d dias" % restan if restan is not None else ""))
        lineas.append("  " + FICHA_MP + (ficha.get("codigo") or ""))
    lineas.append("")
    lineas.append("El detalle completo va en el Excel adjunto.")
    return "\n".join(lineas)


def enviar(cfg, ruta_excel, nuevas, vigentes, hoy, indice):
    correo = cfg["correo"]
    usuario, clave = leer_credenciales()
    destino = os.environ.get("CORREO_PARA", "").strip() or correo.get("para", "").strip()
    primera_carga = bool(indice.get("primera_carga"))

    if not usuario or not clave:
        log("No hay credenciales de correo configuradas: no envio nada.")
        log("  (crea " + str(Path.home() / ".mp_correo") + " o define CORREO_USUARIO y CORREO_CLAVE)")
        return False
    if not destino:
        log("No se a quien mandar el correo: llena 'para' en config.json.")
        return False
    if not nuevas and not primera_carga and not correo.get("enviar_aunque_no_haya_nada"):
        log("Hoy no aparecio ninguna licitacion nueva: no envio correo.")
        return False

    mensaje = EmailMessage()
    if primera_carga:
        asunto = "Radar de licitaciones - primera carga: %d vigentes" % len(vigentes)
    else:
        asunto = correo["asunto"].format(
            fecha=hoy.strftime("%d-%m-%Y"), cantidad=len(nuevas)
        )
    mensaje["Subject"] = asunto
    mensaje["From"] = formataddr(("Radar de licitaciones", usuario))
    mensaje["To"] = destino
    mensaje.set_content(cuerpo_texto(nuevas or vigentes, hoy))
    mensaje.add_alternative(
        cuerpo_html(nuevas, vigentes, hoy, cfg, primera_carga), subtype="html"
    )

    with ruta_excel.open("rb") as f:
        mensaje.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="licitaciones_" + hoy.strftime("%Y-%m-%d") + ".xlsx",
        )

    contexto = ssl.create_default_context()
    with smtplib.SMTP_SSL(correo["servidor"], correo["puerto"], context=contexto) as servidor:
        servidor.login(usuario, clave)
        servidor.send_message(mensaje)

    log("Correo enviado a " + destino)
    return True


def main():
    parser = argparse.ArgumentParser(description="Excel y correo del radar.")
    parser.add_argument("--solo-excel", action="store_true",
                        help="arma el Excel pero no manda el correo")
    argumentos = parser.parse_args()

    cfg = leer_config()
    hoy = datetime.now(ZONA_CHILE).date()

    vigentes = cargar("vigentes.json")
    if vigentes is None:
        log("No hay datos todavia. Ejecuta antes scripts/actualizar.py.")
        sys.exit(1)
    nuevas = cargar("nuevas.json") or []
    indice = cargar("indice.json") or {}

    ruta = armar_excel(nuevas, vigentes, hoy)

    if argumentos.solo_excel or not cfg["correo"].get("activo"):
        log("(sin envio de correo)")
        return
    enviar(cfg, ruta, nuevas, vigentes, hoy, indice)


if __name__ == "__main__":
    main()
