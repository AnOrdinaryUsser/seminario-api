"""
¿Qué instrumentos suenan en una canción?

Deezer (fragmento de 30 s) + librosa (espectrograma) + modelo AST de Hugging Face
(reconoce instrumentos) + Spotify (foto y géneros del artista, opcional).

    python instrumentos.py "Vetusta Morla Copenhague"
    python instrumentos.py                       # modo interactivo
    python instrumentos.py --precache "c1" "c2"  # descarga y analiza para usar sin red
    python instrumentos.py --offline "c1"        # solo caché
"""
import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
import requests
from dotenv import find_dotenv, load_dotenv
from matplotlib.gridspec import GridSpec
from PIL import Image, ImageDraw

load_dotenv(find_dotenv(usecwd=True))

CACHE = Path(__file__).resolve().parent / "cache"
SR = 16000
MODELO = os.getenv("AST_MODEL", "MIT/ast-finetuned-audioset-10-10-0.4593")
VENTANA_S, SALTO_S = 10.0, 5.0  # AST se entrenó con clips de 10 s
TIMEOUT = 15

AZUL, ROJO, TINTA, GRIS, FONDO = "#3A5E9C", "#D21F26", "#2B2D31", "#5E6470", "#FFFFFF"

# etiqueta de AudioSet -> nombre en español
INSTRUMENTOS = {
    "Guitar": "Guitarra", "Electric guitar": "Guitarra eléctrica", "Acoustic guitar": "Guitarra acústica",
    "Bass guitar": "Bajo", "Steel guitar, slide guitar": "Guitarra slide",
    "Plucked string instrument": "Cuerda pulsada", "Strum": "Rasgueo", "Drum kit": "Batería",
    "Drum": "Tambor", "Snare drum": "Caja", "Bass drum": "Bombo", "Cymbal": "Platillos",
    "Hi-hat": "Charles", "Drum roll": "Redoble", "Drum machine": "Caja de ritmos",
    "Percussion": "Percusión", "Tambourine": "Pandereta", "Piano": "Piano",
    "Electric piano": "Piano eléctrico", "Keyboard (musical)": "Teclado", "Synthesizer": "Sintetizador",
    "Organ": "Órgano", "Hammond organ": "Órgano Hammond", "Electronic organ": "Órgano electrónico",
    "Harpsichord": "Clavecín", "Violin, fiddle": "Violín", "Cello": "Violonchelo",
    "Double bass": "Contrabajo", "Bowed string instrument": "Cuerda frotada",
    "String section": "Sección de cuerdas", "Orchestra": "Orquesta", "Trumpet": "Trompeta",
    "Trombone": "Trombón", "French horn": "Trompa", "Tuba": "Tuba", "Saxophone": "Saxofón",
    "Brass instrument": "Metales", "Flute": "Flauta", "Clarinet": "Clarinete", "Oboe": "Oboe",
    "Bassoon": "Fagot", "Wind instrument, woodwind instrument": "Viento madera",
    "Harmonica": "Armónica", "Accordion": "Acordeón", "Ukulele": "Ukelele", "Banjo": "Banjo",
    "Mandolin": "Mandolina", "Harp": "Arpa", "Sitar": "Sitar", "Zither": "Cítara",
    "Bagpipes": "Gaita", "Didgeridoo": "Didgeridoo", "Marimba, xylophone": "Marimba",
    "Glockenspiel": "Glockenspiel", "Vibraphone": "Vibráfono", "Timpani": "Timbales",
    "Tabla": "Tabla", "Bell": "Campana", "Cowbell": "Cencerro", "Shaker": "Shaker",
    "Bongo": "Bongó", "Conga": "Conga", "Maraca": "Maracas", "Gong": "Gong",
    "Steelpan": "Steelpan", "Theremin": "Theremín", "Scratching (performance technique)": "Scratch",
    "Singing": "Canto", "Male singing": "Voz masculina", "Female singing": "Voz femenina",
    "Choir": "Coro", "Rapping": "Rap", "Humming": "Tarareo", "Whistling": "Silbido",
    "Clapping": "Palmas",
}

GENEROS = {
    "Electronic music": "Música electrónica", "Rock music": "Rock", "Pop music": "Pop",
    "Hip hop music": "Hip hop", "Jazz": "Jazz", "Classical music": "Música clásica",
    "Flamenco": "Flamenco", "Techno": "Techno", "House music": "House", "Heavy metal": "Heavy metal",
    "Punk rock": "Punk", "Independent music": "Indie", "Rock and roll": "Rock and roll",
    "Reggae": "Reggae", "Blues": "Blues", "Funk": "Funk", "Soul music": "Soul", "Country": "Country",
    "Folk music": "Folk", "Salsa music": "Salsa", "Music of Latin America": "Música latina",
    "Dance music": "Música de baile", "Ambient music": "Ambient", "Electronica": "Electrónica",
    "Dubstep": "Dubstep", "Drum and bass": "Drum and bass", "Vocal music": "Música vocal",
}


def es(etiqueta):
    return INSTRUMENTOS.get(etiqueta) or GENEROS.get(etiqueta) or etiqueta


def slug(texto):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:60] or "cancion"


def descargar(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


# --- Deezer: búsqueda sin clave, devuelve un preview de 30 s ---------------------------
def buscar_deezer(consulta):
    r = requests.get("https://api.deezer.com/search", params={"q": consulta}, timeout=TIMEOUT)
    r.raise_for_status()
    for pista in r.json().get("data", []):
        if pista.get("preview"):
            return {
                "consulta": consulta,
                "titulo": pista["title"],
                "artista": pista["artist"]["name"],
                "album": pista["album"]["title"],
                "portada": pista["album"].get("cover_xl") or pista["album"].get("cover_big"),
                "preview": pista["preview"],
            }
    raise LookupError(f"Deezer no tiene fragmento para '{consulta}'")


# --- Spotify: client credentials, opcional ---------------------------------------------
def buscar_artista_spotify(nombre):
    cid, secret = os.getenv("SPOTIFY_ID"), os.getenv("SPOTIFY_SECRET")
    if not (cid and secret):
        return None
    try:
        r = requests.post("https://accounts.spotify.com/api/token", timeout=TIMEOUT,
                          data={"grant_type": "client_credentials"}, auth=(cid, secret))
        r.raise_for_status()
        token = r.json()["access_token"]
        r = requests.get("https://api.spotify.com/v1/search", timeout=TIMEOUT,
                         params={"q": nombre, "type": "artist", "limit": 1},
                         headers={"Authorization": f"Bearer {token}"})
        r.raise_for_status()
        items = r.json()["artists"]["items"]
    except Exception as e:  # p. ej. 403 si la app no cumple los requisitos de Spotify
        print(f"  Spotify no disponible ({e.__class__.__name__}), continúo sin él")
        return None
    if not items:
        return None
    a = items[0]
    return {
        "nombre": a.get("name"),
        "generos": a.get("genres") or [],
        "seguidores": (a.get("followers") or {}).get("total"),
        "popularidad": a.get("popularity"),
        "foto": (a.get("images") or [{}])[0].get("url"),
    }


# --- caché ------------------------------------------------------------------------------
def obtener_cancion(consulta, offline=False):
    carpeta = CACHE / slug(consulta)
    if not offline:
        try:
            print("  Deezer: buscando la canción...")
            meta = buscar_deezer(consulta)
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "preview.mp3").write_bytes(descargar(meta["preview"]))
            if meta.get("portada"):
                (carpeta / "portada.jpg").write_bytes(descargar(meta["portada"]))
            print("  Spotify: datos del artista...")
            sp = buscar_artista_spotify(meta["artista"])
            if sp and sp.get("foto"):
                try:
                    (carpeta / "artista.jpg").write_bytes(descargar(sp["foto"]))
                except requests.RequestException:
                    pass
            datos = {"meta": meta, "spotify": sp}
            (carpeta / "meta.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        except Exception as e:
            print(f"  Sin conexión o sin resultados ({e}); uso la caché")
            offline = True

    if offline and not (carpeta / "meta.json").exists():
        guardadas = sorted(CACHE.glob("*/meta.json")) if CACHE.exists() else []
        if not guardadas:
            sys.exit('La caché está vacía. Prueba antes con: --precache "canción"')
        carpeta = guardadas[0].parent
        print(f"  Uso la canción guardada '{carpeta.name}'")

    datos = json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))

    def abrir(nombre):
        ruta = carpeta / nombre
        return Image.open(ruta).convert("RGB") if ruta.exists() else None

    return datos["meta"], carpeta / "preview.mp3", abrir("portada.jpg"), abrir("artista.jpg"), datos.get("spotify")


# --- modelo -----------------------------------------------------------------------------
_modelo = None


def cargar_modelo():
    global _modelo
    if _modelo is None:
        from transformers import ASTForAudioClassification, AutoFeatureExtractor
        _modelo = (AutoFeatureExtractor.from_pretrained(MODELO),
                   ASTForAudioClassification.from_pretrained(MODELO).eval())
    return _modelo


def analizar(y):
    """Puntuación de cada etiqueta de AudioSet sobre ventanas de 10 s.

    Es un problema multietiqueta, por eso sigmoide y no softmax.
    """
    import torch

    extractor, red = cargar_modelo()
    vent, salto = int(VENTANA_S * SR), int(SALTO_S * SR)
    inicios = list(range(0, max(1, len(y) - vent + 1), salto)) or [0]
    trozos = [y[i:i + vent] for i in inicios]
    entradas = extractor(trozos, sampling_rate=SR, return_tensors="pt")
    with torch.no_grad():
        probs = torch.sigmoid(red(**entradas).logits).numpy()
    etiquetas = [red.config.id2label[i] for i in range(probs.shape[1])]
    puntuacion = 0.5 * probs.max(axis=0) + 0.5 * probs.mean(axis=0)
    return etiquetas, puntuacion


# --- figura -----------------------------------------------------------------------------
def recorte_circular(img, lado=600):
    img = img.convert("RGBA")
    m = min(img.size)
    img = img.crop(((img.width - m) // 2, (img.height - m) // 2,
                    (img.width + m) // 2, (img.height + m) // 2)).resize((lado, lado))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, lado, lado), fill=255)
    img.putalpha(mascara)
    return img


def mostrar_imagen(ax, img, redonda=False):
    ax.axis("off")
    if img is not None:
        ax.imshow(recorte_circular(img) if redonda else img)
    ax.set_aspect("equal")


def dibujar(meta, y, etiquetas, puntuacion, portada, foto, sp, salida=None):
    plt.rcParams.update({"font.family": "DejaVu Sans", "axes.edgecolor": "#DDE3EB",
                         "axes.labelcolor": GRIS, "xtick.color": GRIS, "ytick.color": GRIS})
    fig = plt.figure(figsize=(16, 9), facecolor=FONDO)
    gs = GridSpec(2, 4, figure=fig, height_ratios=[1, 1.7], width_ratios=[1, 1.2, 1.2, 1.1],
                  left=0.06, right=0.97, top=0.94, bottom=0.11, hspace=0.32, wspace=0.25)

    orden = np.argsort(puntuacion)[::-1]
    instr = [k for k in orden if etiquetas[k] in INSTRUMENTOS and puntuacion[k] >= 0.03][:8]
    if len(instr) < 5:
        instr = [k for k in orden if etiquetas[k] in INSTRUMENTOS][:5]
    generos = [GENEROS[etiquetas[k]] for k in orden if etiquetas[k] in GENEROS][:3]
    if sp and sp.get("generos"):
        generos = sp["generos"][:3]

    # cabecera
    mostrar_imagen(fig.add_subplot(gs[0, 0]), portada)
    ax = fig.add_subplot(gs[0, 1:3])
    ax.axis("off")
    ax.text(0.02, 0.86, "¿QUÉ INSTRUMENTOS SUENAN?", color=ROJO, fontsize=14, fontweight="bold",
            transform=ax.transAxes)
    ax.text(0.02, 0.56, meta["titulo"], color=TINTA, fontsize=34, fontweight="bold", transform=ax.transAxes)
    ax.text(0.02, 0.32, meta["artista"], color=AZUL, fontsize=24, fontweight="bold", transform=ax.transAxes)
    x = 0.02
    for g in generos:
        t = ax.text(x, 0.08, g, fontsize=13, color=AZUL, transform=ax.transAxes,
                    bbox=dict(boxstyle="round,pad=0.5", fc="#E8EEF7", ec="none"))
        fig.canvas.draw()
        x = t.get_window_extent().transformed(ax.transAxes.inverted()).x1 + 0.035
    mostrar_imagen(fig.add_subplot(gs[0, 3]), foto, redonda=True)

    # espectrograma
    ax = fig.add_subplot(gs[1, 0:3])
    S = librosa.power_to_db(librosa.feature.melspectrogram(y=y, sr=SR, n_mels=128, fmax=8000), ref=np.max)
    librosa.display.specshow(S, sr=SR, x_axis="time", y_axis="mel", fmax=8000, ax=ax, cmap="magma")
    ax.set_title("Espectrograma de Mel (la entrada del modelo)", loc="left", color=TINTA,
                 fontsize=15, fontweight="bold")
    ax.set_xlabel("Tiempo (s)")
    ax.set_ylabel("Hz")

    # barras de instrumentos
    ax = fig.add_subplot(gs[1, 3])
    vals = [puntuacion[k] for k in instr]
    tope = max(vals) if vals else 1
    ax.barh(range(len(instr)), vals, color=[ROJO] + [AZUL] * (len(instr) - 1), height=0.38)
    for i, (k, v) in enumerate(zip(instr, vals)):
        ax.text(0, i - 0.42, es(etiquetas[k]), va="bottom", fontsize=14, color=TINTA,
                fontweight="bold" if i == 0 else "normal")
        ax.text(v + tope * 0.03, i, f"{v:.0%}", va="center", fontsize=12, color=TINTA, fontweight="bold")
    ax.set_xlim(0, tope * 1.3)
    ax.set_ylim(len(instr) - 0.5, -0.9)
    ax.set_xticks([])
    ax.set_yticks([])
    for borde in ax.spines.values():
        borde.set_visible(False)
    ax.set_title("Instrumentos detectados", loc="left", color=TINTA, fontsize=15, fontweight="bold")

    fig.text(0.06, 0.015, "Deezer API: fragmento de 30 s  |  librosa: espectrograma  |  "
             "Hugging Face (AST, AudioSet): instrumentos  |  Spotify API: foto y géneros",
             fontsize=10.5, color=GRIS)
    if salida:
        fig.savefig(salida, dpi=150, facecolor=FONDO)
        print(f"  Guardado en {salida}")
    return fig


def procesar(consulta, offline=False, mostrar=True):
    print(f"\n> {consulta}")
    meta, mp3, portada, foto, sp = obtener_cancion(consulta, offline)
    print(f"  {meta['titulo']} - {meta['artista']}")
    print("  librosa: cargando audio...")
    y, _ = librosa.load(mp3, sr=SR, mono=True)
    print("  AST: analizando...")
    etiquetas, puntuacion = analizar(y)
    top = [k for k in np.argsort(puntuacion)[::-1] if etiquetas[k] in INSTRUMENTOS][:5]
    print("  " + ", ".join(f"{es(etiquetas[k])} {puntuacion[k]:.0%}" for k in top))
    dibujar(meta, y, etiquetas, puntuacion, portada, foto, sp, salida=mp3.parent / "resultado.png")
    if mostrar:
        try:
            plt.get_current_fig_manager().full_screen_toggle()
        except Exception:
            pass
        plt.show()
    plt.close("all")


def main():
    ap = argparse.ArgumentParser(description="¿Qué instrumentos suenan en una canción?")
    ap.add_argument("canciones", nargs="*", help='canción o "artista título"')
    ap.add_argument("--offline", action="store_true", help="usar solo la caché")
    ap.add_argument("--precache", action="store_true", help="descargar y analizar sin mostrar")
    args = ap.parse_args()

    if args.precache:
        for c in args.canciones:
            procesar(c, mostrar=False)
        print("\nListo, ya se pueden usar con --offline.")
    elif args.canciones:
        for c in args.canciones:
            procesar(c, offline=args.offline)
    else:
        cargar_modelo()
        print("Escribe una canción (Enter vacío para salir).")
        while c := input("\nCanción: ").strip():
            procesar(c, offline=args.offline)


if __name__ == "__main__":
    main()
