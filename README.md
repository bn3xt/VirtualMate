# VirtualMate

Asistente RAG portátil para entornos restringidos. Ejecuta una interfaz local, consulta servidores de modelos OpenAI-compatible —incluidos modelos locales o corporativos— y responde a partir de una persona y un corpus que permanecen en el workspace local. No inicia ni requiere ningún servicio de Substrate.

## Uso del portable

1. Copia o extrae completa la carpeta `VirtualMate`.
2. Edita `workspace/persona.md` con la identidad, estilo, rol, preferencias y criterios de incertidumbre del asistente.
3. Copia documentos `.md` y `.docx` dentro de `workspace/knowledge`; se admiten subdirectorios.
4. Opcionalmente, coloca un PNG llamado `workspace/avatar.png` para personalizar el avatar. En **Administration → Appearance**, pulsa **Refresh avatar** después de reemplazarlo.
5. Si un servidor HTTPS usa la CA corporativa, coloca el certificado en `workspace/corporate-ca.pem`.
6. Ejecuta `VirtualMate.exe`. Se abre la interfaz en el navegador y el proceso escucha únicamente en `127.0.0.1`.
7. En **Administration**, configura uno o varios servidores OpenAI-compatible, descubre sus modelos con `GET /models`, asigna los roles `chat` y `embeddings`, y pulsa **Process knowledge**.
8. Usa **Chat**. Cada pregunta ejecuta una nueva recuperación híbrida y muestra las evidencias utilizadas.

`Process knowledge` elimina el índice anterior y reconstruye Chroma y SQLite desde cero. Los paths del workspace no son configurables y el navegador no realiza `POST` locales: las mutaciones y el chat usan WebSocket.

## Directorios

```text
VirtualMate/
├─ VirtualMate.exe
├─ workspace/
│  ├─ persona.md
│  ├─ avatar.png             # opcional; avatar de la instancia
│  ├─ knowledge/
│  └─ corporate-ca.pem       # opcional
├─ data/                     # configuración, corpus.db, Chroma y logs
└─ _internal/                # runtime privado y frontend precompilado de PyInstaller
```

No incluyas credenciales ni datos que no quieras conservar en el portable. La configuración se guarda localmente en `data/config.json` porque la aplicación está diseñada para uso personal sin autenticación. `workspace/`, `data/`, logs, builds y avatares personalizados están excluidos por `.gitignore` y no deben publicarse.

## Ajustes operativos por fichero

Con la aplicación cerrada, puedes ajustar `data/config.json`. Los parámetros operativos están bajo `runtime_tuning`; se conservan al guardar la configuración desde Administración.

```json
{
  "runtime_tuning": {
    "embedding_batch_size": 32,
    "embedding_retry_attempts": 2,
    "embedding_retry_delay_seconds": 2.0,
    "embedding_inter_request_delay_ms": 0,
    "model_request_timeout_seconds": 60.0
  }
}
```

- `embedding_batch_size`: máximo de textos enviados por petición de embeddings. El valor predeterminado es `32`; bájalo si el servidor responde `413`.
- `embedding_retry_attempts`: reintentos adicionales para errores transitorios de embeddings. No se reintenta un `413`, porque requiere reducir el lote.
- `embedding_retry_delay_seconds`: espera entre reintentos.
- `embedding_inter_request_delay_ms`: pausa entre lotes, útil ante límites de tasa.
- `model_request_timeout_seconds`: timeout de las conexiones a servidores de modelos.

Los valores se validan al inicio. Si el JSON no es válido o supera los límites, la aplicación muestra el error y no usa una configuración parcial.

## Desarrollo y verificación

Desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m pytest -c standalone/virtual_mate/pytest.ini -q `
  standalone/virtual_mate/tests/unit `
  standalone/virtual_mate/tests/integration `
  standalone/virtual_mate/tests/packaging

npx playwright test --config standalone/virtual_mate/playwright.config.ts
.\standalone\virtual_mate\scripts\run_operational_e2e.ps1
.\standalone\virtual_mate\scripts\build_portable.ps1
```

La prueba operacional respeta las variables existentes o el contrato de cuatro líneas de `KEY.txt`, sin modificarlo. Requiere OpenRouter con `mistralai/ministral-14b-2512` y el servidor local con `Alibaba-NLP/gte-multilingual-base`.

