# De la teoría a la práctica: conecta tu app con datos abiertos y APIs en tiempo real

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Código: MIT](https://img.shields.io/badge/c%C3%B3digo-MIT-green.svg)](LICENSE)
[![Material: CC BY 4.0](https://img.shields.io/badge/material-CC%20BY%204.0-lightgrey.svg)](docs/LICENSE.md)
[![Diapositivas](https://img.shields.io/badge/diapositivas-PDF-D21F26?logo=adobeacrobatreader&logoColor=white)](docs/seminario-apis.pdf)
[![USAL](https://img.shields.io/badge/Universidad%20de%20Salamanca-ESALab-3A5E9C)](https://www.usal.es/)

![Spotify](https://img.shields.io/badge/Spotify-API-1DB954?logo=spotify&logoColor=white)
![Deezer](https://img.shields.io/badge/Deezer-API-A238FF?logo=deezer&logoColor=white)
![Twitch](https://img.shields.io/badge/Twitch-Helix-9146FF?logo=twitch&logoColor=white)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-AST-FFD21E?logo=huggingface&logoColor=black)
![Claude](https://img.shields.io/badge/Claude-API-D97757?logo=anthropic&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-API-8E75B2?logo=googlegemini&logoColor=white)

Material del seminario impartido el 23 de octubre de 2026 en la Facultad de Ciencias de la
Universidad de Salamanca: las diapositivas y las tres demos que se hicieron en directo.

La idea de fondo es sencilla: los pagos, los mapas, el login o la IA ya están resueltos y se
pueden usar a través de una API. Tu trabajo es la idea y la integración. Cada demo combina
varias APIs públicas para sacar algo que ninguna da por separado.

## Contenido

```
seminario-api/
├── docs/
│   ├── seminario-apis.pdf      diapositivas
│   └── LICENSE.md              licencia CC BY 4.0 del material
├── instrumentos/               ¿Qué instrumentos suenan en una canción?
│   ├── instrumentos.py
│   └── requirements.txt
├── twitch/                     ¿Qué se está viendo ahora en Twitch?
│   ├── directos_twitch.py
│   └── requirements.txt
├── asistente-voz/              Asistente de voz (Whisper + LLM + TTS)
│   ├── asistente_voz.py
│   └── requirements.txt
├── .env.example                plantilla de credenciales
├── CITATION.cff
└── LICENSE                     licencia MIT del código
```

| Demo | APIs y modelos | ¿Necesita clave? | Concepto que enseña |
|---|---|---|---|
| [`instrumentos`](#1-qué-instrumentos-suenan) | Deezer, Spotify, Hugging Face (AST), librosa | No (Spotify opcional) | Encadenar APIs + un modelo de IA, caché para trabajar sin red |
| [`twitch`](#2-qué-se-está-viendo-ahora-en-twitch) | Twitch Helix | Sí (gratis) | OAuth *client credentials*, *polling* en tiempo real |
| [`asistente-voz`](#3-asistente-de-voz) | faster-whisper, Claude o Gemini, edge-tts / Gemini TTS | Sí | Tres APIs en cadena, memoria de conversación, *fallbacks* |

## Puesta en marcha

Hace falta **Python 3.10 o superior**. Cada demo es independiente y tiene su propio
`requirements.txt`, así que lo más cómodo es crear un entorno virtual por carpeta.

```bash
git clone https://github.com/anordinaryusser/seminario-api.git
cd seminario-api
cp .env.example .env        # en Windows: copy .env.example .env
```

Abre `.env` y rellena solo las claves de las demos que vayas a usar. Los scripts buscan el
`.env` subiendo desde la carpeta en la que se ejecutan, así que con uno en la raíz es suficiente.

> **No subas nunca el `.env` a GitHub.** Ya está en el `.gitignore`. Una clave publicada es
> una clave comprometida: si se te escapa, revócala y genera otra.

Para cada demo:

```bash
cd instrumentos             # o twitch, o asistente-voz
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

## 1. ¿Qué instrumentos suenan?

Escribes el nombre de una canción y el script:

1. Busca la canción en la **API de Deezer** (sin clave) y descarga el fragmento de 30 s.
2. Calcula el **espectrograma de Mel** con `librosa`.
3. Se lo pasa al modelo [**AST** de Hugging Face](https://huggingface.co/MIT/ast-finetuned-audioset-10-10-0.4593),
   entrenado con AudioSet, que reconoce instrumentos y voces. Se ejecuta en local, en CPU.
4. Si hay credenciales, pide a la **API de Spotify** la foto y los géneros del artista.

El resultado es una figura con la portada, el espectrograma y los instrumentos detectados.

```bash
python instrumentos.py "Vetusta Morla Copenhague"
python instrumentos.py                                     # modo interactivo
python instrumentos.py --precache "canción 1" "canción 2"  # deja preparadas varias canciones
python instrumentos.py --offline "canción 1"               # sin conexión, desde la caché
```

La primera ejecución descarga el modelo (~350 MB). Todo lo que se baja se guarda en
`instrumentos/cache/`, de modo que con `--precache` la demo funciona aunque falle la wifi.

**Credenciales (opcional):** crea una app en el
[panel de desarrolladores de Spotify](https://developer.spotify.com/dashboard) y copia el
*Client ID* y el *Client Secret* en `SPOTIFY_ID` y `SPOTIFY_SECRET`.

> Desde febrero de 2026 el modo desarrollo de Spotify exige que el dueño de la app tenga
> Premium y limita la búsqueda. Si Spotify responde con error, el script sigue sin él.

## 2. ¿Qué se está viendo ahora en Twitch?

Muestra los ocho directos con más espectadores en este momento, con su miniatura en vivo, la
foto del streamer y el número de espectadores.

1. Canjea *Client ID* + *Secret* por un token de aplicación (OAuth 2.0, *client credentials*).
2. Pide los directos a `/helix/streams`, filtrando por idioma o por juego.
3. Completa las fotos de perfil con `/helix/users`.

```bash
python directos_twitch.py                      # top 8 en español
python directos_twitch.py --idioma en          # en inglés
python directos_twitch.py --juego "Minecraft"  # de un juego, en cualquier idioma
python directos_twitch.py --cada 30            # se actualiza solo cada 30 s
```

Con `--cada` se ve el patrón de **polling**: la fuente no avisa, así que el cliente pregunta
cada N segundos.

**Credenciales:** registra una aplicación en la [consola de Twitch](https://dev.twitch.tv/console)
(como *OAuth Redirect URL* vale `http://localhost`) y copia los valores en `TWITCH_ID` y
`TWITCH_SECRET`.

## 3. Asistente de voz

Un asistente con el que se habla de verdad, montado con tres piezas:

| Pieza | Qué hace | Con qué |
|---|---|---|
| Oído | voz → texto | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), en local y gratis |
| Cerebro | texto → respuesta, recordando la conversación | API de Claude o de Gemini |
| Boca | texto → voz | edge-tts (voces neuronales), Gemini TTS o la voz del sistema |

```bash
python asistente_voz.py                                  # asistente genérico
python asistente_voz.py --personaje abuelo               # un abuelo salmantino
python asistente_voz.py --personaje abuelo --texto       # escribiendo, sin micrófono
python asistente_voz.py --personaje abuelo --cerebro gemini --voz gemini
python asistente_voz.py --modelo small                   # Whisper más preciso (y más lento)
```

En modo voz, pulsa Enter para empezar a hablar y otra vez Enter para terminar. Para salir,
di «adiós» o pulsa Ctrl+C.

Para inventarte tu propio personaje, crea un `personaje.txt` junto al script con su
descripción; se usa en lugar del que venga por defecto.

**Credenciales:** basta con la del cerebro que uses.
`ANTHROPIC_API_KEY` en [console.anthropic.com](https://console.anthropic.com/) o
`GEMINI_API_KEY` en [aistudio.google.com](https://aistudio.google.com/).

Los modelos se pueden cambiar desde el `.env` (`CLAUDE_MODEL`, `GEMINI_MODEL`,
`GEMINI_TTS_MODEL`) sin tocar el código.

> Hay una diferencia interesante entre las dos APIs: con Claude es tu programa el que guarda
> el historial y lo reenvía en cada llamada; con la Interactions API de Gemini lo guarda el
> servidor y solo pasas el id de la interacción anterior.

## Lo que se cuenta en el seminario

Las [diapositivas](docs/seminario-apis.pdf) recorren seis bloques:

1. **Fundamentos.** Qué es una API, estilos (REST, GraphQL, gRPC, SOAP, WebSocket, webhooks),
   verbos HTTP, códigos de estado, autenticación y patrones de tiempo real.
2. **Catálogo.** Redes sociales, música, IA, mapas y movilidad, datos públicos, producto y
   APIs para practicar.
3. **Integración.** Adaptadores para no atarte a un proveedor, arquitectura de referencia,
   claves fuera del *front*, caché, límites, *timeouts* y uso responsable.
4. **Caso práctico.** Combinar ortofoto del PNOA, un modelo de visión y el Catastro.
5. **Tu propia API.** OpenAPI, documentación interactiva, *mocks*, *tool calling* y MCP.
6. **Manos a la obra.** Las demos de este repositorio.

### APIs para practicar sin registrarte

| API | Qué tiene |
|---|---|
| [PokéAPI](https://pokeapi.co) | Pokémon, tipos y movimientos |
| [JSONPlaceholder](https://jsonplaceholder.typicode.com) | API falsa para probar GET, POST, PUT y DELETE |
| [REST Countries](https://restcountries.com) | Países, banderas, monedas e idiomas |
| [Rick and Morty API](https://rickandmortyapi.com) | Personajes y episodios, en REST y GraphQL |
| [Open Trivia DB](https://opentdb.com) | Preguntas de trivial |
| [Dog CEO](https://dog.ceo/dog-api) | Fotos de perros por raza |
| [Open-Meteo](https://open-meteo.com) | Previsión e histórico meteorológico |
| [REE apidatos](https://www.ree.es/es/apidatos) | Precio de la electricidad por horas |

Un primer contacto desde la terminal:

```bash
curl -s https://pokeapi.co/api/v2/pokemon/pikachu | jq '.types[].type.name'
```

## Problemas frecuentes

- **`ModuleNotFoundError`**: el entorno virtual no está activado o falta el
  `pip install -r requirements.txt` en esa carpeta.
- **Spotify devuelve 403**: revisa las condiciones del modo desarrollo de Spotify. La demo de
  instrumentos funciona igualmente sin Spotify.
- **`sounddevice` no encuentra el micrófono** (asistente): prueba con `--texto` para descartar
  el resto, y comprueba los permisos de micrófono del sistema.
- **No se oye nada con edge-tts**: necesita internet. Sin conexión el asistente pasa solo a la
  voz del sistema.
- **La primera ejecución tarda mucho**: se están descargando los modelos (AST o Whisper). Solo
  ocurre una vez.

## Licencia

- El **código** se distribuye bajo licencia [MIT](LICENSE): puedes usarlo, modificarlo y
  redistribuirlo libremente manteniendo el aviso de copyright con el nombre del autor.
- Las **diapositivas y la documentación** se publican bajo
  [CC BY 4.0](docs/LICENSE.md): puedes reutilizarlas y adaptarlas citando siempre la autoría.

Si usas este material en una clase, un taller o un trabajo, cítalo así (también puedes usar
el botón *Cite this repository* de GitHub, que lee el [`CITATION.cff`](CITATION.cff)):

> García González, S. (2026). *De la teoría a la práctica: conecta tu app con datos abiertos
> y APIs en tiempo real*. Universidad de Salamanca, ESALab.
> https://github.com/anordinaryusser/seminario-api

Cada servicio externo (Spotify, Deezer, Twitch, Anthropic, Google…) tiene sus propios
términos de uso. Léelos antes de publicar o monetizar algo construido sobre ellos.

## Autor

**Sergio García González**
Departamento de Informática y Automática · Expert Systems and Applications Laboratory (ESALab)
Facultad de Ciencias, Universidad de Salamanca

[![Email](https://img.shields.io/badge/sergio.gg@usal.es-D14836?logo=gmail&logoColor=white)](mailto:sergio.gg@usal.es)
[![X](https://img.shields.io/badge/@Sergiiio____-000000?logo=x&logoColor=white)](https://x.com/Sergiiio__)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-sergiiiogarciagonzalez-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/sergiiiogarciagonzalez/)
