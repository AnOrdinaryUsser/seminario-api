"""
Asistente de voz en tres piezas:

  oído     Whisper (faster-whisper, local)       voz -> texto
  cerebro  API de Claude o de Gemini             texto -> respuesta (con memoria)
  boca     edge-tts, Gemini TTS o voz del sistema texto -> voz

    python asistente_voz.py
    python asistente_voz.py --personaje abuelo
    python asistente_voz.py --personaje abuelo --texto            # sin micrófono
    python asistente_voz.py --personaje abuelo --cerebro gemini --voz gemini

Si hay un personaje.txt junto al script se usa como prompt del personaje.
Para salir: "adiós" o Ctrl+C.
"""
import argparse
import asyncio
import io
import os
import sys
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

SR = 16000
MODELO_CLAUDE = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
MODELO_GEMINI_TTS = os.getenv("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")

FORMATO_VOZ = (" Responde siempre en español y como si hablaras: dos o tres frases como mucho, "
               "sin listas, sin emojis y sin formato, porque la respuesta se va a leer en voz alta.")

PERSONAJES = {
    "asistente": {
        "sistema": "Eres un asistente de voz en un seminario sobre APIs de la Universidad de "
                   "Salamanca. Eres cercano y breve." + FORMATO_VOZ,
        "saludo": "Hola, soy el asistente del seminario. Pregúntame lo que quieras.",
        "despedida": "¡Hasta luego! Gracias por venir.",
    },
    "abuelo": {
        "sistema": "Eres un abuelo de unos ochenta años de un pueblo de Salamanca, cariñoso y con "
                   "mucha retranca. Hablas despacio, llamas a tu interlocutor «hijo» o «majo», sueltas "
                   "algún refrán y te encanta contar batallitas de cuando eras joven: el campo, la mili, "
                   "las fiestas del pueblo. Te interesas por cómo le va al otro, le preguntas si come "
                   "bien y le das consejos. Las cosas modernas como las APIs o los móviles te hacen "
                   "gracia y no las terminas de entender, pero preguntas con curiosidad." + FORMATO_VOZ,
        "saludo": "¡Hombre, hijo! Qué alegría oírte. Anda, siéntate y cuéntame, ¿cómo te va todo?",
        "despedida": "¡Hasta luego, majo! Cuídate mucho.",
    },
}

# voz, velocidad y tono para edge-tts
VOCES_EDGE = {"asistente": ("es-ES-ElviraNeural", "+0%", "+0Hz"),
              "abuelo": ("es-ES-AlvaroNeural", "-12%", "-8Hz")}

# Gemini TTS acepta instrucciones de estilo en lenguaje natural
VOCES_GEMINI = {
    "asistente": ("Kore", "Léelo con tono amable, claro y natural, como en una conversación"),
    "abuelo": ("Algenib", "Léelo como un abuelo castellano de ochenta años: voz cálida, pausada, "
                          "algo ronca y muy cariñosa, sonriendo al hablar"),
}


def cargar_personaje(nombre):
    p = dict(PERSONAJES[nombre])
    propio = Path(__file__).resolve().parent / "personaje.txt"
    if propio.is_file() and propio.read_text(encoding="utf-8").strip():
        p["sistema"] = propio.read_text(encoding="utf-8").strip() + FORMATO_VOZ
        print("Personaje cargado de personaje.txt")
    return p


# --- oído -------------------------------------------------------------------------------
def grabar():
    input("\n[Enter] para hablar ")
    trozos = []
    with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                        callback=lambda datos, *_: trozos.append(datos.copy())):
        input("Grabando... [Enter] para terminar ")
    return np.concatenate(trozos)[:, 0] if trozos else np.zeros(1, dtype="float32")


def transcribir(whisper, audio):
    t0 = time.time()
    segmentos, _ = whisper.transcribe(audio, language="es", vad_filter=True)
    texto = " ".join(s.text.strip() for s in segmentos).strip()
    print(f"Tú ({time.time() - t0:.1f} s): {texto or '(no se ha entendido)'}")
    return texto


# --- cerebro ----------------------------------------------------------------------------
class CerebroClaude:
    """Con la API de Anthropic el historial lo guarda el cliente y se reenvía en cada llamada."""

    def __init__(self, sistema, saludo):
        import anthropic
        self.cliente = anthropic.Anthropic()
        self.sistema = sistema
        self.historial = [{"role": "user", "content": "(empieza la conversación)"},
                          {"role": "assistant", "content": saludo}]

    def responder(self, texto):
        self.historial.append({"role": "user", "content": texto})
        t0 = time.time()
        r = self.cliente.messages.create(model=MODELO_CLAUDE, max_tokens=200, system=self.sistema,
                                         messages=self.historial)
        respuesta = "".join(b.text for b in r.content if b.type == "text").strip()
        self.historial.append({"role": "assistant", "content": respuesta})
        print(f"Respuesta ({time.time() - t0:.1f} s, Claude): {respuesta}")
        return respuesta


class CerebroGemini:
    """Con la Interactions API de Gemini el historial lo guarda el servidor; basta con el id anterior."""

    def __init__(self, sistema, saludo):
        from google import genai
        self.cliente = genai.Client()
        self.sistema = sistema
        self.anterior = None
        self.contexto = f"(Ya me has saludado diciendo: «{saludo}»)\n"

    def responder(self, texto):
        t0 = time.time()
        extra = {"previous_interaction_id": self.anterior} if self.anterior else {}
        entrada = texto if self.anterior else self.contexto + texto
        r = self.cliente.interactions.create(model=MODELO_GEMINI, system_instruction=self.sistema,
                                             input=entrada, **extra)
        self.anterior = r.id
        respuesta = (r.output_text or "").strip()
        print(f"Respuesta ({time.time() - t0:.1f} s, Gemini): {respuesta}")
        return respuesta


# --- boca -------------------------------------------------------------------------------
class Voz:
    """Prueba el motor elegido y, si falla, baja al siguiente: gemini -> edge -> sistema."""

    def __init__(self, motor, personaje):
        self.motor = motor
        self.personaje = personaje
        self._gemini = None

    def hablar(self, texto):
        if self.motor == "gemini":
            try:
                return self._gemini_tts(texto)
            except Exception as e:
                print(f"(Gemini TTS no disponible: {e}; paso a edge-tts)")
                self.motor = "edge"
        if self.motor == "edge":
            try:
                return self._edge(texto)
            except Exception as e:
                print(f"(edge-tts no disponible: {e.__class__.__name__}; paso a la voz del sistema)")
                self.motor = "sistema"
        self._sistema(texto)

    def _edge(self, texto):
        import edge_tts
        import soundfile as sf

        voz, ritmo, tono = VOCES_EDGE[self.personaje]

        async def generar():
            buf = io.BytesIO()
            async for trozo in edge_tts.Communicate(texto, voz, rate=ritmo, pitch=tono).stream():
                if trozo["type"] == "audio":
                    buf.write(trozo["data"])
            return buf.getvalue()

        datos, sr = sf.read(io.BytesIO(asyncio.run(generar())), dtype="float32")
        sd.play(datos, sr)
        sd.wait()

    def _gemini_tts(self, texto):
        from google import genai
        from google.genai import types

        if self._gemini is None:
            self._gemini = genai.Client()
        voz, estilo = VOCES_GEMINI[self.personaje]
        r = self._gemini.models.generate_content(
            model=MODELO_GEMINI_TTS,
            contents=f"{estilo}: {texto}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voz)))))
        pcm = r.candidates[0].content.parts[0].inline_data.data  # PCM 16 bits, 24 kHz, mono
        sd.play(np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768, 24000)
        sd.wait()

    def _sistema(self, texto):
        import pyttsx3

        motor = pyttsx3.init()  # nuevo en cada frase; si se reutiliza, en Windows se queda mudo
        for v in motor.getProperty("voices"):
            nombre = f"{v.name} {getattr(v, 'languages', '')}".lower()
            if any(x in nombre for x in ("spanish", "español", "es-es", "helena", "laura", "pablo")):
                motor.setProperty("voice", v.id)
                break
        motor.setProperty("rate", 150 if self.personaje == "abuelo" else 175)
        motor.say(texto)
        motor.runAndWait()
        motor.stop()


def main():
    ap = argparse.ArgumentParser(description="Asistente de voz: Whisper + LLM + TTS")
    ap.add_argument("--modelo", default="base", help="tamaño de Whisper: tiny, base, small, medium")
    ap.add_argument("--personaje", default="asistente", choices=list(PERSONAJES))
    ap.add_argument("--texto", action="store_true", help="escribir en lugar de hablar")
    ap.add_argument("--cerebro", default="claude", choices=["claude", "gemini"])
    ap.add_argument("--voz", default="edge", choices=["edge", "gemini", "sistema"])
    args = ap.parse_args()

    claves = {"claude": ("ANTHROPIC_API_KEY", "console.anthropic.com"),
              "gemini": ("GEMINI_API_KEY", "aistudio.google.com")}
    variable, web = claves[args.cerebro]
    if not os.getenv(variable):
        sys.exit(f"Falta {variable} en el .env (se consigue en {web})")
    if args.voz == "gemini" and not os.getenv("GEMINI_API_KEY"):
        sys.exit("Para --voz gemini hace falta GEMINI_API_KEY en el .env")

    per = cargar_personaje(args.personaje)

    whisper = None
    if not args.texto:
        print(f"Cargando Whisper '{args.modelo}' (la primera vez se descarga)...")
        from faster_whisper import WhisperModel
        whisper = WhisperModel(args.modelo, device="cpu", compute_type="int8")

    Cerebro = CerebroGemini if args.cerebro == "gemini" else CerebroClaude
    cerebro = Cerebro(per["sistema"], per["saludo"])
    voz = Voz(args.voz, args.personaje)
    print(f"Cerebro: {args.cerebro} | voz: {args.voz}")

    nombre = args.personaje.capitalize()
    print(f"\n{nombre}: {per['saludo']}")
    voz.hablar(per["saludo"])

    try:
        while True:
            texto = input("\nTú: ").strip() if args.texto else transcribir(whisper, grabar())
            if not texto:
                continue
            if any(p in texto.lower() for p in ("adiós", "adios", "hasta luego")):
                print(f"{nombre}: {per['despedida']}")
                voz.hablar(per["despedida"])
                break
            voz.hablar(cerebro.responder(texto))
    except KeyboardInterrupt:
        print("\nFin.")


if __name__ == "__main__":
    main()
