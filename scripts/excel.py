"""Escritor de archivos .xlsx sin librerias externas.

Un .xlsx es un zip con unos cuantos XML dentro. Aqui se arma el minimo necesario
para lo que necesita el radar: varias hojas, encabezado con color, filtros,
paneles congelados, fechas y montos con formato.
"""

import zipfile
from datetime import date, datetime
from xml.sax.saxutils import escape

# Estilos disponibles al escribir una celda
NORMAL = 0
ENCABEZADO = 1
FECHA = 2
MONEDA = 3
AJUSTADO = 4
ENLACE = 5

CERO_EXCEL = datetime(1899, 12, 30)

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{hojas}
</Types>"""

RELS_RAIZ = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

ESTILOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="dd\\-mm\\-yyyy\\ hh:mm"/>
<numFmt numFmtId="165" formatCode="#,##0"/>
</numFmts>
<fonts count="3">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><u/><sz val="11"/><color rgb="FF1F4FD8"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF1F4FD8"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
</styleSheet>"""


def _columna(indice):
    """0 -> A, 26 -> AA"""
    nombre = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        nombre = chr(65 + resto) + nombre
    return nombre


def _serial(valor):
    """Convierte fecha/hora al numero que entiende Excel."""
    if isinstance(valor, date) and not isinstance(valor, datetime):
        valor = datetime(valor.year, valor.month, valor.day)
    delta = valor - CERO_EXCEL
    return delta.days + delta.seconds / 86400.0


class Hoja:
    def __init__(self, nombre, anchos=None, congelar_fila=1):
        self.nombre = nombre[:31]
        self.anchos = anchos or []
        self.congelar_fila = congelar_fila
        self.filas = []

    def agregar(self, celdas):
        """celdas: lista de valores, o de tuplas (valor, estilo)."""
        self.filas.append(celdas)

    def _celda(self, referencia, valor, estilo):
        if valor is None or valor == "":
            return '<c r="%s" s="%d"/>' % (referencia, estilo)

        if isinstance(valor, (datetime, date)):
            return '<c r="%s" s="%d"><v>%s</v></c>' % (
                referencia, estilo or FECHA, repr(round(_serial(valor), 6))
            )

        if isinstance(valor, bool):
            valor = str(valor)

        if isinstance(valor, (int, float)):
            return '<c r="%s" s="%d"><v>%s</v></c>' % (referencia, estilo, repr(valor))

        texto = str(valor)
        if texto.startswith("=") and texto[1:].startswith("HYPERLINK("):
            return '<c r="%s" s="%d" t="str"><f>%s</f></c>' % (
                referencia, estilo or ENLACE, escape(texto[1:])
            )

        # Excel se cae con caracteres de control
        texto = "".join(c for c in texto if c >= " " or c == "\n")
        return '<c r="%s" s="%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (
            referencia, estilo, escape(texto)
        )

    def xml(self):
        partes = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
                  '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']

        if self.congelar_fila:
            partes.append(
                '<sheetViews><sheetView workbookViewId="0">'
                '<pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" state="frozen"/>'
                "</sheetView></sheetViews>" % (self.congelar_fila, self.congelar_fila + 1)
            )

        if self.anchos:
            columnas = "".join(
                '<col min="%d" max="%d" width="%d" customWidth="1"/>' % (i + 1, i + 1, ancho)
                for i, ancho in enumerate(self.anchos)
            )
            partes.append("<cols>%s</cols>" % columnas)

        partes.append("<sheetData>")
        for numero, fila in enumerate(self.filas, 1):
            celdas = []
            for indice, celda in enumerate(fila):
                valor, estilo = celda if isinstance(celda, tuple) else (celda, NORMAL)
                celdas.append(self._celda(_columna(indice) + str(numero), valor, estilo))
            alto = ' ht="28" customHeight="1"' if numero == 1 else ""
            partes.append("<row r='%d'%s>%s</row>" % (numero, alto, "".join(celdas)))
        partes.append("</sheetData>")

        if self.filas:
            ultima_columna = _columna(max(len(f) for f in self.filas) - 1)
            partes.append(
                '<autoFilter ref="A1:%s%d"/>' % (ultima_columna, len(self.filas))
            )

        partes.append("</worksheet>")
        return "".join(partes)


def escribir(ruta, hojas):
    """Guarda las hojas en un .xlsx en la ruta indicada."""
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        overrides = "".join(
            '<Override PartName="/xl/worksheets/sheet%d.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            % (i + 1)
            for i in range(len(hojas))
        )
        z.writestr("[Content_Types].xml", CONTENT_TYPES.format(hojas=overrides))
        z.writestr("_rels/.rels", RELS_RAIZ)
        z.writestr("xl/styles.xml", ESTILOS)

        pestanas = "".join(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (escape(h.nombre), i + 1, i + 1)
            for i, h in enumerate(hojas)
        )
        z.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>%s</sheets></workbook>" % pestanas,
        )

        relaciones = "".join(
            '<Relationship Id="rId%d" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            'Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1)
            for i in range(len(hojas))
        )
        relaciones += (
            '<Relationship Id="rId%d" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>' % (len(hojas) + 1)
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            "%s</Relationships>" % relaciones,
        )

        for i, hoja in enumerate(hojas, 1):
            z.writestr("xl/worksheets/sheet%d.xml" % i, hoja.xml())
