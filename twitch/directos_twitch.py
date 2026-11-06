"""
¿Qué se está viendo ahora en Twitch?

Token de aplicación (OAuth client credentials) + /helix/streams + /helix/users
+ miniaturas en vivo de cada directo.

    python directos_twitch.py                       # top 8 en español
    python directos_twitch.py --idioma en
    python directos_twitch.py --juego "Minecraft"
    python directos_twitch.py --cada 30             # refresca cada 30 s (polling)
"""
import argparse
import io
import os
import sys
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import requests
from dotenv import find_dotenv, load_dotenv
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec
from PIL import Image, ImageDraw

load_dotenv(find_dotenv(usecwd=True))

API = "https://api.twitch.tv/helix"
TIMEOUT = 15
SALIDA = Path(__file__).resolve().parent / "resultado.png"

MORADO, AZUL, ROJO, TINTA, GRIS, FONDO = "#9146FF", "#3A5E9C", "#D21F26", "#2B2D31", "#5E6470", "#FFFFFF"

IDIOMAS = {"es": "español", "en": "inglés", "pt": "portugués", "fr": "francés", "de": "alemán",
           "it": "italiano", "ja": "japonés", "ko": "coreano", "ru": "ruso"}


def cabeceras_twitch():
    cid, secret = os.getenv("TWITCH_ID"), os.getenv("TWITCH_SECRET")
    if not (cid and secret):
        sys.exit("Faltan TWITCH_ID y TWITCH_SECRET en el .env (se crean en dev.twitch.tv/console)")
    r = requests.post("https://id.twitch.tv/oauth2/token", timeout=TIMEOUT,
                      params={"client_id": cid, "client_secret": secret,
                              "grant_type": "client_credentials"})
    if r.status_code != 200:
        sys.exit(f"Twitch ha rechazado las credenciales ({r.status_code}): {r.text}")
    return {"Client-Id": cid, "Authorization": f"Bearer {r.json()['access_token']}"}


def get(cabeceras, ruta, **params):
    r = requests.get(f"{API}/{ruta}", headers=cabeceras, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("data", [])


def nombre_idioma(codigo):
    return f"en {IDIOMAS.get(codigo, codigo.upper())}"


def directos(cabeceras, idioma=None, juego=None, top=8):
    params = {"first": top}
    titulo = nombre_idioma(idioma) if idioma else "en todos los idiomas"
    if juego:
        juegos = get(cabeceras, "games", name=juego)
        if not juegos:
            sys.exit(f"Twitch no encuentra el juego '{juego}'. Usa el nombre exacto que aparece en Twitch.")
        params["game_id"] = juegos[0]["id"]
        titulo = f"de {juegos[0]['name']}"
        if idioma:
            titulo += " " + nombre_idioma(idioma)
    if idioma:
        params["language"] = idioma

    lista = get(cabeceras, "streams", **params)
    if lista:
        usuarios = get(cabeceras, "users", id=[s["user_id"] for s in lista])
        fotos = {u["id"]: u.get("profile_image_url") for u in usuarios}
        for s in lista:
            s["foto"] = fotos.get(s["user_id"])
    return lista, titulo


def descargar_imagen(url):
    if not url:
        return None
    try:
        return Image.open(io.BytesIO(requests.get(url, timeout=TIMEOUT).content)).convert("RGB")
    except Exception:
        return None


def recorte_circular(img, lado=200):
    img = img.convert("RGBA").resize((lado, lado))
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, lado, lado), fill=255)
    img.putalpha(mascara)
    return img


def miles(n):
    return f"{n:,}".replace(",", ".")


def dibujar(lista, titulo, fig=None):
    plt.rcParams.update({"font.family": "DejaVu Sans"})
    if fig is None:
        fig = plt.figure(figsize=(16, 9), facecolor=FONDO)
    fig.clf()
    fig.set_facecolor(FONDO)
    gs = GridSpec(3, 4, figure=fig, height_ratios=[0.42, 1, 1], left=0.04, right=0.96,
                  top=0.95, bottom=0.07, hspace=0.18, wspace=0.12)

    cab = fig.add_subplot(gs[0, :])
    cab.axis("off")
    cab.text(0, 0.80, "TWITCH API · EN DIRECTO", color=MORADO, fontsize=14, fontweight="bold",
             transform=cab.transAxes)
    cab.text(0, 0.30, f"¿Qué se está viendo ahora {titulo}?", color=TINTA, fontsize=30,
             fontweight="bold", transform=cab.transAxes)
    total = sum(s["viewer_count"] for s in lista)
    cab.text(1, 0.62, miles(total), color=AZUL, fontsize=30, fontweight="bold", ha="right",
             transform=cab.transAxes)
    cab.text(1, 0.32, f"espectadores en estos {len(lista)} directos", color=GRIS, fontsize=12,
             ha="right", transform=cab.transAxes)
    cab.text(1, 0.08, "actualizado a las " + datetime.now().strftime("%H:%M:%S"), color=GRIS,
             fontsize=11, ha="right", transform=cab.transAxes)

    if not lista:
        cab.text(0, -1.5, "No hay directos con ese filtro ahora mismo.", fontsize=18, color=GRIS,
                 transform=cab.transAxes)
        return fig

    tope = max(s["viewer_count"] for s in lista)
    for i, s in enumerate(lista[:8]):
        celda = GridSpecFromSubplotSpec(2, 1, subplot_spec=gs[1 + i // 4, i % 4],
                                        height_ratios=[2.2, 1], hspace=0.06)
        color = ROJO if i == 0 else AZUL

        ax = fig.add_subplot(celda[0])
        ax.axis("off")
        mini = descargar_imagen(s["thumbnail_url"].replace("{width}", "640").replace("{height}", "360"))
        if mini is not None:
            ax.imshow(mini)
        ax.set_title(f"#{i + 1}", loc="left", fontsize=12, color=ROJO if i == 0 else GRIS,
                     fontweight="bold", pad=3)
        ax.text(0.02, 0.92, " ● EN DIRECTO ", transform=ax.transAxes, fontsize=9, color="white",
                fontweight="bold", va="top", bbox=dict(boxstyle="round,pad=0.25", fc=ROJO, ec="none"))
        foto = descargar_imagen(s.get("foto"))
        if foto is not None:
            fig.canvas.draw()
            bb = ax.get_window_extent()
            alto = 0.34
            ancho = alto * bb.height / bb.width  # para que el recorte quede redondo y no ovalado
            ins = ax.inset_axes([0.97 - ancho, 0.04, ancho, alto])
            ins.imshow(recorte_circular(foto))
            ins.axis("off")

        ax = fig.add_subplot(celda[1])
        ax.axis("off")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(0, 0.78, s["user_name"], fontsize=14, fontweight="bold", color=TINTA)
        ax.text(0, 0.48, (s.get("game_name") or "Sin categoría")[:34], fontsize=11, color=MORADO)
        ax.add_patch(plt.Rectangle((0, 0.08), 0.72, 0.16, color="#ECEFF4"))
        ax.add_patch(plt.Rectangle((0, 0.08), 0.72 * s["viewer_count"] / tope, 0.16, color=color))
        ax.text(0.75, 0.16, miles(s["viewer_count"]), fontsize=12, fontweight="bold", color=TINTA,
                va="center")

    fig.text(0.04, 0.02, "OAuth: token  |  /helix/streams: directos  |  /helix/users: fotos  |  "
             "thumbnail_url: captura en vivo", fontsize=10.5, color=GRIS)
    return fig


def main():
    ap = argparse.ArgumentParser(description="¿Qué se está viendo ahora en Twitch?")
    ap.add_argument("--idioma", help="código de idioma: es, en, pt... (por defecto es, salvo con --juego)")
    ap.add_argument("--juego", help="nombre del juego tal y como aparece en Twitch")
    ap.add_argument("--top", type=int, default=8, help="número de directos (máximo 8)")
    ap.add_argument("--cada", type=int, default=0, help="segundos entre actualizaciones (0 = una vez)")
    args = ap.parse_args()
    idioma = args.idioma if (args.idioma or args.juego) else "es"
    top = min(args.top, 8)

    cab = cabeceras_twitch()
    lista, titulo = directos(cab, idioma, args.juego, top)
    for i, s in enumerate(lista, 1):
        print(f"{i:>2}. {s['user_name']:<20} {miles(s['viewer_count']):>9}  {s.get('game_name', '')}")

    fig = dibujar(lista, titulo)
    fig.savefig(SALIDA, dpi=150, facecolor=FONDO)
    try:
        plt.get_current_fig_manager().full_screen_toggle()
    except Exception:
        pass

    if args.cada <= 0:
        plt.show()
        return

    print(f"Actualizando cada {args.cada} s. Cierra la ventana para salir.")
    plt.ion()
    plt.show()
    while plt.fignum_exists(fig.number):
        plt.pause(args.cada)
        if not plt.fignum_exists(fig.number):
            break
        try:
            lista, titulo = directos(cab, idioma, args.juego, top)
            dibujar(lista, titulo, fig)
            fig.canvas.draw_idle()
            print("Actualizado", datetime.now().strftime("%H:%M:%S"))
        except Exception as e:
            print(f"No se ha podido actualizar ({e}), reintento en la siguiente vuelta")


if __name__ == "__main__":
    main()
