# clip-ing
## Qué es

Motor de clipping automatizado: le das un link o un archivo de video largo y devuelve clips verticales 9:16 de 15 a 60 s, con subtítulos estilo viral (palabra resaltada) y un título sugerido para cada uno.

Úsalo solo con contenido propio o con permiso de su autor.

## Requisitos

- Windows 10/11, Python 3.11, ffmpeg (el script `setup.ps1` instala ambos con winget si faltan).
- GPU NVIDIA opcional (acelera transcripción y render con NVENC). Sin GPU todo funciona en CPU, más lento.
- La GTX 1060 (Pascal, compute 6.1) no tiene float16 rápido: se usa siempre `int8`. Con 6 GB de VRAM usa el modelo `medium`; con 3 GB, `small`.
- Driver NVIDIA >= 527.41 (CUDA 12). Recomendado: 16 GB de RAM y >= 50 GB libres en disco.
- Opcional: Claude Code CLI (`claude`) para selección con IA; sin él usa `--sin-ia`.

## Instalación en casa (paso a paso)

```powershell
git clone <url-del-repo-privado> clip-ing
cd clip-ing
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\.venv\Scripts\Activate.ps1
clip doctor
```

- `setup.ps1` es idempotente y pregunta antes de instalar cualquier cosa. Opciones: `-Si` (responde sí a todo), `-CPU` (ignora la GPU), `-SinModelo` (no predescarga el modelo Whisper).
- Si `Activate.ps1` da error de ExecutionPolicy: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y reintenta.
- Si el script instaló Python o ffmpeg, puede que debas cerrar y abrir la terminal y volver a ejecutarlo.

## Primera prueba
Con un video corto PROPIO de 2–5 min con voz:

```powershell
clip auto "C:\ruta\video.mp4" --n 3 --sin-ia
```

1. Revisa `proyectos\<id>\candidatos.json`.
2. `clip render <id>`
3. Los clips quedan en `proyectos\<id>\clips\`.

Luego, con IA: `clip auto video.mp4 --n 5`

## Comandos del CLI

| Comando | Qué hace |
|---|---|
| `clip doctor [--sin-prueba-nvenc]` | Diagnóstico: Python, ffmpeg, GPU, NVENC, dependencias, disco, RAM y configuración recomendada. |
| `clip auto FUENTE [--n 10] [--sin-ia] [--contexto "canal de GTA 6: carros y meets"] [--copiar] [--render]` | FUENTE = ruta o URL (YouTube/Twitch/Kick). Crea el proyecto, descarga, transcribe, detecta audio/escenas, selecciona y guarda `candidatos.json`. Con `--render` renderiza al final. |
| `clip buscar FUENTE_O_PROYECTO "descripción" [--n 3] [--sin-ia]` | Busca momentos que coincidan con una descripción. |
| `clip render PROYECTO [--solo c01,c03] [--reencuadre centro\|blur] [--dry-run]` | Renderiza los candidatos aprobados a clips 9:16 con subtítulos. |
| `clip revisar PROYECTO` | Fase 3: vista HTML de revisión. Por ahora indica cómo editar `candidatos.json` a mano (ver abajo). |
| `clip proyectos` | Lista los proyectos. |

Edición manual de `proyectos\<id>\candidatos.json`: cambia `inicio` / `fin` / `titulo`; pon `"aprobado": false` para excluir un candidato. Luego `clip render <id>`.

## Estructura de `proyectos/<id>/`

```
meta.json            datos del proyecto y fuente
transcripcion.json   transcripción con tiempos por palabra
audio.json           picos de volumen / energía
escenas.json         cortes de escena
candidatos.json      momentos seleccionados (editable)
subs/                subtítulos .ass por clip
clips/               clips finales .mp4 + un .json por clip con título sugerido y razón
```

`clip buscar` agrega sus resultados como `b01`, `b02`… sin pisar los `c01…` de `clip auto`.

Los pasos están cacheados: volver a ejecutar no retranscribe ni vuelve a detectar lo que ya existe.

## Configuración

`config.yaml` en la raíz. Claves principales:

| Clave | Valor por defecto | Descripción |
|---|---|---|
| `proyectos_dir` | `proyectos` | Carpeta de proyectos |
| `transcripcion.modelo` | `auto` | auto, tiny, base, small, medium, large-v3 |
| `transcripcion.dispositivo` | `auto` | auto, cuda, cpu |
| `transcripcion.compute_type` | `auto` | auto, int8, int8_float32, float32 (Pascal: nunca float16) |
| `transcripcion.idioma` | `null` | `null` autodetecta; `"es"` fuerza español |
| `seleccion.n` | `10` | Número de clips |
| `seleccion.min_seg` / `max_seg` | `15` / `60` | Duración mínima y máxima |
| `seleccion.usar_ia` | `true` | Usar claude CLI |
| `render.encoder` | `auto` | auto, h264_nvenc, libx264 |
| `render.reencuadre` | `blur` | centro o blur |
| `subtitulos.fuente` / `tamano` | `Arial Black` / `92` | Estilo de subtítulos |

Overrides por variable de entorno o `.env`: `CLIP__SECCION__CLAVE`, por ejemplo:

```
CLIP__RENDER__ENCODER=libx264
CLIP__TRANSCRIPCION__MODELO=small
CLIP__PROYECTOS_DIR=D:/clips/proyectos
```

## Rendimiento esperado (aprox., GTX 1060)

- Transcripción `medium` int8 con 6 GB: ~3–6x tiempo real (aprox.).
- Transcripción `small` en CPU (i5 10ma gen): ~1x tiempo real (aprox.).
- Render con NVENC: rápido, normalmente bastante más rápido que el tiempo real del clip (aprox.).

## Solución de problemas

| Síntoma | Solución |
|---|---|
| `cublas64_12.dll` o cuDNN no encontrado | Reejecuta `setup.ps1` (instala cuBLAS/cuDNN) o usa `-CPU`. |
| NVENC falla | Actualiza el driver NVIDIA o usa `CLIP__RENDER__ENCODER=libx264`. |
| `claude` no encontrado | Usa `--sin-ia`, o instala `npm install -g @anthropic-ai/claude-code` y ejecuta `claude` para iniciar sesión. |
| Out of memory en GPU | `CLIP__TRANSCRIPCION__MODELO=small`. |