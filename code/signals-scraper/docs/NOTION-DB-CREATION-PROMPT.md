# Prompt one-shot — Crear la base de datos de Notion ("Radar de Temas")

> **Uso:** copia y pega TODO el bloque de abajo (desde "INICIO DEL PROMPT" hasta "FIN DEL PROMPT") en una sesión de Claude que tenga acceso al **Notion MCP**. Es una tarea de un solo disparo: crea la base de datos con el schema exacto y te devuelve los dos IDs que el pipeline necesita.
>
> **Por qué el schema debe ser exacto:** el pipeline (`src/content_intel/sinks/notion.py`) escribe propiedades por **nombre y tipo literal**. Si un nombre o tipo no coincide, la API devuelve `400 validation_error`. Este prompt y el contrato de la Fase 7 del plan de reconstrucción son la misma fuente de verdad.

---

## Contexto del pipeline (para que entiendas qué escribirá cada campo)

Un pipeline de Python corre a diario en GitHub Actions, detecta temas/ideas de contenido para un canal de YouTube de IA, los puntúa, y hace *upsert* de cada tema como una página (fila) en esta base de datos. El dueño revisa la base, ordena por score, observa la evolución temporal de cada tema, y decide manualmente qué grabar usando la columna **"Mi decisión"** — que **solo edita el dueño** (el pipeline jamás la sobrescribe).

El pipeline escribe estas propiedades en cada actualización: `Tema`, `Score`, `Demanda`, `Saturación`, `Validación`, `Tendencia`, `Score pico`, `Prom. 7d`, `Histórico`, `Días en radar`, `Fuentes`, `# Señales`, `Idiomas`, `Keywords`, `Breakout sin cubrir`, `Estado pipeline`, `Primera vez`, `Última señal`, `Actualizado`. Solo al **crear** una fila pone `Mi decisión = 📥 Nuevo`.

---

## ============ INICIO DEL PROMPT ============

Necesito que crees una base de datos en Notion usando el Notion MCP. Es para un sistema de inteligencia de contenido: un pipeline automático escribirá filas (temas de video rankeados) y yo decidiré manualmente qué grabar.

**Antes de crear nada**, pregúntame en qué página padre quieres crearla si no tienes una página de destino clara (o créala como página de nivel superior del workspace si el MCP lo permite). El título de la base de datos debe ser exactamente: **`Radar de Temas`**.

Crea la base de datos con EXACTAMENTE estas propiedades — respeta los nombres (con tildes y mayúsculas), los tipos, y para los Select/Status las opciones indicadas. No agregues, renombres ni omitas ninguna:

| # | Nombre exacto | Tipo | Opciones / notas |
|---|---|---|---|
| 1 | `Tema` | Title | (la propiedad título obligatoria) |
| 2 | `Score` | Number | formato número, 1 decimal |
| 3 | `Demanda` | Number | |
| 4 | `Saturación` | Number | |
| 5 | `Validación` | Number | |
| 6 | `Tendencia` | Select | opciones: `↑ Subiendo`, `→ Estable`, `↓ Bajando` |
| 7 | `Score pico` | Number | |
| 8 | `Prom. 7d` | Number | |
| 9 | `Histórico` | Text (rich_text) | guarda un sparkline tipo `▁▂▃▅▇` |
| 10 | `Días en radar` | Number | |
| 11 | `Fuentes` | Multi-select | sin opciones predefinidas (el pipeline las crea: `github_trending`, `hn`, `reddit`, `hf`, `product_hunt`, `x_apify`, `gtrends`, `rss`) |
| 12 | `# Señales` | Number | |
| 13 | `Idiomas` | Multi-select | opciones: `en`, `es` |
| 14 | `Keywords` | Multi-select | sin opciones predefinidas (el pipeline las crea dinámicamente) |
| 15 | `Breakout sin cubrir` | Checkbox | |
| 16 | `Estado pipeline` | Select | opciones: `Activo`, `Stale` |
| 17 | `Primera vez` | Date | |
| 18 | `Última señal` | Date | |
| 19 | `Actualizado` | Date | |
| 20 | `Mi decisión` | Select | opciones (en este orden): `📥 Nuevo`, `👀 Considerando`, `🎬 A grabar`, `✅ Grabado`, `🗑️ Descartado` |

Notas importantes:
- `Mi decisión`, `Tendencia` y `Estado pipeline` deben ser tipo **Select** (no Status), porque el pipeline las escribe por nombre vía API y necesito poder editar `Mi decisión` a mano sin fricción.
- Para `Tendencia`, `Idiomas`, `Estado pipeline` y `Mi decisión`, **predefine** las opciones listadas arriba (con sus emojis/flechas exactos). Para `Fuentes` y `Keywords` NO predefinas opciones: el pipeline las crea sobre la marcha.
- No crees ninguna fila de ejemplo.

Después de crear la base de datos, configura estas **vistas** (si el MCP lo permite; si no, dímelo y las creo yo a mano):

1. **Vista Tablero (Board)** — agrupada por `Mi decisión`. Es mi vista principal de decisión. Orden dentro de cada columna: `Score` descendente.
2. **Vista Tabla (Table)** — ordenada por `Score` descendente. Columnas visibles en este orden: `Tema`, `Mi decisión`, `Score`, `Tendencia`, `Histórico`, `Demanda`, `Saturación`, `Validación`, `Breakout sin cubrir`, `Fuentes`, `Días en radar`, `Actualizado`.
3. **Vista Breakouts** — tabla filtrada por `Breakout sin cubrir = ✓`, ordenada por `Demanda` descendente. (Oportunidades first-mover: alta demanda, aún sin video en inglés.)
4. **Vista A grabar** — tabla filtrada por `Mi decisión = 🎬 A grabar`.

Cuando termines, **devuélveme exactamente esto** (lo necesito para configurar los secretos del pipeline en GitHub Actions):

```
NOTION_DATABASE_ID = <el database_id, el UUID de la base recién creada>
NOTION_DATA_SOURCE_ID = <el data_source_id de su data source>
URL = <la URL de la base de datos>
```

Para obtener el `data_source_id`: tras crear la base, consulta `GET databases/{database_id}` y toma `data_sources[0].id`. (El pipeline usa la API versión `2025-09-03`, donde la creación de páginas usa `data_source_id` como parent, no `database_id`.)

Por último, recuérdame este paso manual que el MCP probablemente no puede hacer por mí:
> ⚠️ Abre la base en Notion → menú `...` → **Connections** → agrega la integración interna cuyo token es `NOTION_API_KEY`. Sin esto, todas las llamadas del pipeline devuelven `404`.

## ============ FIN DEL PROMPT ============

---

## Después: configurar los secretos (lo haces tú, fuera de Notion)

1. En GitHub → repo → Settings → Secrets and variables → Actions, crea:
   - `NOTION_API_KEY` = el *Internal Integration Secret* de tu integración interna de Notion (creada en https://www.notion.com/my-integrations con permisos Read + Insert + Update).
   - `NOTION_DATABASE_ID` = el valor que devolvió el prompt.
2. Comparte la base con la integración (paso ⚠️ de arriba).
3. El pipeline obtiene el `data_source_id` solo en cada corrida (vía `GET databases/{id}`), así que **no** necesitas guardar `NOTION_DATA_SOURCE_ID` como secreto — pero guárdalo a mano por si lo necesitas para depurar.

## Verificación rápida (opcional, local)
Con `NOTION_API_KEY` y `NOTION_DATABASE_ID` en el entorno:
```bash
uv run python -c "from content_intel.sinks.notion import _client, _get_data_source_id; import os; n=_client(); print(_get_data_source_id(n, os.environ['NOTION_DATABASE_ID']))"
```
Debe imprimir un UUID (el `data_source_id`) sin error. Si da `404`, falta compartir la base con la integración. Si da `401`, el token es inválido.
