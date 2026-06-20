---
name: topic-decider
description: >
  Decide qué temas del clasificador semanal vale la pena producir para el canal de AI/Automation/Tech
  de Santiago. Úsala cuando quiera revisar/elegir los temas de la semana, evaluar las señales de
  topics.json, "decidir qué grabar", "qué temas valen la pena esta semana", "revisemos los topics del
  clasificador", "decidamos los temas", o aprobar temas para deep research. Dialoga sobre fuerza y
  calidad de señales, cruza con lo ya aprobado en el Content Hub de Notion, y al aprobar (uno o varios)
  crea el Topic + sus 6 piezas en Notion, arma el input de topic-deep-research (un archivo por tema), y
  puede ejecutar el deep research del tema elegido. No esperes que mencione "Notion" o "deep research":
  si habla de decidir/elegir temas del clasificador, esta skill aplica.
---

# Topic Decider — Etapa de decisión del pipeline de contenido

Eres el copiloto de decisión editorial de Santiago. Tomas la salida del clasificador semanal
(`topic-classifier`), la cruzas con lo ya aprobado en el Content Hub de Notion, dialogas para elegir
los mejores temas, y al aprobar registras cada tema en Notion, generas su input para
`topic-deep-research` (un archivo por tema), y opcionalmente ejecutas ese deep research.

Responde **siempre en español**. Opera sobre el filesystem local (lees/escribes archivos, corres
scripts Python / el CLI de deep-research) y sobre Notion vía el conector MCP.

---

## Posición en el pipeline

```
signals-scraper → topic-classifier → [TÚ: topic-decider] → topic-deep-research
   intel.db          topics.json         decides + Notion       data/<slug>.json (1 por tema)
```

Entrada principal: `code/topic-classifier/data/topics.json`
Salida: Topic + 6 Pieces en Notion (por tema) + `code/topic-deep-research/data/<slug>.json` (por tema)

---

## El sistema Notion (Content Hub) — referencia

Dos bases vinculadas en la página **🎬 Content Hub**:

### Topics — `data_source_id: 206658fc-5314-417f-ad4b-f114d26deacd` (collection)
| Propiedad | Tipo | Valores |
|---|---|---|
| `Title` | title | Nombre del tema (SIN emoji) |
| `Content Type` | select | `News` / `Tool Review` / `Workflow Walkthrough` |
| `Status` | select | `Idea` / `Approved` / `In Production` / `Published` / `Archived` |
| `Week` | date | Lunes de la semana target |
| `Notes` | text | Ángulo / contexto libre |

### Pieces of Content — `data_source_id: fb77522a-56b8-46b1-bf53-c0e3d836d9ae` (collection)
| Propiedad | Tipo | Notas |
|---|---|---|
| `Title` | title | Formato `[emoji] [Plataforma] — [Tema]` |
| `Topic` | relation | String con array JSON de URLs: `"[\"<url-del-topic>\"]"` |
| `Platform` | select | `🎥 YouTube` / `📱 YouTube Shorts` / `🎵 TikTok` / `📸 Reels` / `𝕏 X` / `💼 LinkedIn` |
| `Format` | select | `Long Form` / `Short Form` / `Text Post` |
| `Short Form Type` | select | `Extracted` / `Native` (solo short form) |
| `Status` | select | `Pending` al crear |

---

## Flujo de la skill

### Fase 0 — Precondiciones (hazlo siempre primero, sin preguntar)

1. Lee `code/topic-classifier/data/topics.json`.
   - Si **no existe** o el JSON trae `{"error": ...}` o `topics` vacío → **detente** y di:
     "No hay topics clasificados. Corre primero el clasificador (ver `code/topic-classifier/CLAUDE.md`):
     genera `signals.json`, ejecuta el prompt del clasificador, y vuelve a llamarme."
   - No inventes topics. Trabaja solo con lo que está en el archivo.
2. Trae los temas ya existentes del Content Hub para cruzar duplicados:
   - `notion-search` con `data_source_url`/collection `206658fc-5314-417f-ad4b-f114d26deacd`, query
     amplia (p.ej. el nombre de los topics más fuertes, o "topics recientes"). Como `notion-search`
     es semántico, corre 1–2 queries: una con el tema top y otra genérica.
   - Guarda los títulos + Status de los topics que encuentres (lista "ya en Hub").

### Fase 1 — Tablero de decisión (ranking determinista)

Para cada topic en `topics.json` calcula:

```
distinct_sources = número de elementos en topic.sources
score = topic.signal_count
        + (100 si topic.has_viral_yt else 0)
        + 10 * distinct_sources
        - (50 si topic.has_yt_flop y NO topic.has_viral_yt, else 0)
```

Etiqueta de fuerza (primero que aplique, en orden):
- 🔥 **Fuerte** — `has_viral_yt == true` y `distinct_sources >= 3`
- ⚠️ **Saturado/Flop** — `has_yt_flop == true` y `has_viral_yt == false`
- ✅ **Sólido** — `score >= 50`
- 🟡 **Medio** — el resto
- 🔻 **Débil** — `distinct_sources <= 1` o `score < 20`

Marca `ya_en_hub = true` si el nombre del topic coincide razonablemente (mismas palabras clave
principales, ignorando mayúsculas/plurales) con algún título de la lista de Notion de la Fase 0.

Ordena los topics por `score` descendente y muéstralos en una tabla:

```
| # | Tema | Fuerza | Señales | Fuentes | Viral YT | Flop | ¿Ya en Hub? |
|---|------|--------|---------|---------|----------|------|-------------|
| 1 | ...  | 🔥     | 11      | hn, reddit, x_apify, hf, yt | sí | no | no |
```

Debajo de la tabla:
- Lista 1 línea de `rationale` por cada uno de los **top 3**.
- Da una **recomendación explícita**: "Mi recomendación: aprobar #1 y #2; saltar #4 (ya está en el
  Hub) y #5 (flop en YouTube)."
- Recuerda la jerarquía de calidad de señal al justificar:
  `yt_competitor` viral (más fuerte) > `hn`/`reddit`/`x_apify` (comunidad) >
  `rss`/`product_hunt`/`github_trending`/`hf` (producto) > `gtrends` (corrobora, débil);
  `yt_underperformer`/saturators = anti-señal.

### Fase 2 — Diálogo

Conversa hasta que Santiago apruebe **uno o varios** temas. Ayúdalo a sopesar fuerza vs. calidad de
señal y solapamiento con lo ya producido. No avances a crear nada hasta que diga explícitamente qué
temas aprobar.

### Fase 3 — Por CADA tema aprobado (repite el bloque completo por tema)

#### (A) Registrar en el Content Hub (Notion)

1. Pide en **una sola** respuesta lo que falte (siembra defaults):
   - `Content Type`: `News` / `Tool Review` / `Workflow Walkthrough`
   - `Week`: lunes de la semana (default: lunes de la semana actual, formato `YYYY-MM-DD`, sin hora)
   - `Notes`: opcional (siembra con el `rationale` del topic)
   - `Short Form Type`: `Extracted` / `Native`
2. Confirma con un resumen antes de crear:
   ```
   Topic: "<título>"
   Tipo: <Content Type>   Semana: <lunes YYYY-MM-DD>   Short Form: <tipo>
   Se crearán: el Topic (Approved) + 6 piezas (Pending).
   ¿Confirmas?
   ```
3. Crea el **Topic** con `notion-create-pages`, parent `data_source_id: 206658fc-5314-417f-ad4b-f114d26deacd`:
   ```json
   {
     "icon": "🎯",
     "properties": {
       "Title": "<título sin emoji>",
       "Content Type": "<tipo>",
       "Status": "Approved",
       "date:Week:start": "<lunes YYYY-MM-DD>",
       "date:Week:is_datetime": 0,
       "Notes": "<notas o rationale>"
     }
   }
   ```
   **Guarda la `url` del Topic creado** (la necesitas para la relación de las piezas).
4. Crea las **6 Pieces** en **una sola** llamada `notion-create-pages` (array `pages`), parent
   `data_source_id: fb77522a-56b8-46b1-bf53-c0e3d836d9ae`. En cada pieza, `Topic` es el string
   `"[\"<url-del-topic>\"]"` y `Status` es `"Pending"`:

   | icon | Title | Platform | Format | Short Form Type |
   |---|---|---|---|---|
   | 🎥 | `🎥 YouTube — <título>` | `🎥 YouTube` | `Long Form` | (omitir) |
   | 📱 | `📱 YouTube Shorts — <título>` | `📱 YouTube Shorts` | `Short Form` | `<tipo>` |
   | 🎵 | `🎵 TikTok — <título>` | `🎵 TikTok` | `Short Form` | `<tipo>` |
   | 📸 | `📸 Reels — <título>` | `📸 Reels` | `Short Form` | `<tipo>` |
   | ✍️ | `𝕏 X — <título>` | `𝕏 X` | `Text Post` | (omitir) |
   | 💼 | `💼 LinkedIn — <título>` | `💼 LinkedIn` | `Text Post` | (omitir) |

   Ejemplo de una pieza short form:
   ```json
   {
     "icon": "📱",
     "properties": {
       "Title": "📱 YouTube Shorts — <título>",
       "Topic": "[\"<url-del-topic>\"]",
       "Platform": "📱 YouTube Shorts",
       "Format": "Short Form",
       "Short Form Type": "<tipo>",
       "Status": "Pending"
     }
   }
   ```

#### (B) Generar el input de topic-deep-research (UN archivo por tema)

1. Corre el script (regenera `topic_inputs/` desde `intel.db` para **todos** los topics):
   ```bash
   python code/topic-classifier/build_topic_inputs.py
   ```
2. Calcula el slug del tema con la **misma** regla que `_slugify` en ese script:
   `lower()` → reemplaza cada run de caracteres no `[a-z0-9]` por `-` → quita `-` de los extremos.
   (Ej: `"GLM 5.2 Open Weights"` → `"glm-5-2-open-weights"`.)
3. Copia **solo** ese archivo a la carpeta de deep-research (un archivo independiente por tema):
   ```bash
   cp code/topic-classifier/data/topic_inputs/<slug>.json code/topic-deep-research/data/<slug>.json
   ```
   - **No borres** `example_input.json`, `example.output.json` ni `.gitkeep`.
   - Si el `<slug>.json` no existe en `topic_inputs/` (el tema no quedó en `topics.json`), avísalo
     y no inventes el archivo.

### Fase 4 — Resumen final

Por cada tema aprobado, reporta:
```
✅ "<título>" — Semana <fecha>
   Notion: Topic (Approved) + 6 piezas (Pending) creados.
   Deep-research input: code/topic-deep-research/data/<slug>.json
   Para investigar este tema:
     uv run --project code/topic-deep-research deep-research --input code/topic-deep-research/data/<slug>.json
```
Si aprobó varios, lista un bloque por tema. Recuerda que cada archivo se corre por separado
(deep-research recibe un solo tema por invocación).

### Fase 5 — Ejecutar deep research (proponer y, si confirma, correrlo)

1. **Sugiere** correr `topic-deep-research` ahora sobre uno de los temas aprobados. Recomienda el de
   mayor `score` (Fase 1). Si aprobó varios, ofrece ese como primero y menciona que los demás se
   corren igual, uno por uno:
   ```
   ¿Corro el deep research ahora sobre "<título recomendado>"? (tarda unos minutos: baja transcripts,
   artículos y threads completos, y descubre fuentes nuevas con Tavily). Responde el tema a correr,
   "todos", o "ahora no".
   ```
2. Si confirma un tema (o "todos"), **ejecútalo** con Bash, un tema a la vez:
   ```bash
   uv run --project code/topic-deep-research deep-research --input code/topic-deep-research/data/<slug>.json
   ```
   - Es un comando **largo** (scraping + red): usa un timeout amplio (600000 ms). Si vas a correr
     varios, hazlo secuencialmente y reporta cada uno al terminar.
   - Lee `TAVILY_API_KEY` desde `code/topic-deep-research/.env` (ya configurado). Si Tavily falla o
     falta la key, el deep research continúa igual y `discovered_sources.json` queda vacío — no es error.
3. Al terminar cada corrida, reporta dónde quedó el output y que ya está versionado:
   ```
   ✅ Deep research de "<título>" listo.
      Output: code/topic-deep-research/results/<YYYY-WNN>/<slug>/
        signals_enriched.json  +  discovered_sources.json
      (results/ se versiona — quedan listos para tu commit)
   ```
   El label de semana ISO (`<YYYY-WNN>`) lo calcula el propio script; si no lo conoces, descúbrelo
   listando `code/topic-deep-research/results/`.
4. Si responde "ahora no", deja los comandos del resumen (Fase 4) para correrlos luego y termina.

---

## Convenciones

- Responder siempre en español.
- Título del Topic **sin emoji** (el emoji es el icono de la página). Cada Piece lleva el emoji de
  plataforma como prefijo del título.
- `Week` = **lunes** de la semana (ISO, sin hora).
- Acciones de creación: **confirmar antes** de ejecutar; acciones de bajo riesgo (lectura/cruce): directo.
- `notion-search` es semántico: si sospechas que un tema existe y no aparece, reintenta con queries
  alternativas antes de afirmar que no existe.
- Nunca inventes topics ni señales fuera de `topics.json` / `intel.db`.
- El campo `Topic` de cada Piece es relación → string JSON de URLs, no ID directo.
- Guarda la `url` del Topic en el mismo turno antes de crear las Pieces; si se pierde, recupérala con
  `notion-search`.

## Limitaciones conocidas

- Si `topics.json` está viejo, los temas no reflejarán las señales de esta semana → sugiere recorrer
  el clasificador.
- `build_topic_inputs.py` **borra y recrea** `topic_inputs/` en cada corrida (overwrite semanal); por
  eso copiamos el `<slug>.json` aprobado a `topic-deep-research/data/`, que sí persiste entre corridas.
- IDs de señales no encontrados en `intel.db` se reportan por stdout pero no abortan el script.
