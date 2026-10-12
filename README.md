# CRT · Planificador de tareas con calendario LFPA

Sitio web **funcional en una computadora**, creado a partir de la plantilla `CRT_Dias_Inhabiles.html`, con diseño similar y un servidor local Python gratuito. Calendario legal basado en el artículo 28 de la Ley Federal de Procedimiento Administrativo (LFPA), tareas guardadas en SQLite y enlaces a la fuente oficial.

**No es un sitio publicado en internet ni un sistema oficial de la CRT.** Es un prototipo local listo para ampliar y llevar a infraestructura institucional con medidas de seguridad adicionales.

## Iniciar sin pagar software

Requiere **Python 3.10 o posterior** ([python.org](https://www.python.org/downloads/)). No requiere `pip install`, cuentas, API keys, bases de datos comerciales ni conexión constante a internet.

### En Windows

1. Descomprimir `CRT_Planificador_Web.zip` y abrir su carpeta.
2. Doble clic en **`INICIAR_WINDOWS.bat`**.
3. Se abrirá automáticamente el navegador. Si no ocurre, entrar en **http://127.0.0.1:8765/**.
4. Para apagar, cerrar la ventana de terminal o pulsar `Ctrl+C`.

> Si Windows no encuentra Python, instalarlo con la opción **Add Python to PATH** y volver a intentar.

### En macOS y Linux

Abrir una terminal dentro de la carpeta y ejecutar:

```bash
python3 server.py
```

También es posible usar `./INICIAR_MAC_LINUX.sh`. Después, abrir http://127.0.0.1:8765/.

### Si el puerto 8765 está ocupado

```bash
python server.py --port 8766
```

Y abrir http://127.0.0.1:8766/.

## Funciones

- Calendario mensual con clasificación de días hábiles/inhábiles **base LFPA**, tareas y acceso al fundamento de cada fecha.
- Consulta de los días especiales del año y exportación de los 365/366 días a CSV (con URL oficial por registro).
- Calculadora de N días hábiles desde el día posterior a la fecha de inicio.
- Alta, edición, consulta, filtros por tipo/estado y eliminación de tareas, responsables, áreas, prioridades, notas y estatus.
- Dos tipos de tareas:
  - **Interna**: fecha de vencimiento manual, que NO se mueve cuando cae en día inhábil LFPA.
  - **Plazo LFPA**: fecha calculada automáticamente con el motor.
- Registro manual de excepciones *revisadas* para días inhábiles adicionales o habilitaciones con fuente oficial obligatoria.
- Cuando una excepción modifica un plazo LFPA ya guardado, se muestra **fecha sugerida**, que NO se aplica sin aprobación explícita en la tabla de tareas. Existe auditoría en SQLite.
- Exportación de tareas a CSV para abrir en Excel o LibreOffice.
- Persistencia local en SQLite (`datos/crt_planificador.sqlite3`) sin licencias de pago.

## Fundamento y límites jurídicos

Fuente principal: [LFPA, artículo 28 — Cámara de Diputados](https://www.diputados.gob.mx/LeyesBiblio/pdf/LFPA.pdf).

Días base del artículo 28: sábados, domingos, 1 de enero, 5 de febrero, 21 de marzo, 1 y 5 de mayo, 1 y 16 de septiembre, 20 de noviembre y 25 de diciembre. No trasladar esas fechas a lunes por reglas de descanso laboral. Existe el supuesto condicionado del 1 de diciembre cada seis años, **que no se agrega automáticamente** y requiere verificar el año concreto.

La LFPA prevé también vacaciones generales y suspensiones de **labores** formalmente publicadas. El programa **no trata las suspensiones de plazos de la CRT como días libres del personal**, porque pueden estar trabajando. Los acuerdos institucionales adicionales deben comprobarse y registrarse con revisión humana. El verificador opcional de PDF no interpreta reformas ni modifica el calendario por sí mismo.

Una clasificación `HABIL_BASE_LFPA` no garantiza apertura de oficinas, disponibilidad de trabajadores o aplicabilidad de LFPA a todo trámite; tampoco implica una conclusión jurídica definitiva. Las fechas de plazos dependen de reglas especiales y del momento en que surta efecto la notificación.

**Importante:** Las fuentes verificadas al crear este software no se actualizan en forma automática. El programa calcula cualquier año a partir de sus reglas existentes. Para detectar posibles cambios del PDF oficial, ver la sección siguiente.

## Control opcional de cambios en la fuente

Con internet activo, desde la terminal:

```bash
python verificar_fuente.py
```

La primera ejecución guarda una huella SHA-256 del documento; las siguientes advierten si **los bytes del PDF cambiaron**, pero no determinan si hubo una reforma. Se requiere revisión jurídica y, en su caso, actualizar el motor. Los enlaces del calendario se abren en el navegador al seleccionarlos.

## Pruebas incluidas

```bash
python -m unittest discover -s tests -v
```

13 pruebas automatizadas de clasificación LFPA, fechas, CRUD, excepciones, recálculo y CSV.

## ¿Dónde se guarda todo?

En `datos/crt_planificador.sqlite3`. Se crea al iniciar y **no viene con tareas ficticias**. Para hacer un respaldo, cierra el servidor y copia ese archivo a un lugar seguro. La captura `vista_previa.png` muestra datos de ejemplo **solo ilustrativos**; no están precargados en el sistema.

## Estructura

| Archivo | Función |
|---|---|
| `server.py` | Backend HTTP local + API REST + persistencia SQLite, sin bibliotecas externas |
| `lfpa.py` | Motor LFPA reutilizable en Python |
| `static/index.html` | Interfaz del sitio basada en la plantilla anterior |
| `static/styles.css` | Diseño CRT adaptado de la plantilla |
| `static/app.js` | Interacciones del calendario y gestión de tareas |
| `verificar_fuente.py` | Comparador opcional SHA-256 del documento oficial |
| `tests/test_app.py` | Pruebas automatizadas |
| `Calendario_LFPA_2026.csv` | Catálogo base de 2026 exportable |

## Uso institucional o publicación en internet

**No publiques este servidor directamente en internet**: escucha solo `127.0.0.1` a propósito y no contiene autenticación, autorización por usuarios, TLS, ni protección integral para datos sensibles. Para producción se necesitaría:

- Autenticación corporativa (por ejemplo, cuentas institucionales) y roles.
- HTTPS, control de acceso, gestión segura de secretos y respaldos.
- Revisión jurídica de reglas de cómputo, auditoría y calendarios institucionales.
- Una plataforma de despliegue autorizada por TI.

El software puede seguir siendo gratuito y de código abierto; la publicación, mantenimiento o infraestructura podrían tener un costo según el entorno.
