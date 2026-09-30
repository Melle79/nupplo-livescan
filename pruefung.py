#!/usr/bin/env python3
"""Prüfung des Live-Scanners – am verborgenen Fenster, ohne Netz.

    /opt/homebrew/bin/python3 pruefung.py

Es wird **kein** Bildschirmfoto gemacht, **keine** Anfrage an die Instanz
geschickt und **nicht** in die echten Einstellungen geschrieben: Statt der
Instanz steht eine Attrappe, statt der Abzüge ein Drehbuch, und die beiden
Dateien zeigen ins Temp-Verzeichnis.

Warum am verborgenen Fenster und nicht über `start.sh`: Das echte Fenster
legt sich über alles und blockiert. Zwei Fallstricke dabei, die schon zweimal
für Fehlalarm gesorgt haben:

* `event_generate("<<ListboxSelect>>")` kommt am verborgenen Fenster nicht an –
  die Behandlung wird direkt aufgerufen.
* Alles aus den Hintergrundfäden geht über `self.post` und wird per
  `after(120, …)` abgeholt. `update()` lässt diese Zeit **nicht** vergehen;
  dafür ist `takt()` da.
"""
import base64
import json
import os
import pathlib
import queue
import io
import shutil
import subprocess
import sys
import urllib.error
import tempfile
import time
import tkinter as tk
from tkinter import ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import livescan

ORDNER = tempfile.mkdtemp(prefix="livescan-pruefung-")
livescan.EINSTELLUNGEN = os.path.join(ORDNER, "einstellungen.json")
livescan.VERLAUF_DATEI = os.path.join(ORDNER, "verlauf.json")
livescan.WUNSCH_TAKT = 15            # nicht zwei Sekunden warten

# Ein winziges, echtes PNG – die Vorschau soll etwas zu tun bekommen.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAE"
    "hQGAhKmMIQAAAABJRU5ErkJggg==")

def bild(nummer):
    """Ein echtes, aber unterscheidbares PNG – Tk muss es laden koennen,
    sonst entstehen keine Daumennaegel und der Test prueft ins Leere."""
    return PNG + b"\x00" * nummer

toene = []
livescan.ton_spielen = lambda datei=None: toene.append("ton")

# Rückfragen beantwortet das Drehbuch, nicht ein Mensch – ein echter Dialog
# hielte die Proben an. Ohne vorbereitete Antwort heißt es „Nein".
antworten = []
gefragt_dialog = []


def _ja_nein(titel, text, parent=None):
    gefragt_dialog.append(text)
    return antworten.pop(0) if antworten else False


livescan.messagebox.askyesno = _ja_nein

bestand = {}          # was die Attrappe auf `infos` antwortet
erkannt = {"items": []}
geschickt = []


class Attrappe:
    """Die Instanz, ohne eine einzige Anfrage."""
    token = "attrappe"
    adresse = "http://example.invalid"
    katalogbild = lambda self, a: None
    sets_der_figur = lambda self, i: []
    listen = lambda self: []
    infos = lambda self, a, bei_bricklink=False: dict(bestand)
    preise = lambda self, typ, nummer: {}
    einstellungen = lambda self: {}

    def erkennen(self, bild):
        geschickt.append(bild)
        return {"items": [dict(t) for t in erkannt["items"]]}

    def nummer_suchen(self, nummer):
        katalog = {
            "sw0011": ("minifig", "Chewbacca"),
            "75192": ("set", "Millennium Falcon"),
        }
        if nummer not in katalog:
            return []
        typ, name = katalog[nummer]
        return [{"item_id": nummer, "item_type": typ, "name": name,
                 "img_url": "", "bricklink_url": "", "score": 100}]

    def in_sammlung(self, *a, **k):
        raise AssertionError("es wurde ungefragt gebucht!")
    auf_wunschliste = auf_liste = in_sammlung


def artikel(nr, punkte, name, typ="minifig", **info):
    return {"item_id": nr, "item_type": typ, "score": punkte, "name": name,
            "img_url": "", "_info": dict(info)}


# ----------------------------------------------------------- Prüfgerüst
bilanz = {"gut": 0, "schlecht": 0}


def abschnitt(titel):
    print("\n\033[1m%s\033[0m" % titel)


# Pillow gibt es nur dort, wo es gebraucht wird: unter Windows im Paket,
# hier höchstens in der Baustube. Fehlt es, entfallen die Proben, die es
# brauchen – sichtbar, nicht stillschweigend.
try:
    from PIL import Image as _PIL
except ImportError:
    _PIL = None


def pruefe(bedingung, text):
    bilanz["gut" if bedingung else "schlecht"] += 1
    print(("   ok   " if bedingung else "  FEHL  ") + text)
    assert bedingung, text


def fenster():
    w = tk.Tk()
    w.withdraw()
    a = livescan.LiveScanner(w)
    a.instanz = Attrappe()
    return w, a


def takt(w, ms=250):
    """Zeit wirklich vergehen lassen – `update()` genügt nicht."""
    w.after(ms, w.quit)
    w.mainloop()


def trennen(app):
    """Den nächsten Scan als neuen Artikel gelten lassen.

    Sonst zieht das Programm zusammen, was hier zwei unabhängige Prüfungen
    sein sollen – sobald sich die Vorschläge überschneiden, ist es für den
    Scanner dieselbe Figur aus einem anderen Winkel. Das ist gewolltes
    Verhalten; hier wird nur der Zeitablauf vorgespult.
    """
    if app.verlauf_daten and app.verlauf_daten[0]:
        app.verlauf_daten[0]["zeit"] = 0


# ============================================================ 1. Rennen
abschnitt("1. Verspätete Antworten überschreiben die Karte nicht")
wurzel, app = fenster()

app._kandidaten_zeigen([artikel("11833", 61, "Plate, Round 4 x 4", "part")])
takt(wurzel)
platte = app.kandidaten[0]
app._kandidaten_zeigen([artikel("sw0579", 92, "General Veers")])
takt(wurzel)
platte["_info"] = {"used": 0.07}
app.post.put(("fuer", (platte, "treffer", platte)))
takt(wurzel)
pruefe(app.name.cget("text") == "General Veers",
       "die Karte gehört weiter zum neuen Scan")
pruefe(app.treffer["item_id"] == "sw0579",
       "und gebucht würde der neue, nicht der alte")

app.treffer["_info"] = {"used": 7.25}
app.post.put(("fuer", (app.treffer, "treffer", app.treffer)))
takt(wurzel)
pruefe("7,25" in app.unter.cget("text"),
       "der Preis für den aktuellen Treffer kommt aber an")

# ==================================================== 2. Ansichten vereinen
abschnitt("2. Drehscheibe: Ansichten werden vereint")
wurzel.destroy()
os.remove(livescan.VERLAUF_DATEI)
wurzel, app = fenster()

app.letztes_bild = bild(1)
app._kandidaten_zeigen([artikel("sw0417", 71, "Mace Windu"),
                        artikel("11833", 64, "Ständer", "part")])
takt(wurzel)
pruefe(app.verlauf.size() == 1, "eine Zeile")

# Die Scheibe dreht sich: andere Quoten, ein neuer Vorschlag, Überschneidung
app.letztes_bild = bild(2)
app._kandidaten_zeigen([artikel("sw0417", 78, "Mace Windu"),
                        artikel("sw0056", 55, "Mace Windu Ep2")])
takt(wurzel)
print("     Liste:", [app.liste.get(i) for i in range(app.liste.size())])
pruefe(app.verlauf.size() == 1, "immer noch eine Verlaufszeile")
pruefe("⟳2" in app.verlauf.get(0), "mit der Zahl der Ansichten")
pruefe(app.liste.size() == 3, "alle Vorschläge beider Ansichten stehen da")
pruefe(app.kandidaten[0]["item_id"] == "sw0417",
       "die zweimal gesehene Figur steht oben")
pruefe(app.kandidaten[0]["score"] == 78, "mit ihrer besten Quote")
pruefe("(2×)" in app.liste.get(0), "und der Zahl der Ansichten in der Zeile")
pruefe(app.bilder == [bild(1), bild(2)],
       "beide Aufnahmen werden aufgehoben")
pruefe(app.bilder_an == {1},
       "vorgewählt ist die Ansicht, die den besten Treffer lieferte")
pruefe(app.ansichtsreihe.winfo_manager() == "pack"
       and len(app._mini_rahmen) == 2,
       "und die Reihe zeigt beide zum Aussuchen")

# Dritte Ansicht, in der die Figur schlechter erkannt wird
app.letztes_bild = bild(3)
app._kandidaten_zeigen([artikel("sw0417", 60, "Mace Windu")])
takt(wurzel)
pruefe(app.kandidaten[0]["score"] == 78, "die beste Quote bleibt die beste")
pruefe(app.kandidaten[0]["_ansichten"] == 3, "dreimal gesehen")
pruefe(len(app.bilder) == 3, "alle drei Aufnahmen liegen bereit")
pruefe(app.bilder_an == {1},
       "die Vorwahl wechselt nicht auf die schlechtere Ansicht")
pruefe(app.letztes_bild == bild(2), "und die Vorschau zeigt die gewählte")

# Von Hand aussuchen – auch mehrere.
app._ansicht_umschalten(2)
pruefe(app.bilder_an == {1, 2}, "ein Klick nimmt eine zweite Ansicht dazu")
pruefe(app.letztes_bild == bild(3), "und zeigt sie groß")
app._ansicht_umschalten(1)
pruefe(app.bilder_an == {2}, "noch ein Klick nimmt die erste wieder heraus")
app._ansicht_umschalten(0)
pruefe(app.bilder_an == {0, 2}, "aussuchen geht in beide Richtungen")
print("     Beschriftung:", app.ansichtstext.cget("text"))
pruefe("2 von 3" in app.ansichtstext.cget("text"),
       "die Reihe sagt in Worten, wie viele angehängt werden")
app.bilder_an.clear()
app._ansichten_faerben()
pruefe("kein Foto" in app.ansichtstext.cget("text"),
       "und sagt es auch, wenn keines ausgesucht ist")
app.bilder_an.add(1)
app._ansichten_faerben()

# Von Hand nachgeschoben, eine Minute später: Rahmen ziehen dauert, und die
# 25 Sekunden für den Wächter reichen dafür nicht.
app.auto_lauf = True                     # die Ansichten kamen vom Wächter
app.eintrag["auto"] = True
app.eintrag["zeit"] = time.time() - 60
zeilen_davor = app.verlauf.size()
app.auto_lauf = False                    # jetzt löst der Mensch aus
app.letztes_bild = bild(4)
app._kandidaten_zeigen([artikel("sw0417", 89, "Mace Windu")])
takt(wurzel)
print("     Verlauf:", app.verlauf.get(0))
pruefe(app.verlauf.size() == zeilen_davor,
       "die eigene Aufnahme zählt zur selben Figur, auch nach einer Minute")
pruefe("⟳4" in app.verlauf.get(0), "und wird mitgezählt")
pruefe(app.verlauf.get(0).count("⏱") == 1,
       "das ⏱ bleibt – eine der Ansichten kam ja vom Wächter")

# Auch der Wächter zählt nach einer Pause weiter mit: Nach vier Ansichten
# macht er von sich aus Halt, und bis sich wieder etwas tut, vergeht Zeit.
app.auto_lauf = True
app.eintrag["zeit"] = time.time() - 90
zeilen_davor = app.verlauf.size()
app._kandidaten_zeigen([artikel("sw0417", 70, "Mace Windu")])
takt(wurzel)
pruefe(app.verlauf.size() == zeilen_davor,
       "auch nach anderthalb Minuten Pause bleibt es dieselbe Figur")

# Irgendwann ist es aber eine neue Begegnung.
app.eintrag["zeit"] = time.time() - livescan.ANSICHT_FENSTER - 5
zeilen_davor = app.verlauf.size()
app._kandidaten_zeigen([artikel("sw0417", 70, "Mace Windu")])
takt(wurzel)
pruefe(app.verlauf.size() == zeilen_davor + 1,
       "nach %.0f Minuten fängt eine neue Zeile an"
       % (livescan.ANSICHT_FENSTER / 60))
app.auto_lauf = False

# Viele Ansichten: Es werden nur so viele gehalten, wie auch gezeigt werden –
# sonst fiele die Vorauswahl auf ein Bild, das man nie zu sehen bekommt.
gewaehlt_vorher = set(app.bilder_an)
app.bilder_an.clear()
app.bilder_an.add(0)                    # die erste ausdrücklich behalten
erstes = app.bilder[0]
for n in range(5, 12):
    app.letztes_bild = bild(n)
    app._kandidaten_zeigen([artikel("sw0417", 70, "Mace Windu")])
takt(wurzel)
print("     Aufnahmen:", len(app.bilder), "· gezeigt:", len(app._mini_rahmen),
      "· gewählt:", app.bilder_an)
pruefe(len(app.bilder) == livescan.MINI_HOECHSTENS,
       "höchstens %d Aufnahmen werden gehalten" % livescan.MINI_HOECHSTENS)
pruefe(len(app._mini_rahmen) == len(app.bilder),
       "und alle davon stehen zum Aussuchen da")
pruefe(all(i < len(app.bilder) for i in app.bilder_an),
       "die Auswahl zeigt auf ein Bild, das es noch gibt")
pruefe(erstes in app.bilder,
       "die ausgesuchte Aufnahme überlebt, verworfen wird eine ungewählte")

# Etwas völlig anderes: keine Überschneidung -> neue Zeile
zeilen_davor = app.verlauf.size()
app._kandidaten_zeigen([artikel("sw0900", 88, "Ganz andere Figur")])
takt(wurzel)
pruefe(app.verlauf.size() == zeilen_davor + 1,
       "ohne Überschneidung fängt eine neue Zeile an")

# ================================================ 3. Auswahl festhalten
abschnitt("3. Eine neue Ansicht reißt die Auswahl nicht weg")
app._kandidaten_zeigen([artikel("sw0100", 90, "Erster"),
                        artikel("sw0101", 60, "Zweiter")])
takt(wurzel)
app.liste.selection_clear(0, "end")
app.liste.selection_set(1)
app._auswahl_geaendert()                 # am verborgenen Fenster direkt
takt(wurzel)
pruefe(app.treffer["item_id"] == "sw0101", "von Hand auf den zweiten gestellt")

app._kandidaten_zeigen([artikel("sw0100", 95, "Erster"),
                        artikel("sw0102", 70, "Dritter")])
takt(wurzel)
print("     Liste:", [app.liste.get(i)[:28] for i in range(app.liste.size())])
pruefe(app.treffer["item_id"] == "sw0101",
       "nach der nächsten Ansicht steht die Wahl unverändert")
pruefe(app.liste.get(app.liste.curselection()[0]).find("sw0101") > 0,
       "und die Markierung ist mitgewandert")

# ================================================ Lesbar in beiden Modi
# Die grauen Töne waren für einen hellen Grund gewählt. Im Nachtmodus war
# #666 fast unsichtbar – Nummer, Trefferquote und Preise verschwanden.
# Hier wird deshalb nicht behauptet, dass es lesbar ist, sondern gemessen.
abschnitt("2c. Die Schrift steht in beiden Modi ab")


def _leuchtkraft(farbe):
    """Relative Helligkeit nach WCAG – Grundlage jedes Kontrastmaßes."""
    farbe = farbe.lstrip("#")
    if len(farbe) == 3:
        farbe = "".join(z * 2 for z in farbe)
    werte = []
    for _i in (0, 2, 4):
        k = int(farbe[_i:_i + 2], 16) / 255.0
        werte.append(k / 12.92 if k <= 0.03928
                     else ((k + 0.055) / 1.055) ** 2.4)
    return 0.2126 * werte[0] + 0.7152 * werte[1] + 0.0722 * werte[2]


def _kontrast(vorne, hinten):
    a, b = _leuchtkraft(vorne), _leuchtkraft(hinten)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# **Der Maßstab ist der Tagmodus selbst.** Eine feste Grenze würde das
# gewachsene helle Bild über einen Zahlenwert umbauen – die leisen Töne
# liegen dort bewusst niedrig (#888 auf Weiß ergibt 3,5). Verlangt wird
# deshalb: Jede Rolle muss nachts **mindestens so gut** stehen wie am Tag.
# Dazu eine Untergrenze, damit nichts ganz verschwindet.
_ROLLEN = ("leise", "matt", "still", "klar", "kraeftig", "verweis",
           "warnung", "geschafft")

livescan.farben_setzen(None, dunkel=False)
_hell_werte = {_r: _kontrast(livescan.FARBEN[_r], "#ffffff") for _r in _ROLLEN}
livescan.farben_setzen(None, dunkel=True)
_dunkel_werte = {_r: _kontrast(livescan.FARBEN[_r], "#1e1e1e")
                 for _r in _ROLLEN}

# Bei den kräftigen Rollen genügen 7,0: Fast-Schwarz auf Weiß erreicht
# fast 16, das ist auf dunklem Grund nicht zu halten und muss es auch
# nicht – ab etwa 7 liest sich Text ohne jede Anstrengung. Wo der Tagmodus
# schwächer ist, gilt weiterhin er als Maßstab.
for _r in _ROLLEN:
    _soll = min(_hell_werte[_r], 7.0)
    pruefe(_dunkel_werte[_r] >= _soll,
           "»%s« steht nachts gut genug (%.1f, verlangt %.1f)"
           % (_r, _dunkel_werte[_r], _soll))

_schwach = min((_dunkel_werte[_r], _r) for _r in _ROLLEN)
pruefe(_schwach[0] >= 2.5,
       "und nichts verschwindet im Dunkeln (schwächster: »%s« mit %.1f)"
       % (_schwach[1], _schwach[0]))

# Die Erkennung misst den Grund, statt das System zu fragen – das
# funktioniert auf beiden Systemen gleich.
_wf = tk.Tk()
_wf.withdraw()
pruefe(isinstance(livescan.grund_ist_dunkel(_wf), bool),
       "der Fenstergrund lässt sich messen")
livescan.farben_setzen(_wf)
_wf.destroy()

_roh_farben = pathlib.Path(livescan.__file__).read_text()
pruefe("winfo_rgb" in _roh_farben,
       "über winfo_rgb – das löst auch die Systemfarben von macOS auf")
pruefe("farben_setzen(wurzel)"
       in _roh_farben[:_roh_farben.index("self._bauen()")],
       "und die Palette wird **vor** dem Aufbau der Oberfläche gesetzt")

# --- Feste helle Zeilen brauchen feste dunkle Schrift ------------------
# Diese beiden Gründe tragen eine Bedeutung und bleiben deshalb hell,
# egal welches Erscheinungsbild gilt. Die Schrift darauf war aber die
# voreingestellte – und die ist im Nachtmodus hell: weiß auf blassgrün.
# Wer den Hintergrund setzt, muss auch die Schrift setzen.
for _grund, _schrift, _wie in (
        (livescan.GRUEN_ZEILE, livescan.GRUEN_ZEILE_SCHRIFT, "»habt ihr schon«"),
        (livescan.WUNSCH_ZEILE, livescan.WUNSCH_ZEILE_SCHRIFT, "»Wunschliste«")):
    _k = _kontrast(_schrift, _grund)
    pruefe(_k >= 4.0,
           "%s: die Schrift steht auf ihrem hellen Grund (Kontrast %.1f)"
           % (_wie, _k))

# Und die Regel selbst: Wo ein Hintergrund gesetzt wird, steht auch eine
# Schriftfarbe daneben.
_roh_zeilen = pathlib.Path(livescan.__file__).read_text()
for _stelle in ("background=livescan.GRUEN_ZEILE", "background=GRUEN_ZEILE",
                "background=WUNSCH_ZEILE"):
    if _stelle in _roh_zeilen:
        _ab = _roh_zeilen[_roh_zeilen.index(_stelle):][:220]
        # **Nicht einfach nach »foreground=« suchen** – das steckt auch in
        # »selectforeground=«, das nur für die *markierte* Zeile gilt. Die
        # erste Fassung dieser Probe fand genau das und schlug deshalb
        # nicht an, als die eigentliche Schriftfarbe fehlte.
        _echte = len([z for z in _ab.split("foreground=")[:-1]
                      if not z.endswith("select")])
        pruefe(_echte >= 1,
               "wo %s gesetzt wird, steht auch eine Schriftfarbe"
               % _stelle.split("=")[1])

# --- Umschalten im laufenden Betrieb -----------------------------------
# macOS wechselt abends von selbst auf dunkel. Der Fenstergrund folgt
# sofort – die Schriftfarben nicht, die stehen fest in den Bedienelementen.
# Vorher stand das als Einschränkung im Quelltext (»greift beim nächsten
# Start«). Eine dokumentierte Einschränkung ist keine Lösung, wenn sie
# jeden Abend zuschlägt.
_ww = tk.Tk()
_ww.withdraw()
livescan.farben_setzen(_ww, dunkel=False)
_wr = ttk.Frame(_ww)
_wr.pack()
_l_ttk = ttk.Label(_wr, text="Meta", foreground=livescan.FARBEN["leise"])
_l_tk = tk.Label(_wr, text="Sets", foreground=livescan.FARBEN["matt"])
_l_gruen = tk.Label(_wr, text="grün", foreground="#1a7f37")
_leinwand = tk.Canvas(_wr, width=40, height=20)
_stueck = _leinwand.create_text(5, 5, text="x",
                                fill=livescan.FARBEN["still"])
for _x in (_l_ttk, _l_tk, _l_gruen, _leinwand):
    _x.pack()
_ww.update_idletasks()

_echt_dunkel = livescan.grund_ist_dunkel
livescan.grund_ist_dunkel = lambda _w: True
try:
    pruefe(livescan.farben_auffrischen(_ww) is True,
           "der Wechsel auf Nachtmodus wird bemerkt")
    _ww.update_idletasks()
    pruefe(str(_l_ttk.cget("foreground")) == "#9a9a9a",
           "eine ttk-Beschriftung färbt sich mit")
    pruefe(str(_l_tk.cget("foreground")) == "#a8a8a8",
           "eine gewöhnliche auch")
    pruefe(str(_leinwand.itemcget(_stueck, "fill")) == "#b4b4b4",
           "und Text auf einer Leinwand ebenfalls – der hängt nicht am\n"
           "       Bedienelement und wäre sonst zurückgeblieben")
    pruefe(str(_l_gruen.cget("foreground")) == "#1a7f37",
           "was nicht aus der Palette stammt, bleibt unangetastet")
    pruefe(livescan.farben_auffrischen(_ww) is False,
           "beim zweiten Mal gibt es nichts mehr zu tun")
finally:
    livescan.grund_ist_dunkel = _echt_dunkel
_ww.destroy()

_roh_takt = pathlib.Path(livescan.__file__).read_text()
pruefe("farben_auffrischen(self.wurzel)" in _roh_takt,
       "und der laufende Takt sieht regelmäßig nach")

# ==================================================== 4. Wunschliste
abschnitt("4. Wunschliste: Blinken und Ton")
toene.clear()
app._kandidaten_zeigen([artikel("sw0500", 88, "Wunschfigur", wanted=1)])
takt(wurzel, 30)
pruefe(len(toene) == 1, "es klingt")
pruefe(app._blinkt is not None, "und blinkt")
# **Nicht auf die Uhr verlassen.** Bis 30.08.2026 tastete diese Probe die
# Farbe sechsmal in 150 ms ab – weniger als *ein* Wechsel (260 ms). Dass
# sie durchging, war Glück: Auf dem Mac-Runner fiel sie durch, auf dem
# Windows-Runner auch, und beide Male war am Programm nichts falsch.
#
# Warten hilft hier nicht weiter, es verschiebt die Wackelei nur. Also
# wird der Schritt selbst ausgelöst: Bei ungeradem Rest **muss** die
# Wunschfarbe stehen, bei geradem der Grund. Das gilt auf jeder Maschine,
# egal wie ausgelastet sie ist. Dass der Blinker von allein läuft, steht
# schon in der Probe darüber.
app._wunsch_blinken(app.rahmen_aus, 7)
pruefe(app.rahmen.cget("background") == livescan.WUNSCH_AN,
       "in der Wunschfarbe")
app._wunsch_blinken(app.rahmen_aus, 6)
pruefe(app.rahmen.cget("background") == app.rahmen_aus,
       "und dazwischen wieder im Grund")
# Und jetzt abwarten, bis der Blinker von selbst fertig ist.
takt(wurzel, livescan.WUNSCH_TAKTE * livescan.WUNSCH_TAKT + 400)
pruefe(app._blinkt is None, "danach hört es auf")
pruefe(app.liste.get(0).startswith("☆"), "die Zeile trägt das ☆")

# Weitere Ansicht derselben Figur: still, der Wunsch ist nicht neu
toene.clear()
app._kandidaten_zeigen([artikel("sw0500", 80, "Wunschfigur", wanted=1)])
takt(wurzel, 30)
pruefe(toene == [], "die nächste Ansicht bleibt still")
pruefe(app._blinkt is None, "und dunkel")

# Ein Wunsch, der erst in der zweiten Ansicht auftaucht: klingt
toene.clear()
app._kandidaten_zeigen([artikel("sw0500", 80, "Wunschfigur", wanted=1),
                        artikel("sw0501", 62, "Neuer Wunsch", wanted=1)])
takt(wurzel, 30)
pruefe(len(toene) == 1, "ein neu hinzugekommener Wunsch klingt sehr wohl")

# ============================================ 5. Nummer nachtragen
abschnitt("5. Nummer nachtragen – der Chewbacca-Fall")
app._kandidaten_zeigen([artikel("11833", 62, "Plate, Round 4 x 4", "part"),
                        artikel("60474", 59, "Plate mit Loch", "part")])
takt(wurzel)
app.nummerfeld.delete(0, "end")
app.nummerfeld.insert(0, "sw0011")
app.nummer_suchen()
takt(wurzel)
print("     Liste:", [app.liste.get(i)[:30] for i in range(app.liste.size())])
pruefe(app.liste.size() == 3, "die Vorschläge bleiben stehen")
pruefe(app.treffer["item_id"] == "sw0011", "die getippte Figur ist gewählt")
pruefe("✎" in app.liste.get(app.liste.curselection()[0]),
       "sie trägt ein ✎ statt einer Trefferquote")
pruefe("von Hand eingetragen" in app.unter.cget("text"),
       "auch die Karte sagt es")

# ============================================== 6. Nur Figuren
abschnitt("6. Haken »Nur Figuren«")
trennen(app)          # sonst vereint er es mit dem Chewbacca von eben
erkannt = {"items": [artikel("11833", 62, "Platte", "part"),
                     artikel("sw0011", 55, "Chewbacca"),
                     artikel("75192", 40, "Falcon", "set")]}
app.nur_figuren.set(False)
app._ausloesen(lambda: PNG)
takt(wurzel, 350)
pruefe(app.liste.size() == 3, "ohne Haken kommen alle drei Arten")

app.nur_figuren.set(True)
trennen(app)
app._ausloesen(lambda: PNG)
takt(wurzel, 350)
pruefe(app.liste.size() == 1, "mit Haken nur die Figur")

erkannt = {"items": [artikel("11833", 62, "Platte", "part"),
                     artikel("60474", 59, "Platte mit Loch", "part")]}
app._treffer_leeren()      # ohne bestehenden Treffer – der Fall steht in 8b
app._ausloesen(lambda: PNG)
takt(wurzel, 350)
print("     Meldung:", app.stand.cget("text"))
pruefe(app.liste.size() == 0, "wird alles aussortiert, bleibt die Liste leer")
pruefe("alle 2 Vorschläge waren Sets oder Teile" in app.stand.cget("text"),
       "und es wird gesagt, wie viel weggefiltert wurde")
pruefe("Nichts erkannt" not in app.stand.cget("text"),
       "nicht behauptet, es sei nichts erkannt worden")
app.nur_figuren.set(False)

# ====================================== 7. Rücksprung im Verlauf
abschnitt("7. Rücksprung im Verlauf")
app.letztes_bild = b"altes-bild"
app._kandidaten_zeigen([artikel("sw0700", 77, "Alte Figur"),
                        artikel("sw0701", 71, "Alte Variante")])
takt(wurzel)
app.liste.selection_clear(0, "end")
app.liste.selection_set(1)
app._auswahl_geaendert()
takt(wurzel)
app.letztes_bild = b"neues-bild"
app._kandidaten_zeigen([artikel("sw0800", 92, "Neue Figur")])
takt(wurzel)

bestand = {"sw0701": {"owned": 1}}
app.verlauf.selection_clear(0, "end")
app.verlauf.selection_set(1)
app._verlauf_geklickt()
takt(wurzel)
print("     Karte:", app.name.cget("text"), "|", app.stand.cget("text")[:40])
pruefe(app.treffer["item_id"] == "sw0701", "die gewählte Variante ist zurück")
pruefe(app.letztes_bild == b"altes-bild", "samt der Aufnahme von damals")
pruefe(app.stand.cget("text").startswith("↩"), "mit Hinweis auf die Vergangenheit")
pruefe("1×" in app.besitz.cget("text"),
       "und der Bestand wurde frisch geholt")
bestand = {}

# ============================== 8. Verlauf über den Neustart
abschnitt("8. Der Verlauf übersteht das Schließen")
gemerkt = [app.verlauf.get(i) for i in range(app.verlauf.size())]
wurzel.destroy()
roh = open(livescan.VERLAUF_DATEI).read()
pruefe("altes-bild" not in roh and "neues-bild" not in roh,
       "keine Aufnahme steht in der Datei")
if livescan.IST_WINDOWS:
    # Windows kennt diese Rechte nicht; dort schützt allein, dass die Datei
    # im Benutzerprofil liegt. Lieber ehrlich überspringen, als so zu tun,
    # als wäre etwas geprüft.
    print("     (Windows kennt keine 0600-Rechte – Probe entfällt)")
else:
    pruefe(oct(os.stat(livescan.VERLAUF_DATEI).st_mode)[-3:] == "600",
           "die Datei ist nur für den Benutzer lesbar")

wurzel, app = fenster()
zeilen = [app.verlauf.get(i) for i in range(app.verlauf.size())]
print("     oben:", zeilen[0])
pruefe("vorige Sitzung" in zeilen[0], "eine Trennzeile steht oben")
pruefe(zeilen[1:] == gemerkt[:livescan.VERLAUF_MERKEN],
       "darunter der Verlauf von vorhin")
app.verlauf.selection_set(1)
app._verlauf_geklickt()
takt(wurzel)
pruefe(app.treffer is not None, "der Rücksprung geht auch nach dem Neustart")
pruefe(app.letztes_bild is None, "nur die Aufnahme fehlt")
pruefe("nicht mehr" in app.vorschau.cget("text"), "und das steht auch da")
wurzel.destroy()

# ================== 8b. Ein Fehlversuch nimmt nichts weg
abschnitt("8b. Ein erfolgloser Scan lässt die Karte stehen")
wurzel, app = fenster()
erkannt = {"items": [artikel("sw0011", 88, "Chewbacca")]}
app._ausloesen(lambda: PNG)
takt(wurzel, 350)
pruefe(app.treffer["item_id"] == "sw0011", "eine Figur steht auf der Karte")
app.preisfeld.insert(0, "7,50")
bild_davor = app.letztes_bild

# Jetzt funkt der Wächter dazwischen und findet nichts.
erkannt = {"items": []}
app._ausloesen(lambda: b"anderes-bild", automatisch=True)
takt(wurzel, 350)
print("     Meldung:", app.stand.cget("text"))
pruefe(app.treffer is not None and app.treffer["item_id"] == "sw0011",
       "der Treffer bleibt stehen")
pruefe(str(app.k_sammlung.cget("state")) == "normal",
       "die Knöpfe bleiben scharf")
pruefe(app.preisfeld.get() == "7,50", "der eingetippte Preis bleibt")
pruefe(app.letztes_bild == bild_davor,
       "und die Aufnahme gehört weiter zu dieser Figur")
pruefe("bleibt stehen" in app.stand.cget("text"), "gesagt wird es trotzdem")

# Eine erkannte Figur wechselt die Karte sehr wohl.
erkannt = {"items": [artikel("sw0579", 92, "Veers")]}
app._ausloesen(lambda: b"neues-bild", automatisch=True)
takt(wurzel, 350)
pruefe(app.treffer["item_id"] == "sw0579", "eine erkannte Figur wechselt")
pruefe(app.letztes_bild == b"neues-bild", "und bringt ihre eigene Aufnahme mit")

# Ohne Treffer auf der Karte wird weiterhin aufgeräumt.
app._treffer_leeren()
erkannt = {"items": []}
app._ausloesen(lambda: PNG)
takt(wurzel, 350)
print("     ohne Stand:", app.stand.cget("text")[:46])
pruefe(app.treffer is None, "ohne bestehenden Treffer bleibt es leer")
pruefe("Nichts erkannt – enger rahmen" in app.stand.cget("text"),
       "und der alte Rat steht wieder da")
pruefe(app.letztes_bild == PNG, "die Aufnahme sieht man trotzdem")
wurzel.destroy()

# ============================= 9a. Fenstergröße und Preisfeld
abschnitt("9a. Alles Bedienbare bleibt erreichbar")
# Früher stand hier „bleibt im Fenster", und dafür sorgte eine Mindesthöhe
# in Höhe des ganzen Bedarfs. Auf einem kleineren Bildschirm kippte das ins
# Gegenteil: Das Fenster ließ sich nicht kleiner ziehen als der Schirm hoch
# ist, unten hing es heraus, und scrollen ging nicht. Jetzt scrollt der
# Inhalt – geprüft wird deshalb Erreichbarkeit, nicht Sichtbarkeit.
wurzel, app = fenster()
wurzel.deiconify()
wurzel.update()
wurzel.update_idletasks()
mindest = wurzel.minsize()
print("     Mindestgröße:", mindest, "· Bedarf:", wurzel.winfo_reqheight())
pruefe(mindest[1] <= 400,
       "das Fenster lässt sich klein ziehen (Mindesthöhe %d)" % mindest[1])
wurzel.geometry("%dx%d" % mindest)
# Der schwerste Fall: kleinstes Fenster **und** vier Ansichten zum Aussuchen.
for n in range(4):
    app.letztes_bild = bild(n)
    app._kandidaten_zeigen([artikel("sw0417", 70 + n, "Mace Windu")])
takt(wurzel, 300)
wurzel.update_idletasks()
pruefe(len(app._mini_rahmen) == 4, "vier Ansichten stehen zur Wahl")

felder = ((app.preisfeld, "Einkaufspreis"),
          (app.preisfeld.master, "Zustand-Reihe"),
          (app.k_sammlung, "＋ Sammlung"),
          (app.listenwahl, "Listenauswahl"),
          (app.nummerfeld, "Nummernfeld"),
          (app.verlauf, "Verlauf"))
pruefe(app.balken.winfo_ismapped(),
       "im kleinsten Fenster ist die Bildlaufleiste da")
for feld, name in felder:
    pruefe(feld.winfo_ismapped(), "%s ist angelegt" % name)

def hinscrollen(feld):
    """Zu einem Feld scrollen und melden, ob es dann in der Fläche steht.

    Nicht einfach ganz nach unten: Das Nummernfeld liegt **über** dem
    Preisfeld – am unteren Ende ist es oben aus der Fläche heraus. Erreichbar
    heißt, dass es zu jedem Feld eine Stellung gibt, in der es dasteht.
    """
    ganz = float(app.innen.winfo_height())
    oben = feld.winfo_rooty() - app.innen.winfo_rooty()
    app.leinwand.yview_moveto(max(0.0, (oben - 20) / ganz))
    wurzel.update_idletasks()
    y = feld.winfo_rooty() - app.leinwand.winfo_rooty()
    return 0 <= y and y + feld.winfo_height() <= app.leinwand.winfo_height() + 2

for feld, name in felder:
    pruefe(hinscrollen(feld), "%s ist nach dem Scrollen erreichbar" % name)
app.leinwand.yview_moveto(0.0)
wurzel.update_idletasks()
pruefe(app.ausloeser.winfo_rooty() - app.leinwand.winfo_rooty() >= 0,
       "und ganz oben steht wieder der Auslöser")

# Und auf einem großen Bildschirm darf sich nichts geändert haben: Ist Platz
# übrig, füllt der innere Rahmen die Fläche, sonst wüchse der Verlauf nicht
# mehr mit.
app.leinwand.yview_moveto(0.0)
app.preisfeld.insert(0, "4,50")
pruefe(app._preis_lesen() == (True, 4.5), "und nimmt einen Preis entgegen")
wurzel.destroy()

# ======================== 9a-2. Die Bildlaufleiste kommt und geht
abschnitt("9a-2. Die Bildlaufleiste kommt und geht")
wurzel, app = fenster()
wurzel.deiconify()

# **Das Fenster zwischen die beiden Inhaltshöhen legen, statt auf den
# Bildschirm zu hoffen.**
#
# Vorher stand hier fast die volle Schirmhöhe, und die Probe setzte
# voraus, dass der Inhalt dabei überläuft. Auf einem 4K-Schirm tut er das
# nicht: 1482 px Inhalt in 2080 px Fenster – die Leiste fehlte zu Recht,
# die Prüfung brach ab, und alles dahinter lief nie (30.08.2026).
#
# Jetzt werden beide Höhen gemessen und das Fenster dazwischen gelegt.
app.verlauf.config(height=40)
takt(wurzel, 200)
gross = app.innen.winfo_reqheight()
app.verlauf.config(height=1)
takt(wurzel, 200)
klein = app.innen.winfo_reqheight()
mitte = (gross + klein) // 2
print("     Inhalt groß %d px, klein %d px -> Fenster %d px"
      % (gross, klein, mitte))
if mitte + 80 > wurzel.winfo_screenheight():
    print("     (Bildschirm zu klein für diese Probe – übersprungen)")
else:
    app.verlauf.config(height=40)
    wurzel.geometry("560x%d" % mitte)
    takt(wurzel, 300)
    pruefe(app.balken.winfo_ismapped(), "voller Verlauf: die Leiste ist da")
    app.verlauf.config(height=1)      # nimmt rund 100 px weg
    takt(wurzel, 400)
    print("     Inhalt %d px in %d px Fläche"
          % (app.innen.winfo_reqheight(), app.leinwand.winfo_height()))
    pruefe(not app.balken.winfo_ismapped(),
           "passt alles hinein, verschwindet die Leiste wieder")
    pruefe(app.innen.winfo_height() >= app.leinwand.winfo_height(),
           "der Inhalt füllt die Fläche, der Verlauf wächst wie bisher mit")
    # Das ging vorher **nicht** von selbst: Die Nachführung setzt die Höhe
    # des inneren Rahmens fest, damit ändert sich seine tatsächliche Größe
    # nicht mehr, und das <Configure>, auf das sie horcht, blieb aus.
    # Seither schaut der ohnehin laufende 120-ms-Takt mit nach.
    app.verlauf.config(height=40)
    takt(wurzel, 300)
    pruefe(app.balken.winfo_ismapped(),
           "wächst der Inhalt wieder, kommt die Leiste von selbst zurück")
wurzel.destroy()

# ================================ 9a-3. Das Mausrad
abschnitt("9a-3. Das Mausrad geht dorthin, wo es hingehört")
wurzel, app = fenster()
wurzel.deiconify()
wurzel.geometry("560x300")
takt(wurzel, 200)


class Rad:
    """Ein Rad-Ereignis von Hand – `event_generate` kommt hier nicht an."""
    def __init__(self, widget, delta):
        self.widget, self.delta = widget, delta


oben = app.leinwand.yview()[0]
app._rad(Rad(app.leinwand, -3))
wurzel.update_idletasks()
pruefe(app.leinwand.yview()[0] > oben, "über der Karte schiebt das Rad sie")

stand = app.leinwand.yview()[0]
app._rad(Rad(app.verlauf, -3))
wurzel.update_idletasks()
pruefe(app.leinwand.yview()[0] == stand,
       "über dem Verlauf bleibt die Karte stehen – die Liste scrollt selbst")
app._rad(Rad(app.liste, -3))
wurzel.update_idletasks()
pruefe(app.leinwand.yview()[0] == stand,
       "über der Trefferliste ebenso")

# Ein zweites Fenster (das große Bild) darf die Karte nicht bewegen.
zweit = tk.Toplevel(wurzel)
inhalt = tk.Frame(zweit)
inhalt.pack()
wurzel.update_idletasks()
app._rad(Rad(inhalt, -3))
wurzel.update_idletasks()
pruefe(app.leinwand.yview()[0] == stand,
       "aus einem anderen Fenster kommt gar nichts an")
zweit.destroy()

# Und wenn nichts zu schieben ist, passiert nichts.
#
# **Nicht auf Platz hoffen.** Frueher zog diese Probe das Fenster auf
# Bildschirmhoehe und nahm an, dann passe der Inhalt hinein. Auf dem
# 2160-px-Schirm stimmte das, auf dem Bau-Runner nicht - dort scheiterte
# sie, obwohl nichts kaputt war. Also andersherum: den Inhalt so lange
# kleiner machen, bis er hineinpasst, und das vorher nachweisen.
app.verlauf.config(height=1)
wurzel.geometry("560x%d" % min(900, wurzel.winfo_screenheight() - 80))
takt(wurzel, 250)
uebrig = list(app.innen.pack_slaves())
while app.innen.winfo_reqheight() > app.leinwand.winfo_height() and uebrig:
    uebrig.pop().pack_forget()
    takt(wurzel, 150)
pruefe(app.innen.winfo_reqheight() <= app.leinwand.winfo_height(),
       "Voraussetzung: der Inhalt passt jetzt in die Flaeche")
app.leinwand.yview_moveto(0.0)
app._rad(Rad(app.leinwand, -3))
wurzel.update_idletasks()
pruefe(app.leinwand.yview()[0] == 0.0,
       "passt alles hinein, bewegt das Rad nichts")
wurzel.destroy()

# ================================ 9b. Fotos nicht doppelt anhängen
abschnitt("9b. Ein Foto je Artikel und Aufnahme")
wurzel, app = fenster()
angehaengt = []


class MitFoto(Attrappe):
    def foto_anhaengen(self, t, bild):
        angehaengt.append((t["item_id"], bild))
    in_sammlung = lambda self, t, z="used", p=None: "in der Sammlung"
    auf_wunschliste = lambda self, t: "auf der Wunschliste"
    auf_liste = lambda self, i, t, z="used", p=None: "auf der Liste"


app.instanz = MitFoto()
app.listen = [{"id": 1, "name": "Flohmarkt"}]
app.listenwahl.config(values=["Flohmarkt"])
app.listenwahl.current(0)
app.letztes_bild = b"aufnahme-A"
app._kandidaten_zeigen([artikel("sw0011", 88, "Chewbacca")])
takt(wurzel)

app.zur_sammlung()
takt(wurzel)
app.auf_liste()
takt(wurzel)
app.merken()
takt(wurzel)
print("     angehängt:", [(nr, b.decode()) for nr, b in angehaengt])
pruefe(len(angehaengt) == 1,
       "dreimal gebucht, aber nur ein Foto in der Galerie")
pruefe("hängt schon dran" in app.verlauf.get(0),
       "und der Verlauf sagt, warum kein zweites kam")

# Eine neue Aufnahme derselben Figur kommt sehr wohl dazu.
app.letztes_bild = b"aufnahme-B"
app._kandidaten_zeigen([artikel("sw0011", 90, "Chewbacca")])
takt(wurzel)
app.zur_sammlung()
takt(wurzel)
print("     angehängt:", [(nr, b.decode()) for nr, b in angehaengt])
pruefe(len(angehaengt) == 2, "eine neue Aufnahme wird angehängt")

# Und eine andere Figur bekommt ihr eigenes Foto.
trennen(app)
app._kandidaten_zeigen([artikel("sw0579", 92, "Veers")])
takt(wurzel)
app.zur_sammlung()
takt(wurzel)
pruefe(len(angehaengt) == 3, "eine andere Figur bekommt ihr eigenes")

# Mehrere ausgesuchte Ansichten gehen alle mit.
angehaengt.clear()
app.letztes_bild = b"dreh-1"
app._kandidaten_zeigen([artikel("sw0700", 70, "Drehfigur")])
takt(wurzel)
app.letztes_bild = b"dreh-2"
app._kandidaten_zeigen([artikel("sw0700", 75, "Drehfigur")])
takt(wurzel)
app.letztes_bild = b"dreh-3"
app._kandidaten_zeigen([artikel("sw0700", 60, "Drehfigur")])
takt(wurzel)
pruefe(len(app.bilder) == 3, "drei Ansichten liegen bereit")
app.bilder_an.clear()
app.bilder_an.update({0, 2})
app.zur_sammlung()
takt(wurzel)
print("     angehängt:", [b.decode() for _n, b in angehaengt])
pruefe([b for _n, b in angehaengt] == [b"dreh-1", b"dreh-3"],
       "genau die beiden ausgesuchten Ansichten hängen am Artikel")
pruefe("mit 2 Fotos" in app.verlauf.get(0), "und der Verlauf sagt, wie viele")

# Ohne Auswahl kommt keins mit.
angehaengt.clear()
app.bilder_an.clear()
app.auf_liste()
takt(wurzel)
pruefe(angehaengt == [], "ohne ausgesuchte Ansicht bleibt die Galerie leer")
wurzel.destroy()

# ================================================ 9. Der Wächter
abschnitt("9. Der Wächter – Stillstand und Drehscheibe")
livescan.AUTO_TAKT = 0.01
livescan.AUTO_PAUSE = 0.0


def wacht_lauf(drehbuch, stufe="mittel", je_minute=99, findet=True):
    """`_wachen` braucht nur eine Handvoll Attribute – die bekommt es hier,
    dazu ein Drehbuch statt echter Bildschirmabzüge."""
    livescan.AUTO_JE_MINUTE = je_minute
    folge = list(drehbuch)
    stand = {"name": "?"}
    raus = []

    class Merkende(queue.Queue):
        """Hält fest, **wann** ausgelöst wurde – hinterher steht im Drehbuch
        längst das letzte Bild, und man erführe nie, für welches es war."""
        def put(self, stueck, *a, **k):
            if stueck[0] == "auto-los":
                raus.append(stand["name"])
                # Statt der Erkennung: Sie meldet zurück, ob sie etwas
                # gefunden hat – genau das tut sonst `_ausloesen`.
                w.auto_leer = 0 if findet else w.auto_leer + 1
            elif stueck[0] == "auto-aus":
                raus.append("ABBRUCH")
            queue.Queue.put(self, stueck, *a, **k)

    class Wacht:
        pass

    w = Wacht()
    w.post, w.wacht, w.stufe = Merkende(), True, stufe
    w.bereich, w.beschaeftigt, w.auto_anfragen = (0, 0, 9, 9), False, []
    w.auto_leer = 0

    def abzug(_b):
        if not folge:
            w.wacht = False
        return PNG

    def finger(roh, kante=0):
        if not folge:
            return [0] * 576
        stand["name"], hell = folge.pop(0)
        return [hell] * 576

    # **Hinterher zurückgeben.** Diese Attrappen hingen bis 30.08.2026 für
    # den Rest des Laufs im Modul – eine spätere Probe bekam dann die
    # Attrappe statt der echten Funktion und fiel durch, obwohl der
    # Quelltext in Ordnung war. Wer global ersetzt, räumt auch wieder auf.
    echt = (livescan.bereich_aufnehmen, livescan.fingerabdruck)
    livescan.bereich_aufnehmen, livescan.fingerabdruck = abzug, finger
    try:
        livescan.LiveScanner._wachen(w)
    finally:
        livescan.bereich_aufnehmen, livescan.fingerabdruck = echt
    return raus


# Ein Verkäufer, der die Figur hochhält: Bewegung, dann Stillstand.
raus = wacht_lauf([("greifen", 150)] * 2 + [("Figur A", 60)] * 5
                  + [("greifen", 150)] * 2 + [("Figur B", 200)] * 5)
print("     Stillstand ->", raus)
pruefe(raus == ["Figur A", "Figur B"],
       "je einmal, wenn die Figur stillgehalten wird")

# Eine Drehscheibe: nie still, aber gleichmäßig. Das Bild wandert in
# gleichen Schritten hin und zurück – nie so weit auf einmal, dass es als
# Griff ins Bild durchginge.
welle = list(range(60, 100, 5)) + list(range(90, 60, -5))
dreh = [("Dreh %d" % i, welle[i % len(welle)]) for i in range(40)]
raus = wacht_lauf(dreh)
print("     Drehscheibe ->", len(raus), "Anfragen")
pruefe(len(raus) >= 2,
       "auf der Drehscheibe wird ausgelöst, obwohl nie Ruhe eintritt")
pruefe(len(raus) <= livescan.AUTO_ANSICHTEN,
       "aber höchstens %d Ansichten je Artikel – bei 40 Takten"
       % livescan.AUTO_ANSICHTEN)

# Und ein Griff ins Bild beendet die Sammlung: danach dürfen wieder
# Ansichten geholt werden.
raus = wacht_lauf(dreh[:20] + [("griff", 250)] + dreh[:20])
print("     Drehen, Griff, Drehen ->", len(raus), "Anfragen")
pruefe(len(raus) > livescan.AUTO_ANSICHTEN,
       "nach dem Artikelwechsel beginnt das Zählen von vorn")

# Eine Laufschrift im Bereich: bewegt sich anhaltend, aber es gibt dort
# nichts zu erkennen. Nach ein paar Fehlversuchen soll Schluss sein.
raus = wacht_lauf(dreh, findet=False)
print("     Bewegung ohne Treffer ->", len(raus), "Anfragen")
pruefe(len(raus) == livescan.AUTO_LEERLAUF,
       "nach %d erfolglosen Anfragen hört der Dreh-Auslöser auf"
       % livescan.AUTO_LEERLAUF)

# Wichtig: Nur der Dreh-Auslöser gibt auf. Wer die Figur ruhig hält, bekommt
# weiterhin seinen Versuch – sonst wäre der Bereich für den Rest des Abends tot.
# Das Bild wandert dabei erst weg – käme es bei einem Wert zur Ruhe, der eben
# schon geschickt wurde, hielte der Wächter es zu Recht für dasselbe Bild.
raus = wacht_lauf(dreh[:24] + [("weg", 100), ("weg", 112)]
                  + [("still gehalten", 124)] * 5, findet=False)
print("     … dann still gehalten ->", raus[-1])
pruefe(raus[-1] == "still gehalten",
       "der Stillstand-Auslöser bleibt trotzdem scharf")

# Aber ein Artikelwechsel gibt ihm eine neue Chance.
raus = wacht_lauf(dreh[:24] + [("griff", 250)] + dreh[:24], findet=False)
print("     … nach einem Griff ins Bild ->", len(raus), "Anfragen")
pruefe(len(raus) > livescan.AUTO_LEERLAUF,
       "nach dem Sprung wird es erneut versucht")

# Ein Standbild, das nur leicht flimmert: nach dem ersten Blick nichts mehr.
raus = wacht_lauf([("flimmern", 100 + (i % 2)) for i in range(30)])
print("     Standbild ->", raus)
pruefe(len(raus) == 1, "ein ruhiges Bild löst nur beim Einschalten aus")

# ============================================================ Warum grün?
abschnitt("Die Marke sagt, warum die Zeile grün ist")

# Am 30.08.2026: Grüne Zeile über der Erklärung „— noch nicht in deiner
# Sammlung". Die Figur steckte in einem eigenen Set und lag auf einer
# Liste, war aber nicht als eigener Eintrag erfasst. Grün war richtig,
# nur sagte nichts, warum.
IN_SET = {"in_sets": "7931-1|T-6 Jedi Shuttle|1|used"}
IN_NEUEM_SET = {"in_sets": "7931-1|T-6 Jedi Shuttle|1|new"}
IN_SET_ALT = {"in_sets": "7931-1|T-6 Jedi Shuttle|1"}   # ohne Zustand
AUF_LISTE = {"on_lists": ["Flohmarkt 30.08."]}

pruefe(livescan._schon_da_marke({"owned": 2}) == "✔",
       "in der Sammlung -> ✔")
pruefe(livescan._schon_da_marke(AUF_LISTE) == "🛒",
       "auf einer Einkaufsliste -> 🛒")
pruefe(livescan._schon_da_marke(IN_SET) == " ",
       "ein eigenes Set allein -> kein Zeichen")
pruefe(livescan._schon_da_marke({}) == " ",
       "nichts davon -> kein Zeichen")
pruefe(livescan._schon_da_marke(dict(AUF_LISTE, owned=1)) == "✔",
       "beides -> Besitz schlägt Liste")

# **Ein eigenes Set färbt nicht mehr grün.** Wer die Figuren zu
# jedem Set einzeln ein; steht eine Figur nicht in der Sammlung, hat er sie
# auch nicht – viele Sets kommen ohne Figuren herein (30.08.2026).
pruefe(livescan._schon_da({"owned": 1}), "grün bei: Besitz")
pruefe(livescan._schon_da(AUF_LISTE), "grün bei: Einkaufsliste")
pruefe(not livescan._schon_da(IN_SET),
       "ein GEBRAUCHTES eigenes Set färbt NICHT grün")
pruefe(livescan._schon_da(IN_NEUEM_SET),
       "ein NEUES (versiegeltes) Set färbt grün – die Figur steckt drin")
pruefe(not livescan._schon_da(IN_SET_ALT),
       "ohne Zustandsangabe gilt die vorsichtigere Annahme: gebraucht")
pruefe(livescan._schon_da_marke(IN_NEUEM_SET) == "📦",
       "versiegeltes Set -> 📦")
pruefe("ungeöffneten Set 7931-1" in
       livescan._besitz_zeile(IN_NEUEM_SET)["text"],
       "und die Zeile sagt, dass es ungeöffnet ist")
pruefe("ungeöffnet" in livescan._woanders(IN_NEUEM_SET),
       "auch der Hinweis darunter unterscheidet versiegelt von offen")
pruefe("ungeöffnet" not in livescan._woanders(IN_SET),
       "beim gebrauchten Set steht das Wort nicht da")
pruefe(not livescan._schon_da({"wanted": 1}),
       "ein Wunsch allein färbt nicht grün")

# Die Zeile darunter beantwortet „habe ich das?" – und nennt die Liste.
pruefe("2× in deiner Sammlung" in livescan._besitz_zeile({"owned": 2})["text"],
       "Besitz steht als Besitz da")
pruefe("Flohmarkt 30.08." in livescan._besitz_zeile(AUF_LISTE)["text"],
       "ohne Besitz, aber auf einer Liste -> die Liste steht da")
pruefe("noch nicht" not in livescan._besitz_zeile(AUF_LISTE)["text"],
       "und nicht mehr »noch nicht in deiner Sammlung«")
zwei = livescan._besitz_zeile({"on_lists": ["A", "B"]})["text"]
pruefe("2 Einkaufslisten" in zwei and "A, B" in zwei,
       "bei mehreren Listen stehen Anzahl und Namen da")
pruefe("noch nicht in deiner Sammlung" in livescan._besitz_zeile(IN_SET)["text"],
       "ein eigenes Set ändert an der Antwort nichts")

# Und die Liste steht nur noch an einer Stelle.
pruefe("🛒" not in livescan._woanders(AUF_LISTE),
       "die Zeile darunter wiederholt die Liste nicht")
pruefe("7931-1" in livescan._woanders(IN_SET),
       "das eigene Set steht weiterhin als Hinweis darunter")

# ============================================ Immer vorn abschaltbar
# Das Fenster liegt über allem - dafür ist es da. Aber Fenster anderer
# Programme gingen dahinter auf und blieben unauffindbar. Der Haken nimmt
# die Ebene weg, ohne den Standard zu ändern.
abschnitt("9c. Der Haken »Immer vorn«")
wurzel, app = fenster()
pruefe(app.immer_vorn.get() is True, "voreingestellt liegt es vorn")
pruefe(wurzel.attributes("-topmost") in (1, True),
       "und das Fenster steht auch wirklich oben")

app.immer_vorn.set(False)
app._vorn_merken()
takt(wurzel, 150)
pruefe(wurzel.attributes("-topmost") in (0, False),
       "Haken weg -> das Fenster gibt die Ebene frei")
pruefe(app.daten.get("immer_vorn") is False,
       "und die Wahl überlebt den Neustart")

# Nach einem Popup darf die Ebene nicht heimlich zurückkommen.
app.immer_vorn.set(False)
wurzel.attributes("-topmost", False)
app._vorn_merken()
takt(wurzel, 120)
pruefe(wurzel.attributes("-topmost") in (0, False),
       "auch nach dem Schließen eines Popups bleibt sie weg")

app.immer_vorn.set(True)
app._vorn_merken()
takt(wurzel, 120)
pruefe(wurzel.attributes("-topmost") in (1, True),
       "Haken wieder dran -> wieder oben")
wurzel.destroy()

# ==================================================== Hilfe-Menue
# macOS legt den Hilfe-Eintrag von sich aus an. Ohne hinterlegten Befehl
# antwortet es "Help isn't available for Brickfolio Live-Scanner" - genau
# so aufgetreten am 30.08.2026.
abschnitt("10. Die Hilfe zeigt das Handbuch")
_w = tk.Tk(); _w.withdraw()
_w.createcommand("::tk::mac::ShowHelp", livescan.handbuch_zeigen)
pruefe(_w.eval("info commands ::tk::mac::ShowHelp").strip() != "",
       "der Befehl haengt am Hilfe-Menue")
_w.destroy()

pruefe(livescan.handbuch_pfad() is not None,
       "das Handbuch wird neben dem Quelltext gefunden")
pruefe(os.path.basename(livescan.handbuch_pfad()) == "README.md",
       "und es ist das README")
# Die Probe oben meldet den Befehl selbst an - sie wuerde also auch
# bestehen, wenn main() das Anmelden vergisst. Darum hier zusaetzlich in
# den Quelltext geschaut.
_scan_roh = pathlib.Path(livescan.__file__).read_text()
_ab_main = _scan_roh[_scan_roh.index("def main():"):]
pruefe('createcommand("::tk::mac::ShowHelp"' in _ab_main,
       "main() meldet den Hilfe-Befehl auch wirklich an")

_bau_roh = pathlib.Path(__file__).with_name("bauen.sh").read_text()
pruefe("codesign --force --sign" in _bau_roh,
       "bauen.sh unterschreibt das Buendel")
pruefe('IDENT="-"' in _bau_roh,
       "und faellt ohne Zertifikat auf ad hoc zurueck, statt abzubrechen")
# `--deep` prueft die eingebetteten Teile vor dem Neu-Unterschreiben und
# bricht ab, sobald eines nicht streng gueltig ist - meldet das, gibt aber
# 0 zurueck und laesst die App ad hoc. So ist 1.1.0 beinahe unsigniert
# hinausgegangen. Deshalb von innen nach aussen, und nachsehen statt hoffen.
# Auf den Befehl schauen, nicht auf den Text: Der Kommentar daneben
# erklaert ja gerade, warum --deep nicht taugt, und enthaelt das Wort.
pruefe("--deep --sign" not in _bau_roh,
       "bauen.sh unterschreibt nicht mehr mit --deep")
pruefe("certificate root" in _bau_roh,
       "und prüft hinterher nach, ob das Zertifikat wirklich drauf ist")
_setup_roh_vorab = pathlib.Path(__file__).with_name("setup.py").read_text()
pruefe('"PIL"' in _setup_roh_vorab,
       "Pillow bleibt aus dem Mac-Bündel – dort wird es nie gebraucht")

_setup_roh = pathlib.Path(__file__).with_name("setup.py").read_text()
pruefe('"README.md"' in _setup_roh,
       "das Buendel nimmt das Handbuch mit - sonst zeigt die Hilfe im\n"
       "       fertigen Programm ins Leere")

# ================================================ Bauvorschrift
# Die Fassung steht in livescan.py; setup.py schreibt sie ins Info.plist des
# Bündels. Läuft das auseinander, zeigt die fertige App eine falsche Nummer –
# und niemand merkt es, weil nichts abstürzt. Darum hier eine Wache.
import re as _re

_setup = pathlib.Path(__file__).with_name("setup.py").read_text()
pruefe('re.search(r\'^VERSION = "([^"]+)"\'' in _setup,
       "setup.py liest die Fassung aus livescan.py, statt sie zu wiederholen")
pruefe(_re.match(r"^\d+\.\d+\.\d+$", livescan.VERSION) is not None,
       "die Fassung hat die Form 1.2.3")
_icns = pathlib.Path(__file__).with_name("livescan.icns")
pruefe(_icns.exists() and _icns.stat().st_size > 1000,
       "das Symbol fürs Bündel liegt bei")
# py2app zieht tkinter nur mit, wenn es ausdrücklich dabeisteht.
pruefe('"packages": ["tkinter"]' in _setup,
       "setup.py nimmt tkinter ausdrücklich mit")

# ============================================== Instanz hinter Cloudflare
# Steht die Instanz hinter Cloudflare Access, kommt statt JSON eine
# Anmeldeseite. Die kann dieses Werkzeug nicht ausfüllen – es muss also
# einen Dienst-Token mitschicken und, wenn der fehlt, verständlich sagen,
# was los ist. »Unerwartete Antwort der Instanz« schickt in die Irre.
abschnitt("10b. Instanz hinter Cloudflare Access")

_i = livescan.Instanz("https://beispiel.test", "tok", "kennung", "geheim")


class _Antrag:
    """Fängt ab, was der Scanner senden würde."""

    def __init__(self):
        self.kopf = {}


_gesehen = {}


def _falscher_oeffner(antrag, timeout=None):
    _gesehen["kopf"] = dict(antrag.headers)
    raise urllib.error.HTTPError(
        antrag.full_url, 302, "Found",
        {"Location": "https://firma.cloudflareaccess.com/cdn-cgi/access/"
                     "login/beispiel.test?kid=abc"}, None)


_echt = livescan._OEFFNER.open
livescan._OEFFNER.open = _falscher_oeffner
try:
    try:
        _i._anfrage("/api/health")
        _meldung = ""
    except livescan.Fehler as _e:
        _meldung = str(_e)
finally:
    livescan._OEFFNER.open = _echt

# urllib schreibt Kopfzeilen in Titel-Schreibweise.
_kopf = {k.lower(): v for k, v in _gesehen.get("kopf", {}).items()}
pruefe(_kopf.get("Cf-access-client-id".lower()) == "kennung",
       "die Client-ID geht mit")
pruefe(_kopf.get("Cf-access-client-secret".lower()) == "geheim",
       "das Client-Secret auch")
pruefe(_kopf.get("authorization") == "Bearer tok",
       "und der eigene Token bleibt daneben bestehen")
pruefe("Brickfolio-Live-Scanner/" in _kopf.get("user-agent", ""),
       "der Scanner sagt, wer er ist – sonst weist Cloudflares Bot-Schutz "
       "ihn ab,\n       bevor Access überhaupt zum Zuge kommt")
pruefe("Cloudflare Access" in _meldung and "Dienst-Token" in _meldung,
       "und die Umleitung wird beim Namen genannt")
pruefe("Unerwartete Antwort" not in _meldung,
       "statt »Unerwartete Antwort der Instanz«, was in die Irre führt")

# Ohne Dienst-Token gehen die beiden Kopfzeilen gar nicht erst mit.
_ohne = livescan.Instanz("https://beispiel.test", "tok")
livescan._OEFFNER.open = _falscher_oeffner
try:
    try:
        _ohne._anfrage("/api/health")
    except livescan.Fehler:
        pass
finally:
    livescan._OEFFNER.open = _echt
_kopf2 = {k.lower() for k in _gesehen.get("kopf", {})}
pruefe("cf-access-client-id" not in _kopf2,
       "ohne Dienst-Token bleiben die Kopfzeilen weg")

# --- Der zweite Weg: eine Sitzung von cloudflared -----------------------
# Hier ist cloudflared nicht installiert. Also eine Attrappe – und die
# wird hinterher **zurückgegeben**, sonst sieht eine spätere Probe sie
# statt der echten Funktion. Genau das ist heute schon einmal passiert.
_JWT = "kopf.inhalt.unterschrift"


def _ist_cloudflared(befehl):
    """Seit die App das Werkzeug selbst sucht, steht dort der volle Pfad –
    »cloudflared« allein trifft nicht mehr."""
    return bool(befehl) and os.path.basename(
        str(befehl[0])).startswith("cloudflared")


class _Fertig:
    """Was subprocess.run zurückgibt – so viel davon, wie hier gebraucht
    wird. `stderr` gehört dazu: cf_anmelden liest es, wenn keine Sitzung
    zustande kam."""

    def __init__(self, aus, code=0, fehler=""):
        self.stdout, self.returncode, self.stderr = aus, code, fehler


_rufe = []
_echt_run = livescan.subprocess.run


def _falsches_cloudflared(befehl, **k):
    _rufe.append(befehl)
    if _ist_cloudflared(befehl):
        return _Fertig(_JWT + "\n")
    return _echt_run(befehl, **k)


# **Nicht davon abhängen, ob cloudflared auf dieser Maschine liegt.**
# Auf den Bau-Runnern liegt es nicht; die Suche gäbe dann "" zurück und
# die Attrappe käme nie zum Zug – die Probe fiel durch, obwohl am
# Programm nichts falsch war. Also auch die Suche vorgeben.
_echt_finden = livescan.cloudflared_finden
livescan.cloudflared_finden = lambda: "/irgendwo/cloudflared"

livescan.subprocess.run = _falsches_cloudflared
try:
    _c = livescan.Instanz("https://beispiel.test", "tok")
    _k = _c._cf_kopfzeilen()
    pruefe(_k.get("cf-access-token") == _JWT,
           "die Sitzung von cloudflared geht als Kopfzeile mit")
    pruefe(_k.get("Cookie") == "CF_Authorization=" + _JWT,
           "und zusätzlich als Cookie, wie im Browser")

    _vorher = len(_rufe)
    _c._cf_kopfzeilen()
    pruefe(len(_rufe) == _vorher,
           "beim zweiten Mal wird cloudflared nicht erneut gefragt –\n"
           "       ein Unterprozess je Bild wäre spürbar")

    # Im Heimnetz steht kein Access davor; dort hat cloudflared nichts zu
    # suchen und wird gar nicht erst gerufen.
    _vorher = len(_rufe)
    _lan = livescan.Instanz("http://localhost:8300", "tok")
    pruefe(_lan._cf_kopfzeilen() == {},
           "bei einer Adresse ohne https bleibt es leer")
    pruefe(len(_rufe) == _vorher,
           "und cloudflared wird dafür nicht einmal gestartet")

    # Der Dienst-Token hat Vorrang – er läuft nicht ab.
    _beide = livescan.Instanz("https://beispiel.test", "tok", "kennung", "geheim")
    pruefe("CF-Access-Client-Id" in _beide._cf_kopfzeilen(),
           "liegt ein Dienst-Token vor, hat er Vorrang")
finally:
    livescan.subprocess.run = _echt_run

# Was cloudflared ohne Anmeldung ausgibt, ist kein Token.
def _keine_anmeldung(befehl, **k):
    if _ist_cloudflared(befehl):
        return _Fertig("Please run: cloudflared access login ...", 1)
    return _echt_run(befehl, **k)


livescan.subprocess.run = _keine_anmeldung
try:
    _ohne_sitzung = livescan.Instanz("https://beispiel.test", "tok")
    pruefe(_ohne_sitzung._cf_kopfzeilen() == {},
           "eine Meldung statt eines Tokens wird nicht mitgeschickt")
finally:
    livescan.subprocess.run = _echt_run

pruefe("cloudflared access login" in _meldung and "Dienst-Token" in _meldung,
       "die Fehlermeldung nennt beide Wege")

# --- Der Knopf »Über Cloudflare anmelden« -------------------------------
# Ins Terminal zu schicken war keine gute Antwort. Der Knopf startet den
# Browser-Weg selbst – und muss dabei alles abfangen, was schiefgehen kann.
_a = livescan.Instanz("http://localhost:8300")
_geschafft, _m = _a.cf_anmelden()
pruefe(not _geschafft and "https" in _m,
       "ohne https lehnt er ab – im Heimnetz steht kein Cloudflare davor")


def _kein_cloudflared(befehl, **k):
    if _ist_cloudflared(befehl):
        raise FileNotFoundError(2, "No such file", "cloudflared")
    return _echt_run(befehl, **k)


livescan.subprocess.run = _kein_cloudflared
try:
    _geschafft, _m = livescan.Instanz("https://beispiel.test").cf_anmelden()
    pruefe(not _geschafft and "brew install cloudflared" in _m,
           "fehlt cloudflared, sagt er, wie man es bekommt")
finally:
    livescan.subprocess.run = _echt_run


def _login_ohne_sitzung(befehl, **k):
    if _ist_cloudflared(befehl):
        # Anmeldung bricht ab: kein Token hinterher.
        return _Fertig("", 1) if befehl[2] == "token" else _Fertig("abgebrochen", 1)
    return _echt_run(befehl, **k)


livescan.subprocess.run = _login_ohne_sitzung
try:
    _geschafft, _m = livescan.Instanz("https://beispiel.test").cf_anmelden()
    pruefe(not _geschafft and "keine Sitzung" in _m,
           "meldet er Erfolg, ohne dass eine Sitzung entstand, glauben wir\n"
           "       ihm nicht – nachgesehen wird an der Sitzung selbst")
finally:
    livescan.subprocess.run = _echt_run


def _login_klappt(befehl, **k):
    if _ist_cloudflared(befehl) and befehl[2] == "login":
        return _Fertig("Successfully fetched your token", 0)
    if _ist_cloudflared(befehl) and befehl[2] == "token":
        return _Fertig(_JWT + "\n", 0)
    return _echt_run(befehl, **k)


livescan.subprocess.run = _login_klappt
try:
    _geschafft, _m = livescan.Instanz("https://beispiel.test").cf_anmelden()
    pruefe(_geschafft and "Angemeldet" in _m,
           "und wenn eine Sitzung da ist, ist es geschafft")
finally:
    livescan.subprocess.run = _echt_run

# Der Knopf darf die Oberfläche nicht einfrieren – der Befehl wartet ja,
# bis jemand im Browser fertig ist.
_scan_roh_cf = pathlib.Path(livescan.__file__).read_text()
_ab_zugang = _scan_roh_cf[_scan_roh_cf.index("def zugang_zeigen"):]
_ab_zugang = _ab_zugang[:_ab_zugang.index("def nummerfeld_zeigen")]
pruefe("threading.Thread" in _ab_zugang,
       "der Knopf wartet in einem eigenen Faden")
pruefe("f.after(0, fertig" in _ab_zugang,
       "und meldet das Ergebnis zurück in den Hauptfaden")

# --- cloudflared finden, nicht hoffen ----------------------------------
# Eine App aus dem Programme-Ordner erbt nicht die Pfade der Shell:
# /opt/homebrew/bin steht dort nicht drin. »cloudflared« galt deshalb als
# nicht installiert, obwohl es lag – am 31.08.2026 genau so passiert.
livescan.cloudflared_finden = _echt_finden

pruefe("shutil.which" in _scan_roh_cf and "/opt/homebrew/bin" in _scan_roh_cf,
       "die Suche schaut an den üblichen Orten nach, nicht nur im Suchpfad")
pruefe("Resources" in _scan_roh_cf.split("def cloudflared_finden")[1][:900],
       "und zuerst im eigenen Bündel – das ist immer da")
_setup_cf = pathlib.Path(__file__).with_name("setup.py").read_text()
pruefe("_cloudflared()" in _setup_cf,
       "das Bündel nimmt cloudflared mit – niemand soll etwas nachinstallieren")
pruefe(pathlib.Path(__file__).with_name("THIRD-PARTY.md").exists(),
       "und die Lizenz liegt dabei, wie Apache-2.0 es verlangt")

# --- Auch das Katalogbild muss durch Cloudflare -------------------------
# Es wurde mit einem nackten urlopen geholt – ohne Kennung, ohne
# Dienst-Token, ohne Sitzung. Hinter Cloudflare Access blieb es leer, und
# das `except` machte daraus ein stilles »kein Katalogbild«. Am 31.08.2026
# genau so aufgetreten, nachdem der Scan selbst längst durchging.
_bild_kopf = {}


def _bild_oeffner(antrag, timeout=None):
    _bild_kopf.update(dict(antrag.headers))
    raise urllib.error.HTTPError(antrag.full_url, 500, "egal", {}, None)


_echt_open = livescan._OEFFNER.open
livescan._OEFFNER.open = _bild_oeffner
try:
    livescan.Instanz("https://beispiel.test", "tok", "kennung",
                     "geheim").katalogbild("/bild.jpg")
finally:
    livescan._OEFFNER.open = _echt_open

_bk = {k.lower(): v for k, v in _bild_kopf.items()}
pruefe(_bk.get("cf-access-client-id") == "kennung",
       "das Katalogbild trägt den Dienst-Token mit")
pruefe("Brickfolio-Live-Scanner/" in _bk.get("user-agent", ""),
       "und die eigene Kennung – sonst blockt schon der Bot-Schutz")

# ======================================= Der Rahmen trifft, was man sieht
# Hier sass der Fehler vom 31.08.2026: Auf einem Windows-Laptop mit
# zweitem Monitor markierte man eine Stelle und fotografiert wurde eine
# ganz andere. Drei Annahmen waren schuld, alle drei stehen hier als Probe.
abschnitt("9d. Aus dem Rahmen wird ein Bildschirmausschnitt")

# 1:1 – ohne Skalierung, ein Bildschirm. Der einfachste Fall.
pruefe(livescan.auswahl_umrechnen(100, 50, 300, 250, 1.0, 1.0)
       == (100, 50, 200, 200),
       "ohne Skalierung kommt heraus, was man gezogen hat")

# Rückwärts gezogen – von rechts unten nach links oben.
pruefe(livescan.auswahl_umrechnen(300, 250, 100, 50, 1.0, 1.0)
       == (100, 50, 200, 200),
       "und rückwärts gezogen dasselbe")

# **150 % Skalierung.** Der alte Code rundete den Faktor auf 2 – der
# Ausschnitt sass um ein Drittel daneben.
pruefe(livescan.auswahl_umrechnen(100, 100, 300, 300, 1.5, 1.5)
       == (150, 150, 300, 300),
       "bei 150 % wird mit 1,5 gerechnet, nicht mit 2")
pruefe(livescan.auswahl_umrechnen(100, 100, 300, 300, 1.25, 1.25)
       == (125, 125, 250, 250),
       "und bei 125 % mit 1,25")

# **Zweiter Monitor links.** Der Ursprung des Desktops ist die linke obere
# Ecke des Hauptbildschirms – links davon wird x negativ.
pruefe(livescan.auswahl_umrechnen(10, 20, 110, 120, 1.0, 1.0,
                                  ursprung=(-1920, 0))
       == (-1910, 20, 100, 100),
       "auf dem Monitor links vom ersten wird x negativ")

# Beides zusammen – der Fall, der es aufgedeckt hat.
_erg = livescan.auswahl_umrechnen(200, 100, 400, 300, 1.5, 1.5,
                                  ursprung=(-2560, -140))
pruefe(_erg == (-2260, 10, 300, 300),
       "und beides zusammen: skalierter Zweitmonitor links oben")

# Ein Klick ist kein Bereich.
pruefe(livescan.auswahl_umrechnen(100, 100, 105, 105, 1.0, 1.0) is None,
       "ein versehentlicher Klick ergibt keinen Bereich")
pruefe(livescan.auswahl_umrechnen(100, 100, 400, 105, 1.0, 1.0) is None,
       "und ein Strich auch nicht")

# Die Aufnahme muss über *alle* Bildschirme gehen – sonst zeigt die
# Vorschau zwei Monitore und der Ausschnitt kommt vom ersten.
_roh_scan = pathlib.Path(livescan.__file__).read_text()
pruefe("ImageGrab.grab(all_screens=True)" in _roh_scan,
       "das Abbild kommt von allen Bildschirmen, nicht nur vom ersten")
pruefe("GetSystemMetrics" in _roh_scan,
       "und die Maße des ganzen Desktops werden erfragt")

# **Der Kern der Sache.** Ohne DPI-Bewusstsein liefert Windows logische
# Maße, während ImageGrab echte Bildpunkte liefert. Bei einem Bildschirm
# fällt das kaum auf, bei zweien mit verschiedener Skalierung geht die
# eine Achse auf und die andere nicht. Das trifft jeden, nicht nur einen
# bestimmten Rechner – deshalb hier festgenagelt.
pruefe("SetProcessDpiAwarenessContext" in _roh_scan,
       "der Scanner meldet sich als DPI-bewusst an")
pruefe("SetProcessDPIAware" in _roh_scan,
       "mit Rückfallweg für ältere Windows-Fassungen")
_ab_main_dpi = _roh_scan[_roh_scan.index("def main():"):]
_vor_fenster = _ab_main_dpi[:_ab_main_dpi.index("tk.Tk()")]
pruefe("windows_dpi_beachten()" in _vor_fenster,
       "und zwar **vor** dem ersten Fenster – danach nimmt Windows es\n"
       "       nicht mehr an")
pruefe('"tk", "scaling"' in _roh_scan,
       "dafür wächst die Schrift selbst mit, sonst steht alles winzig da")
pruefe("EnumDisplayMonitors" in _roh_scan,
       "und die Bildschirme werden aufgezählt – für die Zahlenzeile")

# ============================ Trifft der Ausschnitt wirklich dieselbe Stelle?
# Die Rechnung oben prüft sich selbst – aber ob sie auch zum Betriebssystem
# passt, sagt nur ein Versuch: ganzen Schirm aufnehmen, einen Bereich daraus
# holen, beides vergleichen. Braucht Pillow und die Freigabe für
# Bildschirmaufnahmen; fehlt eines davon, entfällt die Probe sichtbar.
abschnitt("9e. Der Ausschnitt sitzt wirklich dort")

if _PIL is None:
    print("     (Pillow fehlt – der Vergleich am echten Bildschirm entfällt)")
else:
    _voll = os.path.join(tempfile.gettempdir(), "pruefung-voll.png")
    if not livescan.schirmfoto(_voll):
        print("     (keine Bildschirmaufnahme möglich – Probe entfällt)")
    else:
        from PIL import ImageChops as _Chops
        with _PIL.open(_voll) as _b:
            _bb, _bh = _b.size
        if livescan.IST_WINDOWS:
            _ux, _uy, _db, _dh = livescan.windows_desktop()
        else:
            _ux, _uy, _db, _dh = livescan.mac_desktop()
        pruefe(_db > 0 and _dh > 0,
               "die Maße aller Bildschirme lassen sich erfragen")

        _ber = (_ux + 600, _uy + 400, 400, 300)
        _s = _bb / float(_db)

        def _abstand():
            """Wie weit Ausschnitt und Vollbild auseinanderliegen.

            **Beide Aufnahmen aus demselben Anlauf.** Ein einmal
            aufgenommenes Vollbild veraltet: Geht zwischendurch ein Fenster
            auf, weichen alle folgenden Vergleiche ab, und Wiederholen
            hilft nicht mehr.
            """
            if not livescan.schirmfoto(_voll):
                return None
            roh = livescan.bereich_aufnehmen(_ber)
            if not roh:
                return None
            with _PIL.open(io.BytesIO(roh)) as a:
                aus_bild = a.convert("RGB")
                with _PIL.open(_voll) as v:
                    schnitt = v.crop((
                        int((_ber[0] - _ux) * _s), int((_ber[1] - _uy) * _s),
                        int((_ber[0] - _ux + _ber[2]) * _s),
                        int((_ber[1] - _uy + _ber[3]) * _s))).convert("RGB")
                d = _Chops.difference(schnitt, aus_bild.resize(schnitt.size))
                return sum(
                    sum(d.split()[k].histogram()[i] * i for i in range(256))
                    for k in range(3)) / float(schnitt.size[0]
                                               * schnitt.size[1] * 3)

        # **Dreimal, und der beste Versuch zählt.** Zwischen Vollbild und
        # Ausschnitt vergeht Zeit, und der Bildschirm steht nicht still –
        # eine Uhr, ein blinkender Cursor, eine scrollende Ausgabe. Sitzt
        # die Rechnung richtig, liegt der Abstand bei 1; sitzt sie falsch,
        # bei 69. Zwischen diesen beiden Zahlen ist so viel Luft, dass ein
        # Wiederholen die Aussage nicht verwässert.
        _versuche = [_abstand() for _ in range(3)]
        pruefe(any(v is not None for v in _versuche),
               "ein Bereich daraus lässt sich aufnehmen")
        _mittel = min(v for v in _versuche if v is not None)
        print("     mittlere Abweichung: %.1f von 255  (aus %s)"
              % (_mittel, ", ".join("%.1f" % v for v in _versuche
                                    if v is not None)))
        # **25 ist kein Kompromiss, sondern der Abstand zwischen zwei
        # Welten.** Sitzt die Rechnung, liegt der Wert bei 1 bis 5 – der
        # Rest ist eine wandernde Uhr. Sitzt sie um 200 Punkte daneben,
        # liegt er bei 69. Zwischen 5 und 69 ist so viel Luft, dass ein
        # unruhiger Bildschirm keinen Fehlalarm auslösen kann.
        pruefe(_mittel < 25,
               "der aufgenommene Bereich zeigt dieselbe Stelle wie das\n"
               "       Vollbild – die Umrechnung passt zum Betriebssystem")
        try:
            os.remove(_voll)
        except OSError:
            pass

# ==================================================== Der Windows-Weg
# Der Mac-Weg bleibt unangetastet; fuer Windows stehen eigene Zweige
# daneben. Sie lassen sich hier pruefen, indem die Weiche umgelegt wird -
# die Bildarbeit haengt nur an Pillow, nicht am Betriebssystem.
abschnitt("11. Der Windows-Weg")

pruefe(livescan.IST_WINDOWS == sys.platform.startswith("win"),
       "die Weiche erkennt das System richtig")
_ico = pathlib.Path(__file__).with_name("livescan.ico")
pruefe(_ico.exists() and _ico.stat().st_size > 1000,
       "das Windows-Symbol liegt bei")
_scan_roh = pathlib.Path(livescan.__file__).read_text()
pruefe("winsound" in _scan_roh, "der Ton hat einen Windows-Zweig")
pruefe("System.Windows.Forms.Clipboard" in _scan_roh,
       "die Zwischenablage auch")
pruefe("ImageGrab" in _scan_roh, "und die Bildschirmaufnahme")
# Tk kennt nicht ueberall dieselben Mauszeiger. »pointinghand« gibt es nur
# auf dem Mac; Windows bricht mit »bad cursor spec« ab - und zwar beim
# Aufbau des Fensters, also sofort und vollstaendig.
pruefe('cursor="pointinghand"' not in _scan_roh,
       "kein mac-eigener Mauszeiger fest verdrahtet")

if _PIL is None:
    print("     (Pillow fehlt – die Bildproben des Windows-Wegs bleiben aus)")
else:
    _vorher = livescan.IST_WINDOWS
    livescan.IST_WINDOWS = True
    try:
        _puffer = io.BytesIO()
        _PIL.new("RGB", (300, 200), (200, 30, 30)).save(_puffer, format="JPEG")
        _jpeg = _puffer.getvalue()
        pruefe(livescan.als_png(_jpeg)[:4] == b"\x89PNG",
               "JPEG wird zu PNG – Tk zeigt nichts anderes")

        _puffer = io.BytesIO()
        _PIL.new("RGB", (300, 200), (30, 200, 30)).save(_puffer, format="PNG")
        _png = _puffer.getvalue()
        _klein = livescan.auf_groesse(_png, 100)
        with _PIL.open(io.BytesIO(_klein)) as _b:
            pruefe(max(_b.size) == 100,
                   "auf_groesse trifft die längste Kante genau")
            pruefe(_b.size == (100, 66) or _b.size == (100, 67),
                   "und behält das Seitenverhältnis")

        _f = livescan.fingerabdruck(_png, 8)
        pruefe(_f is not None and len(_f) == 64,
               "der Fingerabdruck liefert 8×8 Helligkeitswerte")
        pruefe(all(0 <= w <= 255 for w in _f),
               "und die liegen im gültigen Bereich")
        pruefe(livescan.abweichung(_f, _f) == 0,
               "gleiches Bild -> keine Abweichung")

        _puffer = io.BytesIO()
        _PIL.new("RGB", (300, 200), (0, 0, 0)).save(_puffer, format="PNG")
        _dunkel = livescan.fingerabdruck(_puffer.getvalue(), 8)
        pruefe(livescan.abweichung(_f, _dunkel) > 10,
               "anderes Bild -> deutliche Abweichung")
    finally:
        livescan.IST_WINDOWS = _vorher

# ============================================ Hinweis auf neue Fassungen
# Ein Werkzeug für Auktions-Streams darf sich nicht in den Vordergrund
# spielen. Die Zeile erscheint nur, wenn es wirklich etwas Neues gibt –
# und schweigt bei jedem Problem, statt über sich selbst zu klagen.
abschnitt("12. Hinweis auf eine neuere Fassung")

pruefe(livescan.fassungszahlen("v1.5.2") == (1, 5, 2),
       "»v1.5.2« wird zu (1, 5, 2)")
pruefe(livescan.fassungszahlen("1.5") == (1, 5, 0),
       "Fehlendes wird zu Null ergänzt")
pruefe(livescan.fassungszahlen("kaputt") == (0, 0, 0),
       "und Unlesbares stürzt nicht ab")
pruefe(livescan.fassungszahlen("1.9.0") < livescan.fassungszahlen("1.10.0"),
       "1.10.0 ist neuer als 1.9.0 – als Text verglichen wäre es umgekehrt")

# **Die Update-Prüfung fragt nicht die API.** Die erlaubt ohne Anmeldung
# 60 Abfragen je Stunde und Anschluss – am 25.09.2026 standen sie auf 0,
# und der Hinweis auf 1.9.0 blieb aus. Gefragt wird die Release-Seite.
_echt_urlopen = livescan.urllib.request.urlopen
_echt_weiter = livescan.weiterleitung
_gefragt = []
_mit_paket = True


def _seite(adresse, jetzt=""):
    _gefragt.append(adresse)
    if adresse.endswith("/releases/latest"):
        return 302, ("https://github.com/%s/releases/tag/v9.9.9"
                     % livescan.REPO)
    if "/releases/download/v9.9.9/" in adresse:
        return (302 if _mit_paket else 404), ""
    return 404, ""


def _api_verboten(antrag, timeout=None):
    raise AssertionError("die API wurde gefragt")


livescan.urllib.request.urlopen = _api_verboten
livescan.weiterleitung = _seite
try:
    _neu = livescan.neuere_fassung("1.9.0")
    pruefe(_neu is not None and _neu[0] == "9.9.9",
           "die Release-Seite nennt die neue Fassung")
    pruefe(_neu[1].endswith("/releases/tag/v9.9.9"), "samt Seite")
    pruefe(_neu[2].endswith("/releases/download/v9.9.9/"
                            + livescan.paket_namen()[0]),
           "und dem Paket für dieses System")
    pruefe(not any("api.github.com" in a for a in _gefragt),
           "die API wird nicht gefragt")
    # Repo umbenannt: GitHub schiebt eine Stufe dazwischen. Ohne das
    # Mitgehen meldete der Scanner stillschweigend „du bist aktuell" —
    # für immer, ohne Fehler. Nachgestellt wie bei facebook/jest.
    # Bewusst mit erfundenen Ordnernamen, nicht mit `livescan.REPO`: Sonst
    # zeigt die Attrappe auf sich selbst, sobald der echte Ordner einmal
    # umbenannt wurde - und der Test misst nur noch sich selbst.
    _ALT_ORDNER = "Melle79/alter-ordner"
    _NEU_ORDNER = "Melle79/neuer-ordner"

    def _seite_umbenannt(adresse, jetzt=""):
        _gefragt.append(adresse)
        if adresse == "https://github.com/%s/releases/latest" % livescan.REPO:
            return 301, "https://github.com/%s/releases/latest" % _NEU_ORDNER
        if adresse == "https://github.com/%s/releases/latest" % _NEU_ORDNER:
            return 302, ("https://github.com/%s/releases/tag/v9.9.9"
                         % _NEU_ORDNER)
        if "/releases/download/v9.9.9/" in adresse:
            # Wie GitHub es wirklich tut: weiter an den Ablageort.
            return 302, "https://objects.githubusercontent.com/irgendwo"
        return 404, ""

    livescan.weiterleitung = _seite_umbenannt
    _umb = livescan.neuere_fassung("1.9.0")
    pruefe(_umb is not None and _umb[0] == "9.9.9",
           "nach einer Repo-Umbenennung wird die neue Fassung noch gefunden")

    # **Der Fehler, der am 30.09.2026 draussen war.** Nach der Umbenennung
    # des Ordners beantwortet GitHub auch die Adresse eines NICHT
    # vorhandenen Pakets mit 301 auf den neuen Ordner. Wer das fuer „ist
    # da" haelt, hoert beim ersten Namen auf zu suchen und laedt
    # anschliessend eine 404 - der Rueckfall auf den alten Namen kaeme nie
    # zum Zug.
    _neuer, _alter = livescan.paket_namen()

    def _paket_fehlt_hinter_umleitung(adresse, jetzt=""):
        _gefragt.append(adresse)
        if adresse.endswith("/releases/latest"):
            return 302, ("https://github.com/%s/releases/tag/v9.9.9"
                         % livescan.REPO)
        if _neuer in adresse:
            # Gibt es nicht - aber der Ordner wurde umbenannt.
            if "/alter-ordner/" in adresse:
                return 404, ""
            return 301, ("https://github.com/Melle79/alter-ordner"
                         "/releases/download/v9.9.9/" + _neuer)
        if _alter in adresse:
            return 302, "https://objects.githubusercontent.com/irgendwo"
        return 404, ""

    livescan.weiterleitung = _paket_fehlt_hinter_umleitung
    _fall = livescan.neuere_fassung("1.9.0")
    pruefe(_fall is not None and _fall[2].endswith(_alter),
           "eine 301 auf ein fehlendes Paket gilt nicht als vorhanden")
    livescan.weiterleitung = _seite

    def _endlos(adresse, jetzt=""):
        return 301, "https://github.com/Melle79/immer-weiter/releases/latest"

    livescan.weiterleitung = _endlos
    pruefe(livescan.neuere_fassung("1.9.0") is None,
           "eine Weiterleitungsschleife endet, statt sich festzufressen")
    livescan.weiterleitung = _seite

    # Die Umbenennung von Brickfolio auf Nupplo: Hängt am Release nur noch
    # der ALTE Name, muss die Selbsterneuerung ihn trotzdem finden. Ohne
    # diesen Rückfall bliebe jede bestehende Installation auf ihrer Fassung
    # sitzen, sobald die Pakete umbenannt sind.
    _nur_alter = [False]

    def _seite_nur_alter(adresse, jetzt=""):
        _gefragt.append(adresse)
        if adresse.endswith("/releases/latest"):
            return 302, ("https://github.com/%s/releases/tag/v9.9.9"
                         % livescan.REPO)
        if adresse.endswith("/releases/download/v9.9.9/" + _alter):
            return 302, ""
        return 404, ""

    livescan.weiterleitung = _seite_nur_alter
    _rueck = livescan.neuere_fassung("1.9.0")
    pruefe(_rueck is not None and _rueck[2].endswith(_alter),
           "trägt das Release nur den alten Paketnamen, wird er gefunden")
    pruefe(_neuer != _alter and _neuer.startswith("Nupplo-"),
           "und der neue Name wird zuerst versucht")
    livescan.weiterleitung = _seite

    _mit_paket = False
    pruefe(livescan.neuere_fassung("1.9.0")[2] == "",
           "hängt das Paket noch nicht dran, bleibt es leer statt zu scheitern")
    pruefe(livescan.neuere_fassung("9.9.9") is None,
           "die eigene Fassung ist kein Grund für einen Hinweis")
    pruefe(livescan.neuere_fassung("10.0.0") is None,
           "und eine ältere draußen erst recht nicht")
    livescan.weiterleitung = lambda a, j="": (200, "")
    pruefe(livescan.neuere_fassung("1.0.0") is None,
           "ohne Weiterleitung schweigt sie")

    def _kein_netz(a, j=""):
        raise OSError("kein Netz")
    livescan.weiterleitung = _kein_netz
    pruefe(livescan.neuere_fassung("1.0.0") is None,
           "ohne Netz schweigt sie, statt zu stören")
finally:
    livescan.urllib.request.urlopen = _echt_urlopen
    livescan.weiterleitung = _echt_weiter
pruefe("api.github.com" not in pathlib.Path(livescan.__file__).read_text(),
       "im Scanner steht keine API-Adresse mehr")

_roh_upd = pathlib.Path(livescan.__file__).read_text()
pruefe("daemon=True" in _roh_upd.split("_update_pruefen")[1][:200],
       "die Abfrage läuft im Hintergrund – der Start wartet nicht darauf")
pruefe("updates_pruefen" in _roh_upd,
       "und sie lässt sich in den Einstellungen abschalten")

# ------------------------------------------------- Wo wir selbst liegen
pruefe(livescan.eigener_ort("/Programme/Scanner.app/Contents/MacOS/Scanner",
                            "macosx_app") == "/Programme/Scanner.app",
       "im Bündel führen drei Ebenen hinauf zur App")
pruefe(livescan.eigener_ort("/wo/anders/Scanner", "macosx_app") == "",
       "was nicht in einem Bündel liegt, wird nicht angerührt")
pruefe(livescan.eigener_ort(r"C:\Prog\Scanner\Scanner.exe", True)
       == r"C:\Prog\Scanner",
       "unter Windows ist es der Ordner um die Programmdatei")
pruefe(livescan.eigener_ort("/egal/livescan.py", None) == "",
       "aus dem Quelltext gestartet gibt es nichts zu ersetzen")

# ------------------------------------------------- Auspacken und prüfen
_upd = os.path.join(ORDNER, "upd")
os.makedirs(_upd, exist_ok=True)
if livescan.IST_WINDOWS:
    _drin = os.path.join(_upd, "drin")
    os.makedirs(_drin, exist_ok=True)
    pathlib.Path(_drin, "Brickfolio Live-Scanner.exe").write_bytes(b"MZ")
    _zip = os.path.join(_upd, "p.zip")
    import zipfile as _zf
    with _zf.ZipFile(_zip, "w") as _a:
        _a.write(os.path.join(_drin, "Brickfolio Live-Scanner.exe"),
                 "Brickfolio Live-Scanner.exe")
    _aus = livescan.paket_auspacken(_zip, os.path.join(_upd, "aus"))
    pruefe(os.path.exists(os.path.join(_aus, "Brickfolio Live-Scanner.exe")),
           "das Windows-Paket wird in den Programmordner ausgepackt")
    pruefe(livescan.paket_pruefen(_aus, _aus) == "",
           "ein Paket mit Programmdatei darf eingespielt werden")
    _leer = os.path.join(_upd, "leer")
    os.makedirs(_leer, exist_ok=True)
    pruefe(livescan.paket_pruefen(_leer, _leer) != "",
           "ein Paket ohne Programmdatei wird abgelehnt")
else:
    _app = os.path.join(_upd, "Probe.app")
    os.makedirs(os.path.join(_app, "Contents", "MacOS"), exist_ok=True)
    pathlib.Path(_app, "Contents", "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>'
        '<key>CFBundleExecutable</key><string>probe</string>'
        '<key>CFBundleIdentifier</key><string>test.probe</string>'
        '</dict></plist>\n')
    _bin = pathlib.Path(_app, "Contents", "MacOS", "probe")
    _bin.write_text("#!/bin/sh\nexit 0\n")
    _bin.chmod(0o755)
    _zip = os.path.join(_upd, "p.zip")
    subprocess.run(["ditto", "-c", "-k", "--keepParent", "--sequesterRsrc",
                    _app, _zip], check=True, capture_output=True)
    _aus = livescan.paket_auspacken(_zip, os.path.join(_upd, "aus"))
    pruefe(_aus.endswith("Probe.app") and os.path.isdir(_aus),
           "aus dem Mac-Paket kommt das Bündel heraus")
    pruefe(os.access(os.path.join(_aus, "Contents", "MacOS", "probe"), os.X_OK),
           "und die Rechte im Bündel überleben das Auspacken")

    _ohne = os.path.join(_upd, "ohne")
    os.makedirs(_ohne, exist_ok=True)
    pathlib.Path(_ohne, "nur.txt").write_text("nichts")
    _zip2 = os.path.join(_upd, "ohne.zip")
    subprocess.run(["ditto", "-c", "-k", "--keepParent", _ohne, _zip2],
                   check=True, capture_output=True)
    try:
        livescan.paket_auspacken(_zip2, os.path.join(_upd, "aus2"))
        _gemerkt = False
    except livescan.Fehler:
        _gemerkt = True
    pruefe(_gemerkt, "ein Paket ohne App wird nicht stillschweigend genommen")

    # **Der Kern**: Ohne gültige Signatur wird nichts eingespielt.
    pruefe(livescan.paket_pruefen(_aus, _aus) != "",
           "unsigniert kommt es nicht durch – so bleibt es auch, wenn "
           "jemand das Paket unterwegs austauscht")
    subprocess.run(["codesign", "--force", "-s", "-", _aus],
                   check=True, capture_output=True)
    pruefe(livescan.kennmal(_aus) != "",
           "an einem signierten Bündel steht ein Kennmal")
    pruefe(livescan.paket_pruefen(_aus, _aus) == "",
           "dasselbe Kennmal wie die laufende Fassung darf eingespielt werden")
    _fremd = os.path.join(_upd, "Fremd.app")
    subprocess.run(["ditto", _aus, _fremd], check=True, capture_output=True)
    pathlib.Path(_fremd, "Contents", "MacOS", "probe").write_text(
        "#!/bin/sh\nexit 1\n")
    subprocess.run(["codesign", "--force", "-s", "-", _fremd],
                   check=True, capture_output=True)
    pruefe(livescan.kennmal(_fremd) != livescan.kennmal(_aus),
           "ein anders signiertes Bündel trägt ein anderes Kennmal")
    pruefe(livescan.paket_pruefen(_fremd, _aus) != "",
           "und wird darum abgelehnt")

# ------------------------------------------------- Der Tausch selbst
_z = os.path.join(_upd, "ziel")
_n = os.path.join(_upd, "neu")
os.makedirs(_z, exist_ok=True)
os.makedirs(_n, exist_ok=True)
pathlib.Path(_z, "alt.txt").write_text("alt")
pathlib.Path(_n, "neu.txt").write_text("neu")
if livescan.IST_WINDOWS:
    _halt = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"],
                             stdout=subprocess.DEVNULL)
else:
    _halt = subprocess.Popen(["sleep", "60"])
_helferordner = os.path.join(_upd, "helfer")
os.makedirs(_helferordner, exist_ok=True)
livescan.tausch_starten(_z, _n, _helferordner, warten_auf=_halt.pid)
_bis = time.time() + 2.0
while time.time() < _bis:
    time.sleep(0.1)
pruefe(os.path.exists(os.path.join(_z, "alt.txt"))
       and not os.path.exists(os.path.join(_z, "neu.txt")),
       "solange der Scanner läuft, rührt der Helfer nichts an")
_halt.terminate()
_halt.wait()
_bis = time.time() + 20.0
while time.time() < _bis and not os.path.exists(os.path.join(_z, "neu.txt")):
    time.sleep(0.2)
pruefe(os.path.exists(os.path.join(_z, "neu.txt")),
       "sobald er beendet ist, steht die neue Fassung an seiner Stelle")
pruefe(not os.path.exists(os.path.join(_z, "alt.txt")),
       "und die alte ist weg, nicht danebengelegt")

# ------------------------------------------------- Das Fenster dazu
_w, _a = fenster()
try:
    _a.update_fenster("9.9.9", "https://beispiel.test/neu",
                      "https://beispiel.test/p.zip")
    _w.update()
    _oben = [k for k in _w.winfo_children() if isinstance(k, tk.Toplevel)]
    pruefe(len(_oben) == 1, "der Hinweis öffnet ein Fenster, statt den "
                            "Browser aufzureißen")

    def _beschriftungen(widget, hinein=None):
        hinein = [] if hinein is None else hinein
        for kind in widget.winfo_children():
            try:
                hinein.append(str(kind.cget("text")))
            except Exception:
                pass
            _beschriftungen(kind, hinein)
        return hinein

    _t = _beschriftungen(_oben[0])
    pruefe(any("9.9.9" in x for x in _t), "die neue Fassung steht darin")
    pruefe(any(livescan.VERSION in x for x in _t),
           "und daneben, was gerade läuft")
    pruefe("Seite öffnen" in _t and "Später" in _t,
           "Seite und Weglegen stehen zur Wahl")
    pruefe("Jetzt aktualisieren" not in _t,
           "aus dem Quelltext gestartet fehlt der Knopf – er hätte nichts "
           "zu ersetzen")
    pruefe(any("git" in x for x in _t),
           "und es steht da, warum er fehlt, statt ihn tot anzubieten")
finally:
    _w.destroy()

# Und derselbe Fall mit etwas, das sich ersetzen ließe.
_echt_ort = livescan.eigener_ort
_scheinbar = os.path.join(ORDNER, "Schein.app")
os.makedirs(_scheinbar, exist_ok=True)
livescan.eigener_ort = lambda *_a, **_k: _scheinbar
_w, _a = fenster()
try:
    _a.update_fenster("9.9.9", "https://beispiel.test/neu",
                      "https://beispiel.test/p.zip")
    _w.update()
    _oben = [k for k in _w.winfo_children() if isinstance(k, tk.Toplevel)]
    _t = _beschriftungen(_oben[0])
    pruefe("Jetzt aktualisieren" in _t,
           "wo etwas zu ersetzen ist, steht der Knopf da")
    _a.update_fenster("9.9.9", "https://beispiel.test/neu", "")
    _w.update()
    _ohne = [k for k in _w.winfo_children() if isinstance(k, tk.Toplevel)][-1]
    pruefe("Jetzt aktualisieren" not in _beschriftungen(_ohne),
           "ohne Paket wird keine Aktualisierung versprochen")
finally:
    _w.destroy()
    livescan.eigener_ort = _echt_ort

pruefe("Quarantäne" in _roh_upd.split("def update_fenster")[1][:900],
       "im Fenster steht, warum der Scanner selbst lädt statt des Browsers")
pruefe("webbrowser.open(seite)" in _roh_upd.split("def update_fenster")[1],
       "der Weg über die Seite bleibt daneben stehen")

# ============================================ Die Handschrift der App
# Eigene Knöpfe statt ttk – nach außen müssen sie sich benehmen wie vorher,
# sonst bräche jede Stelle, die `config(state=...)` setzt.
abschnitt("13. Knöpfe und Pillen in der Handschrift der App")
wurzel, app = fenster()
pruefe(isinstance(app.k_sammlung, livescan.Knopf)
       and isinstance(app.ausloeser, livescan.Knopf),
       "Auslöser und Sammlung sind eigene Knöpfe")
gedrueckt = []
_k = livescan.Knopf(app.innen, text="Probe", command=lambda: gedrueckt.append(1))
_k.config(state="disabled")
_k.invoke()
pruefe(gedrueckt == [] and _k.cget("state") == "disabled",
       "ein gesperrter Knopf löst nichts aus")
_k.config(state="normal")
_k.invoke()
pruefe(gedrueckt == [1], "ein freier Knopf schon")
_k.config(text="Anders")
pruefe(_k.cget("text") == "Anders", "die Beschriftung lässt sich tauschen")

# Die Pille hängt an der Variablen: Beides muss in beide Richtungen gehen.
app.zustand.set("used")
pille = [w for w in app.preisfeld.master.winfo_children()
         if isinstance(w, livescan.Pille)][0]
pruefe(pille.get() == "used", "die Zustandspille zeigt die Variable")
wurzel.update_idletasks()
breite_gebraucht = pille._breiten[0]
class _Klick:
    def __init__(self, x): self.x, self.y = x, 5
pille._geklickt(_Klick(pille._rand + breite_gebraucht + 5))
pruefe(app.zustand.get() == "new", "ein Klick auf „Neu“ setzt den Zustand")
pruefe(app.daten.get("zustand") == "new", "und er wird gemerkt")
gemerkt_stufe = []
app.empfindlich._befehl = lambda: gemerkt_stufe.append(app.empfindlich.get())
app.empfindlich._geklickt(_Klick(app.empfindlich._rand + 1))
pruefe(app.empfindlich.get() == list(livescan.EMPFINDLICHKEIT)[0]
       and gemerkt_stufe, "die Empfindlichkeit wechselt per Klick")

# Der Stern: gefüllt, wenn die Figur schon auf der Wunschliste steht.
app._kandidaten_zeigen([artikel("sw0036", 62, "Stormtrooper", wanted=True)])
takt(wurzel)
pruefe(app.k_merken.cget("text") == "★" and app.k_merken._an,
       "auf der Wunschliste steht ein gelber ★")
trennen(app)
app._kandidaten_zeigen([artikel("sw0097", 41, "Stormtrooper, Black Head")])
takt(wurzel)
pruefe(app.k_merken.cget("text") == "☆" and not app.k_merken._an,
       "sonst ein leerer ☆")
app.post.put(("gemerkt", app.treffer))
takt(wurzel)
pruefe(app.k_merken.cget("text") == "★", "nach dem Merken füllt er sich")
app._treffer_leeren()
pruefe(app.k_merken.cget("text") == "☆"
       and app.k_merken.cget("state") == "disabled",
       "eine leere Karte hat einen leeren, gesperrten Stern")

# Unter Windows setzt main() `tk scaling` nach dem Bildschirm – bei 150 %
# (144 dpi) sind das 2 Bildpunkte je Punkt. Dann muss der Knopf mitwachsen, sonst
# steht große Schrift in einem kleinen Knopf.
_vorher = float(wurzel.tk.call("tk", "scaling"))
wurzel.tk.call("tk", "scaling", 2.0)
_gross = livescan.Knopf(app.innen, text="＋ Zur Sammlung", hoehe=32)
_hoch = int(_gross.cget("height"))
_breit = int(_gross.cget("width"))
_text = _gross._schrift.measure("＋ Zur Sammlung")
wurzel.tk.call("tk", "scaling", _vorher)
pruefe(_hoch >= 1.45 * int(app.k_bereich.cget("height")),
       "bei 150 %% wächst der Knopf mit (%d px hoch)" % _hoch)
pruefe(_breit > _text, "und die Beschriftung passt hinein")

# Nach einem Wechsel zwischen Tag und Nacht zeichnen sich alle neu.
livescan.farben_setzen(wurzel, dunkel=True)
livescan.bauteile_auffrischen()
pruefe(app.k_sammlung.find_all(), "nachts gezeichnet")
livescan.farben_setzen(wurzel, dunkel=False)
livescan.bauteile_auffrischen()
wurzel.destroy()

# ===================================== Die Liste zuerst, die Wunschliste
abschnitt("14. Einkaufsliste als Hauptsache, Wunschliste in beide Richtungen")


class Buchhalter(Attrappe):
    """Merkt sich, was gebucht wurde, und antwortet auf `infos` mit dem
    jeweils aktuellen Stand."""
    def __init__(self):
        self.stand = {}
        self.weg = []
        self.gelegt = []

    def infos(self, artikel, bei_bricklink=False):
        return {t["item_id"]: dict(self.stand.get(t["item_id"], {}))
                for t in artikel}

    def auf_liste(self, i, t, z="used", p=None):
        self.gelegt.append((i, t["item_id"]))
        self.stand.setdefault(t["item_id"], {})["on_lists"] = ["Stream"]
        return "auf der Liste"

    def von_wunschliste(self, t):
        self.weg.append(t["item_id"])
        self.stand.setdefault(t["item_id"], {})["wanted"] = False
        return "von der Wunschliste genommen"

    def auf_wunschliste(self, t):
        self.stand.setdefault(t["item_id"], {})["wanted"] = True
        return "auf der Wunschliste"


wurzel, app = fenster()
buch = Buchhalter()
app.instanz = buch
pruefe(app.k_liste._art == "gruen" and app.k_sammlung._art == "normal",
       "der breite grüne Knopf legt auf die Liste, die Sammlung ist Nebensache")
app.post.put(("listen", [{"id": 7, "name": "Stream Freitag"}]))
takt(wurzel)
pruefe(app.k_liste.cget("text") == "🛒 Auf »Stream Freitag«",
       "der Knopf sagt, auf welche Liste es geht")

# Auf die Liste – die Figur steht auf der Wunschliste: Rückfrage, ja.
buch.stand["sw0036"] = {"wanted": True}
app._kandidaten_zeigen([artikel("sw0036", 62, "Stormtrooper", wanted=True)])
takt(wurzel)
gefragt_dialog.clear()
antworten[:] = [True]
app.auf_liste()
takt(wurzel, 400)
pruefe(buch.gelegt == [(7, "sw0036")], "auf die gewählte Liste gelegt")
pruefe(gefragt_dialog and "Wunschliste" in gefragt_dialog[0],
       "und gefragt, ob sie von der Wunschliste darf")
takt(wurzel, 400)
pruefe(buch.weg == ["sw0036"], "auf „Ja“ ist sie von der Wunschliste")
pruefe(app.k_merken.cget("text") == "☆", "der Stern ist wieder leer")
pruefe("steht auf" in app.besitz.cget("text"),
       "und die Karte zeigt nachgefragt: steht auf der Liste")

# Nicht gewünscht: keine Frage.
trennen(app)
app._kandidaten_zeigen([artikel("sw0097", 41, "Stormtrooper, Black Head")])
takt(wurzel)
gefragt_dialog.clear()
app.auf_liste()
takt(wurzel, 400)
pruefe(gefragt_dialog == [], "ohne Wunsch wird nicht gefragt")

# Der Stern als Umschalter: ★ drücken fragt, „Nein" lässt alles stehen.
trennen(app)
buch.stand["sw0188"] = {"wanted": True}
buch.weg.clear()
app._kandidaten_zeigen([artikel("sw0188", 78, "Dotted Mouth", wanted=True)])
takt(wurzel)
pruefe(app.k_merken.cget("text") == "★", "gemerkt: gelber ★")
antworten[:] = [False]
app.merken()
takt(wurzel, 400)
pruefe(buch.weg == [] and app.k_merken.cget("text") == "★",
       "auf „Nein“ bleibt sie auf der Wunschliste")
antworten[:] = [True]
app.merken()
takt(wurzel, 400)
pruefe(buch.weg == ["sw0188"] and app.k_merken.cget("text") == "☆",
       "auf „Ja“ ist sie weg und der Stern leer")
app.merken()
takt(wurzel, 400)
pruefe(app.k_merken.cget("text") == "★",
       "und ein erneuter Tipp merkt sie wieder – ohne Frage")

# Keine Liste da: der Hauptknopf führt zum Anlegen, statt ins Leere.
app.post.put(("listen", []))
takt(wurzel)
angelegt = []
app.liste_anlegen = lambda: angelegt.append(1)
app.auf_liste()
pruefe(angelegt == [1] and app.k_liste.cget("text") == "🛒 Auf die Liste",
       "ohne Liste öffnet 🛒 das Anlegen")
wurzel.destroy()

# ================================ Die Empfindlichkeit gehört zum Haken
abschnitt("15. Die Empfindlichkeit steht beim Haken und ist blass, solange er aus ist")
wurzel, app = fenster()
pruefe(app.empfindlich.master is app.k_automatik.master,
       "Pille und Haken stehen in derselben Zeile")
pruefe(app.empfindlich.pack_info().get("side") == "left",
       "und zwar direkt dahinter, nicht rechts am Rand")
app.automatik.set(False)
pruefe(app.empfindlich.cget("state") == "disabled", "Haken aus: blass")
app.automatik.set(True)
pruefe(app.empfindlich.cget("state") == "normal", "Haken an: gilt")
app.automatik.set(False)
app.empfindlich._geklickt(type("K", (), {"x": app.empfindlich._rand + 1})())
pruefe(app.empfindlich.get() == list(livescan.EMPFINDLICHKEIT)[0],
       "blass ist sie trotzdem wählbar – vor dem Einschalten")
wurzel.destroy()

# ================================ Preise wie im Steckbrief der App
abschnitt("16. Preise stehen wie im Steckbrief der App")
ECHT = {   # so antwortet /api/price – Beträge als Text
    "new": {"min": "260.0000", "avg": "265.0000", "max": "270.0000",
            "times_sold": 2, "used_scope": "DE", "fell_back": False},
    "used": {"min": "203.3720", "avg": "1264.0165", "max": "1329.9500",
             "times_sold": 7, "used_scope": "europe", "fell_back": True},
    "stock": {"used": {"min": "189.99", "angebote": 4, "used_scope": "DE"}},
}
pruefe(livescan.geld("1264.0165") == "1.264,02\u00a0€", "Beträge deutsch: 1.264,02\u00a0€")
pruefe(livescan.geld(3, "GBP") == "3,00\u00a0£", "Währung aus dem Konto")
zeilen = livescan.preis_zeilen(ECHT)
flagge = "(DE)" if livescan.IST_WINDOWS else "🇩🇪"
eu = "(EU)" if livescan.IST_WINDOWS else "🇪🇺"
pruefe([z[0] for z in zeilen] == ["Neu", "Gebraucht"],
       "je Zustand genau eine Zeile – nichts untereinander")
pruefe(zeilen[0][1] == "Ø 265,00\u00a0€", "Ø fett")
pruefe(zeilen[0][2] == "(260,00\u00a0€ – 270,00\u00a0€) · 2× verkauft\u00a0" + flagge,
       "Spanne und Verkaufszahl mit Gebiet in derselben Zeile")
pruefe(zeilen[1][2] == "(203,37\u00a0€ – 1.329,95\u00a0€) · 7× verkauft\u00a0" + eu
       + " · 4\u00a0im\u00a0Angebot\u00a0ab\u00a0189,99\u00a0€\u00a0" + flagge,
       "das Angebot hängt an der Gebraucht-Zeile, ausdrücklich „im Angebot ab“")
einzeln = livescan.preis_zeilen({"new": {"min": "5", "avg": "5", "max": "5",
                                          "times_sold": 1}})
pruefe("–" not in einzeln[0][2], "gleiche Enden: keine Spanne")
pruefe(livescan.preis_zeilen({"new": {}, "used": {"avg": "5"}})[0][2]
       == "keine Verkäufe", "ohne Verkäufe steht es da")

class MitPreisen(Attrappe):
    preise = lambda self, typ, nummer: dict(ECHT)
    einstellungen = lambda self: {"currency": "EUR"}

wurzel, app = fenster()
app.instanz = MitPreisen()
t = artikel("sw0547", 91, "Darth Revan", new=265.0, used=264.02)
app.gewaehlt = t        # wie nach einem Scan: Antworten gelten nur ihm
app._treffer_zeigen(t)
pruefe("Ø neu" in app.unter.cget("text"), "vor den vollen Preisen: die kurze Zeile")
app._preis_nachfragen(t)
takt(wurzel, 600)
pruefe(t.get("_preise") is not None, "volle Preise geholt")
pruefe("Ø neu" not in app.unter.cget("text"),
       "danach steht der Ø nicht doppelt in der Unterzeile")
texte = []
def sammeln(w):
    for k in w.winfo_children():
        try:
            texte.append(str(k.cget("text")))
        except Exception:
            pass
        sammeln(k)
sammeln(app.preisblock)
pruefe("Ø 265,00\u00a0€" in texte and "Neu" in texte and "Gebraucht" in texte,
       "Schild und Preis stehen in der Karte")
app._treffer_leeren()
pruefe(not app.preisblock.winfo_children(), "nächster Treffer: der Block ist leer")
wurzel.destroy()

# ============================================================ Bilanz
print("\n" + "─" * 58)
print("\033[1m%d Proben bestanden, %d fehlgeschlagen\033[0m"
      % (bilanz["gut"], bilanz["schlecht"]))
for p in (livescan.EINSTELLUNGEN, livescan.VERLAUF_DATEI):
    if os.path.exists(p):
        os.remove(p)
shutil.rmtree(ORDNER, ignore_errors=True)
raise SystemExit(1 if bilanz["schlecht"] else 0)
