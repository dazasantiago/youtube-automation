# Handoff: topic-deep-research

## Qué hace esta etapa

Recibe un conjunto de señales ya clasificadas bajo un tema específico y hace scraping profundo de su contenido completo. También descubre fuentes adicionales sobre el tema vía Tavily. **No evalúa, no puntúa, no usa IA** — solo scraping.

---

## Cómo invocarla

**Modo clásico** — JSON con señales pre-clasificadas:
```bash
cd code/topic-deep-research
uv run deep-research --input <path-al-json>
```

**Modo topic** — descubre señales desde cero (ver [CLAUDE.md](CLAUDE.md) para detalles):
```bash
uv run deep-research --topic "GLM 5.2"
```

`--input` y `--topic` son mutuamente excluyentes. La estructura de salida es **idéntica** en
ambos modos (`signals_enriched.json` + `discovered_sources.json`).

Flags opcionales:
- `--out-dir <path>` — carpeta base de resultados (default: `results/`)
- `--top-signals <n>` — máximo de señales a enriquecer (default: 20)
- `--top-comments <n>` — máximo de comentarios Reddit por post (default: 10)
- `--per-source <n>` — señales a descubrir por fuente en modo `--topic` (default: 8)

---

## Input esperado

Un archivo JSON con esta estructura:

```json
{
  "topic": "MCP Servers",
  "generated_at": "2026-06-18T12:00:00Z",
  "signals": [
    {
      "source": "hn",
      "source_id": "41955256",
      "title": "...",
      "url": "https://...",
      "description": "...",
      "posted_at": "2026-06-16T14:32:00Z",
      "language": "en",
      "metrics": { "points": 847, "num_comments": 213 },
      "signal_type": "signal",
      "roles": ["signal"]
    },
    {
      "source": "youtube",
      "source_id": "abc111ABC11",
      "title": "...",
      "url": "https://www.youtube.com/watch?v=abc111ABC11",
      "description": "...",
      "posted_at": "2026-06-14T16:00:00Z",
      "language": "en",
      "metrics": { "views": 187000, "outlier_ratio": 6.2 },
      "signal_type": "yt_video",
      "roles": ["signal"]
    }
  ]
}
```

### Campos requeridos por señal

| Campo | Tipo | Notas |
|---|---|---|
| `source` | string | `"hn"`, `"reddit"`, `"youtube"`, `"rss"`, `"github_trending"`, etc. |
| `source_id` | string | ID único dentro de la fuente |
| `title` | string | |
| `url` | string \| null | Necesario para enriquecer; sin URL → skip |
| `signal_type` | `"signal"` \| `"yt_video"` | `"yt_video"` activa el enricher de YouTube |
| `roles` | string[] | Ver sección siguiente |
| `metrics` | object | Para YouTube debe incluir `outlier_ratio` |

### Roles

Etiquetas asignadas por la etapa anterior. Un signal puede tener múltiples.

| Rol | Significado |
|---|---|
| `"signal"` | Fuente de contenido principal |
| `"validator"` | Corrobora la dirección del tema |
| `"saturator"` | Indica saturación del tema en esa fuente |

Los roles se preservan intactos en el output — esta etapa no los modifica ni los usa para decidir qué enriquecer.

---

## Lógica de enriquecimiento por fuente

| `source` / `signal_type` | Enricher | Qué obtiene |
|---|---|---|
| `signal_type == "yt_video"` | YouTube | Transcript completo (hasta 20k chars) |
| `source == "hn"` | Trafilatura | Texto completo del artículo + autor/fecha |
| `source.startswith("reddit")` | Reddit JSON API | Cuerpo del post + top 10 comentarios + fechas |
| Cualquier otro con URL | Trafilatura (fallback) | Texto extraído de la URL |

### Umbral de outlier para YouTube

Solo se hace fetch del transcript si:
- `outlier_ratio >= 3.0` (overperformer claro), **o**
- `outlier_ratio <= 0.33` (underperformer extremo)

Videos con ratio entre 0.34 y 2.99 → `fetch_status: "skipped"`, pasan al output sin transcript.

---

## Output

Se escribe en:
```
results/YYYY-WNN/<topic-slug>/
  signals_enriched.json
  discovered_sources.json
```

La semana ISO se calcula automáticamente. El slug es el topic en lowercase con espacios → guiones (`"MCP Servers"` → `"mcp-servers"`).

### `signals_enriched.json`

Array de señales enriquecidas:

```json
[
  {
    "original": { ...signal original completo con roles y metrics... },
    "full_text": "Transcript o artículo completo...",
    "metadata": {
      "transcript_segment_count": 312,
      "video_id": "abc111ABC11"
    },
    "scraped_at": "2026-06-18T13:45:00Z",
    "fetch_status": "ok",
    "fetch_error": null
  }
]
```

`fetch_status` puede ser `"ok"`, `"skipped"` (sin error, simplemente no aplica), o `"error"` (falló el scraping).

### `discovered_sources.json`

Array de fuentes nuevas encontradas por Tavily:

```json
[
  {
    "url": "https://...",
    "domain": "simonwillison.net",
    "title": "...",
    "content": "Texto extraído por Tavily...",
    "published_date": "2026-06-15",
    "search_query": "MCP Servers",
    "scraped_at": "2026-06-18T13:45:00Z"
  }
]
```

`published_date` puede ser `null` si Tavily no la detecta.

---

## Variables de entorno requeridas

| Variable | Requerida | Uso |
|---|---|---|
| `TAVILY_API_KEY` | Sí | Web discovery. Sin key → `discovered_sources.json` vacío, enrichment continúa igual |

---

## Referencia rápida para la skill orquestadora

```
1. Generar el topic input JSON con la estructura descrita arriba
2. Escribirlo en code/topic-deep-research/data/<topic-slug>.json
3. Ejecutar: uv run deep-research research --input data/<topic-slug>.json
4. Leer resultados en: results/<YYYY-WNN>/<topic-slug>/
```

Ver [data/example_input.json](data/example_input.json) como referencia completa de input.
