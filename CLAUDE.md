# Radar de licitaciones de Mercado Público

Busca cada mañana las licitaciones vigentes de Chile, filtra las que calzan con un
perfil de palabras clave, avisa por correo con un Excel adjunto y publica una web
para consultarlas. Corre en GitHub Actions: **no necesita ningún computador encendido**.

- **Web publicada**: https://annibe.github.io/radar-licitaciones/
- **Repositorio**: https://github.com/annibe/radar-licitaciones
- **Fuente de datos**: API pública de ChileCompra (`api.mercadopublico.cl`)

---

## Qué hace, en concreto

| Pieza | Dónde corre | Qué hace |
|---|---|---|
| **Robot diario** | GitHub Actions | Barre ~4.700 licitaciones vigentes, filtra, compara con la foto de ayer y publica |
| **Correo** | GitHub Actions | Solo las nuevas, con Excel de 3 hojas adjunto. Si no hay nada nuevo, no escribe |
| **Web** | GitHub Pages | Filtros, cuadro de requerimientos, likes, eliminadas, descargas |
| **Guardar en carpeta** | Navegador (Chrome/Edge) | Crea una carpeta por licitación en OneDrive con ficha, datos y notas |
| **Organizador de anexos** | Computador local | Archiva los adjuntos descargados en la carpeta de cada licitación |

---

## Estructura

```
config.json                    Qué busca y a quién le escribe. Se edita a mano.
Abrir radar.cmd                Ejecuta el radar en local y abre la web
Organizador de anexos.cmd      Ejecuta el organizador de anexos
scripts/
  actualizar.py                Motor: consulta la API, filtra, arma la foto del día
  enviar_correo.py             Excel de 3 hojas + correo HTML
  excel.py                     Escritor de .xlsx sin librerías (zip + XML)
  abrir.py                     Servidor local y navegador, para uso en el equipo
  organizador.py               Vigila Descargas y archiva los anexos
web/
  index.html  app.js  estilos.css  guardar.js
  datos/      vigentes.json, nuevas.json, indice.json  (los genera el robot)
  descargas/  licitaciones.xlsx, licitaciones.csv      (los genera el robot)
.github/workflows/radar.yml    El robot diario
```

**Principios del proyecto**: Python 3.13 **sin dependencias de pip**, JavaScript **sin
librerías**, y **sin LLMs** en tiempo de ejecución. Todo con la biblioteca estándar.
No introducir dependencias nuevas sin una razón fuerte.

---

## Ponerlo a andar en otro computador

### A. Solo consultar las licitaciones
No hay que instalar nada: abre la web publicada. Funciona en cualquier navegador.

### B. Usar el organizador de anexos (lo más habitual)

1. **Descarga el proyecto**: en GitHub, botón verde `Code` → `Download ZIP` → descomprime
   en `Documentos\licitaciones-mercado-publico`.
2. **Instala Python 3.13** desde python.org. En la primera pantalla del instalador,
   **marca "Add python.exe to PATH"**; sin eso el `.cmd` no encuentra Python.
3. **Doble clic en `Organizador de anexos.cmd`**. La primera vez pide elegir la carpeta
   compartida (la de OneDrive donde se guardan las licitaciones) y la recuerda.
4. Para que arranque solo con Windows: crea un acceso directo al `.cmd` en la carpeta
   `shell:startup` (Win+R, escribe `shell:startup`, Enter). Un candado impide que corran
   dos instancias a la vez.
5. Archiva lo descargado hasta 2 horas después de apretar «Guardar y abrir anexos»,
   aunque el organizador se haya abierto después de la descarga.

La carpeta compartida se sincroniza por OneDrive, así que varias personas pueden
trabajar sobre las mismas licitaciones.

### C. Correr el radar completo en tu equipo

Necesitas un **ticket propio** de la API: se pide gratis en chilecompra.cl y llega por
correo. Guárdalo en `C:\Users\<tu usuario>\.mp_ticket` — solo el ticket, sin comillas.

```
py scripts/actualizar.py                   consulta la API y arma la foto
py scripts/enviar_correo.py --solo-excel   arma el Excel sin enviar correo
```

> **Ojo**: si tu red o tu antivirus intercepta HTTPS, Python falla con
> `CERTIFICATE_VERIFY_FAILED — self-signed certificate in certificate chain`. No es un
> error del proyecto. `curl` sí funciona porque usa el almacén de certificados de
> Windows. En GitHub Actions no ocurre nunca.

### D. Montar tu propio robot diario

1. Haz un *fork* del repositorio (o crea uno nuevo y sube estos archivos).
2. `Settings` → `Secrets and variables` → `Actions`, y crea cuatro secretos:
   `MP_TICKET`, `CORREO_USUARIO`, `CORREO_CLAVE`, `CORREO_PARA`.
   `CORREO_CLAVE` es una **contraseña de aplicación de Gmail** (requiere verificación
   en dos pasos), no la contraseña normal de la cuenta.
3. `Settings` → `Pages` → en *Source*, elige **GitHub Actions**.
4. `Actions` → *Radar diario de licitaciones* → `Run workflow`.

El repositorio debe ser **público** para que GitHub Pages lo publique gratis. Por eso
`config.json` lleva `"para": ""`: el destinatario del correo viene del secreto, para no
dejar direcciones a la vista de los robots de spam.

---

## El ciclo diario

Corre a las **10:17 UTC** (≈06:17 en Chile). La hora es rara a propósito: GitHub encola
las tareas gratuitas y las horas en punto son las más congestionadas.

1. Pide a la API `estado=activas` — todas las licitaciones abiertas del país.
2. Filtra por nombre con las palabras clave y las exclusiones.
3. Pide el detalle solo de las que calzan, una por una y con pausa, y de paso lee la
   ficha para extraer la dirección de su ventana de adjuntos.
4. **Descarta las que ya cerraron**: la API sigue diciendo «Publicada» en licitaciones
   cuyo plazo venció. Se confía en la fecha de cierre, no en el estado declarado.
5. Compara con la foto anterior: lo que no estaba es **nuevo**, y eso va al correo.
6. Guarda los datos en el repositorio y publica la web.

La base se **rehace entera** cada día. Por eso solo contiene licitaciones vigentes y no
hace falta podar nada.

---

## Configuración (`config.json`)

| Campo | Qué hace |
|---|---|
| `palabras_clave` | Solo revisa licitaciones cuyo nombre contenga alguna. Vacío = todas |
| `excluir_palabras` | Descarta las que las contengan, aunque calcen con las anteriores |
| `monto_min_clp` / `monto_max_clp` | Rango del monto estimado. `null` = sin tope |
| `regiones` | Lista de regiones; vacío = todo Chile |
| `ocultar_vencidas` | `true` descarta las de plazo vencido (una de cada seis) |
| `correo.para` | Destinatario. Vacío en el repositorio: viene del secreto `CORREO_PARA` |
| `correo.maximo_en_el_correo` | Cuántas se listan en el cuerpo; el resto va en el Excel |

Las mayúsculas y las tildes dan lo mismo. Las palabras de **más de 3 letras aceptan
derivados** (`digital` encuentra *digitales* y *digitalización*); las de 3 o menos
exigen palabra suelta, para que `ia` no calce dentro de *vigilancia* o *farmacia*.

---

## Los anexos: por qué hay un paso manual

La ventana de adjuntos de Mercado Público está protegida con **reCAPTCHA Enterprise**
de Google, el invisible. La grilla de archivos solo aparece si ese control aprueba al
visitante, así que **ningún programa puede descargarlos** y no se intenta rodear.

El flujo asistido deja el trabajo manual en dos clics:

1. En la web: ♡ → **⬇ Guardar y abrir anexos**, o el botón **Bases administrativas y
   técnicas** de cualquier tarjeta. Ambos abren **directamente la ventana de adjuntos**:
   el robot guarda su dirección (`url_anexos`) al armar la foto del día.
2. Si por lo que sea esa dirección falta, el botón abre la ficha y hay que pinchar
   **«Ver adjuntos»** — primer icono de la fila de nueve, encima de «Productos o
   servicios».
3. **«Seleccionar Todos»** + el código de la imagen → baja un ZIP con todo.
   Tope de 20 MB impuesto por el sitio; si se pasa, hay que usar la lupa de cada fila.
4. El organizador descomprime, archiva en `<licitación>\anexos\` y limpia Descargas.

El organizador **solo archiva descargas que vengan de mercadopublico.cl**: lo comprueba
en la marca `Zone.Identifier` que Windows deja en cada archivo bajado. Lo que descargues
de otro sitio se queda donde está.

---

## Detalles que cuestan tiempo si no se saben

- **Adobe Acrobat traba los PDF.** Al descargar uno, Acrobat lo abre para
  previsualizarlo y Windows ya no deja moverlo. Por eso se atascan los documentos
  grandes y nunca los `.docx`. Cerrar Acrobat los libera.
- **En Windows «mover» es copiar y después borrar.** Con el archivo tomado, la copia se
  hace pero el borrado falla. Tratar eso como fracaso y reintentar generó 277 copias del
  mismo PDF en una tarde. Por eso las dos operaciones van separadas.
- **Chrome prohíbe que una página web cree archivos `.url`.** Los trata como peligrosos.
  El acceso directo a las bases se escribe como `abrir-bases.html`.
- **Guardar en carpeta solo funciona en Chrome o Edge de escritorio.** Usa la File
  System Access API. En el celular no existe.
- **La API engaña en cuatro campos**: `FechaCierre` y `FechaPublicacion` de la raíz
  vienen nulas —las buenas están dentro de `Fechas`—; `Modalidad` y las unidades de
  tiempo son códigos numéricos; `SubContratacion` contradice al texto de
  `ProhibicionContratacion`, así que se muestra el texto; y `CantidadReclamos` es del
  organismo completo, no de la licitación.
- **Los documentos no están en ninguna API.** Ni la clásica (87 campos, ninguno de
  adjuntos) ni el estándar OCDS, que solo los expone en el bloque de adjudicación y con
  un mes de retraso.
- **El token de los anexos es portátil.** El `enc` de la ventana de adjuntos solo
  existe dentro del HTML de la ficha, pero una vez extraído sirve en cualquier navegador
  y en otra sesión. Por eso el robot puede guardarlo y el botón lleva directo.
- **El puerto local parte en 8790** y busca uno libre hacia arriba.

---

## Convenciones al trabajar en este proyecto

- **Nada de `pip` ni de LLMs.** Si algo parece necesitar una librería, casi siempre hay
  una forma con la biblioteca estándar (el escritor de `.xlsx` es un ejemplo).
- **Código y mensajes en español.** En los `.py` se evitan las tildes dentro del código
  para no pelear con la consola de Windows; en la web y los correos sí se usan.
- **Después de editar JavaScript, abrir la página en el navegador y mirar la consola.**
  Un `\n` mal escrito por un script deja la web entera sin cargar y ningún compilador
  lo avisa.
- **`notas.txt` de cada licitación no se sobrescribe jamás.** Es lo que escribe el
  equipo y la carpeta es compartida.
- **Ningún archivo central que la web reescriba**, salvo `_marcas.json`. La carpeta es
  compartida y OneDrive genera copias en conflicto cuando dos personas tocan lo mismo.
- **Los secretos nunca van en el repositorio.** El ticket vive en `~/.mp_ticket`, fuera
  de la carpeta del proyecto, para que no se suba al arrastrarla a GitHub.
