# Radar de licitaciones · Mercado Público

Todas las mañanas busca las licitaciones nuevas de Mercado Público, se queda con
las que calzan con tus filtros y **te manda un correo** con el resumen y un Excel
adjunto. También deja una página web con todo, por si quieres filtrar a mano.

**Corre en los servidores de GitHub, no en tu computador**: tu notebook puede estar
apagado y el correo llega igual.

## Sobre las bases de licitación

La API de Mercado Público entrega los *datos* de cada licitación (nombre, monto,
plazos, organismo…), pero **no entrega los documentos**: sus 87 campos no incluyen
adjuntos. Las bases administrativas y técnicas viven en la ficha oficial.

Por eso cada licitación —en el correo y en el Excel— lleva un botón
**⬇ Bases administrativas y técnicas** que abre su ficha en mercadopublico.cl, donde
está el contenido completo de las bases y los archivos que haya subido el organismo.
Un clic, sin clave.

---

## Cómo usarlo en tu computador

Doble clic en **`Abrir radar.cmd`**.

Se abre una ventana negra (es el motor trabajando, no la cierres) y al rato se abre
el navegador con la página. Para cerrarlo, cierra la ventana negra.

En la página puedes filtrar por texto, estado, región, monto y fecha. Los filtros
que elijas quedan guardados para la próxima vez.

## Dónde está el ticket de la API

En `C:\Users\anagu\.mp_ticket` — **fuera** de esta carpeta, a propósito: así nunca
se sube a internet por accidente. Si algún día ChileCompra te da un ticket nuevo,
abre ese archivo con el Bloc de notas, pega el nuevo y guarda.

## Cómo cambiar lo que busca

Abre **`config.json`** con el Bloc de notas. Lo que importa:

| Campo | Qué hace |
|---|---|
| `palabras_clave` | Solo revisa licitaciones cuyo nombre contenga alguna de estas palabras. Vacío = todas. |
| `excluir_palabras` | Descarta las que contengan estas palabras, aunque calcen con las anteriores. |
| `monto_min_clp` / `monto_max_clp` | Rango de monto estimado. `null` = sin tope. |
| `regiones` | Lista de regiones; vacío = todo Chile. |

No hace falta tocar `pausa_entre_consultas_seg`, `max_detalles_por_corrida` ni
`refrescar_detalle_cada_dias`: están puestos para no pasarse de las 10.000 consultas
diarias que permite el ticket.

## Vigentes y nuevas

Cada corrida barre las **licitaciones vigentes** de todo Chile (unas 4.700 al día),
se queda con las que calzan con tus palabras clave y **rehace la foto completa**. Por
eso la base nunca acumula basura: cuando una licitación cierra, desaparece sola.

Después compara con la foto anterior: lo que no estaba ayer es **nuevo**, y eso es lo
que te llega por correo. En la web salen todas las vigentes, con las nuevas marcadas
y una casilla para ver solo esas.

La primera corrida no manda avisos de "nuevas" (lo serían todas): te llega un correo
de bienvenida con el total de vigentes, y desde el día siguiente solo los cambios.

---

## El cuadro de requerimientos técnicos

Cada licitación —en el correo, en la web y en el Excel— trae un cuadro con lo que
realmente hay que saber antes de decidir si postular:

- **Qué piden**: los ítems solicitados con cantidad y unidad (en el Excel, la hoja
  *Requerimientos* trae uno por fila, con el texto completo del requerimiento).
- **Visita a terreno** y **entregas** de antecedentes o soporte físico, con dirección.
- **Hitos**: cuándo publican respuestas a las consultas y cuándo es la apertura técnica.
- **Contrato**: duración, si es renovable, modalidad de pago.
- **Prohibiciones**: el texto literal del organismo (ojo, aquí suele decir si acepta
  subcontratación).
- **Reclamos al organismo**: cuántos reclamos por atraso en pagos acumula la
  institución en 12 meses. Es del organismo completo, no de esta licitación.

Todo eso sale de la API. El texto largo de las bases sigue estando en la ficha, a un
clic del botón.

---

## Cómo publicarlo en internet (paso a paso, todo con el mouse)

La primera vez toma unos 20 minutos. Después se actualiza solo, todos los días, sin
que tengas que hacer nada.

### 1. Crear la cuenta

Entra a **github.com** → *Sign up*. Correo, contraseña, nombre de usuario (ese
nombre saldrá en la dirección de tu web, así que elige uno decente). Es gratis.

### 2. Crear el repositorio

Arriba a la derecha, el botón **+** → *New repository*.

- **Repository name**: `radar-licitaciones`
- Marca **Public**
- **No** marques "Add a README file"
- Botón verde *Create repository*

> ¿Por qué público? Porque GitHub solo publica webs gratis desde repositorios
> públicos. Los datos que se ven son públicos de todas formas (salen de Mercado
> Público). Tu ticket **no** queda ahí: va en una casilla aparte, cifrada.

### 3. Subir los archivos

En la página que aparece, pincha el enlace **uploading an existing file**.

Abre la carpeta `Documentos\licitaciones-mercado-publico`, selecciona todo con
`Ctrl+E` (o Ctrl+A) y arrástralo a la zona del navegador que dice *Drag files here*.

Abajo, botón verde **Commit changes**.

> Si al terminar no ves una carpeta llamada `.github` en la lista de archivos, es
> que Windows no la arrastró por ser una carpeta oculta. Se arregla en el paso 5.

### 4. Guardar el ticket y el correo como secretos

Pestaña **Settings** (arriba) → en el menú de la izquierda, *Secrets and variables*
→ **Actions** → botón **New repository secret**. Vas a crear tres, uno por uno:

| Name | Secret |
|---|---|
| `MP_TICKET` | tu ticket de la API de Mercado Público |
| `CORREO_USUARIO` | tu Gmail completo, `ana.gutierrezj@gmail.com` |
| `CORREO_CLAVE` | la **contraseña de aplicación** de Gmail (ver abajo) |

Una vez guardados nadie puede volver a verlos, ni tú ni yo: solo los usa el robot.

#### La contraseña de aplicación de Gmail

Gmail no deja que un programa entre con tu contraseña normal. Hay que generarle una
contraseña aparte, que solo sirve para esto y puedes revocar cuando quieras:

1. Entra a **myaccount.google.com** → *Seguridad*.
2. Activa la **verificación en dos pasos** si no la tienes (es requisito).
3. En el buscador de esa página escribe **"contraseñas de aplicaciones"** y entra.
4. Nombre: `Radar licitaciones` → *Crear*.
5. Google te muestra 16 letras. **Esa** es la que pegas en `CORREO_CLAVE`, sin espacios.

Genérala tú y pégala directamente en GitHub: no me la pases por el chat ni la
guardes en un archivo del proyecto.

### 5. Revisar que exista la tarea automática

Pestaña **Actions**. Si ves *Radar diario de licitaciones*, listo, salta al paso 6.

Si no aparece nada: *set up a workflow yourself*, borra todo lo que traiga el editor,
y pega el contenido del archivo `.github\workflows\radar.yml` de tu carpeta (ábrelo
con el Bloc de notas). Arriba, donde dice `main.yml`, escribe `radar.yml`. Botón
verde *Commit changes*.

### 6. Encender la publicación web

**Settings** → menú izquierdo, **Pages** → en *Source*, elige **GitHub Actions**.

### 7. Primera ejecución

**Actions** → *Radar diario de licitaciones* → botón **Run workflow** → *Run workflow*.

Tarda unos minutos (la barra se pone verde cuando termina). Tu web queda en:

```
https://TU-USUARIO.github.io/radar-licitaciones/
```

Guárdala en favoritos. Desde ahí en adelante se actualiza sola cada mañana; si
quieres adelantarla, vuelves a apretar *Run workflow*.

Y en tu correo debería llegar el primer resumen con el Excel adjunto.

### 8. Pegar la dirección de la web en el correo

Abre `config.json`, y en `"url_web"` pega la dirección que te quedó
(`https://TU-USUARIO.github.io/radar-licitaciones/`). Con eso el correo diario
incluye el botón *Ver el radar completo*. Guarda y vuelve a subir el archivo a
GitHub (en el repositorio, pinchas `config.json` → el lápiz → pegas → *Commit*).

---

## El correo

Se configura en el bloque `correo` de `config.json`:

| Campo | Qué hace |
|---|---|
| `activo` | `false` apaga el envío y deja solo la web. |
| `para` | A quién llega. Puedes poner varios separados por coma. |
| `asunto` | Admite `{cantidad}` y `{fecha}`. |
| `url_web` | La dirección de tu web, para el botón del correo. |
| `maximo_en_el_correo` | Cuántas licitaciones se listan en el cuerpo. El resto va en el Excel. |
| `enviar_aunque_no_haya_nada` | `false` = si un día no hay nada nuevo, no te molesta. |

## Si algo falla

- **La web dice "Todavía no hay datos guardados"**: el radar aún no ha corrido, o
  corrió y no encontró nada que calzara. Prueba con menos palabras clave.
- **En Actions aparece una X roja**: pincha la ejecución y luego el paso rojo. Casi
  siempre es el ticket (mal pegado o vencido).
- **El radar local no encuentra nada**: revisa que las palabras clave estén en
  minúsculas y sin tildes en `config.json`.
- **No llega el correo**: revisa en *Actions* que el paso "Armar el Excel y enviar
  el correo" esté verde. Si dice `Username and Password not accepted`, la contraseña
  de aplicación está mal pegada (van las 16 letras juntas, sin espacios).
- **Llegó pero sin licitaciones**: ese día no se publicó nada que calzara. Es normal;
  amplía las palabras clave si pasa varios días seguidos.
