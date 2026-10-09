# svc-productos

Servicio síncrono (pod en GKE) de **Productos y Configuración de Mercado**.

Hoy sirve los **documentos legales versionados** del registro (términos y condiciones,
tratamiento de datos personales y consulta en centrales de riesgo). Contrato:
[`openapi/openapi.yaml`](openapi/openapi.yaml).

- Cada documento es **inmutable**: un cambio de texto se publica como una versión nueva
  (`V1`, `V2`, …), nunca se modifica la existente. La vigente es la más alta por
  mercado e idioma.
- La tabla `documento_legal_version` solo se inserta (con `creado_en` y `creado_por`);
  en SQLite dos triggers abortan cualquier `UPDATE` o `DELETE`.
- Al arrancar, el servicio carga de forma idempotente los textos de
  [`app/seeds/documentos_legales.json`](app/seeds/documentos_legales.json) (es-CO, `V1`).
  Para corregir un texto se **agrega** una versión nueva en ese archivo; editar una ya
  publicada no tiene efecto.
- La aceptación del cliente no vive aquí: la registra CoreTransaccional.

## Plantillas de correo

También guarda las **plantillas de los correos** (`bienvenida` y `verificacion-correo`) por
mercado e idioma, con el mismo esquema inmutable y versionado. Las consume CoreTransaccional
(`GET /plantillas-correo/{tipo}?mercado=CO&idioma=es-CO`, interno, sin rellenar); Core las rellena
y las manda a la función `fn-notificaciones`.

Los textos viven en `app/seeds/plantillas_correo/<mercado>/<idioma>/` y se cargan al arrancar:

- `<tipo>.v<N>.html` — el **asunto** es el `<title>` del HTML — y su par `<tipo>.v<N>.txt`
  (versión de texto plano).
- Variables con la forma `{{nombre}}`. `bienvenida`: `nombre`, `urlWeb`, `anio`.
  `verificacion-correo`: `nombre`, `enlaceVerificacion` (obligatoria), `anio`. Una variable
  desconocida o un marcador mal formado detiene el arranque.
- **Para reemplazar una plantilla**: sobrescribe los archivos de la versión actual. Surte efecto
  cuando la base está vacía (hoy, en cada arranque del pod). Para publicarla sobre una base que ya
  la tiene, agrega `<tipo>.v2.html` y `<tipo>.v2.txt`: la versión vigente es la más alta.

## Correr el servicio en local

Requiere Python 3.12+.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash);  en Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload --port 8100
```

- Contrato: <http://localhost:8100/openapi.yaml> · salud: <http://localhost:8100/health>
- Prueba rápida:

```bash
curl "http://localhost:8100/documentos-legales?mercado=CO"
curl "http://localhost:8100/documentos-legales/terminos/versiones/V1?mercado=CO"
```

### Variables de entorno (prefijo `PRODUCTOS_`)

| Variable | Default | Notas |
|---|---|---|
| `PRODUCTOS_REPOSITORY_BACKEND` | `sqlite` | `sqlite` \| `memory` (pruebas) |
| `PRODUCTOS_DATABASE_PATH` | `./svc_productos.db` | archivo SQLite |
| `PRODUCTOS_SEED_ENABLED` | `true` | carga inicial al arrancar |
| `PRODUCTOS_SEED_AUTOR` | `seed-inicial` | valor de `creado_por` de lo cargado |
| `PRODUCTOS_OTEL_ENABLED` | `false` | trazas/métricas/logs hacia Alloy (DI-008) |

## Pruebas

```bash
pytest --cov=app        # gate de cobertura: 80 %
ruff check . && ruff format --check .
```
