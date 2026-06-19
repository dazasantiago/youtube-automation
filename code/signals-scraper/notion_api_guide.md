# Notion API Integration Guide
> Referencia técnica — API version 2025-09-03

---

## 1. Cambio de modelo de datos (Sept 2025) — lectura obligatoria

En septiembre de 2025, Notion introdujo la versión `2025-09-03`, no retrocompatible con `2022-06-28`.

El cambio central: el concepto de "base de datos" se separó en dos objetos distintos.

| Concepto anterior | Concepto nuevo |
|---|---|
| `database` (contenedor + datos en uno) | `database` = solo el contenedor |
| (implícito, único set de datos) | `data_source` = el set de filas y propiedades |

**Impacto práctico:** las operaciones que antes usaban `database_id` ahora requieren `data_source_id`. Usar `database_id` donde se espera `data_source_id` retorna `400 validation_error`.

---

## 2. Setup: integración interna

### Crear la integración
1. Ir a [https://www.notion.com/my-integrations](https://www.notion.com/my-integrations)
2. Crear una integración de tipo **Internal**
3. Habilitar solo los permisos necesarios:
   - ✅ Read content
   - ✅ Insert content
   - ✅ Update content
4. Copiar el **Internal Integration Secret** → usarlo como `NOTION_API_KEY`

### Dar acceso a una base de datos
En Notion: abrir la base de datos → "..." → "Connections" → agregar la integración.

La integración **solo puede acceder a lo que explícitamente se le comparte**. Sin este paso, todas las llamadas retornan `404`.

---

## 3. Librería recomendada

```bash
pip install notion-client
```

SDK oficial de Python, mantenido por Notion. Soporta sync y async.

```python
from notion_client import Client

notion = Client(
    auth=os.environ["NOTION_API_KEY"],
    notion_version="2025-09-03"  # Siempre especificar versión explícitamente
)
```

---

## 4. Discovery: obtener el `data_source_id`

Antes de cualquier operación de escritura en una base de datos, obtener su `data_source_id`:

```python
def get_data_source_id(database_id: str) -> str:
    response = notion.request(
        method="GET",
        path=f"databases/{database_id}"
    )
    data_sources = response.get("data_sources", [])
    if not data_sources:
        raise ValueError(f"No data sources found for database {database_id}")
    return data_sources[0]["id"]
```

> El `data_source_id` es estable — no cambia a menos que se elimine y recree la base. Cachearlo para no repetir esta llamada en cada ejecución.

Para obtener el `database_id` desde Notion: la URL de una base tiene el formato `https://notion.so/workspace/[TITULO]-[DATABASE_ID]?v=[VIEW_ID]`. El ID es el UUID antes del `?v=`.

---

## 5. Crear una página en una base de datos

Con `2025-09-03`, el parent usa `data_source_id`:

```python
notion.pages.create(**{
    "parent": {
        "type": "data_source_id",
        "data_source_id": DATA_SOURCE_ID
    },
    "properties": {
        "Nombre": {
            "title": [{"text": {"content": "valor"}}]
        },
        "Estado": {
            "status": {"name": "Idea"}
        },
        "Puntuación": {
            "number": 87.5
        },
        "Fuente": {
            "select": {"name": "HackerNews"}
        },
        "URL": {
            "url": "https://ejemplo.com"
        },
        "Notas": {
            "rich_text": [{"text": {"content": "texto libre"}}]
        }
    }
})
```

---

## 6. Consultar páginas de una base de datos

Con `2025-09-03`, la query va al endpoint `/data_sources/{id}/query`:

```python
def query_data_source(data_source_id: str, filter_body: dict = None) -> list:
    results = []
    cursor = None

    while True:
        body = {}
        if filter_body:
            body["filter"] = filter_body
        if cursor:
            body["start_cursor"] = cursor

        response = notion.request(
            method="POST",
            path=f"data_sources/{data_source_id}/query",
            body=body
        )

        results.extend(response.get("results", []))

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    return results
```

Ejemplo de filtro:

```python
# Filtrar por un campo Select
filter_body = {
    "property": "Fuente",
    "select": {"equals": "Reddit"}
}
```

---

## 7. Actualizar una página existente

```python
notion.pages.update(
    page_id="PAGE_ID",
    properties={
        "Estado": {
            "status": {"name": "En desarrollo"}
        }
    }
)
```

---

## 8. Leer el schema de una base de datos

Para conocer exactamente los nombres y tipos de propiedades disponibles:

```python
response = notion.request(
    method="GET",
    path=f"data_sources/{DATA_SOURCE_ID}"
)
print(response["properties"])  # Fuente de verdad del schema
```

---

## 9. Manejo de rate limits

Límite: **3 requests/segundo promedio (2,700 por cada 15 minutos)**. HTTP 429 cuando se excede, con header `Retry-After` en segundos.

```python
import time
import random
from notion_client.errors import APIResponseError

def notion_request_with_retry(fn, max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            return fn()
        except APIResponseError as e:
            if e.status == 429:
                wait = (2 ** attempt) + random.uniform(0, 1)
                time.sleep(wait)
            elif e.status >= 500:
                time.sleep(2 ** attempt)
            else:
                raise  # Errores de cliente (400, 401, 403, 404) no se reintentan
    raise Exception(f"Max retries exceeded after {max_retries} attempts")
```

---

## 10. Tipos de propiedades — referencia rápida

| Tipo Notion | Estructura en el payload |
|---|---|
| Title | `{"title": [{"text": {"content": "valor"}}]}` |
| Rich text | `{"rich_text": [{"text": {"content": "valor"}}]}` |
| Number | `{"number": 42.5}` |
| Select | `{"select": {"name": "opción"}}` |
| Multi-select | `{"multi_select": [{"name": "a"}, {"name": "b"}]}` |
| Status | `{"status": {"name": "En progreso"}}` |
| Date | `{"date": {"start": "2026-06-07"}}` |
| URL | `{"url": "https://ejemplo.com"}` |
| Checkbox | `{"checkbox": True}` |

---

## 11. Errores comunes

| Error | Causa | Solución |
|---|---|---|
| `401 Unauthorized` | Token inválido | Verificar `NOTION_API_KEY` |
| `404 Not Found` | Integración sin acceso | Compartir la DB con la integración en Notion |
| `400 validation_error` | Property name o type incorrecto | Verificar schema con `GET /data_sources/{id}` |
| `400` en operaciones de DB | Usando `database_id` donde se espera `data_source_id` | Hacer el paso de discovery (sección 4) |
| `429 Too Many Requests` | Rate limit excedido | Usar exponential backoff (sección 9) |
