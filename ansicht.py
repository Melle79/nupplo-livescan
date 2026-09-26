"""Ein Bildschirmfoto des Scanners mit einer Beispielfigur – ohne Instanz.

Wozu: Wie die selbst gezeichneten Knöpfe unter **Windows** aussehen, lässt
sich vom Mac aus nicht prüfen. Der Bau-Runner führt dieses Skript aus und
legt das Bild als Artefakt ab; auf dem Mac geht es genauso.

    python ansicht.py ansicht.png

An die Stelle der Instanz tritt eine Attrappe: keine Anmeldung, keine
Anfrage, keine Datei außerhalb eines Wegwerf-Ordners.
"""
import json
import os
import subprocess
import sys
import tempfile
import tkinter as tk

import livescan

ZIEL = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "ansicht.png")
UNTEN = os.path.splitext(ZIEL)[0] + "-unten.png"
ORDNER = tempfile.mkdtemp(prefix="livescan-ansicht-")
livescan.EINSTELLUNGEN = os.path.join(ORDNER, "einstellungen.json")
livescan.VERLAUF_DATEI = os.path.join(ORDNER, "verlauf.json")
with open(livescan.EINSTELLUNGEN, "w") as f:
    json.dump({"updates_pruefen": False, "adresse": "http://example.invalid",
               "token": "attrappe", "bereich": [100, 100, 400, 400]}, f)
livescan.ton_spielen = lambda datei=None: None

INFO = {
    "sw0188": {"owned": 1, "year": 2007, "new": 5.95, "used": 3.70,
               "all_sets": [{"no": "10188-1", "name": "Death Star - UCS"}]},
    "sw0036": {"wanted": True, "year": 2001, "new": 13.59, "used": 6.18},
}


class Attrappe:
    token = "attrappe"
    adresse = "http://example.invalid"
    katalogbild = lambda self, adresse: None
    sets_der_figur = lambda self, nummer: []

    def listen(self):
        return [{"id": 1, "name": "Flohmarkt"}]

    def infos(self, artikel, bei_bricklink=False):
        return {t["item_id"]: dict(INFO.get(t["item_id"], {}))
                for t in artikel}

    # Die volle Preisangabe wie aus /api/price – Beträge als Text.
    einstellungen = lambda self: {"currency": "EUR", "angebotspreise": True}

    def preise(self, typ, nummer):
        return {
            "new": {"min": "4.50", "avg": "5.95", "max": "7.99",
                    "times_sold": 13, "used_scope": "DE"},
            "used": {"min": "2.10", "avg": "3.70", "max": "5.49",
                     "times_sold": 41, "used_scope": "DE"},
            "stock": {"used": {"min": "2.99", "angebote": 18,
                               "used_scope": "DE"}},
        }


def _abbild(wurzel, ziel):
    wurzel.update_idletasks()
    x, y = wurzel.winfo_rootx(), wurzel.winfo_rooty()
    b, h = wurzel.winfo_width(), wurzel.winfo_height()
    if livescan.IST_WINDOWS:
        from PIL import ImageGrab
        ImageGrab.grab(bbox=(x, y, x + b, y + h), all_screens=True).save(ziel)
    else:
        subprocess.run(["screencapture", "-x", "-R",
                        f"{x},{y},{b},{h}", ziel])
    print("Bild:", ziel, f"({b}×{h})")


def knipsen(wurzel, app):
    """Oben und – ans Ende geschoben – unten. Auf einem niedrigen Schirm
    (etwa dem des Bau-Runners) stünde sonst die Knopfreihe nie im Bild."""
    _abbild(wurzel, ZIEL)
    app.leinwand.yview_moveto(1.0)
    wurzel.after(300, lambda: (_abbild(wurzel, UNTEN), wurzel.destroy()))


def main():
    livescan.windows_dpi_beachten()
    wurzel = tk.Tk()
    if livescan.IST_WINDOWS:
        wurzel.tk.call("tk", "scaling", wurzel.winfo_fpixels("1i") / 72.0)
    app = livescan.LiveScanner(wurzel)
    app.instanz = Attrappe()
    app.listen_laden()
    wurzel.geometry("+40+40")
    wurzel.attributes("-topmost", True)

    def zeigen():
        app._kandidaten_zeigen([
            {"item_id": "sw0188", "item_type": "minifig", "score": 78,
             "name": "Imperial Stormtrooper - Black Head, Dotted Mouth Helmet",
             "img_url": "", "_info": dict(INFO["sw0188"])},
            {"item_id": "sw0036", "item_type": "minifig", "score": 62,
             "name": "Imperial Stormtrooper - Yellow Head", "img_url": "",
             "_info": dict(INFO["sw0036"])},
        ])

    wurzel.after(400, zeigen)
    wurzel.after(2500, lambda: knipsen(wurzel, app))
    wurzel.mainloop()


if __name__ == "__main__":
    main()
