"""Génère les visuels de présentation GitHub pour Cortex Bridge.

- docs/media/hero-banner.png : 1280x640 (taille social preview GitHub)
- docs/media/architecture-flow.png : schéma d'architecture 1600x900
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Wedge
import matplotlib.font_manager as fm

setup_plot()

REPO = Path(__file__).resolve().parent.parent
MEDIA = REPO / "docs" / "media"
MEDIA.mkdir(parents=True, exist_ok=True)

# Palette sombre cohérente avec GitHub dark
BG = "#0d1117"
PANEL = "#161b22"
BORDER = "#30363d"
ACCENT = "#58a6ff"   # bleu GitHub
GREEN = "#3fb950"
ORANGE = "#d29922"
PURPLE = "#bc8cff"
TEXT = "#e6edf3"
MUTED = "#8b949e"

FONT = "Helvetica Neue"


# ---------------------------------------------------------------- banner ---
def hero_banner():
    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)  # exactement 1280x640
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1280)
    ax.set_ylim(0, 640)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1280, 640, color=BG))

    # halo décoratif
    for r, alpha in ((340, 0.05), (260, 0.07), (180, 0.09)):
        ax.add_patch(plt.Circle((1120, 520), r, color=ACCENT, alpha=alpha, lw=0))
    for r, alpha in ((260, 0.04), (180, 0.06)):
        ax.add_patch(plt.Circle((120, 80), r, color=PURPLE, alpha=alpha, lw=0))

    # badge "local-first"
    ax.add_patch(FancyBboxPatch((84, 472), 308, 50, boxstyle="round,pad=6,rounding_size=25",
                                fc=PANEL, ec=GREEN, lw=1.6))
    ax.text(238, 501, "● LOCAL-FIRST · macOS", ha="center", va="center",
            fontsize=18, color=GREEN, fontfamily=FONT, fontweight="bold")

    # titre
    ax.text(80, 390, "Cortex Bridge", fontsize=84, color=TEXT,
            fontfamily=FONT, fontweight="bold", ha="left", va="center")

    # tagline
    ax.text(84, 308, "Connecte ChatGPT (chat classique, Chrome)",
            fontsize=24, color=MUTED, fontfamily=FONT, ha="left", va="center")
    ax.text(84, 268, "à un exécuteur local déterministe —",
            fontsize=24, color=MUTED, fontfamily=FONT, ha="left", va="center")
    ax.text(84, 228, "chaque action validée par un humain, sans clé API OpenAI.",
            fontsize=24, color=MUTED, fontfamily=FONT, ha="left", va="center")

    # chips mots-clés
    chips = [
        ("ChatGPT classic chat", ACCENT),
        ("Chrome extension MV3", PURPLE),
        ("Human-in-the-loop", GREEN),
        ("No API key", ORANGE),
        ("Ollama optional", ACCENT),
    ]
    x = 84
    for label, color in chips:
        w = 22 + len(label) * 11.5
        ax.add_patch(FancyBboxPatch((x, 136), w, 52, boxstyle="round,pad=6,rounding_size=14",
                                    fc=PANEL, ec=color, lw=1.5))
        ax.text(x + w / 2, 166, label, ha="center", va="center",
                fontsize=17.5, color=TEXT, fontfamily=FONT)
        x += w + 18

    # footer
    ax.text(84, 76, "scripts/cortex.sh start  →  127.0.0.1:8420",
            fontsize=19, color=MUTED, fontfamily="Menlo", ha="left", va="center")
    ax.text(1196, 76, "open source · MIT",
            fontsize=16, color=MUTED, fontfamily=FONT, ha="right", va="center")

    fig.savefig(MEDIA / "hero-banner.png")  # pas de bbox_inches="tight" : taille fixe
    plt.close(fig)


# ----------------------------------------------------------- architecture ---
def box(ax, x, y, w, h, title, lines, accent):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=8,rounding_size=16",
                                fc=PANEL, ec=accent, lw=2))
    ax.text(x + w / 2, y + h - 40, title, ha="center", va="center",
            fontsize=21, color=accent, fontfamily=FONT, fontweight="bold")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 88 - i * 34, line, ha="center", va="center",
                fontsize=15.5, color=TEXT, fontfamily=FONT)


def arrow(ax, x1, y1, x2, y2, label="", color=MUTED, dashed=False):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                 mutation_scale=26, lw=2.2, color=color,
                                 linestyle="--" if dashed else "-"))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 24, label, ha="center", va="bottom",
                fontsize=14.5, color=color, fontfamily=FONT, style="italic")


def architecture():
    fig = plt.figure(figsize=(16, 9), dpi=100)  # 1600x900
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1600)
    ax.set_ylim(0, 900)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1600, 900, color=BG))

    ax.text(800, 848, "Cortex Bridge — architecture locale",
            ha="center", va="center", fontsize=34, color=TEXT,
            fontfamily=FONT, fontweight="bold")
    ax.text(800, 800, "Tout tourne sur ta machine · aucune clé API OpenAI · approbation humaine à chaque action",
            ha="center", va="center", fontsize=18, color=MUTED, fontfamily=FONT)

    # Zone Chrome
    ax.add_patch(FancyBboxPatch((60, 420), 560, 320, boxstyle="round,pad=10,rounding_size=20",
                                fc="none", ec=BORDER, lw=1.5, linestyle=":"))
    ax.text(340, 712, "TON CHROME", ha="center", fontsize=15, color=MUTED,
            fontfamily=FONT, fontweight="bold")

    box(ax, 100, 480, 220, 170, "ChatGPT", ["chat classique", "(jamais Work)"], ACCENT)
    box(ax, 360, 480, 220, 170, "Extension MV3", ["handshake pairé", "protocole v2"], PURPLE)

    # Zone locale
    ax.add_patch(FancyBboxPatch((700, 120), 560, 620, boxstyle="round,pad=10,rounding_size=20",
                                fc="none", ec=BORDER, lw=1.5, linestyle=":"))
    ax.text(980, 712, "TA MACHINE (127.0.0.1)", ha="center", fontsize=15, color=MUTED,
            fontfamily=FONT, fontweight="bold")

    box(ax, 740, 480, 220, 170, "Serveur local", ["scripts/cortex.sh", "port 8420"], GREEN)
    box(ax, 1000, 480, 220, 170, "Console UI", ["missions", "historique unifié"], GREEN)
    box(ax, 740, 230, 220, 170, "Exécuteur", ["déterministe", "shell · fichiers"], ORANGE)
    box(ax, 1000, 230, 220, 170, "Ollama", ["optionnel", "modèles locaux"], PURPLE)

    # Humain
    box(ax, 1330, 330, 220, 160, "TOI", ["approbation", "à chaque action"], GREEN)
    # icône personne dessinée (pas d'emoji)
    ax.add_patch(plt.Circle((1440, 590), 26, fc="none", ec=GREEN, lw=2.5))
    ax.add_patch(Wedge((1440, 536), 44, 20, 160, fc="none", ec=GREEN, lw=2.5))

    # Flèches
    arrow(ax, 320, 565, 360, 565, "", ACCENT)
    arrow(ax, 580, 565, 740, 565, "bridge local", ACCENT)
    arrow(ax, 960, 565, 1000, 565, "", GREEN)
    arrow(ax, 850, 480, 850, 400, "", ORANGE)
    arrow(ax, 1110, 480, 1110, 400, "", PURPLE)
    arrow(ax, 1330, 380, 1220, 330, "", ORANGE)
    ax.text(1275, 300, "demande", ha="center", va="top",
            fontsize=14.5, color=ORANGE, fontfamily=FONT, style="italic")
    arrow(ax, 1330, 460, 1220, 545, "", GREEN)
    ax.text(1275, 585, "valide / refuse", ha="center", va="bottom",
            fontsize=14.5, color=GREEN, fontfamily=FONT, style="italic")

    # Bandeau garanties
    ax.add_patch(FancyBboxPatch((60, 130), 560, 220, boxstyle="round,pad=10,rounding_size=20",
                                fc=PANEL, ec=BORDER, lw=1.5))
    ax.text(340, 310, "GARANTIES", ha="center", fontsize=16, color=GREEN,
            fontfamily=FONT, fontweight="bold")
    for i, g in enumerate([
        "• chat classique uniquement (garde intégrée)",
        "• rien ne s'exécute sans ton accord",
        "• workspace stable ~/cortex-workspaces",
        "• doctor : auto-diagnostic en 5 checks",
    ]):
        ax.text(90, 262 - i * 38, g, fontsize=15.5, color=TEXT, fontfamily=FONT, ha="left")

    fig.savefig(MEDIA / "architecture-flow.png")
    plt.close(fig)


hero_banner()
architecture()

from PIL import Image
for name in ("hero-banner.png", "architecture-flow.png"):
    # purge toutes les métadonnées PNG (Software matplotlib, etc.)
    path = MEDIA / name
    im = Image.open(path)
    clean = Image.new(im.mode, im.size)
    clean.putdata(list(im.getdata()))
    clean.save(path, format="PNG")
    im2 = Image.open(path)
    print(name, im2.size, dict(im2.info))
