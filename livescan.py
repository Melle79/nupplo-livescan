#!/usr/bin/env python3
"""Brickfolio Live-Scanner – Ausschnitt vom Bildschirm an die App schicken.

Gedacht für Auktions-Streams: Der Verkäufer hält eine Figur hoch, du ziehst
einen Rahmen darum, und der Treffer steht mit Nummer, Ø-Preisen und
„habt ihr schon" da – ohne Bildschirmfoto, ohne Datei, ohne Ziehen und
Ablegen.

**Eigenständig.** Dieses Programm gehört nicht zur App und wird auch nicht
mit ihr ausgeliefert. Es benutzt nur ihre Schnittstelle, genauso wie es der
Browser tut: anmelden, `/api/scan`, und auf Knopfdruck die üblichen Wege in
Sammlung, Wunschliste oder auf eine Einkaufsliste.

**Ein Auslöser = eine Anfrage.** Die Erkennung dahinter (Brickognize) wird
kostenlos bereitgestellt, und ein Videostream hätte 25 Bilder je Sekunde, von
denen 24 dasselbe zeigen. Deshalb wird nie ein Strom von Bildern verschickt.

Auf Wunsch löst der Scanner selbst aus, wenn im gemerkten Bereich eine neue
Figur erscheint (⏱). Auch dann bleibt es bei einer Anfrage je Figur: Verglichen
wird **auf diesem Rechner**, und geschickt wird erst, wenn sich das Bild
geändert hat *und* danach still steht. Höchstens ein Dutzend Anfragen je
Minute, mit Mindestabstand dazwischen. Von selbst **gebucht** wird nie – in
Sammlung, Wunschliste oder auf eine Liste kommt nur, was ihr anklickt.

**Ohne Fremdbibliotheken.** Läuft mit dem Python, das in macOS steckt:

    python3 livescan.py

Beim ersten Bildschirmfoto fragt macOS nach der Berechtigung
**Bildschirmaufnahme** – für das Programm, aus dem ihr das hier startet
(meist Terminal). Ohne sie kommt ein schwarzes Bild.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import ntpath
import os
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
# --------------------------------------------------------------- Tcl/Tk
# **Vor** dem tkinter-Import, darum steht der Block mitten zwischen den
# Importen. py2app kopiert zwar libtcl und libtk ins Buendel, aber nicht
# deren Skript-Bibliothek (init.tcl und Verwandtschaft). Tcl sucht sie
# dann am einkompilierten Pfad der Baumaschine und bricht mit
# "Cannot find a usable init.tcl" ab - beim Anwender, nicht beim Bauen.
# setup.py legt die Bibliothek unter Resources/lib ab; hier zeigen wir
# darauf. Ausserhalb eines Buendels passiert nichts.
if getattr(sys, "frozen", None) == "macosx_app":
    _mit = os.path.join(os.path.dirname(sys.executable), os.pardir, "Resources")
    for _var, _name in (("TCL_LIBRARY", "tcl9.0"), ("TK_LIBRARY", "tk9.0")):
        _weg = os.path.normpath(os.path.join(_mit, "lib", _name))
        if os.path.isdir(_weg):
            os.environ[_var] = _weg

import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
import uuid
import weakref
import webbrowser
from tkinter import font as tkfont
from tkinter import messagebox
from tkinter import ttk

# Steht auch im Info.plist des Bündels. setup.py liest sie von hier,
# damit sie nicht an zwei Stellen auseinanderläuft; pruefung.py wacht darüber.
VERSION = "1.10.0"

# Auf welchem System laufen wir? Der Mac-Weg bleibt unangetastet; fuer
# Windows stehen daneben eigene Zweige. Alles andere (Linux) faellt auf den
# Mac-Weg zurueck und scheitert dort hoerbar - das ist ehrlicher, als so zu
# tun, als koennten wir es.
IST_WINDOWS = sys.platform.startswith("win")

# Tk kennt nicht ueberall dieselben Mauszeiger: »pointinghand« ist ein
# macOS-Name, Windows bricht damit ab (bad cursor spec). »crosshair« gibt
# es auf beiden, das braucht keine Weiche.
ZEIGEHAND = "hand2" if IST_WINDOWS else "pointinghand"


def cloudflared_finden() -> str:
    """Wo `cloudflared` liegt – oder "" wenn nirgends.

    **Nicht auf den Suchpfad verlassen.** Ein Programm aus dem
    Programme-Ordner erbt nicht die Pfade der Shell: `/opt/homebrew/bin`
    steht dort nicht drin, und `cloudflared` galt deshalb als »nicht
    installiert«, obwohl es lag. Am 31.08.2026 genau so passiert.

    Zuerst die mitgelieferte Fassung – die ist immer da und passt zur App.
    Danach die ueblichen Orte, damit eine selbst installierte auch gefunden
    wird, und zuletzt der Suchpfad.
    """
    name = "cloudflared.exe" if IST_WINDOWS else "cloudflared"
    orte = []
    if getattr(sys, "frozen", None) == "macosx_app":
        orte.append(os.path.normpath(os.path.join(
            os.path.dirname(sys.executable), os.pardir, "Resources", name)))
    elif getattr(sys, "frozen", False):          # PyInstaller unter Windows
        orte.append(os.path.join(getattr(sys, "_MEIPASS", ""), name))
    orte += [os.path.join(o, name) for o in
             ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")]
    for ort in orte:
        if ort and os.path.isfile(ort) and os.access(ort, os.X_OK):
            return ort
    return shutil.which(name) or ""

EINSTELLUNGEN = os.path.expanduser("~/.brickfolio-livescan.json")

# Der Verlauf überlebt jetzt den Neustart – aber nur die Zeilen, **nie die
# Aufnahmen**. Eigene Datei, damit die Zugangsdaten schlank bleiben und man
# den Verlauf wegwerfen kann, ohne sich neu anzumelden.
VERLAUF_DATEI = os.path.expanduser("~/.brickfolio-livescan-verlauf.json")

# Laengste Kante der beiden Daumennaegel. Das Fenster ist darauf
# abgestimmt - wer sie aendert, sollte die Fensterbreite mitziehen.
BILDKANTE = 250

# Die Daumennägel zum Aussuchen, wenn eine Figur aus mehreren Ansichten kam.
# Ein farbiger Rand allein reicht nicht: Bei sechs Bildern nebeneinander sieht
# man ihn im Augenwinkel nicht mehr. Das gewählte trägt deshalb zusätzlich ein
# Häkchen in der Ecke, und die ungewählten treten zurück.
MINI_KANTE = 54
MINI_RAND = 4
MINI_AN = "#1a7f37"        # Rand und Häkchen: dieses Bild wird angehängt
MINI_AUS = "#e2e2e2"
# So viele passen nebeneinander, ohne das Fenster zu sprengen – und so viele
# werden auch nur aufgehoben. Beides muss dieselbe Zahl sein: Sonst kann die
# Vorauswahl auf eine Aufnahme fallen, die gar nicht angezeigt wird, und man
# hängt ein Bild an, das man nie gesehen hat.
MINI_HOECHSTENS = 6


# ------------------------------------------------------------ Einstellungen

def lesen() -> dict:
    try:
        with open(EINSTELLUNGEN) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def schreiben(daten: dict) -> None:
    with open(EINSTELLUNGEN, "w") as f:
        json.dump(daten, f, indent=1)
    if not IST_WINDOWS:
        # 0600 – nur fuer dich lesbar. Windows kennt diese Rechte nicht;
        # dort schuetzt allein, dass die Datei im Benutzerprofil liegt.
        os.chmod(EINSTELLUNGEN, stat.S_IRUSR | stat.S_IWUSR)


# --------------------------------------------------------------- Instanz

class Fehler(RuntimeError):
    pass


class _KeineUmleitung(urllib.request.HTTPRedirectHandler):
    """Umleitungen **nicht** von selbst verfolgen.

    Sonst landet eine Anfrage stillschweigend auf der Anmeldeseite von
    Cloudflare Access, kommt mit 200 und HTML zurueck, und der Scanner
    meldet »Unerwartete Antwort« - obwohl das Problem einen Namen hat.
    Ungefragt umgeleitet zu werden ist bei einer Schnittstelle ohnehin
    kein guter Zustand.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OEFFNER = urllib.request.build_opener(_KeineUmleitung)


class Instanz:
    """Die Verbindung zu einer Brickfolio-Instanz – über deren Schnittstelle,
    ohne irgendetwas über ihr Inneres anzunehmen."""

    def __init__(self, adresse: str = "", token: str = "",
                 cf_kennung: str = "", cf_geheim: str = ""):
        self.adresse = adresse.rstrip("/")
        self.token = token
        # Steht die Instanz hinter Cloudflare Access, laesst dieses Paar
        # ein Programm durch - eine Anmeldeseite koennte es ja nicht
        # ausfuellen. Beides legt der Betreiber in Cloudflare Zero Trust
        # an; hier wird es nur weitergereicht.
        self.cf_kennung = cf_kennung
        self.cf_geheim = cf_geheim
        # Der zweite Weg: Wer sich einmal mit `cloudflared access login`
        # im Browser angemeldet hat - also ganz normal per E-Mail und
        # Zugangscode -, hat dort eine Sitzung liegen. Die holen wir uns,
        # aber nicht bei jeder Anfrage: Ein Unterprozess je Bild waere
        # spuerbar. Darum gemerkt, mit Verfallszeit.
        self._cf_sitzung = ""
        self._cf_sitzung_bis = 0.0

    # ------------------------------------------------------- Grundlagen
    def _anfrage(self, weg: str, daten=None, methode="GET", felder=None):
        url = self.adresse + weg
        # **Sagen, wer man ist.** Ohne eigene Kennung schickt urllib
        # »Python-urllib/3.x« - und Cloudflares Bot-Schutz weist das ab,
        # noch bevor Access ueberhaupt zum Zuge kommt: »The site owner has
        # blocked access based on your browser's signature«. Mit Namen und
        # Fassung ist die Anfrage zuordenbar, und der Betreiber kann sie
        # gezielt durchlassen.
        kopf = {"Accept": "application/json"}
        kopf.update(self._grundkopf())
        if self.token:
            kopf["Authorization"] = "Bearer " + self.token
        koerper = None
        if felder is not None:
            grenze = "----brickfolio" + uuid.uuid4().hex
            koerper = _multipart(felder, grenze)
            kopf["Content-Type"] = "multipart/form-data; boundary=" + grenze
            methode = "POST"
        elif daten is not None:
            koerper = json.dumps(daten).encode()
            kopf["Content-Type"] = "application/json"
            methode = "POST"
        antrag = urllib.request.Request(url, data=koerper, headers=kopf,
                                        method=methode)
        try:
            with _OEFFNER.open(antrag, timeout=90) as antwort:
                roh = antwort.read()
        except urllib.error.HTTPError as e:
            # **Cloudflare Access antwortet mit einer Umleitung**, nicht mit
            # einem Fehler. Ohne diesen Zweig laeuft man in die Anmeldeseite
            # und liest »Unerwartete Antwort der Instanz« - eine Meldung,
            # die in die falsche Richtung schickt.
            if e.code in (301, 302, 303, 307, 308):
                ziel = e.headers.get("Location", "")
                if "cloudflareaccess.com" in ziel or "/cdn-cgi/access/" in ziel:
                    raise Fehler(
                        "Diese Instanz steht hinter Cloudflare Access – eine "
                        "Anmeldeseite kann dieses Werkzeug nicht ausfüllen. "
                        "Zwei Wege: unter »Zugang …« einen Dienst-Token "
                        "hinterlegen, oder einmal »cloudflared access login "
                        "%s« ausführen." % self.adresse) from None
                raise Fehler("Die Instanz leitet weiter (%s). Stimmt die "
                             "Adresse?" % e.code) from None
            raise Fehler(_meldung(e)) from None
        except urllib.error.URLError as e:
            raise Fehler(f"Instanz nicht erreichbar ({e.reason})") from None
        try:
            return json.loads(roh)
        except ValueError:
            raise Fehler("Unerwartete Antwort der Instanz") from None

    # --------------------------------------------------- Cloudflare Access
    def _grundkopf(self) -> dict:
        """Was **jede** Anfrage nach draußen braucht.

        Eigene Kennung und, falls noetig, der Weg an Cloudflare Access
        vorbei. Frueher stand das nur in `_anfrage` - und das Katalogbild,
        das mit einem nackten `urlopen` geholt wurde, blieb hinter
        Cloudflare leer. Der Fehler fiel nicht auf, weil das `except` ihn
        zu einem stillen »kein Katalogbild« machte.
        """
        kopf = {"User-Agent": "Brickfolio-Live-Scanner/%s" % VERSION}
        kopf.update(self._cf_kopfzeilen())
        return kopf

    def _cf_kopfzeilen(self) -> dict:
        """Was eine Anfrage braucht, um an Cloudflare Access vorbeizukommen.

        Zwei Wege, in dieser Reihenfolge:

        1. **Dienst-Token.** Zwei Werte aus Zero Trust, hinterlegt unter
           »Zugang …«. Braucht keine zusaetzliche Software und laeuft nicht
           ab – der Weg fuer fremde Rechner und fuer Windows.
        2. **Eine Sitzung von `cloudflared`.** Wer sich einmal mit
           `cloudflared access login` angemeldet hat – ganz normal per
           E-Mail und Zugangscode –, braucht keine eigene Richtlinie in
           Cloudflare. Dafuer muss `cloudflared` auf dem Rechner liegen,
           und die Sitzung laeuft irgendwann ab.

        Ist beides nicht da, bleibt es leer und `_anfrage` sagt hinterher,
        was fehlt.
        """
        if self.cf_kennung and self.cf_geheim:
            return {"CF-Access-Client-Id": self.cf_kennung,
                    "CF-Access-Client-Secret": self.cf_geheim}
        sitzung = self._cf_sitzung_holen()
        if sitzung:
            # Beide Formen: Access nimmt die Kopfzeile, der Cookie ist der
            # Weg, den auch ein Browser geht. Zwei zu schicken kostet
            # nichts und erspart die Frage, welche Fassung was erwartet.
            return {"cf-access-token": sitzung,
                    "Cookie": "CF_Authorization=" + sitzung}
        return {}

    def _cf_sitzung_holen(self) -> str:
        """Den Sitzungs-Token von `cloudflared` erfragen – hoechstens alle
        zehn Minuten neu."""
        if not self.adresse.startswith("https://"):
            return ""                     # im Heimnetz steht kein Access davor
        jetzt = time.time()
        if self._cf_sitzung and jetzt < self._cf_sitzung_bis:
            return self._cf_sitzung
        werkzeug = cloudflared_finden()
        if not werkzeug:
            return ""
        try:
            fertig = subprocess.run(
                [werkzeug, "access", "token", "-app=" + self.adresse],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            return ""                     # nicht installiert – kein Drama
        wert = (fertig.stdout or "").strip()
        # Ohne Anmeldung schreibt cloudflared eine Meldung statt eines
        # Tokens. Ein JWT hat drei durch Punkte getrennte Teile und keine
        # Leerzeichen – daran laesst sich das eine vom anderen scheiden.
        if fertig.returncode != 0 or wert.count(".") != 2 or " " in wert:
            return ""
        self._cf_sitzung = wert
        self._cf_sitzung_bis = jetzt + 600
        return wert

    def cf_anmelden(self, adresse: str = "") -> tuple:
        """Den Browser für die Cloudflare-Anmeldung öffnen und warten.

        Das ist der Weg, den man erwartet: Browser auf, E-Mail und Code
        eintragen, fertig. `cloudflared` uebernimmt dabei alles – wir
        starten es nur und sehen hinterher nach, ob wirklich eine Sitzung
        entstanden ist.

        Gibt (geschafft, Meldung) zurueck. Laeuft in einem eigenen Faden,
        denn der Befehl wartet, bis der Mensch im Browser fertig ist.
        """
        adresse = (adresse or self.adresse).rstrip("/")
        if not adresse.startswith("https://"):
            return (False, "Dafür braucht es eine https-Adresse. Im "
                           "Heimnetz steht ohnehin kein Cloudflare davor.")
        werkzeug = cloudflared_finden()
        if not werkzeug:
            return (False, "»cloudflared« wurde nicht gefunden – weder "
                           "mitgeliefert noch installiert.")
        try:
            fertig = subprocess.run(
                [werkzeug, "access", "login", adresse],
                capture_output=True, text=True, timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError:
            return (False, "»cloudflared« ist nicht installiert. "
                           "Auf dem Mac: brew install cloudflared")
        except subprocess.TimeoutExpired:
            return (False, "Zu lange gewartet – die Anmeldung im Browser "
                           "wurde nicht zu Ende gebracht.")
        except (OSError, subprocess.SubprocessError) as e:
            return (False, "cloudflared ließ sich nicht starten (%s)." % e)

        # **Nicht auf den Rückgabewert verlassen.** Ob wirklich eine
        # Sitzung entstanden ist, sagt nur die Sitzung selbst.
        self._cf_sitzung = ""
        self._cf_sitzung_bis = 0.0
        self.adresse = adresse
        if self._cf_sitzung_holen():
            return (True, "Angemeldet bei Cloudflare. Jetzt »Anmelden«.")
        ende = ((fertig.stderr or fertig.stdout or "").strip().splitlines()
                or ["ohne Angabe"])[-1]
        return (False, "Es kam keine Sitzung zustande (%s)." % ende[:120])

    # ----------------------------------------------------------- Wege
    def anmelden(self, benutzer: str, passwort: str) -> None:
        antwort = self._anfrage("/api/login",
                                {"username": benutzer, "password": passwort})
        self.token = antwort.get("token") or ""
        if not self.token:
            raise Fehler("Dieses Konto verlangt einen zweiten Faktor – "
                         "dafür ist dieses Werkzeug nicht gebaut.")

    def erkennen(self, bild: bytes) -> dict:
        return self._anfrage("/api/scan", felder={
            "file": ("stream.png", "image/png", bild)})

    def infos(self, artikel: list, bei_bricklink: bool = False) -> dict:
        """Jahr, Ø-Preise und „wie oft habt ihr das schon".

        Zwei Stufen, genau wie die App sie nimmt: Ohne `detail` kommt nur,
        was schon in deiner Datenbank steht – sofort da, aber leer bei einer
        Figur, die ihr noch nie hattet. Mit `detail=1` fragt die Instanz
        **BrickLink**. Das dauert einen Moment, liefert aber auch für
        Unbekanntes einen Preis.
        """
        weg = "/api/suggest_info?detail=1" if bei_bricklink \
            else "/api/suggest_info"
        try:
            return self._anfrage(weg, {"items": artikel})
        except Fehler:
            return {}

    def einstellungen(self) -> dict:
        """Währung und Schalter des Kontos (`/api/config`), zehn Minuten
        gemerkt – dieselben, nach denen die App ihre Preise zeigt."""
        jetzt = time.time()
        if getattr(self, "_einst_bis", 0.0) > jetzt:
            return self._einst
        try:
            self._einst = self._anfrage("/api/config") or {}
        except Fehler:
            self._einst = getattr(self, "_einst", None) or {}
        self._einst_bis = jetzt + 600
        return self._einst

    def preise(self, typ: str, nummer: str) -> dict:
        """Die volle Preisangabe, wie sie der Steckbrief der App zeigt.

        Je Zustand Ø, Spanne, Verkaufszahl und Gebiet – und, wenn im Konto
        „Angebotspreise“ eingeschaltet ist, das billigste aktuelle Angebot.
        Die Instanz antwortet aus ihrem Zwischenspeicher; nur die Angebote
        kosten zwei BrickLink-Abrufe, und die holt sie nur auf Verlangen.
        """
        weg = (f"/api/price/{urllib.parse.quote(typ or 'minifig')}/"
               f"{urllib.parse.quote(nummer)}")
        if self.einstellungen().get("angebotspreise"):
            weg += "?angebote=1"
        try:
            return self._anfrage(weg) or {}
        except Fehler:
            return {}

    def sets_der_figur(self, item_id: str) -> list:
        """In welchen Sets kam diese Figur heraus?

        `suggest_info?detail=1` liefert das zwar auch als `all_sets` – aber
        nur für Artikel, denen Jahr **und** Preis fehlen. Bei einer Figur,
        die ihr längst habt, kommt dort nie etwas an; genau die schaut man
        beim Mitbieten aber am häufigsten an. `/api/fig_sets` beantwortet
        dieselbe Frage direkt und liegt auf der Instanz 30 Tage im Speicher.
        """
        try:
            return self._anfrage(f"/api/fig_sets/{item_id}").get("sets", [])
        except Fehler:
            return []

    def listen(self) -> list:
        try:
            alle = self._anfrage("/api/lists").get("lists", [])
        except Fehler:
            return []
        return [l for l in alle if not l.get("archived")]

    def nummer_suchen(self, nummer: str) -> list:
        """Alle Artikel zu einer Katalognummer – Figur, Set **und** Teil.

        Für den Fall, dass die Erkennung nichts hergibt: schlechtes Licht,
        die Figur zu weit weg, der Verkäufer zu schnell. Die Nummer steht
        oft im Bild oder wird angesagt, und dann ist Tippen schneller als
        ein zweiter Versuch.

        Geraten wird dabei **nicht**. `3001` ist bei BrickLink sowohl das
        Set „Propeller Buggy" als auch der Stein 2 × 4 – wer hier die eine
        Art auswählt, legt bei jeder zweiten Nummer die falsche an. Also
        alle drei fragen und die Treffer zur Auswahl stellen, genauso wie
        die Erkennung ihre Varianten anbietet. Die Instanz antwortet aus
        ihrem Zwischenspeicher; drei Fragen kosten kaum mehr als eine.
        """
        nummer = (nummer or "").strip()
        if not nummer:
            return []
        gefunden = []
        for art in ("minifig", "set", "part"):
            try:
                d = self._anfrage(
                    f"/api/lookup/{art}/{urllib.parse.quote(nummer)}")
            except Fehler:
                continue
            if d.get("item_id"):
                gefunden.append({"item_id": d["item_id"], "item_type": art,
                                 "name": d.get("name") or d["item_id"],
                                 "img_url": d.get("img_url") or "",
                                 "bricklink_url": d.get("bricklink_url") or "",
                                 "score": 100})
        return gefunden

    def liste_anlegen(self, name: str) -> int:
        """Neue Einkaufsliste – und ihre Nummer zurück.

        Bis hierher musste man dafür in die App wechseln. Mitten in einem
        Stream ist das der Moment, in dem der nächste Artikel hochgehalten
        wird: Man kauft bei jemand Neuem und hat keine Liste dafür.
        """
        d = self._anfrage("/api/lists", {"name": name})
        return d.get("id")

    # Die drei Wege, die auch die Trefferkarte in der App anbietet –
    # samt Zustand und Preis, denn ohne die ist ein Flohmarkt-Eintrag
    # nur die halbe Miete.
    def in_sammlung(self, t: dict, zustand: str = "used",
                    preis: float | None = None) -> str:
        koerper = {**_gemeinsam(t), "condition": zustand}
        if preis is not None:
            koerper["paid_price"] = preis
        d = self._anfrage("/api/collection", koerper)
        return "Menge erhöht" if d.get("merged") else "in der Sammlung"

    def auf_wunschliste(self, t: dict) -> str:
        d = self._anfrage("/api/wanted", _gemeinsam(t))
        return "stand schon drauf" if d.get("exists") else "auf der Wunschliste"

    def von_wunschliste(self, t: dict) -> str:
        """Den Artikel wieder von der Wunschliste nehmen.

        Die Schnittstelle löscht nach Eintragsnummer; die kennt der Scanner
        nicht, also erst nachsehen. Steht er doppelt drauf (anderer Weg,
        andere Zeit), gehen beide – gemeint ist „nicht mehr wünschen".
        """
        typ = t.get("item_type") or "minifig"
        alle = self._anfrage("/api/wanted").get("items", [])
        weg = [w for w in alle if w.get("item_id") == t["item_id"]
               and (w.get("item_type") or "minifig") == typ]
        if not weg:
            return "stand nicht auf der Wunschliste"
        for w in weg:
            self._anfrage(f"/api/wanted/{w['id']}", methode="DELETE")
        return "von der Wunschliste genommen"

    def auf_liste(self, liste_id: int, t: dict, zustand: str = "used",
                  preis: float | None = None) -> str:
        koerper = {**_gemeinsam(t), "condition": zustand}
        if preis is not None:
            koerper["paid_price"] = preis
        d = self._anfrage(f"/api/lists/{liste_id}/items", koerper)
        return "Menge erhöht" if d.get("merged") else "auf der Liste"

    def katalogbild(self, adresse: str) -> bytes | None:
        """Das Referenzbild holen – über den Weiterleiter der Instanz.

        Nicht direkt von BrickLink: Die Instanz hat es ohnehin schon im
        Speicher, und so geht von hier aus nichts nach außen. Einen Login
        der **Instanz** braucht der Weg nicht – ein `<img>` trägt ja auch
        keinen Token.

        **Cloudflare Access sitzt aber davor**, und das interessiert sich
        nicht dafür, ob dahinter ein Login verlangt wird. Deshalb geht der
        Grundkopf auch hier mit; ohne ihn blieb das Bild leer, und das
        `except` machte daraus ein stilles »kein Katalogbild«.
        """
        if not adresse:
            return None
        if adresse.startswith("//"):
            adresse = "https:" + adresse
        weg = (self.adresse + "/catalog?u="
               + urllib.parse.quote(adresse, safe="")
               if adresse.startswith(("http://", "https://"))
               else self.adresse + adresse)
        antrag = urllib.request.Request(weg, headers=self._grundkopf())
        try:
            with _OEFFNER.open(antrag, timeout=30) as antwort:
                return antwort.read()
        except (urllib.error.URLError, urllib.error.HTTPError, OSError):
            return None

    def foto_anhaengen(self, t: dict, bild: bytes) -> None:
        """Den aufgenommenen Ausschnitt als eigenes Foto an den Artikel
        hängen – **zusätzlich** zum Katalogbild, wie in der App.

        Zwei Schritte, weil die App es so anbietet: erst die Datei ablegen,
        dann den Verweis an den Artikel heften.
        """
        adresse = self._anfrage("/api/upload_image", felder={
            "file": ("livescan.png", "image/png", bild)}).get("url")
        if not adresse:
            raise Fehler("Bild konnte nicht abgelegt werden")
        self._anfrage("/api/item_photos", {
            "item_type": t.get("item_type") or "minifig",
            "item_id": t["item_id"], "url": adresse})


def _gemeinsam(t: dict) -> dict:
    return {"item_id": t["item_id"],
            "item_type": t.get("item_type") or "minifig",
            "name": t.get("name") or t["item_id"],
            "img_url": t.get("img_url") or "",
            "bricklink_url": t.get("bricklink_url") or ""}


def _woanders(info: dict) -> str:
    """Wo taucht die Figur außerhalb der Sammlung schon auf?

    Die Sammlung ist nur eine von mehreren Antworten auf „habe ich das
    schon?". Wer in einem Live-Stream mitbietet, will genauso wissen, ob die
    Figur längst auf der Wunschliste steht, auf einer Einkaufsliste liegt
    oder zu einem Set gehört, das zu Hause unvollständig herumsteht – sonst
    kauft man zum zweiten Mal.

    All das liefert `/api/suggest_info` von sich aus mit; angezeigt wurde
    bisher nur `owned`. Hier wird nichts Neues erfragt, nur Vorhandenes
    hingeschrieben.
    """
    teile = []
    if info.get("wanted"):
        teile.append("☆ auf der Wunschliste")
    # **Die Einkaufslisten stehen seit dem 30.08.2026 eine Zeile höher.**
    # Dort beantworten sie „habe ich das?", und zweimal dasselbe zu sagen
    # macht die Zeile nur länger.
    eigene = _eigene_sets(info)
    for nummer, name, anzahl, zustand in eigene[:EIGENE_SETS]:
        # **Versiegelt oder offen** – das ist beim Mitbieten der ganze
        # Unterschied. Im neuen Set steckt die Figur noch, im gebrauchten
        # stünde sie längst einzeln in der Sammlung.
        teile.append("🧩 steckt in deinem {}Set {} ({}){}".format(
            "ungeöffneten " if zustand == "new" else "",
            nummer, _kurz(name, 40),
            "" if anzahl <= 1 else " ×{}".format(anzahl)))
    if len(eigene) > EIGENE_SETS:
        teile.append("und {} weiteren".format(len(eigene) - EIGENE_SETS))
    return "   ".join(teile)


# Wie viel in die beiden Zeilen darf. Der Umbruch richtet sich nach der
# Fensterbreite, es geht also nichts verloren – aber eine Figur aus dreißig
# Sets soll die Karte trotzdem nicht zur Tapete machen.
EIGENE_SETS = 4
KATALOG_SETS = 8

# Wie viele Zeilen der Verlauf hält – und wie viele davon ihre Aufnahme
# behalten. Beides ist verschieden: Eine Zeile kostet ein paar Byte, ein
# Bildschirmausschnitt schnell ein halbes Megabyte. 200 Aufnahmen im Speicher
# zu halten, nur damit die dreißigste noch anklickbar ist, wäre schlechter
# Tausch – die Zeile bleibt, das Bild geht.
VERLAUF_ZEILEN = 200
VERLAUF_BILDER = 30
# Und so viele überleben das Schließen. Weniger als im Betrieb, mit Absicht:
# Beim nächsten Start will man sehen, womit man aufgehört hat, nicht den
# ganzen Abend noch einmal. Die Aufnahmen sind ohnehin nicht dabei.
VERLAUF_MERKEN = 20

# Wie lange nach einem Scan ein weiterer noch als **andere Ansicht derselben
# Figur** gilt. Der Verkäufer dreht sie, zeigt die Rückseite, hält sie schräg –
# und die Erkennung liefert jedes Mal etwas anderes. Solange sich die
# Vorschläge überschneiden und es schnell hintereinander geht, gehört das
# zusammen.
#
# Großzügig bemessen, und für den Wächter genauso wie für die eigene Hand.
# Mit 25 Sekunden zerfiel eine Figur in mehrere Zeilen: Von Hand dauert
# Rahmen ziehen länger, und der Wächter macht nach vier Ansichten von sich
# aus Pause, bis sich etwas Größeres tut – bis dahin ist die Frist um.
#
# Die Zeit ist ohnehin nur die zweite Bedingung. Die erste ist, dass sich die
# Vorschläge überschneiden **und** die Figur noch obenauf im Verlauf liegt:
# Sobald etwas anderes gescannt oder gebucht wurde, ist ohnehin Schluss.
ANSICHT_FENSTER = 180.0

# Der Rahmen um die beiden Bilder. Grün heißt „hast du schon irgendwo" –
# im Set, das bei dir steht, oder auf einer offenen Einkaufsliste. Aus
# bleibt er sonst; die Fensterfarbe hängt am Erscheinungsbild, deshalb wird
# sie beim Start abgefragt statt hier festgeschrieben.
RAHMEN_DICK = 6
RAHMEN_AN = "#1a7f37"

# Und das Gegenstück: Die Figur steht auf der **Wunschliste**. Grün heißt
# „hast du schon, lass es" – ein Wunsch heißt das genaue Gegenteil, und
# deshalb darf er nicht dieselbe Farbe tragen. Er bekommt eine eigene, und
# er blinkt: Grün darf man übersehen, einen Wunsch nicht. Der ist der Grund,
# aus dem man überhaupt zuschaut.
WUNSCH_AN = "#e08a00"
WUNSCH_ZEILE = "#ffeec2"        # blasser Grund in der Trefferliste
WUNSCH_ZEILE_SCHRIFT = "#7a5c00"

# **Wer den Hintergrund setzt, muss auch die Schrift setzen.** Diese beiden
# Gründe sind fest hell – sie tragen eine Bedeutung und dürfen sich nicht
# mit dem Erscheinungsbild ändern. Die Schrift darauf blieb aber die
# voreingestellte, und die ist im Nachtmodus hell: weiß auf blassgrün,
# unlesbar. Am 01.09.2026 genau so aufgetreten.
GRUEN_ZEILE = "#d7f0dd"         # „habt ihr schon"
GRUEN_ZEILE_SCHRIFT = "#14532d"
WUNSCH_TAKTE = 8                # so oft wird umgeschaltet
WUNSCH_TAKT = 260               # Millisekunden je Wechsel
# Der Mac hat den Ton im System liegen. Windows hat kein Gegenstueck an
# fester Stelle - dort nimmt `ton_spielen` den Systemklang, weil winsound
# ihn ohne Datei spielen kann.
WUNSCH_TON = ("" if IST_WINDOWS
              else "/System/Library/Sounds/Hero.aiff")


def _schon_da(info: dict) -> bool:
    """Habt ihr die Figur in irgendeiner Form schon?

    Zwei Gründe, im Stream **nicht** mitzubieten: Sie steht in der Sammlung,
    oder sie liegt auf einer offenen Einkaufsliste. Beide machen den Rahmen
    grün – die Farbe heißt schlicht „hast du schon".

    **Ein gebrauchtes Set zählt seit dem 30.08.2026 nicht mehr mit.** Wer
    trägt zu jedem Set, das er *mit* Figuren kauft, die Figuren einzeln in
    die Sammlung ein. Steht eine Figur also nicht in der Sammlung, hat er
    sie auch nicht – viele Sets kommen ohne Figuren herein. Der grüne
    Rahmen hieß dann „hast du schon", während die Zeile darunter „noch
    nicht in deiner Sammlung" sagte, und von beiden hatte nur die Zeile
    recht.

    **Ein neues Set dagegen zählt sehr wohl**: Es ist versiegelt, die
    Figuren stecken noch darin. Genau deshalb liefert die App seit 2.76.0
    den Zustand des Sets mit.

    Dass die Figur zu einem gebrauchten Set gehört, steht weiterhin
    darunter – als Hinweis, nicht als Kaufverbot.

    Die Wunschliste zählt ebenfalls **nicht** mit: Ein Wunsch ist ein Grund
    zu kaufen, kein Grund es zu lassen. Wäre der Rahmen dort auch grün,
    hieße er zweierlei und damit nichts.
    """
    return (bool(info.get("owned"))
            or bool(info.get("on_lists"))
            or bool(_versiegelte_sets(info)))


def _versiegelte_sets(info: dict) -> list:
    """Eigene Sets, die **neu** sind – dort steckt die Figur noch drin."""
    return [s for s in _eigene_sets(info) if s[3] == "new"]


# ------------------------------------------------------------ Preise
# Dieselbe Anzeige wie im Steckbrief der App (seit 2.90.18): links ein gelbes
# Schild „Neu“/„Gebraucht“, daneben der Ø fett mit der Spanne, darunter
# eingerückt die Verkaufszahl mit dem Gebiet, aus dem der Preis stammt. Das
# Fenster des Scanners ist schmal – also gleich die Handy-Form der App, in
# der die Verkaufszahl immer eine eigene Zeile bekommt.
REGION_FLAGGE = {"": "🌍", "DE": "🇩🇪", "AT": "🇦🇹", "CH": "🇨🇭",
                 "europe": "🇪🇺"}
# Windows hat keine Flaggen in seiner Emoji-Schrift – dort stünden zwei
# Buchstaben in Kästchen. Also gleich die Buchstaben.
REGION_KURZ = {"": "weltweit", "DE": "DE", "AT": "AT", "CH": "CH",
               "europe": "EU"}
WAEHRUNG_ZEICHEN = {"EUR": "€", "GBP": "£", "USD": "$", "CHF": "CHF"}


def geld(wert, waehrung: str = "EUR") -> str:
    """„1.234,56 €“ – die Instanz schickt die Beträge als Text („265.0000“)."""
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return "–"
    text = f"{zahl:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} {WAEHRUNG_ZEICHEN.get(waehrung or 'EUR', waehrung)}"


def gebiet(d: dict) -> str:
    """Woher der Preis stammt – als Fahne, unter Windows als Kürzel."""
    if not d or "used_scope" not in d:
        return ""
    wo = d.get("used_scope") or ""
    if IST_WINDOWS:
        return f"({REGION_KURZ.get(wo, wo)})"
    return REGION_FLAGGE.get(wo, "🌍")


def preis_zeilen(p: dict, waehrung: str = "EUR") -> list:
    """Die Zeilen des Preisblocks: `(schild, fett, dahinter, darunter, art)`.

    `art` ist „verkauf“ oder „angebot“. Ohne Verkäufe steht „keine Verkäufe“
    da wie in der App – eine fehlende Zeile sähe aus wie ein Ladefehler.
    """
    zeilen = []
    for schild, schluessel in (("Neu", "new"), ("Gebraucht", "used")):
        d = (p or {}).get(schluessel) or {}
        if not d.get("avg"):
            zeilen.append((schild, "", "keine Verkäufe", "", "verkauf"))
            continue
        spanne = ""
        if d.get("min") is not None and d.get("max") is not None:
            spanne = f"({geld(d['min'], waehrung)} – {geld(d['max'], waehrung)})"
        unten = []
        if d.get("times_sold") is not None:
            unten.append(f"{d['times_sold']}× verkauft")
        if gebiet(d):
            unten.append(gebiet(d))
        zeilen.append((schild, f"Ø {geld(d['avg'], waehrung)}", spanne,
                       "\u00a0".join(unten), "verkauf"))
    lager = (p or {}).get("stock") or {}
    for schild, schluessel in (("Neu", "new"), ("Gebraucht", "used")):
        d = lager.get(schluessel) or {}
        if d.get("min") is None:
            continue
        unten = []
        if d.get("angebote"):
            unten.append(f"{d['angebote']} im Angebot")
        if gebiet(d):
            unten.append(gebiet(d))
        zeilen.append((schild, f"ab {geld(d['min'], waehrung)}", "",
                       "\u00a0".join(unten), "angebot"))
    return zeilen


def _besitz_zeile(info: dict) -> dict:
    """Die eine Zeile, die „habe ich das?" beantwortet.

    Drei Fälle, in dieser Reihenfolge:

    - **In der Sammlung.** Die klare Antwort.
    - **Nicht in der Sammlung, aber auf einer Einkaufsliste.** Vorher stand
      hier „— noch nicht in deiner Sammlung", während der Rahmen grün
      leuchtete – zwei Aussagen, die sich widersprachen. Jetzt steht dort,
      **auf welcher Liste** sie liegt; das ist die Antwort, die im Stream
      zählt.
    - **Weder noch.** Dann darf es auch so dastehen.

    Ein eigenes Set kommt hier nicht vor. Es steht in der Zeile darunter,
    als Hinweis – die Figuren zu einem Set trägt man einzeln ein, ein Set
    ohne Figureneintrag heißt also: Figur nicht da.
    """
    habe = info.get("owned") or 0
    if habe:
        return {"text": "✔ {}× in deiner Sammlung".format(habe),
                "foreground": "#1a7f37"}
    listen = info.get("on_lists") or []
    if len(listen) == 1:
        return {"text": "🛒 steht auf »{}«".format(_kurz(listen[0], 46)),
                "foreground": "#1a7f37"}
    if listen:
        return {"text": "🛒 steht auf {} Einkaufslisten: {}".format(
                    len(listen), _kurz(", ".join(listen), 46)),
                "foreground": "#1a7f37"}
    versiegelt = _versiegelte_sets(info)
    if versiegelt:
        return {"text": "📦 steckt im ungeöffneten Set {}".format(
                    ", ".join(s[0] for s in versiegelt[:2])),
                "foreground": "#1a7f37"}
    return {"text": "— noch nicht in deiner Sammlung",
            "foreground": "#8a6d00"}


def _schon_da_marke(info: dict) -> str:
    """**Warum** die Zeile grün ist – ein Zeichen je Grund.

    Grün heißt „hast du schon", und das hat drei mögliche Gründe. Ohne
    Unterscheidung stand am 30.08.2026 eine grüne Zeile über der
    Erklärung „— noch nicht in deiner Sammlung", und das las sich wie ein
    Widerspruch: Die Figur steckte in einem eigenen Set und lag auf einer
    Liste, war aber nicht als eigener Eintrag erfasst.

    Besitz schlägt Liste schlägt versiegeltes Set. Ein **gebrauchtes**
    Set steht hier nicht: Es macht die Zeile seit dem 30.08.2026 auch
    nicht mehr grün, weil die Figuren daraus einzeln erfasst wären.
    """
    if info.get("owned"):
        return "✔"
    if info.get("on_lists"):
        return "🛒"
    if _versiegelte_sets(info):
        return "📦"
    return " "


def _gewuenscht(info: dict) -> bool:
    """Steht die Figur auf der Wunschliste?

    Bewusst getrennt von `_schon_da`: Die beiden beantworten entgegengesetzte
    Fragen. „Habt ihr schon" ist ein Grund, die Hand unten zu lassen; „steht
    auf der Wunschliste" ist der Grund, aus dem ihr überhaupt zuschaut.
    """
    return bool(info.get("wanted"))


def ton_spielen(datei: str = WUNSCH_TON) -> None:
    """Kurz Bescheid geben – auf dem Mac mit `afplay`, unter Windows mit
    `winsound`, beides im System enthalten.

    Nicht `bell()`: Der Systemton ist bei vielen abgeschaltet oder so leise,
    dass er neben einem laufenden Stream untergeht. Und in einem eigenen
    Faden, denn die Oberfläche hat nicht zu warten, bis der Ton zu Ende ist.
    """
    if not IST_WINDOWS and not os.path.isfile(datei):
        return

    def lauf():
        try:
            if IST_WINDOWS:
                import winsound
                if datei and os.path.isfile(datei):
                    winsound.PlaySound(datei, winsound.SND_FILENAME
                                       | winsound.SND_ASYNC)
                else:
                    # Ohne eigene Datei der Systemklang - besser als
                    # Stille, und es muss nichts mitgeliefert werden.
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
            else:
                subprocess.run(["afplay", datei], check=False, timeout=10,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        except (subprocess.SubprocessError, OSError, RuntimeError, ImportError):
            pass
    threading.Thread(target=lauf, daemon=True).start()


def _kurz(text: str, laenge: int) -> str:
    """Abschneiden mit Auslassungszeichen – sonst bricht ein Setname mitten
    im Wort ab und sieht aus wie ein Fehler."""
    text = (text or "").strip()
    return text if len(text) <= laenge else text[:laenge - 1].rstrip() + "…"


def _eigene_sets(info: dict) -> list:
    """Sets aus **deiner** Sammlung, in denen diese Figur steckt.

    `in_sets` kommt als "nummer|name|anzahl|zustand;;…". Das vierte Feld
    gibt es seit App-Fassung 2.76.0; fehlt es, gilt „gebraucht" – das ist
    die vorsichtigere Annahme, denn nur ein **neues** Set zählt als
    „Figur ist drin".
    """
    raus = []
    for stueck in (info.get("in_sets") or "").split(";;"):
        felder = stueck.split("|")
        if len(felder) < 3:
            continue
        try:
            anzahl = int(felder[2])
        except ValueError:
            anzahl = 1
        zustand = felder[3] if len(felder) > 3 else "used"
        raus.append((felder[0], felder[1], anzahl, zustand))
    return raus


def _alle_sets(info: dict, hoechstens: int = 0) -> str:
    """In welchen Sets kam die Figur überhaupt heraus?

    Nicht dasselbe wie `in_sets`: Das sind die Sets, die **ihr** habt; dies
    hier ist der Katalog. Beim Mitbieten ist beides eine eigene Frage – „habe
    ich das Set schon" und „woher stammt die Figur eigentlich".

    Kommt erst mit der zweiten Antwort (`?detail=1`), zusammen mit dem Preis.
    """
    sets = info.get("all_sets") or []
    if not sets:
        return ""
    hoechstens = hoechstens or KATALOG_SETS
    gezeigt = ["{} {}".format(s.get("no", ""), _kurz(s.get("name"), 34))
               for s in sets[:hoechstens]]
    rest = len(sets) - len(gezeigt)
    if rest > 0:
        gezeigt.append("+{} weitere".format(rest))
    return "📦 aus {} Set{}: {}".format(
        len(sets), "" if len(sets) == 1 else "s", ",  ".join(gezeigt))


def ansicht_dazulegen(eintrag: dict, bild: bytes) -> None:
    """Eine weitere Aufnahme zum Stand legen – höchstens `MINI_HOECHSTENS`.

    Ist der Platz voll, fliegt die **älteste nicht ausgesuchte** heraus. Was
    der Anwender angehakt hat, bleibt: Er hat es sich ja angesehen. Die
    Nummern der Auswahl rutschen dabei mit, sonst zeigte sie hinterher auf
    das falsche Bild.
    """
    bilder = eintrag.setdefault("bilder", [])
    gewaehlt = eintrag.setdefault("bilder_an", set())
    bilder.append(bild)
    if len(bilder) <= MINI_HOECHSTENS:
        return
    weg = next((i for i in range(len(bilder) - 1) if i not in gewaehlt), 0)
    del bilder[weg]
    eintrag["bilder_an"] = {i - 1 if i > weg else i
                            for i in gewaehlt if i != weg}


def _ansichten_vereinen(bisher: list, neu: list):
    """Zwei Trefferlisten derselben Figur zu einer machen.

    Auf einer Drehscheibe sieht die Erkennung dieselbe Figur drei- oder
    viermal aus verschiedenen Winkeln und antwortet jedes Mal etwas anders.
    Das ist kein Ärgernis, sondern die beste Auskunft, die man kriegen kann:
    Eine Figur, die aus zwei Winkeln mit 62 % und 58 % kommt, ist mit viel
    höherer Wahrscheinlichkeit die richtige als eine, die einmal mit 83 %
    aufblitzt und danach nie wieder.

    Deshalb: nichts wegwerfen, sondern zählen. Von der Trefferquote bleibt
    die beste stehen, die Zahl der Ansichten kommt dazu, und sortiert wird
    nach Bestätigungen zuerst. Zurück kommt die vereinte Liste und die Menge
    der Nummern, deren Quote aus der **neuen** Ansicht stammt.
    """
    nach_nummer = {t["item_id"]: t for t in bisher}
    verbessert = set()
    for t in neu:
        alt = nach_nummer.get(t["item_id"])
        if alt is None:
            t["_ansichten"] = 1
            bisher.append(t)
            nach_nummer[t["item_id"]] = t
            verbessert.add(t["item_id"])
            continue
        alt["_ansichten"] = alt.get("_ansichten", 1) + 1
        if (t.get("score") or 0) > (alt.get("score") or 0):
            alt["score"] = t["score"]
            verbessert.add(t["item_id"])
        # Was die Instanz frisch mitgeschickt hat, gilt – aber nichts
        # Leeres über etwas Gefülltes.
        for schluessel, wert in (t.get("_info") or {}).items():
            if wert is not None:
                alt.setdefault("_info", {})[schluessel] = wert
    # Mehrfach Bestätigtes nach oben; von Hand Eingetragenes ganz nach oben,
    # denn dort hat niemand geraten.
    bisher.sort(key=lambda t: (not t.get("_getippt"),
                               -t.get("_ansichten", 1),
                               -(t.get("score") or 0)))
    return bisher, verbessert


def _meldung(fehler) -> str:
    """Die App antwortet mit brauchbaren deutschen Sätzen – die zeigen wir,
    nicht die nackte Statusnummer."""
    try:
        d = json.loads(fehler.read())
        if isinstance(d, dict) and d.get("detail"):
            return str(d["detail"])
    except Exception:
        pass
    return f"HTTP {fehler.code}"


def _pillow():
    """Pillow – aber nur unter Windows und nur beim ersten Bedarf.

    Auf dem Mac erledigen `sips` und `screencapture` alles, was hier
    gebraucht wird; das Werkzeug kommt dort ohne eine einzige
    Fremdbibliothek aus, und dabei soll es bleiben. Windows bringt kein
    Gegenstueck mit, deshalb dort Pillow.

    Gibt None zurueck, wenn es fehlt - die Aufrufer kommen damit zurecht
    und liefern das Bild lieber ungeaendert aus, als abzustuerzen.
    """
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def als_png(roh: bytes) -> bytes | None:
    """Beliebiges Bild in PNG wandeln – Tk zeigt nur PNG, GIF und PPM.

    Der Katalog-Weiterleiter der Instanz liefert JPEG. Auf dem Mac wandelt
    `sips`, das im System steckt; unter Windows Pillow.
    """
    if not roh:
        return None
    if roh[:4] == b"\x89PNG":
        return roh
    if IST_WINDOWS:
        Image = _pillow()
        if Image is None:
            return None
        try:
            with Image.open(io.BytesIO(roh)) as bild:
                hinaus = io.BytesIO()
                bild.convert("RGBA").save(hinaus, format="PNG")
                return hinaus.getvalue()
        except Exception:
            return None
    quelle = os.path.join(tempfile.gettempdir(),
                          f"brickfolio-ref-{uuid.uuid4().hex}")
    ziel = quelle + ".png"
    try:
        with open(quelle, "wb") as f:
            f.write(roh)
        subprocess.run(["sips", "-s", "format", "png", quelle, "--out", ziel],
                       check=False, timeout=30,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.isfile(ziel) and os.path.getsize(ziel):
            with open(ziel, "rb") as f:
                return f.read()
        return None
    except (subprocess.SubprocessError, OSError):
        return None
    finally:
        for p in (quelle, ziel):
            try:
                os.remove(p)
            except OSError:
                pass


def auf_groesse(roh: bytes, kante: int) -> bytes | None:
    """Ein PNG auf die längste Kante bringen – stufenlos.

    Tk kann von sich aus nur ganzzahlig verkleinern (halb, drittel, …), und
    dazwischen gibt es nichts: Aus 512 px wird 256 oder 171, sonst nichts.
    `sips` rechnet sauber auf jede Größe – und steckt in macOS, kostet also
    keine Bibliothek.
    """
    if not roh:
        return None
    if IST_WINDOWS:
        Image = _pillow()
        if Image is None:
            return roh                     # dann eben ungeändert
        try:
            with Image.open(io.BytesIO(roh)) as bild:
                bild = bild.convert("RGBA")
                b, h = bild.size
                if max(b, h) > kante:
                    teiler = max(b, h) / float(kante)
                    bild = bild.resize((max(1, int(b / teiler)),
                                        max(1, int(h / teiler))),
                                       Image.LANCZOS)
                hinaus = io.BytesIO()
                bild.save(hinaus, format="PNG")
                return hinaus.getvalue()
        except Exception:
            return roh
    quelle = os.path.join(tempfile.gettempdir(),
                          f"brickfolio-skal-{uuid.uuid4().hex}.png")
    try:
        with open(quelle, "wb") as f:
            f.write(roh)
        fertig = subprocess.run(
            ["sips", "-Z", str(kante), "-s", "format", "png", quelle,
             "--out", quelle], check=False, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if fertig.returncode != 0 or not os.path.getsize(quelle):
            return roh                     # dann eben ungeändert
        with open(quelle, "rb") as f:
            return f.read()
    except (subprocess.SubprocessError, OSError):
        return roh
    finally:
        try:
            os.remove(quelle)
        except OSError:
            pass


# ------------------------------------------------------------- Automatik
#
# Damit der Scanner von selbst auslösen kann, muss er merken, ob sich im
# gemerkten Bereich etwas getan hat. Das geschieht **hier**, auf diesem
# Rechner: Der Bildschirmausschnitt wird auf 24 × 24 Pixel eingedampft und
# mit dem vorigen verglichen. Nach außen geht dabei nichts – erst wenn das
# Bild zur Ruhe gekommen ist, wird eine einzige Anfrage geschickt.
#
# Das ist auch der Grund, warum die Automatik der Erkennung nicht schadet,
# sondern nützt: Sie wartet, bis die Figur still gehalten wird. Genau daran
# scheitern die meisten Versuche von Hand – Bewegungsunschärfe kostet mehr
# Treffer als schlechtes Licht.
FINGER_KANTE = 24
AUTO_TAKT = 0.6            # Sekunden zwischen zwei Messungen
AUTO_RUHE = 3              # so viele Takte muss das Bild still stehen
AUTO_PAUSE = 3.0           # Mindestabstand zweier Anfragen, in Sekunden
AUTO_JE_MINUTE = 12        # Obergrenze; die Instanz selbst bremst bei 40

# Drehscheiben. Manche Verkäufer stellen die Figur auf einen Teller, der sich
# dauernd dreht – dann wird das Bild **nie** still, und ein Wächter, der auf
# Ruhe wartet, löste dort niemals aus. Also die zweite Regel: Hält die
# Bewegung an, ohne dass sie ein Sprung wäre, dreht sich offenbar etwas, und
# dann wird eben mittendrin geschickt.
AUTO_DREH_TAKTE = 6        # so lange Bewegung am Stück gilt als „es dreht sich"
AUTO_SPRUNG = 3.0          # ab diesem Vielfachen der Schwelle: neuer Artikel
AUTO_ANSICHTEN = 4         # so viele Ansichten je Artikel genügen
# Nach so vielen erfolglosen Anfragen am Stück hört der Dreh-Auslöser auf.
# Denn er kann eine Drehscheibe nicht von irgendeiner anderen anhaltenden
# Bewegung unterscheiden: Eine Laufschrift, ein Countdown, ein scrollender
# Chat im gemerkten Bereich sehen für ihn genauso aus. Wo aber dreimal
# hintereinander nichts zu erkennen war, bringt ein viertes Bild desselben
# Flecks auch nichts – dann besser schweigen, bis sich wirklich etwas ändert.
AUTO_LEERLAUF = 3

# Ab welcher Abweichung „ruhig" aufhört und „etwas Neues" anfängt. Ein
# Bildschirmabzug ist pixelgenau, ein Videobild rauscht – deshalb drei
# Stufen statt einer geratenen Zahl.
EMPFINDLICHKEIT = {
    "hoch":     (1.0, 2.5),
    "mittel":   (2.0, 5.0),
    "niedrig":  (3.5, 10.0),
}


def fingerabdruck(roh: bytes, kante: int = FINGER_KANTE) -> list | None:
    """Ein Bild auf ein paar hundert Helligkeitswerte eindampfen.

    Über BMP, nicht über Tk: `tk.PhotoImage` darf nur der Hauptfaden anfassen,
    und gemessen wird im Hintergrund. BMP hat dafür genau die richtige Menge
    Format – ein Kopf mit fester Länge, dahinter die Bildpunkte.
    """
    if not roh:
        return None
    if IST_WINDOWS:
        Image = _pillow()
        if Image is None:
            return None
        try:
            with Image.open(io.BytesIO(roh)) as bild:
                # Genau dieselbe Menge Zahlen wie auf dem Mac: ein Quadrat
                # aus Helligkeitswerten. Verglichen wird immer nur mit einem
                # Abzug derselben Herkunft, also muessen die beiden Wege
                # nicht aufs Byte uebereinstimmen - nur jeder mit sich.
                klein = bild.convert("L").resize((kante, kante))
                return list(klein.getdata())
        except Exception:
            return None
    quelle = os.path.join(tempfile.gettempdir(),
                          f"brickfolio-wacht-{uuid.uuid4().hex}.png")
    ziel = quelle + ".bmp"
    try:
        with open(quelle, "wb") as f:
            f.write(roh)
        subprocess.run(["sips", "-z", str(kante), str(kante), "-s", "format",
                        "bmp", quelle, "--out", ziel], check=False, timeout=20,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.isfile(ziel):
            return None
        with open(ziel, "rb") as f:
            d = f.read()
        if len(d) < 54:
            return None
        beginn = int.from_bytes(d[10:14], "little")
        breite = int.from_bytes(d[18:22], "little", signed=True)
        hoehe = abs(int.from_bytes(d[22:26], "little", signed=True))
        proz = int.from_bytes(d[28:30], "little") // 8
        if breite <= 0 or hoehe <= 0 or proz < 3:
            return None
        # BMP-Zeilen sind auf vier Byte aufgerundet. Ob sie von oben oder von
        # unten kommen, ist hier gleichgültig – verglichen wird immer nur mit
        # einem Abzug derselben Herkunft.
        zeile = (breite * proz + 3) // 4 * 4
        if len(d) < beginn + zeile * hoehe:
            return None
        return [sum(d[beginn + y * zeile + x * proz:
                      beginn + y * zeile + x * proz + 3]) // 3
                for y in range(hoehe) for x in range(breite)]
    except (subprocess.SubprocessError, OSError, ValueError):
        return None
    finally:
        for p in (quelle, ziel):
            try:
                os.remove(p)
            except OSError:
                pass


def abweichung(a: list, b: list) -> float:
    """Wie weit zwei Fingerabdrücke auseinanderliegen – 0 heißt gleich."""
    if not a or not b or len(a) != len(b):
        return 999.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def in_zwischenablage(bild: bytes) -> bool:
    """Das Bild in die Zwischenablage legen – für den zweiten Weg.

    Dann geht es in der App weiter wie bisher: ins Scannen-Feld klicken,
    ⌘V, und der gewohnte Ablauf mit allen Knöpfen läuft. Das Werkzeug muss
    dafür nichts können, was die App nicht schon kann.
    """
    pfad = os.path.join(tempfile.gettempdir(),
                        f"brickfolio-ablage-{uuid.uuid4().hex}.png")
    try:
        with open(pfad, "wb") as f:
            f.write(bild)
        if IST_WINDOWS:
            # Ueber Windows PowerShell 5.1 - die liegt auf jedem Windows und
            # laeuft im STA-Modus, den die Zwischenablage verlangt. pwsh 7
            # taete es nicht ohne Weiteres, und eine Fremdbibliothek nur
            # hierfuer waere zu viel.
            sicher = pfad.replace("'", "''")
            fertig = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command",
                 "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
                 "$b=[System.Drawing.Image]::FromFile('%s'); "
                 "[System.Windows.Forms.Clipboard]::SetImage($b); "
                 "$b.Dispose()" % sicher],
                check=False, timeout=25, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return fertig.returncode == 0
        befehl = ('set the clipboard to (read (POSIX file "%s") '
                  'as «class PNGf»)' % pfad)
        fertig = subprocess.run(["osascript", "-e", befehl], check=False,
                                timeout=20, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        return fertig.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False
    finally:
        try:
            os.remove(pfad)
        except OSError:
            pass


def reste_aufraeumen(hoechstens_alt: float = 3600.0) -> int:
    """Eigene Zwischendateien wegräumen, die ein Absturz hinterlassen hat.

    Im ordentlichen Betrieb entsteht kein Rest: Jede dieser Dateien wird im
    `finally` ihres Erzeugers gelöscht. Wird das Programm aber hart beendet –
    Absturz, „Sofort beenden", Abmelden mitten im Wächtertakt –, bleibt der
    gerade laufende Abzug liegen. Einzeln ist das nichts; es sind aber
    **Bildschirmausschnitte**, und die sollen nicht wochenlang herumliegen,
    bis macOS von sich aus aufräumt.

    Nur die eigenen Namensmuster, nur im Temp-Verzeichnis, und nur was älter
    als eine Stunde ist – ein zweites, gerade laufendes Fenster soll seine
    Dateien nicht unter den Händen weggelöscht bekommen.
    """
    muster = ("brickfolio-livescan-", "brickfolio-ref-", "brickfolio-skal-",
              "brickfolio-wacht-", "brickfolio-ablage-", "brickfolio-bereich-")
    ordner = tempfile.gettempdir()
    jetzt = time.time()
    weg = 0
    try:
        namen = os.listdir(ordner)
    except OSError:
        return 0
    for name in namen:
        if not name.startswith(muster):
            continue
        pfad = os.path.join(ordner, name)
        try:
            if not os.path.isfile(pfad):
                continue
            if jetzt - os.path.getmtime(pfad) < hoechstens_alt:
                continue
            os.remove(pfad)
            weg += 1
        except OSError:
            pass
    return weg


def _multipart(felder: dict, grenze: str) -> bytes:
    """Kleiner Formular-Zusammenbau – damit dieses Werkzeug ohne
    Fremdbibliotheken auskommt."""
    teile = []
    for name, (dateiname, typ, inhalt) in felder.items():
        teile.append(f"--{grenze}\r\n".encode())
        teile.append((f'Content-Disposition: form-data; name="{name}"; '
                      f'filename="{dateiname}"\r\n'
                      f"Content-Type: {typ}\r\n\r\n").encode())
        teile.append(inhalt)
        teile.append(b"\r\n")
    teile.append(f"--{grenze}--\r\n".encode())
    return b"".join(teile)


# --------------------------------------------------------- Bildschirmfoto

# ---------------------------------------------------------------- Farben
#
# **Warum das nicht einfach feste Werte sein können.** Die grauen Töne hier
# waren für einen hellen Grund gewählt: #666 auf Weiß ist ein ruhiges,
# gut lesbares Grau. Auf dem dunklen Grund des Nachtmodus ist dasselbe
# #666 fast unsichtbar – Nummer, Trefferquote und Preise verschwanden.
#
# Gemessen statt geraten: Welcher Modus gerade gilt, verrät die Helligkeit
# des Fenstergrunds. Das kommt ohne Systemabfrage aus und stimmt auch dann,
# wenn jemand mitten im Betrieb umschaltet – dann greift es beim nächsten
# Start.
FARBEN = {
    "leise":    "#666",    # Beiwerk: Beschriftungen, Hinweise
    "matt":     "#888",    # noch leiser: Zusätze in Zeilen
    "still":    "#999",    # am leisesten: Erledigtes, Ausgegrautes
    "klar":     "#222",    # kräftiger Text
    "kraeftig": "#444",    # etwas weniger kräftig
    "linie":    "#ddd",    # Trennlinien und leere Flächen
    "verweis":  "#0b5fa5", # anklickbar
    "warnung":  "#b00000", # etwas ist schiefgegangen
    "geschafft": "#22aa77", # etwas hat geklappt
}

_FARBEN_DUNKEL = {
    "leise":  "#9a9a9a",
    "matt":   "#a8a8a8",
    "still":  "#b4b4b4",
    "klar":   "#e8e8e8",
    "kraeftig": "#d0d0d0",
    "linie":  "#3a3a3a",
    "verweis": "#6cb6f0",
    # Nachts nicht dasselbe Rot: #b00000 auf dunklem Grund ist kaum noch zu
    # lesen (Kontrast 2,4). Aufgehellt steht es da, ohne zu schreien.
    "warnung": "#ff8a80",
    "geschafft": "#5bd6a4",
}


def grund_ist_dunkel(wurzel) -> bool:
    """Ist der Fenstergrund dunkel?

    Über `winfo_rgb`, das auch die Systemfarben von macOS auflöst – deshalb
    braucht es keine Abfrage beim Betriebssystem und funktioniert auf
    beiden Systemen gleich.
    """
    try:
        farbe = ttk.Style().lookup("TFrame", "background") \
            or wurzel.cget("background")
        r, g, b = wurzel.winfo_rgb(farbe)
    except Exception:
        return False
    # winfo_rgb liefert 16 Bit je Kanal.
    return (0.299 * r + 0.587 * g + 0.114 * b) / 65535.0 < 0.5


_MODUS = {"dunkel": None}


def farben_setzen(wurzel, dunkel=None) -> bool:
    """Die Palette an den Grund anpassen. Gibt zurück, ob dunkel."""
    dunkel = grund_ist_dunkel(wurzel) if dunkel is None else dunkel
    FARBEN.update(_FARBEN_DUNKEL if dunkel else _FARBEN_HELL)
    _MODUS["dunkel"] = dunkel
    return dunkel


def _umfaerben(widget, umschlag: dict) -> int:
    """Jede Schriftfarbe aus dem alten Satz durch die neue ersetzen.

    Ohne Verzeichnis der Bedienelemente: Es wird schlicht nachgesehen,
    welche Farbe dort steht. Was nicht aus der Palette stammt – Grün,
    Wunschgelb, Weiß auf farbigem Grund – bleibt unangetastet, weil es im
    Umschlag nicht vorkommt.
    """
    geaendert = 0
    for kind in widget.winfo_children():
        for feld in ("foreground", "fill"):
            try:
                jetzt = str(kind.cget(feld))
            except Exception:
                continue
            if jetzt in umschlag:
                try:
                    kind.config(**{feld: umschlag[jetzt]})
                    geaendert += 1
                except Exception:
                    pass
        # Text auf einer Leinwand hängt nicht am Bedienelement.
        try:
            for stueck in kind.find_all():
                jetzt = str(kind.itemcget(stueck, "fill"))
                if jetzt in umschlag:
                    kind.itemconfigure(stueck, fill=umschlag[jetzt])
                    geaendert += 1
        except Exception:
            pass
        geaendert += _umfaerben(kind, umschlag)
    return geaendert


def farben_auffrischen(wurzel) -> bool:
    """Hat der Rechner den Modus gewechselt? Dann alles umfärben.

    **Warum das nötig ist.** macOS schaltet abends von selbst auf dunkel.
    Der Grund des Fensters folgt sofort – die Schriftfarben nicht, die
    stehen ja fest in den Bedienelementen. Ergebnis: dunkler Grund, helle
    Palette von vorhin, und Nummer, Quote und Preise sind wieder weg.

    Genau das stand vorher als Einschränkung im Quelltext (»greift beim
    nächsten Start«). Eine dokumentierte Einschränkung ist keine Lösung,
    wenn sie jeden Abend zuschlägt.
    """
    jetzt_dunkel = grund_ist_dunkel(wurzel)
    if jetzt_dunkel == _MODUS["dunkel"]:
        return False
    vorher = dict(FARBEN)
    farben_setzen(wurzel, dunkel=jetzt_dunkel)
    umschlag = {vorher[rolle]: FARBEN[rolle] for rolle in FARBEN
                if vorher[rolle] != FARBEN[rolle]}
    if umschlag:
        _umfaerben(wurzel, umschlag)
    bauteile_auffrischen()
    return True


_FARBEN_HELL = dict(FARBEN)


# ------------------------------------------------ Bauteile der Handschrift
#
# **Warum eigene Knöpfe.** Die App hat eine erkennbare Handschrift: dunkle
# Kante, runde Ecken, Gelb für den Auslöser, Grün für „Zur Sammlung", und
# was seltener gebraucht wird, steht als Zeichen daneben. Die Systemknöpfe
# von ttk können davon nichts – unter macOS nehmen sie weder Farbe noch
# Kante an, alle sehen gleich wichtig aus. Also zeichnen sich die beiden
# Bauteile hier selbst auf eine Leinwand. Das geht unter macOS und Windows
# gleich und braucht keine Fremdbibliothek.
#
# Nach außen benehmen sie sich wie die Knöpfe vorher: `config(state=...)`,
# `cget("state")`, `pack`. Dadurch bleibt der übrige Code, wie er war.

_BAUTEILE = weakref.WeakSet()

# Je Art: (Fläche, Schrift, Fläche beim Überfahren). Kante und Schatten
# gelten für alle gleich.
_KNOPF_HELL = {
    "normal":  ("#FFFFFF", "#1D1D1B", "#F2F3F5"),
    "gelb":    ("#FFCF00", "#1D1D1B", "#F2C300"),
    "gruen":   ("#00963E", "#FFFFFF", "#008837"),
    "an":      ("#FFCF00", "#1D1D1B", "#F2C300"),   # gesetztes Zeichen ★
    "kante": "#1D1D1B", "schatten": "#B9BCC1",
    "aus": ("#F1F2F4", "#9A9DA2", "#C4C7CC"),        # Fläche, Schrift, Kante
    "spur": "#E1E3E7", "spur_schrift": "#6B6E73",
    "blass": "#D3D6DB", "blass_schrift": "#9A9DA2",
}
# Nachts keine weiße Fläche – sie leuchtete im dunklen Fenster wie ein
# Loch. Gelb und Grün bleiben: Sie tragen die Bedeutung, und auf Dunkel
# stehen sie sogar besser.
_KNOPF_DUNKEL = {
    "normal":  ("#3A3A3C", "#F2F2F2", "#48484A"),
    "gelb":    ("#FFCF00", "#1D1D1B", "#F2C300"),
    "gruen":   ("#00963E", "#FFFFFF", "#00A444"),
    "an":      ("#FFCF00", "#1D1D1B", "#F2C300"),
    "kante": "#8E8E93", "schatten": "#141416",
    "aus": ("#2C2C2E", "#6E6E73", "#48484A"),
    "spur": "#3A3A3C", "spur_schrift": "#A8A8A8",
    "blass": "#55555A", "blass_schrift": "#7C7C80",
}


def _knopffarben() -> dict:
    return _KNOPF_DUNKEL if _MODUS["dunkel"] else _KNOPF_HELL


def _grund(widget) -> str:
    """Die Farbe hinter dem Bauteil – damit die runden Ecken nicht eckig
    aussehen. Unter macOS ist das ein Systemname, der Tag und Nacht von
    selbst mitgeht."""
    try:
        return ttk.Style().lookup("TFrame", "background") \
            or widget.winfo_toplevel().cget("background")
    except Exception:
        return widget.winfo_toplevel().cget("background")


def _rund(leinwand, x1, y1, x2, y2, r, **art):
    """Ein Rechteck mit runden Ecken – als geglättetes Vieleck, das Tk von
    Haus aus kann."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    punkte = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
              x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
              x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return leinwand.create_polygon(punkte, smooth=True, **art)


def _punkt(widget) -> float:
    """Bildpunkte je typografischem Punkt.

    **Unter Windows wächst die Schrift mit der Bildschirmskalierung** –
    `main()` setzt `tk scaling` passend. Maße in festen Bildpunkten wüchsen
    nicht mit: Auf einem 150-%-Schirm stünde große Schrift in einem zu
    kleinen Knopf. Darum wachsen die Maße der Bauteile mit.

    Bezugsgröße sind 96 dpi, also 4/3 Bildpunkte je Punkt: So rechnet Tk
    auf dem Mac, und so steht Windows bei 100 %. Beide ergeben 1, bei 150 %
    unter Windows kommt 1,5 heraus. (Nicht einfach Punkte nehmen: Dann
    wären die Knöpfe auch auf dem Mac um ein Drittel gewachsen.)
    """
    try:
        return max(1.0, float(widget.winfo_fpixels("1p")) * 72 / 96)
    except Exception:
        return 1.0


def _fett(groesse: int = 13):
    schrift = tkfont.nametofont("TkDefaultFont").copy()
    schrift.configure(weight="bold", size=groesse)
    return schrift


class Knopf(tk.Canvas):
    """Ein Knopf in der Handschrift der App.

    `art`: "normal" (weiß), "gelb" (Auslöser), "gruen" (Zur Sammlung) oder
    "zeichen" (quadratisch, nur ein Zeichen wie ☆ – gesetzt mit `an=True`
    wird er gelb, genau wie der Stern in der App).
    """

    def __init__(self, master, text="", command=None, art="normal",
                 state="normal", hoehe=32, breite=None, groesse=12):
        super().__init__(master, highlightthickness=0, bd=0,
                         background=_grund(master), cursor=ZEIGEHAND)
        self._text = text
        self._befehl = command
        self._art = art
        self._zustand = state
        self._an = False
        self._ueber = False
        self._gedrueckt = False
        self._schrift = _fett(groesse)
        self._k = _punkt(self)
        self._hoehe = round(hoehe * self._k)
        self._feste_breite = round(breite * self._k) if breite else None
        super().configure(width=self._breite(),
                          height=self._hoehe + round(2 * self._k))
        self.bind("<Configure>", lambda _e: self._zeichnen())
        self.bind("<Enter>", lambda _e: self._setzen(ueber=True))
        self.bind("<Leave>", lambda _e: self._setzen(ueber=False,
                                                     gedrueckt=False))
        self.bind("<ButtonPress-1>", lambda _e: self._setzen(gedrueckt=True))
        self.bind("<ButtonRelease-1>", self._losgelassen)
        _BAUTEILE.add(self)
        self._zeichnen()

    def _breite(self) -> int:
        if self._feste_breite:
            return self._feste_breite
        if self._art == "zeichen":
            return self._hoehe + round(6 * self._k)
        return self._schrift.measure(self._text) + round(30 * self._k)

    # ----- dieselbe Schnittstelle wie ttk.Button
    def configure(self, cnf=None, **kw):
        if cnf:
            kw.update(cnf)
        neu = False
        for schluessel, feld in (("text", "_text"), ("command", "_befehl"),
                                 ("state", "_zustand"), ("an", "_an")):
            if schluessel in kw:
                setattr(self, feld, kw.pop(schluessel))
                neu = True
        if kw:
            super().configure(**kw)
        if "text" in (cnf or {}) or neu:
            # Ein längerer Text braucht mehr Platz – sonst würde er
            # abgeschnitten („Der Browser ist offen – bitte anmelden …").
            super().configure(width=self._breite())
        if neu:
            super().configure(cursor=ZEIGEHAND if self._zustand != "disabled"
                              else "")
            self._zeichnen()

    config = configure

    def cget(self, schluessel):
        if schluessel == "state":
            return self._zustand
        if schluessel == "text":
            return self._text
        return super().cget(schluessel)

    def invoke(self):
        if self._zustand != "disabled" and self._befehl:
            return self._befehl()

    # ----- Verhalten
    def _setzen(self, ueber=None, gedrueckt=None):
        if ueber is not None:
            self._ueber = ueber
        if gedrueckt is not None:
            self._gedrueckt = gedrueckt
        self._zeichnen()

    def _losgelassen(self, ereignis):
        drin = 0 <= ereignis.x < self.winfo_width() and \
            0 <= ereignis.y < self.winfo_height()
        war = self._gedrueckt
        self._setzen(gedrueckt=False)
        if drin and war:
            self.invoke()

    def _zeichnen(self):
        self.delete("all")
        f = _knopffarben()
        super().configure(background=_grund(self.master))
        b = max(self.winfo_width(), int(super().cget("width")))
        h = max(self.winfo_height(), int(super().cget("height")))
        aus = self._zustand == "disabled"
        k = self._k
        tief = round(k) if (self._gedrueckt and not aus) else 0
        rund, kante_breit, schatten = 10 * k, max(2, round(2 * k)), 2 * k
        if aus:
            flaeche, schrift, kante = f["aus"]
        else:
            art = "an" if self._an else \
                ("normal" if self._art == "zeichen" else self._art)
            flaeche, schrift, flaeche_ueber = f[art]
            if self._ueber:
                flaeche = flaeche_ueber
            kante = f["kante"]
            if not tief:
                # Der Schatten: dieselbe Form, zwei Punkt tiefer – wie der
                # „--shadow" der App.
                _rund(self, 1, 1 + schatten, b - 1, h - 1, rund,
                      fill=f["schatten"], outline="")
        _rund(self, 1, 1 + tief, b - 1, h - 1 - schatten + tief, rund,
              fill=flaeche, outline=kante, width=kante_breit)
        self.create_text(b / 2, (h - schatten) / 2 + tief, text=self._text,
                         fill=schrift, font=self._schrift)


class Pille(tk.Canvas):
    """Eine Auswahl aus wenigen Werten – wie „Gebraucht / Neu" in der App.

    Hängt an einer `tk.StringVar`; wer die Variable setzt, sieht es hier,
    und ein Klick setzt die Variable. `get`/`set` gibt es trotzdem, damit
    sie sich wie das Auswahlfeld vorher bedienen lässt.
    """

    def __init__(self, master, werte, variable, command=None, groesse=12,
                 hoehe=30):
        super().__init__(master, highlightthickness=0, bd=0,
                         background=_grund(master), cursor=ZEIGEHAND)
        self._werte = list(werte)             # [(wert, beschriftung), …]
        self._var = variable
        self._zustand = "normal"
        self._befehl = command
        self._schrift = _fett(groesse)
        self._k = _punkt(self)
        self._rand = round(3 * self._k)
        breiten = [self._schrift.measure(t) + round(22 * self._k)
                   for _w, t in self._werte]
        self._breiten = breiten
        super().configure(width=sum(breiten) + 2 * self._rand,
                          height=round(hoehe * self._k))
        self.bind("<Configure>", lambda _e: self._zeichnen())
        self.bind("<ButtonRelease-1>", self._geklickt)
        self._var.trace_add("write", lambda *_e: self._zeichnen())
        _BAUTEILE.add(self)
        self._zeichnen()

    def get(self):
        return self._var.get()

    def set(self, wert):
        self._var.set(wert)

    def configure(self, cnf=None, **kw):
        """`state="disabled"` macht die Pille **blass** – klickbar bleibt
        sie: Die Stufe darf man wählen, bevor sie gilt."""
        if cnf:
            kw.update(cnf)
        if "state" in kw:
            self._zustand = kw.pop("state")
            self._zeichnen()
        if kw:
            super().configure(**kw)

    config = configure

    def cget(self, schluessel):
        if schluessel == "state":
            return self._zustand
        return super().cget(schluessel)

    def _geklickt(self, ereignis):
        x = self._rand
        for (wert, _t), breite in zip(self._werte, self._breiten):
            if x <= ereignis.x < x + breite:
                if self._var.get() != wert:
                    self._var.set(wert)
                    if self._befehl:
                        self._befehl()
                return
            x += breite

    def _zeichnen(self):
        self.delete("all")
        f = _knopffarben()
        super().configure(background=_grund(self.master))
        h = int(super().cget("height"))
        r = self._rand
        b = sum(self._breiten) + 2 * r
        _rund(self, 0, 0, b, h, h / 2, fill=f["spur"], outline="")
        x = r
        for (wert, text), breite in zip(self._werte, self._breiten):
            gewaehlt = self._var.get() == wert
            blass = self._zustand == "disabled"
            if gewaehlt:
                _rund(self, x, r, x + breite, h - r, (h - 2 * r) / 2,
                      fill=f["blass"] if blass else "#FFCF00", outline="")
            if blass:
                farbe = f["spur_schrift"] if gewaehlt else f["blass_schrift"]
            else:
                farbe = "#1D1D1B" if gewaehlt else f["spur_schrift"]
            self.create_text(x + breite / 2, h / 2, text=text,
                             font=self._schrift, fill=farbe)
            x += breite


def bauteile_auffrischen() -> None:
    """Nach einem Wechsel zwischen Tag und Nacht alle neu zeichnen."""
    for teil in list(_BAUTEILE):
        try:
            teil._zeichnen()
        except tk.TclError:
            pass


DPI_WEG = "noch nicht gesetzt"


def mac_desktop() -> tuple:
    """Ursprung und Maße **aller** Bildschirme – in Punkten.

    Über den Finder, der die Vereinigung aller Schirme als »Fenster des
    Schreibtischs« kennt. Das ist der einzige Weg, der ohne Fremdbibliothek
    und ohne Zusatzrechte auskommt.

    Klappt es nicht – etwa weil die Freigabe für Kurzbefehle fehlt –, bleibt
    es beim Hauptbildschirm. Dann sieht man im Auswahlfenster eben nur
    diesen, statt gar nichts.

    (x, y, breite, hoehe) oder (0, 0, 0, 0).
    """
    try:
        fertig = subprocess.run(
            ["osascript", "-e",
             "tell application \"Finder\" to get bounds of window of desktop"],
            capture_output=True, text=True, timeout=15)
        teile = [int(s.strip()) for s in fertig.stdout.strip().split(",")]
        if len(teile) == 4 and teile[2] > teile[0] and teile[3] > teile[1]:
            return (teile[0], teile[1], teile[2] - teile[0],
                    teile[3] - teile[1])
    except (subprocess.SubprocessError, OSError, ValueError):
        pass
    return (0, 0, 0, 0)


def windows_dpi_beachten() -> str:
    """Windows sagen, dass wir mit echten Bildpunkten rechnen können.

    **Ohne das belügt Windows das Programm** – wohlmeinend: Ein Programm,
    das sich nicht als DPI-bewusst meldet, bekommt *logische* Maße
    vorgesetzt, während `ImageGrab` echte Bildpunkte liefert. Bei einem
    Bildschirm fällt das kaum auf; bei zweien mit unterschiedlicher
    Skalierung geht die eine Achse auf und die andere nicht.

    Genau das war der Fehler vom 31.08.2026, und er lag nicht an einem
    bestimmten Rechner – er trifft jeden mit skaliertem Bildschirm.

    Muss **vor** dem ersten Fenster stehen; danach nimmt Windows es nicht
    mehr an. Gibt zurück, welcher Weg gegriffen hat.
    """
    global DPI_WEG
    if not IST_WINDOWS:
        DPI_WEG = "keiner (nicht Windows)"
        return DPI_WEG
    import ctypes
    # -4 ist PER_MONITOR_AWARE_V2: jeder Bildschirm mit eigener Skalierung.
    # Das gibt es seit Windows 10 1703; darunter die beiden Rückfallwege.
    try:
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(
                ctypes.c_void_p(-4)):
            DPI_WEG = "per Monitor (v2)"
            return DPI_WEG
    except Exception:
        pass
    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            DPI_WEG = "per Monitor"
            return DPI_WEG
    except Exception:
        pass
    try:
        if ctypes.windll.user32.SetProcessDPIAware():
            DPI_WEG = "systemweit"
            return DPI_WEG
    except Exception:
        pass
    DPI_WEG = "keiner – Windows rechnet weiter für uns um"
    return DPI_WEG


def windows_monitore() -> list:
    """Alle Bildschirme mit ihren Rechtecken – für die Zahlenzeile.

    Erst wenn man sieht, wie sie zueinander stehen, lässt sich eine
    Verschiebung erklären, statt sie zu vermuten.
    """
    if not IST_WINDOWS:
        return []
    try:
        import ctypes
        from ctypes import wintypes
        gefunden = []

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        RUECK = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p,
                                   ctypes.c_void_p, ctypes.POINTER(RECT),
                                   ctypes.c_double)

        def sammeln(_h, _dc, rect, _daten):
            r = rect.contents
            gefunden.append((r.left, r.top, r.right - r.left,
                             r.bottom - r.top))
            return 1

        ctypes.windll.user32.EnumDisplayMonitors(None, None, RUECK(sammeln), 0)
        return gefunden
    except Exception:
        return []


def windows_desktop() -> tuple:
    """Ursprung und Maße **aller** Bildschirme zusammen.

    Ein zweiter Monitor links vom ersten hat negative x-Werte – der
    Ursprung des virtuellen Desktops ist die linke obere Ecke des
    *Hauptbildschirms*, nicht die des Gesamtbilds. Wer das übersieht,
    fotografiert an einer ganz anderen Stelle ab.

    (x, y, breite, hoehe). Ohne Windows: (0, 0, 0, 0).
    """
    if not IST_WINDOWS:
        return (0, 0, 0, 0)
    try:
        import ctypes
        hole = ctypes.windll.user32.GetSystemMetrics
        # 76..79: SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN,
        #         SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
        return (hole(76), hole(77), hole(78), hole(79))
    except Exception:
        return (0, 0, 0, 0)


def schirmfoto(pfad: str) -> bool:
    """Ein Abbild des Hauptbildschirms nach `pfad` legen.

    Auf dem Mac `screencapture -D 1` – ohne `-D 1` legt es bei mehreren
    Monitoren mehrere Dateien an, und keine heisst wie erwartet. Unter
    Windows Pillow.

    **Zur Bildschirmskalierung unter Windows:** Der Scanner meldet sich
    absichtlich *nicht* als DPI-bewusst an. Dann sind Abbild und Tk-Punkte
    in derselben Rechnung, und ein gezogener Rahmen trifft genau das, was
    man gesehen hat. Der Preis ist ein etwas weicheres Bild bei 125 % oder
    150 %. Andersherum – DPI-bewusst – waere es schaerfer, aber die
    Koordinaten muessten stimmen, und das kann hier niemand nachmessen.
    Wenn die Erkennung auf einem skalierten Bildschirm schwaechelt, ist das
    die erste Stellschraube.

    Beide liefern **Bildpunkte**, nicht Fensterpunkte: Auf Retina und auf
    skalierten Windows-Bildschirmen ist das Abbild groesser als der
    Bildschirm Punkte hat. Wer damit rechnet, muss den Faktor selbst
    herausfinden – `bereich_waehlen` tut das.
    """
    try:
        if IST_WINDOWS:
            try:
                from PIL import ImageGrab
            except ImportError:
                return False
            # **Über alle Bildschirme.** Ohne `all_screens` kommt nur der
            # Hauptmonitor – die Aufnahme des gemerkten Bereichs geht aber
            # über alle. Zwei verschiedene Koordinatenräume, und der
            # Ausschnitt sitzt woanders als der gezogene Rahmen.
            bild = ImageGrab.grab(all_screens=True)
            bild.save(pfad, format="PNG")
        else:
            # **Über alle Bildschirme, wenn sich ihre Maße erfragen
            # lassen.** Mit `-D 1` käme nur der Hauptbildschirm – und wer
            # den Stream auf dem zweiten Monitor laufen hat, könnte ihn
            # gar nicht einrahmen. Ohne `-D` legt screencapture bei
            # mehreren Monitoren mehrere Dateien an, keine heißt wie
            # erwartet; deshalb der Umweg über `-R` und die Gesamtmaße.
            x, y, breite, hoehe = mac_desktop()
            zusatz = (["-R", "%d,%d,%d,%d" % (x, y, breite, hoehe)]
                      if breite > 0 else ["-D", "1"])
            subprocess.run(["screencapture", "-x", "-t", "png"] + zusatz
                           + [pfad], check=False, timeout=60,
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
        return os.path.isfile(pfad) and os.path.getsize(pfad) > 0
    except (subprocess.SubprocessError, OSError, Exception):
        return False


def rahmen_ziehen() -> bytes | None:
    """Den Rahmen von macOS ziehen lassen – dieselbe Auswahl wie bei ⌘⇧4.

    Warum nicht selbst gebaut: Die eingebaute kennt jeder, sie zeigt die
    Maße mit, lässt sich mit der Leertaste verschieben und mit Esc abbrechen.
    Und sie kostet keine Zeile Code.
    """
    if IST_WINDOWS:
        # Gibt es dort nicht – `rahmen_senden` nimmt den anderen Weg und
        # ruft das hier gar nicht erst auf. Lieber None als ein leeres Bild.
        return None
    return _screencapture(["-i"])


def bereich_aufnehmen(bereich: tuple) -> bytes | None:
    x, y, b, h = bereich
    if IST_WINDOWS:
        try:
            from PIL import ImageGrab
        except ImportError:
            return None
        try:
            # `all_screens`, damit ein Bereich auf dem zweiten Monitor nicht
            # ins Leere greift. Die Koordinaten kommen aus derselben Quelle
            # wie das Abbild, passen also zusammen.
            bild = ImageGrab.grab(bbox=(x, y, x + b, y + h), all_screens=True)
            hinaus = io.BytesIO()
            bild.save(hinaus, format="PNG")
            return hinaus.getvalue()
        except Exception:
            return None
    return _screencapture(["-R", f"{x},{y},{b},{h}"])


def _screencapture(zusatz: list) -> bytes | None:
    pfad = os.path.join(tempfile.gettempdir(),
                        f"brickfolio-livescan-{uuid.uuid4().hex}.png")
    try:
        subprocess.run(["screencapture", "-x", "-t", "png"] + zusatz + [pfad],
                       check=False, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Bei Abbruch (Esc) legt screencapture keine Datei an.
        if not os.path.isfile(pfad) or os.path.getsize(pfad) == 0:
            return None
        with open(pfad, "rb") as f:
            return f.read()
    except (subprocess.SubprocessError, OSError):
        return None
    finally:
        try:
            os.remove(pfad)
        except OSError:
            pass


# ------------------------------------------------------- Bereich merken

def auswahl_umrechnen(x1, y1, x2, y2, faktor_x, faktor_y,
                      ursprung=(0, 0), mindestens=40) -> tuple | None:
    """Aus einem Rahmen in der Vorschau ein Rechteck auf dem Bildschirm.

    Steht hier als eigene Funktion, weil genau in dieser Rechnung der
    Fehler vom 31.08.2026 saß – und weil sie in einem Tk-Ereignis
    versteckt nicht zu prüfen war.

    Drei Dinge, die sie leisten muss:

    * **Kommazahlen.** Windows skaliert mit 125 %, 150 %, 175 %. Wer
      ganzzahlig rundet, sitzt um ein Drittel daneben.
    * **Ein Ursprung.** Ein zweiter Monitor links vom ersten fängt bei
      negativen x an; der Ursprung des Desktops ist die linke obere Ecke
      des *Haupt*bildschirms.
    * **Eine Untergrenze.** Ein versehentlicher Klick ist kein Bereich.

    Gibt None zurück, wenn der Rahmen zu klein ist.
    """
    links, oben = min(x1, x2), min(y1, y2)
    breite = abs(x2 - x1) * faktor_x
    hoehe = abs(y2 - y1) * faktor_y
    if breite <= mindestens or hoehe <= mindestens:
        return None
    return (int(round(ursprung[0] + links * faktor_x)),
            int(round(ursprung[1] + oben * faktor_y)),
            int(round(breite)), int(round(hoehe)))


def bereich_waehlen(wurzel: tk.Tk) -> tuple | None:
    """Einen festen Bereich merken – für Serien aus demselben Ausschnitt.

    macOS' eigene Auswahl verrät leider nicht, *wo* gezogen wurde. Deshalb
    hier ein eigener Weg – aber **ohne durchsichtiges Fenster**: Der erste
    Versuch legte eine halbdurchsichtige Fläche über den Bildschirm, und die
    kam auf macOS schwarz und undurchsichtig heraus. Statt an der
    Durchsichtigkeit herumzuraten, wird jetzt ein **Abbild** des Bildschirms
    gezeigt: ein gewöhnliches, deckendes Fenster, in dem man den Rahmen
    zieht. Sieht genauso aus, kann aber nicht schiefgehen.
    """
    roh_pfad = os.path.join(tempfile.gettempdir(),
                            f"brickfolio-bereich-{uuid.uuid4().hex}.png")
    klein_pfad = ""
    try:
        if not schirmfoto(roh_pfad):
            return None

        fenster = tk.Toplevel(wurzel)
        fenster.title("Bereich markieren")
        fenster.attributes("-topmost", True)
        fenster.config(cursor="crosshair")

        breite_pkt = wurzel.winfo_screenwidth()
        hoehe_pkt = wurzel.winfo_screenheight()

        if IST_WINDOWS:
            # **Hier muss mit Kommazahlen gerechnet werden.** Der Mac-Weg
            # unten teilt ganzzahlig – auf Retina ist das Verhältnis 1 oder
            # 2, da geht das auf. Windows skaliert mit 125 %, 150 %, 175 %;
            # gerundet käme 1 oder 2 heraus, und der Ausschnitt säße um ein
            # Drittel daneben. Genau so ist es am 31.08.2026 aufgetreten.
            #
            # Und gerechnet wird gegen den **ganzen** Desktop, nicht gegen
            # den Hauptbildschirm: Bei zwei Monitoren ist `winfo_screenwidth`
            # nur der erste, das Abbild aber zeigt beide.
            Bild = _pillow()
            u_x, u_y, d_breite, d_hoehe = windows_desktop()
            if Bild is None or d_breite <= 0:
                return None
            with Bild.open(roh_pfad) as roh_bild:
                b_breite, b_hoehe = roh_bild.size
                skala = min(1.0, (breite_pkt - 80) / float(b_breite),
                            (hoehe_pkt - 140) / float(b_hoehe))
                v_breite = max(1, int(b_breite * skala))
                v_hoehe = max(1, int(b_hoehe * skala))
                klein_pfad = roh_pfad + "-vorschau.png"
                roh_bild.resize((v_breite, v_hoehe),
                                Bild.LANCZOS).save(klein_pfad, "PNG")
            klein = tk.PhotoImage(file=klein_pfad)
            # Von Vorschaupunkt zu Bildschirmpunkt – als Kommazahl, und je
            # Richtung getrennt, falls die Vorschau nicht exakt proportional
            # gerundet wurde.
            ursprung = (u_x, u_y)
        else:
            # Tk kann PNG von sich aus – dafür braucht es keine Bibliothek.
            bild = tk.PhotoImage(file=roh_pfad)
            b_breite, b_hoehe = bild.width(), bild.height()
            u_x, u_y, d_breite, d_hoehe = mac_desktop()
            if d_breite <= 0:
                # Der Finder gab nichts her – dann zeigt `schirmfoto` den
                # Hauptbildschirm, und der ist auch die Rechengrundlage.
                u_x, u_y = 0, 0
                d_breite, d_hoehe = breite_pkt, hoehe_pkt
            # Tk verkleinert nur ganzzahlig. Das macht nichts: Wie viel es
            # am Ende wirklich war, steht in der Größe der Vorschau, und
            # daraus wird unten der Faktor als Kommazahl gebildet.
            n = 1
            while b_breite // n > breite_pkt - 80 \
                    or b_hoehe // n > hoehe_pkt - 140:
                n += 1
            klein = bild.subsample(n)
            ursprung = (u_x, u_y)

        # **Aus der wirklichen Größe der Vorschau**, nicht aus dem, was
        # beim Verkleinern beabsichtigt war. Beides kann um einen Punkt
        # auseinanderliegen, und ein gerundeter Faktor verschiebt den
        # Ausschnitt über die ganze Breite hinweg.
        faktor_x = d_breite / float(klein.width())
        faktor_y = d_hoehe / float(klein.height())

        flaeche = tk.Canvas(fenster, width=klein.width(),
                            height=klein.height(), highlightthickness=0)
        flaeche.pack()
        # Ausdrücklich in die linke obere Ecke des Hauptbildschirms. Sonst
        # entscheidet das Fenstersystem, wo das Fenster landet – und wenn
        # es dabei über den Rand hinausragt, sieht man einen Ausschnitt der
        # Vorschau und zieht den Rahmen an der falschen Stelle.
        fenster.geometry("+0+0")
        flaeche.create_image(0, 0, anchor="nw", image=klein)
        flaeche.create_text(klein.width() // 2, 26, fill="#39b54a",
                            font=("Helvetica", 15, "bold"),
                            text="Rahmen um das Videobild ziehen  ·  "
                                 "Esc bricht ab")
        if IST_WINDOWS:
            # **Die Zahlen sichtbar machen.** Bei mehreren Bildschirmen mit
            # unterschiedlicher Skalierung kann diese Rechnung auf einem
            # fremden Rechner danebenliegen, und von hier aus lässt sich das
            # nicht nachmessen. Wer sie sieht, kann sie melden – das ist
            # ehrlicher, als den Anwender raten zu lassen.
            schirme = " ".join("%d×%d@%d,%d" % (b, h, x, y)
                               for x, y, b, h in windows_monitore()) or "?"
            flaeche.create_text(
                klein.width() // 2, 50, fill="#8fd8a0",
                font=("Helvetica", 11),
                text="Abbild %d×%d  ·  Desktop %d×%d ab (%d,%d)  ·  "
                     "Vorschau %d×%d  ·  Faktor %.3f / %.3f"
                     % (b_breite, b_hoehe, d_breite, d_hoehe, u_x, u_y,
                        klein.width(), klein.height(), faktor_x, faktor_y))
            flaeche.create_text(
                klein.width() // 2, 70, fill="#8fd8a0",
                font=("Helvetica", 11),
                text="Bildschirme: %s  ·  DPI: %s" % (schirme, DPI_WEG))
        stand = {"x": 0, "y": 0, "rahmen": None, "fertig": None}

        def runter(e):
            stand["x"], stand["y"] = e.x, e.y
            if stand["rahmen"]:
                flaeche.delete(stand["rahmen"])
            stand["rahmen"] = flaeche.create_rectangle(
                e.x, e.y, e.x, e.y, outline="#39b54a", width=3)

        def ziehen(e):
            if stand["rahmen"]:
                flaeche.coords(stand["rahmen"], stand["x"], stand["y"],
                               e.x, e.y)

        def hoch(e):
            stand["fertig"] = auswahl_umrechnen(
                stand["x"], stand["y"], e.x, e.y,
                faktor_x, faktor_y, ursprung)
            fenster.destroy()

        flaeche.bind("<ButtonPress-1>", runter)
        flaeche.bind("<B1-Motion>", ziehen)
        flaeche.bind("<ButtonRelease-1>", hoch)
        fenster.bind("<Escape>", lambda _: fenster.destroy())
        fenster.focus_force()
        wurzel.wait_window(fenster)
        return stand["fertig"]
    finally:
        for weg in (roh_pfad, klein_pfad):
            try:
                if weg:
                    os.remove(weg)
            except OSError:
                pass


# ------------------------------------------------------------ Oberfläche

class LiveScanner:
    def __init__(self, wurzel: tk.Tk):
        self.wurzel = wurzel
        self.daten = lesen()
        self.instanz = Instanz(self.daten.get("adresse", ""),
                               self.daten.get("token", ""),
                               self.daten.get("cf_kennung", ""),
                               self.daten.get("cf_geheim", ""))
        self.bereich = tuple(self.daten["bereich"]) if self.daten.get(
            "bereich") else None
        self.treffer = None
        # Der Vorschlag, dem die Karte gerade gehört. Nicht dasselbe wie
        # `treffer`: Preis und Katalogbild kommen aus Hintergrundfäden und
        # treffen manchmal erst ein, wenn längst der nächste Scan läuft.
        # Alles, was von dort zurückkommt, wird gegen diesen hier geprüft.
        self.gewaehlt = None
        # Die Verlaufszeile, auf der wir gerade stehen – nach einem Scan die
        # oberste, nach einem Rücksprung eine ältere.
        self.eintrag = None
        self.letztes_bild = None      # der gerade gezeigte Ausschnitt
        # Alle Aufnahmen zum aktuellen Stand – auf einer Drehscheibe sind das
        # mehrere Ansichten derselben Figur. `bilder_an` sind die Nummern
        # derer, die beim Buchen als Foto an den Artikel gehen.
        self.bilder = []
        self.bilder_an = set()
        self.listen = []
        self.post = queue.Queue()
        self.beschaeftigt = False
        # Der Wächter läuft in einem eigenen Faden; `wacht` ist sein
        # Ausschalter. Bewusst ein schlichtes Attribut und keine Tk-Variable –
        # die dürfte er von dort aus nicht lesen.
        self.wacht = False
        self.stufe = self.daten.get("empfindlichkeit", "mittel")
        self.auto_anfragen = []       # Zeitpunkte der letzten Minute
        # Erfolglose automatische Anfragen am Stück. Geschrieben wird das im
        # Erkennungsfaden, gelesen im Wächterfaden – beides sind einzelne
        # Zuweisungen auf eine Zahl, und zwei Erkennungen gleichzeitig
        # verhindert `beschaeftigt`.
        self.auto_leer = 0
        self.auto_lauf = False        # war der letzte Auslöser der Wächter?
        self._blinkt = None           # läuft gerade ein Wunsch-Blinken?
        # Welche Aufnahme schon an welchem Artikel hängt – damit dasselbe
        # Bild nicht dreimal in derselben Galerie landet, wenn eine Figur auf
        # mehreren Wegen gebucht wird. Nur die Prüfsummen, nicht die Bilder.
        self.fotos = set()

        # **Vor `_bauen`**, denn die Farben werden beim Anlegen der
        # Bedienelemente gelesen.
        farben_setzen(wurzel)
        wurzel.title("Brickfolio Live-Scanner")
        # Der Haken »Immer vorn« entscheidet; voreingestellt bleibt es an.
        wurzel.attributes("-topmost",
                          bool(self.daten.get("immer_vorn", True)))
        self._bauen()
        self._hoehe_festlegen()
        wurzel.after(120, self._post_abarbeiten)
        # Im Hintergrund und nur einmal je Start. Wer nicht gefragt werden
        # will, setzt "updates_pruefen": false in die Einstellungsdatei –
        # dafür gibt es keinen Haken, weil die Zeile ohnehin nur erscheint,
        # wenn es wirklich etwas Neues gibt.
        if self.daten.get("updates_pruefen", True):
            threading.Thread(target=self._update_pruefen,
                             daemon=True).start()
        if not self.instanz.token:
            wurzel.after(300, self.zugang_zeigen)

    def _hoehe_festlegen(self):
        """Fenstergröße aus dem wirklichen Bedarf der Karte bestimmen.

        Vorher standen hier feste Zahlen, und die stimmten nur so lange, bis
        eine Reihe dazukam: Nach drei Erweiterungen war die Mindesthöhe zu
        klein geworden, das Fenster ließ sich auf eine Größe ziehen, in der
        **das Preisfeld unten heraushing** – und wer es nicht sieht, hält es
        für kaputt. Also fragt das Fenster jetzt selbst, wie viel es braucht.

        Der Verlauf ist das Einzige, was mitwächst, und damit auch das
        Einzige, was nachgeben darf – drei seiner sieben Zeilen müssen ihm
        aber bleiben, sonst ist er als Sprungbrett nutzlos.
        """
        self.wurzel.update_idletasks()
        verlauf = self.verlauf.winfo_reqheight()
        # Die Reihe mit den Ansichten steht noch nicht da – sie erscheint erst,
        # wenn eine Figur aus mehreren Winkeln kam. Ihren Platz trotzdem schon
        # einplanen: Sonst schöbe sie später etwas anderes aus dem Fenster,
        # und zwar genau in dem Augenblick, in dem man am meisten zu tun hat.
        # **Der innere Rahmen**, nicht das Fenster: Eine Leinwand gibt die
        # Größe ihres Inhalts nicht nach oben weiter. Über das Fenster
        # gefragt kämen hier 265 px heraus – die Wunschgröße der leeren
        # Leinwand – und das Fenster startete winzig.
        noetig = (self.innen.winfo_reqheight() + MINI_KANTE + 40
                  - verlauf * 4 // 7)
        schirm = self.wurzel.winfo_screenheight()
        # Die Mindesthöhe war der volle Bedarf der Karte, gedeckelt auf
        # Bildschirmhöhe minus 80. Gedacht war sie gegen ein Fenster, in dem
        # unten etwas heraushängt – bewirkt hat sie auf kleinen Bildschirmen
        # das Gegenteil: Es ließ sich nicht kleiner ziehen als der Schirm
        # hoch ist, der untere Teil blieb unerreichbar, und scrollen ging
        # nicht. Seit der Inhalt scrollt, ist die Sperre die Antwort auf ein
        # Problem, das es nicht mehr gibt. 300 px lassen den Auslöser und die
        # ersten Reihen stehen; alles Weitere holt man mit dem Rad.
        self.wurzel.minsize(540, 300)
        self.wurzel.geometry("560x{}".format(min(noetig + verlauf * 4 // 7,
                                                 schirm - 120)))

    # ------------------------------------------------- Scrollbare Fläche
    def _scrollflaeche(self):
        """Den Inhalt in eine Fläche legen, die scrollt statt abzuschneiden.

        Vorher war die Karte ein einziger Stapel im Fenster. Passte sie
        nicht, fielen die untersten Reihen weg – Verlauf und „Zugang …"
        waren auf einem kleinen Bildschirm schlicht nicht erreichbar, und
        die Mindesthöhe (Bildschirm minus 80) verhinderte auch noch, das
        Fenster kleiner zu ziehen.

        Auf einem großen Bildschirm soll sich nichts ändern: Ist die Fläche
        höher als der Inhalt, wird der innere Rahmen auf die volle Höhe
        gezogen. Nur dann greift `expand=True` beim Verlauf, und nur so
        wächst er wie bisher mit.
        """
        aussen = ttk.Frame(self.wurzel)
        aussen.pack(fill="both", expand=True)
        self.leinwand = tk.Canvas(aussen, highlightthickness=0, takefocus=0,
                                  background=self.wurzel.cget("background"))
        self.leinwand.pack(side="left", fill="both", expand=True)
        self.balken = ttk.Scrollbar(aussen, orient="vertical",
                                    command=self.leinwand.yview)
        self.leinwand.configure(yscrollcommand=self.balken.set)

        self.innen = ttk.Frame(self.leinwand, padding=10)
        self._innen_id = self.leinwand.create_window(
            (0, 0), window=self.innen, anchor="nw")
        self.innen.bind("<Configure>", self._scroll_nachfuehren)
        self.leinwand.bind("<Configure>", self._scroll_nachfuehren)
        self.wurzel.bind_all("<MouseWheel>", self._rad)
        return self.innen

    def _scroll_nachfuehren(self, _ereignis=None):
        """Breite, Höhe und Scrollbereich des Inhalts nachziehen.

        **Nicht** über `bbox("all")`: Die Leinwand kennt die Ausmaße ihres
        Fensterelements erst, nachdem sie es gezeichnet hat. Beim ersten
        Durchlauf kam dort `None` zurück, der Scrollbereich blieb leer – und
        damit ließ sich nichts schieben, obwohl die Bildlaufleiste dastand.
        Das sah aus wie ein hängendes Fenster.

        Die Höhe ist das Maximum aus Bedarf und Fläche: Ist Platz übrig,
        wird der innere Rahmen auf die volle Höhe gezogen, sonst griffe
        `expand=True` beim Verlauf nicht und er wüchse nicht mehr mit.
        """
        breite = self.leinwand.winfo_width()
        hoch = max(self.innen.winfo_reqheight(), self.leinwand.winfo_height())
        if (breite, hoch) == getattr(self, "_scroll_stand", None):
            return                     # sonst ruft sich das gegenseitig auf
        self._scroll_stand = (breite, hoch)
        self.leinwand.itemconfigure(self._innen_id, width=breite, height=hoch)
        self.leinwand.configure(scrollregion=(0, 0, breite, hoch))
        self._balken_pruefen()

    def _balken_pruefen(self):
        """Die Leiste nur zeigen, wenn es etwas zu schieben gibt.

        Mit Spielraum von 12 px: Ohne den flackert sie am Rand des
        Umschlagpunkts. Die Leiste nimmt Breite weg, der Text bricht anders
        um, der Inhalt wird höher – und braucht die Leiste wieder.
        """
        noetig = self.innen.winfo_reqheight()
        hat = self.leinwand.winfo_height()
        sichtbar = bool(self.balken.winfo_ismapped())
        if not sichtbar and noetig > hat:
            self.balken.pack(side="right", fill="y")
        elif sichtbar and noetig <= hat - 12:
            self.balken.pack_forget()

    def _rad(self, ereignis):
        """Mausrad – aber nur, wo es hingehört.

        `bind_all` bekommt jedes Rad-Ereignis, auch das aus den beiden
        Listen und aus dem Fenster mit dem großen Bild. Über einer Liste
        soll die Liste scrollen, nicht die Karte darunter; im Bildfenster
        geht die Karte gar nichts an.
        """
        if ereignis.widget.winfo_toplevel() is not self.wurzel:
            return
        ziel = ereignis.widget
        listen = [w for w in (getattr(self, "liste", None),
                              getattr(self, "verlauf", None)) if w]
        while ziel is not None:
            if ziel in listen:
                return
            ziel = getattr(ziel, "master", None)
        if self.innen.winfo_reqheight() <= self.leinwand.winfo_height():
            return                       # nichts zu schieben
        schritt = ereignis.delta
        # macOS zählt in Einzelschritten, Windows und X11 in 120ern.
        if abs(schritt) >= 120:
            schritt //= 120
        self.leinwand.yview_scroll(-schritt, "units")

    # ------------------------------------------------------------ Aufbau
    def _bauen(self):
        r = self._scrollflaeche()
        # Die Textzeilen brachen fest bei 350 px um – aus einer Zeit, in der
        # das Fenster schmal war. Wer es breitzieht, bekam den Setnamen
        # trotzdem über drei Zeilen, während rechts eine Handbreit leer
        # blieb. Jetzt richtet sich der Umbruch nach der wirklichen Breite.
        self._breite_labels = []
        r.bind("<Configure>", self._umbruch_anpassen)

        # Der Auslöser ist die Hauptsache des Werkzeugs – gelb und breit,
        # wie „Scannen" in der App.
        self.ausloeser = Knopf(r, text="▣  Rahmen ziehen und senden",
                               command=self.rahmen_senden, art="gelb",
                               hoehe=40, groesse=13)
        self.ausloeser.pack(fill="x")

        zweite = ttk.Frame(r)
        zweite.pack(fill="x", pady=(8, 0))
        Knopf(zweite, text="🎯 Bereich merken",
              command=self.bereich_merken).pack(side="left")
        self.k_bereich = Knopf(zweite, text="📷 Aus Bereich",
                               command=self.bereich_senden,
                               state="normal" if self.bereich else "disabled")
        self.k_bereich.pack(side="left", padx=(6, 0))

        # Von selbst auslösen, wenn im gemerkten Bereich eine neue Figur
        # hochgehalten wird. Das widerspricht dem „ein Auslöser = eine
        # Anfrage" **nicht**: Gemessen wird hier auf dem Rechner, und
        # geschickt wird erst, wenn sich etwas geändert hat *und* das Bild
        # danach still steht. Das sind weniger Anfragen, als ein Mensch
        # auslöst, der im Zweifel zweimal drückt.
        autoreihe = ttk.Frame(r)
        autoreihe.pack(fill="x", pady=(6, 0))
        self.automatik = tk.BooleanVar(value=False)
        self.k_automatik = ttk.Checkbutton(
            autoreihe, variable=self.automatik, command=self._automatik_schalten,
            text="⏱ Von selbst auslösen",
            state="normal" if self.bereich else "disabled")
        self.k_automatik.pack(side="left")
        # Als Pille sieht man alle drei Stufen, statt sie hinter einem
        # Auswahlfeld zu suchen. **Sie gehört zum Haken** und steht darum
        # direkt dahinter, nicht rechts am Rand – dort wirkte sie wie eine
        # eigene Einstellung (Rückmeldung vom 25.09.2026). Solange der Haken
        # aus ist, ist sie blass: gilt gerade nicht.
        self.empfindlich_var = tk.StringVar(
            value=self.daten.get("empfindlichkeit", "mittel"))
        self.empfindlich_titel = ttk.Label(
            autoreihe, text="· Empfindlichkeit", foreground=FARBEN["leise"])
        self.empfindlich_titel.pack(side="left", padx=(4, 6))
        self.empfindlich = Pille(autoreihe, [(w, w) for w in EMPFINDLICHKEIT],
                                 self.empfindlich_var, groesse=11, hoehe=26,
                                 command=self._empfindlich_merken)
        self.empfindlich.pack(side="left")
        self.automatik.trace_add("write", lambda *_e: self._empfindlich_faerben())
        self._empfindlich_faerben()
        # Eigene Zeile, nicht die allgemeine Statuszeile: Der Wächter meldet
        # sich jede Sekunde, und er soll dabei nicht überschreiben, was gerade
        # zum Treffer dasteht.
        # Wird erst eingeblendet, wenn der Wächter läuft – sonst nähme eine
        # leere Zeile dauerhaft Höhe weg, die unten der Verlauf braucht.
        self.autostand = ttk.Label(r, text="", foreground=FARBEN["matt"])

        # Der andere Weg: nicht hier weitermachen, sondern das Bild der App
        # geben und dort den gewohnten Ablauf nehmen.
        self.k_ablage = Knopf(r, text="📋 Bild in die Zwischenablage "
                                      "(dann ⌘V in der App)",
                              command=self.in_ablage, state="disabled")
        self.k_ablage.pack(fill="x", pady=(8, 0))

        self.stand = ttk.Label(r, text="", foreground=FARBEN["leise"])
        self.stand.pack(fill="x", pady=(8, 4))

        # Links die eigene Aufnahme, rechts das Katalogbild der gewählten
        # Figur. Nebeneinander sieht man auf einen Blick, ob der Vorschlag
        # passt – Zahlen allein sagen das nicht.
        # Die **ganze Fläche** hinter beiden Bildern wird grün, sobald die
        # Figur schon irgendwo eingetragen ist – nicht nur ein Streifen
        # außen herum. Im Stream schaut man auf das Bild, nicht auf die
        # Zeile darunter, und eine Farbfläche sieht man aus dem Augenwinkel,
        # während der Verkäufer schon weiterredet.
        #
        # Alles hier sind bewusst **klassische** Tk-Widgets: ttk nimmt keine
        # eigene Hintergrundfarbe entgegen, dort ginge es nur über ein
        # eigenes Design. Für vier Rahmen und zwei Beschriftungen lohnt das
        # nicht – und umfärben lässt sich so jedes einzeln.
        self.rahmen_aus = self.wurzel.cget("background")
        self.rahmen = tk.Frame(r, background=self.rahmen_aus)
        self.rahmen.pack(pady=(2, 0))
        bilder = tk.Frame(self.rahmen, background=self.rahmen_aus)
        bilder.pack(padx=RAHMEN_DICK, pady=RAHMEN_DICK)
        links = tk.Frame(bilder, background=self.rahmen_aus)
        links.pack(side="left")
        b_links = tk.Label(links, text="Aufnahme", foreground=FARBEN["leise"],
                           background=self.rahmen_aus)
        b_links.pack()
        self.vorschau = tk.Label(links, bd=1, relief="solid", width=17,
                                 height=9, text="—", foreground=FARBEN["still"])
        self.vorschau.pack()
        rechts = tk.Frame(bilder, background=self.rahmen_aus)
        rechts.pack(side="left", padx=(8, 0))
        b_rechts = tk.Label(rechts, text="BrickLink", foreground=FARBEN["leise"],
                            background=self.rahmen_aus)
        b_rechts.pack()
        self.referenz = tk.Label(rechts, bd=1, relief="solid", width=17,
                                 height=9, text="—", foreground=FARBEN["still"])
        self.referenz.pack()
        # Die Bildfelder selbst bleiben außen vor: Solange kein Bild da ist,
        # steht dort ein „—", und mit grünem Grund sähe das nach Ladefehler
        # aus. Sobald ein Bild kommt, deckt es die Fläche ohnehin.
        self._gruen_flaechen = [self.rahmen, bilder, links, rechts,
                                b_links, b_rechts]
        # Grau auf Grün liest sich schlecht – die beiden Beschriftungen
        # wechseln deshalb die Schriftfarbe mit.
        self._gruen_schriften = [b_links, b_rechts]
        self._vorschaubild = None          # Verweise halten, sonst weggeräumt
        self._referenzbild = None
        self._referenz_roh = None
        # Ein Klick aufs Bild zeigt es groß. Der Zeigefinger sagt vorher,
        # dass da etwas geht – ohne ihn probiert es niemand aus.
        for feld, hole, titel in (
                (self.vorschau, lambda: self.letztes_bild, "Aufnahme"),
                (self.referenz, lambda: self._referenz_roh, "BrickLink")):
            feld.config(cursor=ZEIGEHAND)
            feld.bind("<Button-1>",
                      lambda _e, h=hole, t=titel: self.gross_zeigen(h(), t))

        # Kam die Figur aus mehreren Ansichten, stehen sie hier zum Aussuchen.
        # Bei nur einer Aufnahme bleibt die Reihe weg – sie wäre dann eine
        # Auswahl ohne Wahl und nähme dem Verlauf nur Platz.
        self.ansichtsreihe = ttk.Frame(r)
        self._mini_bilder = []
        self._mini_rahmen = []

        haken = ttk.Frame(r)
        haken.pack(fill="x", pady=(6, 0))
        self.mitschicken = tk.BooleanVar(value=bool(
            self.daten.get("foto_mitschicken", True)))
        ttk.Checkbutton(
            haken, variable=self.mitschicken, command=self._foto_merken,
            text="📷 Foto mitspeichern").pack(side="left")
        self.ton = tk.BooleanVar(value=bool(self.daten.get("ton", True)))
        ttk.Checkbutton(
            haken, variable=self.ton, command=self._ton_merken,
            text="🔔 Ton bei Wunsch").pack(side="left", padx=(10, 0))
        # Die Erkennung sucht **ein** Objekt im Bild und nimmt das
        # deutlichste. Steht die Figur auf einem Ständer, ist das der Ständer.
        # Wer einen Figuren-Stream sieht, kann sich das ersparen.
        self.nur_figuren = tk.BooleanVar(
            value=bool(self.daten.get("nur_figuren", False)))
        ttk.Checkbutton(
            haken, variable=self.nur_figuren, command=self._figuren_merken,
            text="🧍 Nur Figuren").pack(side="left", padx=(10, 0))
        # Das Fenster liegt über allem, damit man den Stream weiter sieht.
        # Der Preis: Fenster **anderer** Programme gehen dahinter auf, und
        # man sucht sie. Wer gerade nicht scannt, nimmt den Haken weg.
        # Voreinstellung bleibt „an" – so war es immer.
        # Der Haken selbst steht unten neben „Zugang …": Er gilt dem Fenster,
        # nicht dem Scan – und vier Haken passten nicht in die Mindestbreite,
        # „Immer vorn" war rechts abgeschnitten.
        self.immer_vorn = tk.BooleanVar(
            value=bool(self.daten.get("immer_vorn", True)))

        ttk.Separator(r).pack(fill="x", pady=4)

        # Die Erkennung liefert **mehrere** Kandidaten mit Trefferquote –
        # bei ähnlichen Figuren liegt die richtige oft auf Platz zwei. Vorher
        # nahm dieses Werkzeug stumm den ersten; jetzt stehen sie alle da.
        self.kandidaten = []
        self.liste = tk.Listbox(r, height=4, activestyle="dotbox",
                                exportselection=False)
        self.liste.pack(fill="x")
        self.liste.bind("<<ListboxSelect>>", self._auswahl_geaendert)

        # Nummer von Hand nachtragen. Stand früher **nur** da, wenn die
        # Erkennung nichts hergab – aber der häufigere Fall ist der andere:
        # Es werden Vorschläge geliefert, und keiner davon stimmt. In vielen
        # Streams wird die Nummer angesagt oder eingeblendet, und dann ist
        # Tippen der kürzeste Weg zur richtigen Figur. Deshalb ist das Feld
        # jetzt immer da; die paar Pixel sind es wert.
        self.nummerreihe = ttk.Frame(r)
        self.nummerreihe.pack(fill="x", pady=(6, 0))
        ttk.Label(self.nummerreihe, text="✎ Nr. nachtragen:").pack(side="left")
        # 11 Zeichen reichen für jede Katalognummer („sw0417a", „75192-1")
        # und halten die Reihe innerhalb der Mindestbreite.
        self.nummerfeld = ttk.Entry(self.nummerreihe, width=11)
        self.nummerfeld.pack(side="left", padx=(6, 0))
        self.nummerfeld.bind("<Return>", lambda _: self.nummer_suchen())
        Knopf(self.nummerreihe, text="Suchen", hoehe=28,
              command=self.nummer_suchen).pack(side="left", padx=(6, 0))
        # Kurz halten: Die Reihe muss auch in die Mindestbreite des Fensters
        # passen, sonst schiebt sie den „Suchen"-Knopf hinaus.
        ttk.Label(self.nummerreihe, text="z. B. sw0402, 75192, 3001",
                  foreground=FARBEN["matt"]).pack(side="left", padx=(8, 0))

        self.name = ttk.Label(r, text="—", font=("Helvetica", 14, "bold"))
        self.name.pack(fill="x", pady=(6, 0))
        self.unter = ttk.Label(r, text="", foreground=FARBEN["kraeftig"])
        self.unter.pack(fill="x", pady=(2, 0))
        # Die Preise wie im Steckbrief der App – gefüllt, sobald die
        # Instanz sie liefert (`_preise_zeigen`). Leer nimmt er keinen Platz.
        self.preisblock = ttk.Frame(r)
        self.preisblock.pack(fill="x", pady=(4, 0))
        self.preisblock.columnconfigure(1, weight=1)
        self.besitz = ttk.Label(r, text="", font=("Helvetica", 12, "bold"))
        self.besitz.pack(fill="x", pady=(4, 0))
        # Zweite Zeile, weil sie eine andere Frage beantwortet: Die erste
        # sagt „habe ich es", diese „habe ich es mir vorgemerkt". Beides in
        # einer Zeile bräuchte zwei Farben.
        self.woanders = ttk.Label(r, text="", foreground=FARBEN["verweis"])
        self.woanders.pack(fill="x", pady=(1, 0))
        # Dritte Zeile: der Katalog, nicht dein Bestand. Blasser gesetzt,
        # weil sie beim Mitbieten seltener zählt als die beiden darüber.
        self.setliste = ttk.Label(r, text="", foreground=FARBEN["leise"])
        self.setliste.pack(fill="x", pady=(1, 0))

        self._breite_labels = [self.stand, self.name, self.unter,
                               self.besitz, self.woanders, self.setliste]

        # Zustand und Einkaufspreis gehören zum Eintrag, nicht zur Figur –
        # deshalb hier und nicht im Treffer. Sie gelten für „Sammlung" und
        # „Liste"; die Wunschliste kennt beides nicht und lässt es liegen.
        erfassung = ttk.Frame(r)
        erfassung.pack(fill="x", pady=(10, 0))
        self.zustand = tk.StringVar(value=self.daten.get("zustand", "used"))
        Pille(erfassung, (("used", "Gebraucht"), ("new", "Neu")),
              self.zustand, hoehe=28).pack(side="left")
        # An der Variablen, nicht am Knopf: So wird auch gemerkt, was von
        # anderer Stelle gesetzt wird, und es gibt nur einen Weg.
        self.zustand.trace_add("write", self._zustand_merken)
        ttk.Label(erfassung, text="Einkauf:").pack(side="left", padx=(14, 0))
        self.preisfeld = ttk.Entry(erfassung, width=7)
        self.preisfeld.pack(side="left", padx=(4, 0))
        ttk.Label(erfassung, text="€").pack(side="left", padx=(2, 0))

        # **Die Einkaufsliste ist die Hauptsache.** Im Stream füllt man vor
        # allem Listen – gekauft ist, was der Verkäufer zuschlägt, in die
        # Sammlung kommt es erst, wenn es da ist. Darum steht die Wahl der
        # Liste direkt über dem breiten Knopf, und der Knopf sagt, wohin es
        # geht. Die Sammlung ist die Nebensache daneben.
        listenreihe = ttk.Frame(r)
        listenreihe.pack(fill="x", pady=(10, 0))
        # Wer bei jemand Neuem kauft, soll die Liste hier anlegen können
        # statt mitten im Stream in die App zu wechseln.
        Knopf(listenreihe, text="＋ Liste",
              command=self.liste_anlegen).pack(side="right")
        # Wer in der App eine neue Einkaufsliste anlegt, soll sie hier
        # bekommen, ohne das Werkzeug neu zu starten.
        Knopf(listenreihe, text="↻", art="zeichen",
              command=self.listen_laden).pack(side="right", padx=(6, 6))
        self.listenwahl = ttk.Combobox(listenreihe, state="readonly",
                                       width=20, values=[])
        self.listenwahl.pack(side="left", fill="x", expand=True)
        self.listenwahl.bind("<<ComboboxSelected>>",
                             lambda _e: self._listenknopf_beschriften())

        reihe = ttk.Frame(r)
        reihe.pack(fill="x", pady=(8, 0))
        self.k_sammlung = Knopf(reihe, text="＋ Sammlung",
                                command=self.zur_sammlung, state="disabled",
                                hoehe=38)
        self.k_sammlung.pack(side="right")
        self.k_merken = Knopf(reihe, text="☆", art="zeichen",
                              command=self.merken, state="disabled",
                              hoehe=38, groesse=15)
        self.k_merken.pack(side="right", padx=(8, 8))
        self.k_liste = Knopf(reihe, text="🛒 Auf die Liste", art="gruen",
                             command=self.auf_liste, state="disabled",
                             hoehe=38, groesse=13)
        self.k_liste.pack(side="left", fill="x", expand=True)

        ttk.Separator(r).pack(fill="x", pady=8)
        # Der Verlauf ist nicht nur Protokoll: Ein Klick holt den ganzen
        # Stand von damals zurück – Vorschläge, gewählte Zeile, Aufnahme.
        # Ohne `exportselection=False` nähme diese Auswahl der Trefferliste
        # darüber ihre eigene weg; zwei Listen streiten sich sonst um dieselbe
        # Markierung, und oben stünde plötzlich keine Zeile mehr hervor.
        self.verlauf_daten = []
        self.verlauf = tk.Listbox(r, height=7, activestyle="none",
                                  exportselection=False)
        self.verlauf.pack(fill="both", expand=True)
        self.verlauf.bind("<<ListboxSelect>>", self._verlauf_geklickt)
        self._verlauf_laden()

        fuss = ttk.Frame(r)
        fuss.pack(fill="x", pady=(8, 0))
        Knopf(fuss, text="Zugang …", command=self.zugang_zeigen
              ).pack(side="left")
        ttk.Checkbutton(
            fuss, variable=self.immer_vorn, command=self._vorn_merken,
            text="📌 Immer vorn").pack(side="left", padx=(12, 0))
        ttk.Label(fuss, text="⏎ löst auch aus", foreground=FARBEN["matt"]
                  ).pack(side="right")
        # **Steht nur da, wenn es etwas zu sagen gibt.** Ohne neuere
        # Fassung bleibt die Zeile leer und nimmt keinen Platz weg – das
        # gewohnte Bild ändert sich nicht.
        self.update_hinweis = ttk.Label(fuss, text="",
                                        foreground=FARBEN["verweis"],
                                        cursor=ZEIGEHAND)
        self.wurzel.bind("<Return>", lambda _: self.rahmen_senden())

    def _update_pruefen(self):
        """Läuft im Hintergrund und meldet nur, wenn es etwas Neues gibt."""
        gefunden = neuere_fassung(VERSION)
        if gefunden:
            self.post.put(("update", gefunden))

    def _update_zeigen(self, fassung: str, seite: str, paket: str = ""):
        self.update_hinweis.config(
            text="↑ Fassung %s ist da – hier laden" % fassung)
        self.update_hinweis.pack(side="right", padx=(0, 14))
        self.update_hinweis.bind(
            "<Button-1>",
            lambda _e: self.update_fenster(fassung, seite, paket))

    def update_fenster(self, fassung: str, seite: str, paket: str):
        """Der Scanner erneuert sich selbst – ein Knopf, sonst nichts.

        **Warum nicht einfach die Seite aufmachen?** Weil der Browser jedem
        Download das Quarantäne-Merkmal anhängt und macOS die neue Fassung
        dann nicht startet: »Apple konnte nicht überprüfen …«, ohne Knopf
        zum Freigeben. Holt das Programm die Datei selbst, entsteht das
        Merkmal gar nicht erst. Der Weg über die Seite bleibt trotzdem
        stehen – für den Fall, dass hier etwas klemmt.
        """
        ziel = eigener_ort()
        f = tk.Toplevel(self.wurzel)
        f.title("Aktualisierung")
        f.attributes("-topmost", True)
        r = ttk.Frame(f, padding=14)
        r.pack(fill="both", expand=True)
        ttk.Label(r, text="Fassung %s ist da." % fassung,
                  font=("Helvetica", 14, "bold")).pack(anchor="w")
        ttk.Label(r, text="Du hast %s." % VERSION,
                  foreground=FARBEN["leise"]).pack(anchor="w", pady=(0, 10))

        stand = ttk.Label(r, text="", wraplength=330,
                          foreground=FARBEN["kraeftig"])
        knoepfe = ttk.Frame(r)
        knoepfe.pack(fill="x")

        # Was im Faden passiert, kommt hierüber zurück. Tk vom fremden Faden
        # aus anzufassen geht schief – der Rest des Programms macht es aus
        # demselben Grund über `self.post`.
        briefkasten = queue.Queue()

        def sagen(text):
            briefkasten.put(("stand", text))

        def arbeiten():
            ordner = tempfile.mkdtemp(prefix="livescan-update-")
            try:
                archiv = os.path.join(ordner, paket_name())
                sagen("Lade …")

                def fortschritt(geholt, ganz):
                    if ganz:
                        sagen("Lade … %d %%" % (100 * geholt // ganz))

                paket_laden(paket, archiv, fortschritt)
                sagen("Packe aus …")
                neu = paket_auspacken(archiv, os.path.join(ordner, "aus"))
                sagen("Prüfe …")
                klage = paket_pruefen(neu, ziel)
                if klage:
                    briefkasten.put(("aus", klage))
                    return
                tausch_starten(ziel, neu, ordner)
                briefkasten.put(("fertig", None))
            except Exception as e:
                briefkasten.put(("aus", _meldung(e)))

        def loslegen():
            for kind in knoepfe.winfo_children():
                kind.config(state="disabled")
            stand.pack(anchor="w", pady=(10, 0))
            threading.Thread(target=arbeiten, daemon=True).start()
            nachsehen()

        def nachsehen():
            try:
                while True:
                    art, wert = briefkasten.get_nowait()
                    if art == "stand":
                        stand.config(text=wert, foreground=FARBEN["kraeftig"])
                    elif art == "aus":
                        stand.config(text=wert + " Über die Seite geht es "
                                     "von Hand.", foreground=FARBEN["warnung"])
                        for kind in knoepfe.winfo_children():
                            kind.config(state="normal")
                        return
                    else:
                        stand.config(text="Fertig – der Scanner startet neu.")
                        # Erst zeigen, dann gehen: Der Helfer wartet ohnehin
                        # auf unser Ende, eine halbe Sekunde stört ihn nicht.
                        self.wurzel.after(600, self.wurzel.destroy)
                        return
            except queue.Empty:
                pass
            f.after(120, nachsehen)

        if ziel and paket and os.access(os.path.dirname(ziel), os.W_OK):
            Knopf(knoepfe, text="Jetzt aktualisieren", art="gelb",
                  command=loslegen).pack(side="left")
        else:
            if not ziel:
                warum = ("Aus dem Quelltext gestartet – hier hilft git, "
                         "nicht der Knopf.")
            elif not paket:
                warum = "Am Release hängt kein Paket für dieses System."
            else:
                warum = "Hier darf ich nichts ersetzen – fehlende Rechte."
            ttk.Label(r, text=warum, foreground=FARBEN["leise"],
                      wraplength=330).pack(anchor="w", pady=(0, 8))
        Knopf(knoepfe, text="Seite öffnen",
              command=lambda: webbrowser.open(seite)).pack(
                  side="left", padx=(8, 0))
        Knopf(knoepfe, text="Später", command=f.destroy).pack(
            side="right")

    # --------------------------------------------------------- Meldungen
    def melden(self, text: str, in_verlauf: bool = False, daten=None):
        """`daten` ist der Stand, zu dem diese Zeile zurückführt – die
        Vorschläge, die gewählte Zeile und die Aufnahme. Zeilen ohne so einen
        Datensatz (Buchungen, Fehler, angelegte Listen) führen nirgendwohin.
        """
        self.stand.config(text=text)
        if not in_verlauf:
            return
        # Die Markierung klebt am Eintrag, nicht an der Zeilennummer: Oben
        # kommt etwas dazu, also rutscht alles darunter um eins.
        vorher = self.verlauf.curselection()
        self.verlauf.insert(0, time.strftime("%H:%M  ") + text)
        self.verlauf_daten.insert(0, daten)
        if daten is None:
            # Blass gesetzt heißt: von hier führt kein Weg zurück. Das sagt
            # es, ohne an jede zweite Zeile ein Zeichen zu hängen.
            self.verlauf.itemconfig(0, foreground=FARBEN["matt"])
        if vorher:
            self.verlauf.selection_clear(0, "end")
            self.verlauf.selection_set(vorher[0] + 1)
        # Ältere Aufnahmen loslassen – die Zeile bleibt anklickbar, sie zeigt
        # dann nur die Karte ohne die Bilder von damals.
        for alt in self.verlauf_daten[VERLAUF_BILDER:]:
            if alt is not None and alt.get("bilder"):
                alt["bilder"] = []
                alt["bilder_an"] = set()
        if self.verlauf.size() > VERLAUF_ZEILEN:
            self.verlauf.delete(VERLAUF_ZEILEN, "end")
            del self.verlauf_daten[VERLAUF_ZEILEN:]
        self._verlauf_sichern()

    # ------------------------------------------------------ Verlauf halten
    def _verlauf_sichern(self):
        """Die obersten Zeilen wegschreiben – ohne die Aufnahmen.

        Die Vorschläge selbst sind ein paar hundert Byte und kommen mit: Damit
        führt ein Rücksprung auch nach dem Neustart noch zur richtigen Figur,
        samt gewählter Variante. Nur das Bild fehlt dann, und dafür steht
        „Aufnahme nicht mehr da" – ein Bildschirmausschnitt hat auf der Platte
        nichts verloren.
        """
        zeilen = []
        for i in range(min(self.verlauf.size(), VERLAUF_MERKEN)):
            daten = self.verlauf_daten[i] \
                if i < len(self.verlauf_daten) else None
            if daten is not None:
                # Die Aufnahmen bleiben draußen – ein Bildschirmausschnitt
                # hat auf der Platte nichts verloren. Mit ihnen fällt auch
                # die Auswahl weg, die sich ohne Bilder auf nichts bezöge.
                daten = {k: v for k, v in daten.items()
                         if k not in ("bild", "bilder", "bilder_an")}
            zeilen.append({"text": self.verlauf.get(i), "daten": daten})
        try:
            with open(VERLAUF_DATEI, "w") as f:
                json.dump({"datum": time.strftime("%d.%m."),
                           "zeilen": zeilen}, f)
            os.chmod(VERLAUF_DATEI, stat.S_IRUSR | stat.S_IWUSR)
        except (OSError, TypeError, ValueError):
            pass          # ein nicht geschriebener Verlauf ist kein Grund
                          # zum Stehenbleiben

    def _verlauf_laden(self):
        """Den Verlauf der vorigen Sitzung unter eine Trennzeile hängen.

        Die Trennzeile ist nicht Zierrat: In den Zeilen steht nur die Uhrzeit.
        Ohne den Strich sähe „22:41" von gestern aus wie von eben.
        """
        try:
            with open(VERLAUF_DATEI) as f:
                gespeichert = json.load(f)
        except (OSError, ValueError):
            return
        zeilen = gespeichert.get("zeilen") or []
        if not zeilen:
            return
        # Das Datum nur, wenn es ein anderer Tag war – „vorige Sitzung vom
        # 10.08." liest sich seltsam, wenn heute der 10.08. ist.
        datum = gespeichert.get("datum")
        self.verlauf.insert("end", "── vorige Sitzung{} ──".format(
            " vom " + datum if datum and datum != time.strftime("%d.%m.")
            else ""))
        self.verlauf_daten.append(None)
        self.verlauf.itemconfig(self.verlauf.size() - 1, foreground=FARBEN["matt"])
        for e in zeilen:
            daten = e.get("daten")
            if daten is not None and not daten.get("kandidaten"):
                daten = None          # ohne Vorschläge führt sie nirgendwohin
            self.verlauf.insert("end", e.get("text") or "")
            self.verlauf_daten.append(daten)
            if daten is None:
                self.verlauf.itemconfig(self.verlauf.size() - 1,
                                        foreground=FARBEN["matt"])

    def _umbruch_anpassen(self, ereignis):
        """Die Textzeilen so breit umbrechen lassen, wie das Fenster ist.

        Tk bricht ein Label nur an einer festen Pixelzahl um – ohne die
        bräche es gar nicht, mit einer festen stünde der Text in einer
        Spalte, während rechts eine Handbreit leer bleibt. Also bei jeder
        Größenänderung nachziehen.

        Die 24 px sind der Innenabstand des Rahmens plus etwas Luft; ohne
        sie schöbe der letzte Buchstabe die Bildlaufleiste an.
        """
        breite = max(200, ereignis.width - 24)
        if breite == getattr(self, "_letzte_breite", 0):
            return                       # jede Mausbewegung neu wäre unnötig
        self._letzte_breite = breite
        for label in self._breite_labels:
            label.config(wraplength=breite)

    # ------------------------------------------------------- Wunschliste
    def _blinken_beenden(self, grundfarbe=None):
        """Ein laufendes Blinken abbrechen und die Fläche geradeziehen.

        Muss bei jedem Treffferwechsel geschehen: Sonst blinkte der Wunsch
        von eben über der Figur von jetzt – dieselbe Sorte Falschaussage wie
        eine Karte, die zum vorigen Scan gehört.
        """
        if self._blinkt is not None:
            try:
                self.wurzel.after_cancel(self._blinkt)
            except (tk.TclError, ValueError):
                pass
            self._blinkt = None
        if grundfarbe is not None:
            self._flaeche_faerben(grundfarbe)

    def _flaeche_faerben(self, farbe):
        """Die ganze Fläche hinter beiden Bildern umfärben."""
        hell = farbe != self.rahmen_aus
        for flaeche in self._gruen_flaechen:
            flaeche.config(background=farbe)
        for schrift in self._gruen_schriften:
            schrift.config(foreground="#ffffff" if hell else FARBEN["leise"])

    def _wunsch_blinken(self, grundfarbe, uebrig: int = WUNSCH_TAKTE):
        """Zwischen der Wunschfarbe und dem Grund hin und her.

        Gegen den **Grund**, nicht gegen Grau: Eine Figur kann auf der
        Wunschliste stehen und trotzdem schon in einem deiner Sets stecken.
        Dann soll das Grün nicht verschwinden, sondern das Blinken darüber
        laufen – beide Nachrichten bleiben lesbar.
        """
        if uebrig <= 0:
            self._blinkt = None
            self._flaeche_faerben(grundfarbe)
            return
        self._flaeche_faerben(WUNSCH_AN if uebrig % 2 else grundfarbe)
        self._blinkt = self.wurzel.after(
            WUNSCH_TAKT, self._wunsch_blinken, grundfarbe, uebrig - 1)

    def _foto_merken(self):
        self.daten["foto_mitschicken"] = bool(self.mitschicken.get())
        schreiben(self.daten)

    def _vorn_merken(self):
        an = bool(self.immer_vorn.get())
        self.daten["immer_vorn"] = an
        schreiben(self.daten)
        self.wurzel.attributes("-topmost", an)
        self.melden("Das Fenster bleibt über allem." if an else
                    "Andere Fenster dürfen jetzt davor.")

    def _figuren_merken(self):
        self.daten["nur_figuren"] = bool(self.nur_figuren.get())
        schreiben(self.daten)
        self.melden("Es werden nur noch Figuren gezeigt."
                    if self.nur_figuren.get()
                    else "Figuren, Sets und Teile werden gezeigt.")

    def _ton_merken(self):
        self.daten["ton"] = bool(self.ton.get())
        schreiben(self.daten)
        if self.ton.get():
            ton_spielen()          # einmal hören, wie laut es ist

    def _bild_einpassen(self, bild: bytes, kante: int = BILDKANTE):
        """Auf Anzeigegröße bringen und in Tk laden.

        Erst `sips` (stufenlos, sauber gerechnet), und nur falls das nicht
        will, Tks eigene grobe Halbierung als Rückfall.
        """
        kleiner = auf_groesse(bild, kante) or bild
        roh = tk.PhotoImage(data=base64.b64encode(kleiner).decode("ascii"))
        teiler = 1
        while roh.width() // teiler > kante or roh.height() // teiler > kante:
            teiler += 1
        return roh if teiler == 1 else roh.subsample(teiler)

    def gross_zeigen(self, roh: bytes, titel: str):
        """Ein Bild groß zeigen – als Popup, das jeder Klick wieder schließt.

        Die beiden Daumennägel sind 250 px breit: genug, um zu erkennen, ob
        der Vorschlag grob passt, aber nicht, um eine Bedruckung zu
        vergleichen. Genau daran hängt bei Varianten die Entscheidung.

        Kein richtiges Fenster, sondern eine rahmenlose Fläche mit
        `grab_set`: Damit gehen **alle** Klicks hierher, drinnen wie
        draußen, und ein einziger Aufruf räumt es weg. Wer im Stream schnell
        weiterklickt, soll nicht erst ein Fenster schließen müssen.

        Größer als der Bildschirm wird es nicht – ein Katalogbild kann 1600
        px hoch sein.
        """
        if not roh:
            return
        kante = max(400, min(self.wurzel.winfo_screenheight() - 160, 1100))
        f = tk.Toplevel(self.wurzel)
        # Erst unsichtbar aufbauen. Auf macOS greift „-topmost" nicht, solange
        # das Fenster noch nicht angezeigt wurde – gesetzt man es vorher,
        # öffnet sich das Popup **hinter** dem Scanner, und der Klick, mit dem
        # man es nach vorn holen will, schließt es sofort wieder.
        f.withdraw()
        f.overrideredirect(True)              # kein Rahmen, kein Titelbalken
        try:
            bild = self._bild_einpassen(roh, kante)
        except tk.TclError:
            f.destroy()
            self.melden("Dieses Bild lässt sich nicht darstellen.")
            return
        # Der Verweis muss am Fenster hängen, sonst räumt Python ihn weg und
        # die Fläche bleibt leer – der klassische Tk-Stolperstein.
        f._bild = bild
        rahmen = tk.Frame(f, background=FARBEN["klar"], padx=3, pady=3)
        rahmen.pack()
        tk.Label(rahmen, image=bild, bd=0).pack()
        tk.Label(rahmen, text=titel + "   ·   Klick schließt",
                 background=FARBEN["klar"], foreground=FARBEN["linie"]).pack(pady=(3, 1))

        # Mittig auf dem **Bildschirm**, nicht über dem Fenster: Das Popup
        # ist mit 1100 px oft breiter als der Scanner selbst, und dann
        # rutschte es an den linken Rand statt in die Mitte.
        f.update_idletasks()
        x = (f.winfo_screenwidth() - f.winfo_width()) // 2
        y = (f.winfo_screenheight() - f.winfo_height()) // 2
        f.geometry("+{}+{}".format(max(0, x), max(0, y)))

        def zu(_ereignis=None):
            try:
                f.grab_release()
            except tk.TclError:
                pass
            # Das Hauptfenster bekommt die Ebene zurück, die der Haken
            # vorgibt – nicht stur „oben". Sonst käme das Fenster nach jedem
            # Popup wieder nach vorn, obwohl der Haken weg ist.
            try:
                self.wurzel.attributes(
                    "-topmost", bool(self.immer_vorn.get()))
            except tk.TclError:
                pass
            f.destroy()

        for ereignis in ("<Button-1>", "<Button-2>", "<Button-3>",
                         "<Escape>", "<FocusOut>"):
            f.bind(ereignis, zu)
        # Das Hauptfenster steht selbst auf „immer oben", damit es über dem
        # Stream bleibt. Zwei Fenster auf derselben Ebene sortiert macOS
        # nicht verlässlich, und das rahmenlose zieht dabei den Kürzeren –
        # das Popup ging hinter dem Scanner auf. Also nimmt es dem
        # Hauptfenster die Ebene für die Dauer der Anzeige weg; `zu()` gibt
        # sie zurück.
        self.wurzel.attributes("-topmost", False)
        # Jetzt erst anzeigen – und in dieser Reihenfolge, sonst greift
        # „-topmost" auf macOS gar nicht.
        f.deiconify()
        f.update_idletasks()
        f.lift()
        f.attributes("-topmost", True)
        # Anwendungsweite Sperre, **nicht** `grab_set_global`: Damit gehen
        # Klicks überall im Scanner hierher – also auch „daneben" – und das
        # Popup räumt sich selbst weg. Global würde bei einem hängenden
        # Popup der ganze Bildschirm blockieren; das ist es nicht wert.
        # Klicks in andere Programme fängt `<FocusOut>` ab.
        f.grab_set()
        f.focus_force()

    # -------------------------------------------------------- Ansichten
    def _ansichten_aufbauen(self):
        """Die Aufnahmen zum aktuellen Stand als Daumennägel zum Aussuchen.

        Auf einer Drehscheibe kommen drei, vier Bilder derselben Figur
        zusammen, und welches das schönste ist, sieht man – der Rechner
        nicht. Ein grüner Rahmen heißt: Dieses hier wird beim Buchen an den
        Artikel gehängt. Mehrere dürfen es sein, keines auch.
        """
        for altes in self.ansichtsreihe.winfo_children():
            altes.destroy()
        self._mini_bilder = []
        self._mini_rahmen = []
        if len(self.bilder) < 2:
            self.ansichtsreihe.pack_forget()
            return
        self.ansichtsreihe.pack(fill="x", pady=(4, 0), after=self.rahmen)
        # Die Beschriftung sagt, was die Markierung bedeutet. Ohne sie sieht
        # „grüner Rand **und** Häkchen" nach zwei verschiedenen Zuständen aus,
        # obwohl es einer ist – die Frage kam prompt. Sie steht **über** den
        # Bildern: Daneben nähme sie ihnen die Breite, und sechs Daumennägel
        # plus Satz passen nicht in ein schmales Fenster.
        self.ansichtstext = ttk.Label(self.ansichtsreihe, text="")
        self.ansichtstext.pack(anchor="w")
        streifen = ttk.Frame(self.ansichtsreihe)
        streifen.pack(fill="x")
        for i, roh in enumerate(self.bilder[:MINI_HOECHSTENS]):
            try:
                mini = self._bild_einpassen(roh, MINI_KANTE)
            except tk.TclError:
                continue
            self._mini_bilder.append(mini)      # Verweise halten
            rahmen = tk.Frame(streifen, padx=MINI_RAND, pady=MINI_RAND)
            rahmen.pack(side="left", padx=(0, 5))
            feld = tk.Label(rahmen, image=mini, bd=0, cursor=ZEIGEHAND)
            feld.pack()
            # Das Häkchen liegt **über** dem Bild, in der oberen Ecke. Es ist
            # das, was man von weitem sieht – die Randfarbe allein geht in
            # einer Reihe aus sechs Bildern unter.
            haken = tk.Label(rahmen, text="✓", background=MINI_AN,
                             foreground="#ffffff", bd=0, padx=2,
                             font=("Helvetica", 11, "bold"))
            for teil in (rahmen, feld, haken):
                teil.bind("<Button-1>",
                          lambda _e, k=i: self._ansicht_umschalten(k))
            # Die Nummer mitführen, nicht aus der Position ableiten: Lässt
            # sich eine Aufnahme nicht darstellen, fehlt ihr Daumennagel, und
            # von da an zeigte jeder Rahmen auf das falsche Bild.
            self._mini_rahmen.append((i, rahmen, haken, feld))
        rest = len(self.bilder) - MINI_HOECHSTENS
        if rest > 0:
            ttk.Label(streifen, text="+{}".format(rest),
                      foreground=FARBEN["matt"]).pack(side="left", padx=(6, 0))
        self._ansichten_faerben()

    def _ansichten_faerben(self):
        """Gewählt heißt: grüner Rand **und** Häkchen – das ist **eine**
        Markierung, nicht zwei. Ungewählt tritt zurück: blasser Rand, kein
        Zeichen. Daneben steht in Worten, wie viele es sind."""
        an = len(self.bilder_an)
        self.ansichtstext.config(text="✓ wird angehängt ({} von {}):".format(
            an, len(self.bilder)) if an
            else "kein Foto anhängen ({} zur Wahl):".format(len(self.bilder)))
        for nummer, rahmen, haken, feld in self._mini_rahmen:
            an = nummer in self.bilder_an
            rahmen.config(background=MINI_AN if an else MINI_AUS)
            if an:
                haken.place(in_=feld, relx=1.0, rely=0.0, anchor="ne")
                haken.lift()
            else:
                haken.place_forget()

    def _ansicht_umschalten(self, nummer: int):
        """Ein Klick zeigt die Ansicht groß **und** schaltet sie an oder ab.

        Zwei Dinge auf einen Klick, weil im Stream jeder zusätzliche
        Handgriff einer zu viel ist: Wer hinsieht, will meist auch wählen.
        """
        if nummer in self.bilder_an:
            self.bilder_an.discard(nummer)
        else:
            self.bilder_an.add(nummer)
        if 0 <= nummer < len(self.bilder):
            self.letztes_bild = self.bilder[nummer]
            self._vorschau_zeigen(self.letztes_bild)
        self._ansichten_faerben()
        self.melden("{} von {} Ansichten werden angehängt.".format(
            len(self.bilder_an), len(self.bilder)))

    def _vorschau_zeigen(self, bild: bytes):
        try:
            self._vorschaubild = self._bild_einpassen(bild)
        except tk.TclError:
            self.vorschau.config(image="", text="(nicht\ndarstellbar)",
                                 width=17, height=9)
            return
        self.vorschau.config(image=self._vorschaubild, text="",
                             width=self._vorschaubild.width(),
                             height=self._vorschaubild.height())

    def _referenz_zeigen(self, bild):
        """Das Katalogbild rechts – oder ein ehrlicher Hinweis, wenn keins da
        ist. Eine leere Fläche ließe offen, ob es lädt oder fehlt."""
        # Die Rohdaten bleiben liegen: Der Daumennagel ist auf 250 px
        # gerechnet, die Großansicht braucht das Bild in voller Größe.
        self._referenz_roh = bild
        if not bild:
            self._referenzbild = None
            self.referenz.config(image="", text="kein\nKatalogbild",
                                 foreground=FARBEN["still"], width=17, height=9)
            return
        try:
            self._referenzbild = self._bild_einpassen(bild)
        except tk.TclError:
            self.referenz.config(image="", text="(nicht\ndarstellbar)",
                                 width=17, height=9)
            return
        self.referenz.config(image=self._referenzbild, text="",
                             width=self._referenzbild.width(),
                             height=self._referenzbild.height())

    def _post_abarbeiten(self):
        try:
            while True:
                art, last = self.post.get_nowait()
                # Was ein Hintergrundfaden zu **einem bestimmten** Vorschlag
                # herausgefunden hat. Ist inzwischen ein anderer gewählt –
                # weil der nächste Scan schneller war als BrickLink –, gehört
                # es nicht mehr auf die Karte. Ohne diese Prüfung überschrieb
                # der Preis der vorigen Figur Namen, Nummer und Bestand der
                # neuen, und die drei Knöpfe buchten wieder die alte.
                if art == "update":
                    self._update_zeigen(*last)
                    continue
                if art == "fuer":
                    fuer, art, last = last
                    if fuer is not self.gewaehlt:
                        continue
                if art == "stand":
                    self.melden(last)
                elif art == "verlauf":
                    self.melden(last, True)
                elif art in ("gemerkt", "entmerkt"):
                    # Der Stern folgt sofort, wie in der App – aber nur, wenn
                    # die Karte noch dieser Figur gehört. Der Rest der Karte
                    # (Zeile „auf der Wunschliste", Farbe in der Liste) kommt
                    # mit dem Nachfragen gleich danach.
                    last.setdefault("_info", {})["wanted"] = art == "gemerkt"
                    if self.treffer is last:
                        self._stern_setzen(art == "gemerkt")
                elif art == "wunsch-fragen":
                    self._wunsch_abgeben_fragen(last)
                elif art == "nachbuchen":
                    # Nach jeder Buchung „habt ihr schon" neu holen – sonst
                    # stünde die Figur noch als „nicht in der Sammlung" oder
                    # „auf der Wunschliste" da, obwohl sie längst woanders ist.
                    if self.kandidaten and any(
                            t is last for t in self.kandidaten):
                        self._bestand_auffrischen(self.kandidaten)
                elif art == "preis-leeren":
                    # Sonst uebernaehme die naechste Figur stumm den Preis
                    # der vorigen – der Zustand darf dagegen stehen bleiben.
                    self.preisfeld.delete(0, "end")
                elif art == "referenz":
                    self._referenz_zeigen(last)
                elif art == "vorschau":
                    self._vorschau_zeigen(last)
                    self.k_ablage.config(state="normal")
                elif art == "auto-stand":
                    # Nach dem Ausschalten liegt oft noch eine Meldung des
                    # letzten Taktes hier – die füllte sonst eine Anzeige,
                    # hinter der nichts mehr läuft.
                    if self.wacht:
                        self.autostand.config(text=last)
                elif art == "auto-aus":
                    # Der Wächter hat sich selbst beendet – ohne den Haken
                    # nachzuziehen stünde er auf „an", während nichts läuft.
                    self.wacht = False
                    self.automatik.set(False)
                    self.autostand.config(text="")
                    self.melden(last, True)
                elif art == "auto-los":
                    # Ebenso: Wer eben ausgeschaltet hat, will keine Anfrage
                    # mehr, auch wenn der letzte Takt sie schon beschlossen
                    # hatte.
                    if self.wacht:
                        self._ausloesen(lambda b=last: b, automatisch=True)
                elif art == "kandidaten":
                    self._kandidaten_zeigen(last)
                elif art == "nachtragen":
                    self._nummer_eintragen(last)
                elif art == "auffrischen":
                    # Nur, wenn noch derselbe Stand auf dem Schirm steht –
                    # sonst kommt der Bestand eines Scans an, von dem der
                    # Anwender längst weitergegangen ist.
                    if last is self.kandidaten and any(
                            t is self.gewaehlt for t in last):
                        wahl = self.liste.curselection()
                        self._zeilen_schreiben(last)
                        self.liste.selection_set(wahl[0] if wahl else 0)
                        self._treffer_zeigen(self.gewaehlt, still=True)
                elif art == "leeren":
                    self._treffer_leeren()
                elif art == "nummerfeld":
                    # Nicht `bool(last)`: „ohne-fokus" ist wahr, und genau der
                    # Unterschied entscheidet, ob der Eingabestrich springt.
                    self.nummerfeld_zeigen(last)
                elif art == "treffer":
                    self._treffer_zeigen(last)
                elif art == "frei":
                    self.beschaeftigt = False
                    self.ausloeser.config(state="normal")
                elif art == "listen":
                    # Die bisherige Wahl behalten, wenn es sie noch gibt –
                    # sonst springt sie beim Aktualisieren mitten im
                    # Abarbeiten auf eine andere Liste.
                    vorher = self.listenwahl.get()
                    self.listen = last
                    namen = [l["name"] for l in last]
                    self.listenwahl.config(values=namen)
                    if namen:
                        self.listenwahl.current(
                            namen.index(vorher) if vorher in namen else 0)
                    else:
                        self.listenwahl.set("")
                    self._listenknopf_beschriften()
                    self.melden("{} Einkaufsliste{}".format(
                        len(namen), "" if len(namen) == 1 else "n"))
                elif art == "listenwahl":
                    # Kommt **nach** „listen": Wer eine Liste anlegt, will
                    # auf sie buchen, nicht auf die erste im Alphabet.
                    namen = list(self.listenwahl.cget("values"))
                    if last in namen:
                        self.listenwahl.current(namen.index(last))
                    self._listenknopf_beschriften()
        except queue.Empty:
            pass
        # Hier mit, und zwar aus einem Grund, der nicht auf der Hand liegt:
        # `_scroll_nachfuehren` setzt die Höhe des inneren Rahmens fest –
        # damit ändert sich seine **tatsächliche** Größe nicht mehr, wenn der
        # Inhalt wächst oder schrumpft, und genau das `<Configure>` bleibt
        # aus, auf das die Nachführung horcht. Sie hing dadurch fest: Die
        # Bildlaufleiste blieb stehen, obwohl längst alles hineinpasste.
        # Der Takt läuft ohnehin; ein paar Abfragen alle 120 ms fallen nicht
        # ins Gewicht, und damit stimmt es immer.
        self._scroll_nachfuehren()
        # Alle rund zwei Sekunden nachsehen, ob der Rechner inzwischen auf
        # Nachtmodus umgeschaltet hat. Öfter braucht es nicht – niemand
        # merkt zwei Sekunden –, und `winfo_rgb` ist billig genug, dass es
        # auch bei jedem Takt nicht auffiele.
        self._farbtakt = getattr(self, "_farbtakt", 0) + 1
        if self._farbtakt >= 16:
            self._farbtakt = 0
            try:
                if farben_auffrischen(self.wurzel):
                    self.melden("Ansicht an den Nacht- bzw. Tagmodus "
                                "angepasst.")
            except tk.TclError:
                pass
        self.wurzel.after(120, self._post_abarbeiten)

    # ------------------------------------------------------------ Zugang
    def zugang_zeigen(self):
        f = tk.Toplevel(self.wurzel)
        f.title("Zugang zur Instanz")
        f.attributes("-topmost", True)
        r = ttk.Frame(f, padding=12)
        r.pack(fill="both", expand=True)
        ttk.Label(r, text="Adresse der Instanz").pack(anchor="w")
        e_adresse = ttk.Entry(r, width=42)
        e_adresse.insert(0, self.instanz.adresse or "http://localhost:8300")
        e_adresse.pack(fill="x", pady=(0, 8))
        ttk.Label(r, text="Benutzername").pack(anchor="w")
        e_benutzer = ttk.Entry(r, width=42)
        e_benutzer.insert(0, self.daten.get("benutzer", ""))
        e_benutzer.pack(fill="x", pady=(0, 8))
        ttk.Label(r, text="Passwort").pack(anchor="w")
        e_passwort = ttk.Entry(r, width=42, show="•")
        e_passwort.pack(fill="x", pady=(0, 8))

        # Nur nötig, wenn die Instanz hinter Cloudflare Access steht. Die
        # Felder stehen leer da und stören niemanden, der sie nicht braucht
        # – aber wer sie braucht, findet sie ohne zu suchen.
        ttk.Separator(r).pack(fill="x", pady=(4, 8))
        ttk.Label(r, text="Cloudflare Access – nur falls nötig",
                  font=("Helvetica", 11, "bold")).pack(anchor="w")
        ttk.Label(r, wraplength=330, foreground=FARBEN["leise"],
                  text="Steht die Instanz hinter Cloudflare Access, braucht "
                       "es einen Dienst-Token. Den legt ihr in Zero Trust an "
                       "und erlaubt ihn in der Richtlinie der Anwendung.").pack(
            anchor="w", pady=(0, 6))
        ttk.Label(r, text="Client-ID").pack(anchor="w")
        e_cf_id = ttk.Entry(r, width=42)
        e_cf_id.insert(0, self.daten.get("cf_kennung", ""))
        e_cf_id.pack(fill="x", pady=(0, 8))
        ttk.Label(r, text="Client-Secret").pack(anchor="w")
        e_cf_geheim = ttk.Entry(r, width=42, show="•")
        e_cf_geheim.insert(0, self.daten.get("cf_geheim", ""))
        e_cf_geheim.pack(fill="x", pady=(0, 8))

        # Der Weg ohne eigene Richtlinie in Cloudflare: Browser auf,
        # E-Mail und Code wie gewohnt. `cloudflared` muss dafür auf dem
        # Rechner liegen – fehlt es, sagt der Knopf das auch.
        ttk.Label(r, foreground=FARBEN["leise"], wraplength=330,
                  text="Oder ohne Dienst-Token: einmal im Browser anmelden, "
                       "wie gewohnt mit E-Mail und Code.").pack(
            anchor="w", pady=(4, 4))
        k_cf = Knopf(r, text="🌐 Über Cloudflare anmelden …")
        k_cf.pack(anchor="w", pady=(0, 8))

        hinweis = ttk.Label(r, text="", foreground=FARBEN["warnung"],
                            wraplength=330)
        hinweis.pack(fill="x")

        def cf_anmelden():
            adresse = e_adresse.get().strip()
            k_cf.config(state="disabled",
                        text="🌐 Der Browser ist offen – bitte anmelden …")
            hinweis.config(text="", foreground=FARBEN["leise"])

            def fertig(geschafft, meldung):
                k_cf.config(state="normal",
                            text="🌐 Über Cloudflare anmelden …")
                hinweis.config(text=meldung,
                               foreground=FARBEN["geschafft" if geschafft
                                                 else "warnung"])

            def arbeit():
                geschafft, meldung = Instanz(adresse).cf_anmelden()
                # Zurück in den Hauptfaden – Tk gehört ihm.
                f.after(0, fertig, geschafft, meldung)

            threading.Thread(target=arbeit, daemon=True).start()

        k_cf.config(command=cf_anmelden)

        def anmelden():
            # Der Dienst-Token muss schon beim Anmelden mit – sonst kommt
            # die Anfrage gar nicht erst bis zur Instanz.
            neue = Instanz(e_adresse.get().strip(), "",
                           e_cf_id.get().strip(), e_cf_geheim.get().strip())
            try:
                neue.anmelden(e_benutzer.get().strip(), e_passwort.get())
            except Fehler as e:
                hinweis.config(text=str(e))
                return
            self.instanz = neue
            self.daten.update({"adresse": neue.adresse,
                               "benutzer": e_benutzer.get().strip(),
                               "token": neue.token,
                               "cf_kennung": neue.cf_kennung,
                               "cf_geheim": neue.cf_geheim})
            schreiben(self.daten)
            self.listen_laden()
            self.melden("Angemeldet.")
            f.destroy()

        Knopf(r, text="Anmelden", art="gelb", command=anmelden).pack(
            pady=(8, 0))
        e_passwort.bind("<Return>", lambda _: anmelden())
        e_passwort.focus_set()

    def nummerfeld_zeigen(self, an):
        """Das Feld steht immer da – hier geht es nur noch um den Fokus.

        Fand die Erkennung nichts, ist Tippen der einzige Weg weiter, und dann
        soll der Eingabestrich schon blinken. Hat der Wächter ausgelöst, darf
        er ihn niemandem wegnehmen: Man tippt vielleicht gerade einen Preis.
        """
        if an is True:
            self.nummerfeld.delete(0, "end")
            self.nummerfeld.focus_set()

    def _nummer_eintragen(self, neue: list):
        """Die nachgeschlagene Nummer **zu** den Vorschlägen legen.

        Nicht an ihre Stelle: Die Erkennung liefert oft etwas, das falsch ist,
        ohne wertlos zu sein – beim Chewbacca auf dem Ständer erkennt sie den
        Ständer. Wer die Nummer nachträgt, will die richtige Figur *dazu*,
        nicht die Liste weggewischt. Und wer sich vertippt, hat die
        Vorschläge noch.

        Die Liste wird an Ort und Stelle erweitert, nicht ersetzt: Der
        Verlaufseintrag hält genau diese Liste fest, und ein Rücksprung soll
        das Nachgetragene wiederfinden.
        """
        if not self.kandidaten:
            self._kandidaten_zeigen(neue)      # nichts erkannt – der alte Weg
            return
        vorhanden = {t["item_id"] for t in self.kandidaten}
        dazu = [t for t in neue if t["item_id"] not in vorhanden]
        if dazu:
            self.kandidaten.extend(dazu)
            wohin = len(self.kandidaten) - len(dazu)
            # Die Kennung des Standes wächst mit: Sonst hielte der nächste
            # Scan diesen hier für eine Wiederholung seiner selbst.
            if self.eintrag is not None:
                self.eintrag["ids"] = [t["item_id"] for t in self.kandidaten]
            text = "✎ {} nachgetragen".format(
                ", ".join(t["item_id"] for t in dazu))
        else:
            # Schon in der Liste – dann eben hinspringen statt verdoppeln.
            wohin = next(i for i, t in enumerate(self.kandidaten)
                         if t["item_id"] == neue[0]["item_id"])
            text = "{} steht schon unter den Vorschlägen".format(
                neue[0]["item_id"])
        self._liste_fuellen(self.kandidaten, wohin)
        self.nummerfeld.delete(0, "end")
        # Erst jetzt melden: `_liste_fuellen` schreibt selbst in die
        # Statuszeile, und was dort stehen bleiben soll, ist das hier.
        # In den Verlauf kommt nur das wirklich Nachgetragene – und mit
        # demselben Datensatz wie der Scan darunter, denn es ist derselbe
        # Stand, nur um die getippte Nummer reicher. Ohne ihn wäre die Zeile
        # blass und führte nirgendwohin: ausgerechnet die, die man später
        # sucht.
        self.melden(text, bool(dazu), self.eintrag if dazu else None)

    def nummer_suchen(self):
        """Von Hand eingetippte Nummer nachschlagen und wie einen Treffer
        behandeln – samt Katalogbild, Preis und den drei Knöpfen."""
        nummer = self.nummerfeld.get().strip()
        if not nummer:
            return
        if not self.instanz.token:
            self.melden("Erst anmelden (Zugang …).")
            return
        self.melden(f"Suche {nummer} im Katalog …")

        def lauf():
            alle = self.instanz.nummer_suchen(nummer)
            if not alle:
                self.post.put(("stand", f"{nummer} steht nicht im "
                                        f"BrickLink-Katalog."))
                return
            # Denselben Weg wie ein erkannter Treffer nehmen: Bestand für
            # alle auf einmal holen, dann anzeigen. Sonst stünde die Karte
            # ohne „habt ihr schon" da.
            frage = [{"item_id": t["item_id"], "item_type": t["item_type"]}
                     for t in alle]
            info = self.instanz.infos(frage)
            for t in alle:
                t["_info"] = info.get(t["item_id"], {})
                # Merken, dass diese Zeile getippt und nicht erkannt wurde –
                # „100 %" stünde dort sonst als Trefferquote, und eine
                # Trefferquote ist es gerade nicht.
                t["_getippt"] = True
            self.post.put(("nachtragen", alle))
        threading.Thread(target=lauf, daemon=True).start()

    def liste_anlegen(self):
        """Neue Einkaufsliste anlegen, ohne in die App zu wechseln.

        Im Stream ist genau das der Engpass: Man kauft bei jemand Neuem, hat
        keine Liste dafür, und bis man in der App eine angelegt hat, ist der
        Artikel weg. Die neue Liste wird danach gleich ausgewählt – wer sie
        anlegt, will auf sie buchen.
        """
        if not self.instanz.token:
            self.melden("Erst anmelden (Zugang …).")
            return
        f = tk.Toplevel(self.wurzel)
        f.title("Neue Einkaufsliste")
        f.attributes("-topmost", True)
        r = ttk.Frame(f, padding=12)
        r.pack(fill="both", expand=True)
        ttk.Label(r, text="Name der Liste").pack(anchor="w")
        eingabe = ttk.Entry(r, width=34)
        eingabe.pack(fill="x", pady=(0, 4))
        # Ein Vorschlag mit dem heutigen Datum – so heißen die bestehenden
        # Listen auch („Flohmarkt 04.08."), und die Hälfte ist damit getippt.
        eingabe.insert(0, time.strftime(" %d.%m."))
        eingabe.icursor(0)
        hinweis = ttk.Label(r, text="", foreground=FARBEN["warnung"],
                            wraplength=300)
        hinweis.pack(fill="x")

        def anlegen():
            name = eingabe.get().strip()
            if not name:
                hinweis.config(text="Ohne Namen geht es nicht.")
                return
            def lauf():
                try:
                    self.instanz.liste_anlegen(name)
                except Fehler as e:
                    self.post.put(("verlauf", "Liste anlegen: " + _meldung(e)))
                    return
                # Frisch holen statt selbst einsortieren: Die Instanz kennt
                # die endgültige Reihenfolge, wir raten sie nicht.
                self.post.put(("listen", self.instanz.listen()))
                self.post.put(("listenwahl", name))
                self.post.put(("verlauf", f"Liste »{name}« angelegt"))
            threading.Thread(target=lauf, daemon=True).start()
            f.destroy()

        Knopf(r, text="Anlegen", art="gelb", command=anlegen).pack(
            pady=(8, 0))
        eingabe.bind("<Return>", lambda _: anlegen())
        eingabe.focus_set()

    def listen_laden(self):
        if not self.instanz.token:
            self.melden("Erst anmelden (Zugang …).")
            return
        self.melden("Hole die Einkaufslisten …")
        threading.Thread(
            target=lambda: self.post.put(("listen", self.instanz.listen())),
            daemon=True).start()

    # ---------------------------------------------------------- Auslösen
    def rahmen_senden(self):
        if IST_WINDOWS:
            # Windows hat keine eingebaute Auswahl wie macOS' ⌘⇧4. Also
            # derselbe Weg wie bei »Bereich merken«: ein Abbild des
            # Bildschirms zeigen und darin den Rahmen ziehen – nur wird er
            # hier nicht gemerkt, sondern gleich aufgenommen.
            #
            # **Im Hauptfaden**, nicht in `_ausloesen`s Arbeitsfaden: Tk
            # gehört dem Hauptfaden, und `bereich_waehlen` baut ein Fenster.
            self.wurzel.withdraw()
            self.wurzel.update()
            time.sleep(0.25)
            gewaehlt = bereich_waehlen(self.wurzel)
            self.wurzel.deiconify()
            if not gewaehlt:
                self.melden("Abgebrochen.")
                return
            self._ausloesen(lambda: bereich_aufnehmen(gewaehlt))
            return
        self._ausloesen(rahmen_ziehen, versteckt=True)

    def bereich_senden(self):
        if not self.bereich:
            self.melden("Erst einen Bereich merken.")
            return
        self._ausloesen(lambda: bereich_aufnehmen(self.bereich))

    def bereich_merken(self):
        self.wurzel.withdraw()
        self.wurzel.update()
        time.sleep(0.25)
        gewaehlt = bereich_waehlen(self.wurzel)
        self.wurzel.deiconify()
        if gewaehlt:
            self.bereich = gewaehlt
            self.daten["bereich"] = list(gewaehlt)
            schreiben(self.daten)
            self.k_bereich.config(state="normal")
            self.k_automatik.config(state="normal")
            self.melden(f"Bereich gemerkt: {gewaehlt[2]}×{gewaehlt[3]}.")

    # --------------------------------------------------------- Automatik
    def _empfindlich_merken(self, *_egal):
        self.stufe = self.empfindlich.get()
        self.daten["empfindlichkeit"] = self.stufe
        schreiben(self.daten)

    def _empfindlich_faerben(self):
        """Pille und Titel blass, solange nicht von selbst ausgelöst wird."""
        an = bool(self.automatik.get())
        self.empfindlich.config(state="normal" if an else "disabled")
        self.empfindlich_titel.config(
            foreground=FARBEN["leise"] if an else FARBEN["still"])

    def _automatik_schalten(self):
        """Den Wächter an- oder abschalten."""
        if not self.automatik.get():
            self.wacht = False
            self.autostand.config(text="")
            self.autostand.pack_forget()
            return
        if not self.bereich:
            self.automatik.set(False)
            self.melden("Erst einen Bereich merken.")
            return
        self.stufe = self.empfindlich.get()
        # Der Bereich wird aufgenommen, wie er ist – ohne das eigene Fenster
        # wegzublenden, sonst flackerte es alle paar Sekunden. Liegt der
        # Scanner über dem Bereich, fotografierte er also sich selbst. Das
        # merkt man sonst erst an einer Reihe sinnloser Erkennungen.
        x, y, b, h = self.bereich
        fx, fy = self.wurzel.winfo_rootx(), self.wurzel.winfo_rooty()
        fb, fh = self.wurzel.winfo_width(), self.wurzel.winfo_height()
        if fx < x + b and x < fx + fb and fy < y + h and y < fy + fh:
            self.automatik.set(False)
            self.melden("Der Scanner liegt über dem gemerkten Bereich – "
                        "so nähme er sich selbst auf. Fenster daneben "
                        "schieben oder den Bereich neu merken.")
            return
        self.wacht = True
        self.auto_anfragen = []
        self.auto_leer = 0
        self.autostand.config(text="⏱ sieht zu …")
        # Direkt unter die Automatik-Reihe, nicht ans Ende der Karte.
        self.autostand.pack(fill="x", after=self.k_automatik.master)
        threading.Thread(target=self._wachen, daemon=True).start()
        self.melden("Automatik an – es wird geschickt, sobald sich etwas tut "
                    "und danach still steht.", True)

    def _wachen(self):
        """Den gemerkten Bereich im Auge behalten – ganz auf diesem Rechner.

        Ausgelöst wird genau dann, wenn drei Dinge zusammenkommen: Es hat
        sich etwas geändert, das Bild steht seither still, und es zeigt nicht
        dasselbe wie beim letzten Mal. Die dritte Bedingung ist die
        wichtigste – ohne sie schickte eine Figur, die eine Minute lang
        stillgehalten wird, immer weiter dasselbe Bild.
        """
        letzter = None          # der Abzug vom Takt davor
        gesendet = None         # der zuletzt geschickte
        ruhe = 0                # so viele Takte steht das Bild schon still
        # Beim ersten Takt gibt es nichts zu vergleichen, und das zählt als
        # Änderung: Wer die Automatik einschaltet, während der Verkäufer
        # gerade eine Figur hochhält, will diese Figur. Es kostet eine
        # einzige Anfrage, und danach greift der gewöhnliche Ablauf.
        bewegt = 999.0          # wie viel sich seit dem letzten Mal tat
        letzte_anfrage = 0.0
        dreht = 0               # Takte ununterbrochener, ruhiger Bewegung
        ansichten = 0           # wie viele Anfragen seit dem letzten Sprung
        while self.wacht:
            beginn = time.time()
            # Der Abzug wird aufgehoben, nicht nur gemessen: Löst dieser Takt
            # aus, geht genau dieses Bild zur Erkennung. Ein zweiter Abzug
            # wäre ein anderer Augenblick – und der eine, auf den es ankommt,
            # ist der, in dem das Bild still stand.
            roh = bereich_aufnehmen(self.bereich)
            jetzt = fingerabdruck(roh)
            if jetzt is None:
                self.post.put(("auto-aus", "Der Bereich lässt sich nicht "
                                           "aufnehmen – fehlt die "
                                           "Berechtigung zur "
                                           "Bildschirmaufnahme?"))
                return
            # `self.stufe` statt der Combobox: Ein Tk-Bedienelement darf nur
            # der Hauptfaden anfassen, und hier läuft der Wächter.
            still, neu = EMPFINDLICHKEIT.get(self.stufe,
                                             EMPFINDLICHKEIT["mittel"])
            d = abweichung(jetzt, letzter) if letzter else 999.0
            letzter = jetzt
            sprung = neu * AUTO_SPRUNG
            if d < still:
                ruhe += 1
                dreht = 0
            else:
                ruhe = 0
                bewegt = max(bewegt, d)
                # Ein Sprung ist kein Drehen: Da greift jemand ins Bild oder
                # stellt etwas Neues hin. Dann fängt das Zählen von vorn an –
                # und der Artikel gilt als gewechselt, es dürfen also wieder
                # Ansichten gesammelt werden.
                if d > sprung:
                    dreht = 0
                    ansichten = 0
                    # Neuer Artikel, neuer Versuch: Dass am vorigen nichts zu
                    # erkennen war, sagt über diesen nichts.
                    self.auto_leer = 0
                else:
                    dreht += 1
            # Nur Anfragen der letzten Minute zählen.
            self.auto_anfragen = [t for t in self.auto_anfragen
                                  if beginn - t < 60]
            grund = ""
            # Zwei Wege zum Auslösen. Der erste ist der gewöhnliche: Das Bild
            # ist zur Ruhe gekommen, die Figur wird stillgehalten.
            # `== AUTO_RUHE`, nicht `>=`: genau in dem Takt, in dem sie
            # eintritt – sonst löste jedes weitere Stillstehen erneut aus.
            steht = ruhe == AUTO_RUHE and bewegt >= neu
            # Der zweite ist die Drehscheibe: Es bewegt sich gleichmäßig
            # weiter, ohne je stillzustehen. Dann wird mittendrin geschickt –
            # lieber ein leicht bewegtes Bild als gar keins. `== `, damit es
            # danach erst wieder nach AUTO_DREH_TAKTE Takten drankommt.
            kreist = bool(dreht) and dreht % AUTO_DREH_TAKTE == 0
            if steht or kreist:
                if kreist and not steht and ansichten >= AUTO_ANSICHTEN:
                    grund = "genug Ansichten dieses Artikels"
                elif kreist and not steht \
                        and self.auto_leer >= AUTO_LEERLAUF:
                    # Es bewegt sich zwar, aber hier ist nichts zu holen.
                    # Der Stillstand-Auslöser bleibt scharf – wer die Figur
                    # ruhig hält, bekommt weiterhin seinen Versuch.
                    grund = "hier war {}× nichts zu erkennen".format(
                        self.auto_leer)
                elif abweichung(jetzt, gesendet) < neu and gesendet:
                    grund = "dasselbe Bild wie zuletzt"
                elif self.beschaeftigt:
                    grund = "die vorige Erkennung läuft noch"
                elif beginn - letzte_anfrage < AUTO_PAUSE:
                    grund = "Mindestabstand"
                elif len(self.auto_anfragen) >= AUTO_JE_MINUTE:
                    grund = "{}/Min. erreicht".format(AUTO_JE_MINUTE)
                else:
                    gesendet = jetzt
                    letzte_anfrage = beginn
                    bewegt = 0.0
                    ansichten += 1
                    self.auto_anfragen.append(beginn)
                    self.post.put(("auto-los", roh))
            self.post.put(("auto-stand", "⏱ {}  ·  Bewegung {:.1f}  ·  "
                                         "{} Anfrage{} in der Minute{}".format(
                "still" if ruhe else ("dreht sich" if dreht else "sieht zu"),
                d if d < 900 else 0.0, len(self.auto_anfragen),
                "" if len(self.auto_anfragen) == 1 else "n",
                "  ·  wartet: " + grund if grund else "")))
            rest = AUTO_TAKT - (time.time() - beginn)
            if rest > 0:
                time.sleep(rest)

    def _ausloesen(self, aufnehmen, versteckt: bool = False,
                   automatisch: bool = False):
        if self.beschaeftigt:
            return
        if not self.instanz.token:
            self.melden("Erst anmelden (Zugang …).")
            return
        self.beschaeftigt = True
        self.auto_lauf = automatisch
        self.ausloeser.config(state="disabled")
        # Jetzt lesen, nicht im Faden: Ein Tk-Bedienelement gehört dem
        # Hauptfaden.
        nur_figuren = bool(self.nur_figuren.get())
        # Beim Ziehen des Rahmens ist das eigene Fenster im Weg – es liegt
        # ja über allem.
        if versteckt:
            self.wurzel.withdraw()
            self.wurzel.update()
            time.sleep(0.15)

        def arbeit():
            roh = aufnehmen()
            if versteckt:
                self.wurzel.after(0, self.wurzel.deiconify)
            if not roh:
                self.post.put(("stand", "Abgebrochen – oder die Berechtigung "
                                        "zur Bildschirmaufnahme fehlt."))
                self.post.put(("frei", None))
                return
            # Erst zeigen, dann fragen: Kommt nichts zurück, sieht man
            # wenigstens, was geschickt wurde. Übernommen wird der Ausschnitt
            # aber erst, wenn etwas erkannt wurde – siehe unten.
            steht_schon = self.treffer is not None
            if not steht_schon:
                self.letztes_bild = roh
            self.post.put(("vorschau", roh))
            self.post.put(("stand", "Erkennung läuft …"))
            try:
                antwort = self.instanz.erkennen(roh)
            except Fehler as e:
                self.post.put(("verlauf", f"Fehler: {e}"))
                self.post.put(("frei", None))
                return
            alle = antwort.get("items") or []
            # Aussortieren, was keine Figur ist – aber mitzählen, wie viel
            # das war. „Nichts erkannt" wäre sonst gelogen, und man suchte
            # den Fehler beim Rahmen statt beim Haken.
            aussortiert = 0
            if nur_figuren:
                figuren = [t for t in alle
                           if (t.get("item_type") or "minifig") == "minifig"]
                aussortiert = len(alle) - len(figuren)
                alle = figuren
            if automatisch:
                # Dem Wächter sagen, ob sich das Hinsehen gelohnt hat. Nur er
                # kann daraus schließen, dass in diesem Bereich nichts zu
                # holen ist – die Bewegung allein sagt ihm das nicht.
                self.auto_leer = self.auto_leer + 1 if not alle else 0
            if not alle:
                # Woran es lag, gilt in beiden Fällen – der Haken hat
                # aussortiert, oder es war wirklich nichts da.
                warum = "Nichts erkannt"
                if aussortiert == 1:
                    warum = "Keine Figur darunter – der Vorschlag war ein " \
                            "Set oder Teil."
                elif aussortiert:
                    warum = "Keine Figur darunter – alle {} Vorschläge " \
                            "waren Sets oder Teile.".format(aussortiert)
            if not alle and steht_schon:
                # Es steht schon eine Figur auf der Karte, und dieser Versuch
                # hat nichts ergeben. Dann bleibt **alles**, wie es war –
                # Karte, Knöpfe, Aufnahme.
                #
                # Früher wurde hier geräumt, aus Sorge, man könnte sonst die
                # Figur von eben auf die Liste legen. Im Betrieb ist das
                # Gegenteil das Problem: Der Wächter löst aus, während man
                # gerade den Preis eintippt, findet nichts – und nimmt einem
                # mitten in der Eingabe den Treffer weg, an dem man arbeitet.
                # Ein Versuch, der nichts gefunden hat, hat auch nichts
                # widerlegt. Erst eine erkannte Figur wechselt die Karte.
                self.post.put(("vorschau", self.letztes_bild))
                self.post.put(("stand", warum.rstrip(".")
                               + " – der Treffer von eben bleibt stehen."))
                self.post.put(("frei", None))
                return
            if not alle:
                # Ohne Treffer auf der Karte gibt es nichts zu bewahren:
                # aufräumen und das Nummernfeld anbieten.
                self.post.put(("leeren", None))
                # Beim Wächter ohne Fokus: Der Anwender tippt vielleicht
                # gerade einen Preis, und ein Feld, das sich von selbst den
                # Eingabestrich holt, während man schreibt, ist eine Zumutung.
                self.post.put(("nummerfeld", "ohne-fokus" if automatisch
                               else True))
                if aussortiert:
                    self.post.put(("stand", warum + " Haken »Nur Figuren« "
                                                    "aus, oder die Nummer "
                                                    "eintippen."))
                else:
                    self.post.put(("stand", "Nichts erkannt – enger rahmen, "
                                            "abwarten bis die Figur still "
                                            "hält, oder die Nummer "
                                            "eintippen."))
                self.post.put(("frei", None))
                return
            # Alle Kandidaten, nicht nur der erste – und für alle auf einmal
            # der schnelle Blick in die eigene Datenbank. Das kostet eine
            # Anfrage, keine je Figur.
            # Jetzt erst gehört der Ausschnitt zum Stand: Er ist die Aufnahme
            # zu **dieser** Figur, hängt als Foto an ihr und liegt im
            # Verlaufseintrag. Ein Fehlversuch hat ihn nicht ersetzt.
            self.letztes_bild = roh
            frage = [{"item_id": t["item_id"],
                      "item_type": t.get("item_type") or "minifig"}
                     for t in alle]
            gespeichert = self.instanz.infos(frage)
            for t in alle:
                t["_info"] = gespeichert.get(t["item_id"], {})
            self.post.put(("kandidaten", alle))
            self.post.put(("frei", None))

        threading.Thread(target=arbeit, daemon=True).start()

    # ----------------------------------------------------------- Treffer
    def _kandidaten_zeigen(self, alle: list):
        """Alle Vorschläge auflisten, den besten vorauswählen.

        Bei ähnlichen Figuren – zwei Varianten desselben Kopfes etwa – liegt
        die richtige oft auf Platz zwei. Wer nur den ersten sieht, legt die
        falsche an und merkt es nie.
        """
        # Die Nummern mitschreiben, nicht nur die Anzahl: Beim Durchsehen
        # hinterher will man wissen, *welche* Figur das war – „1 Vorschlag"
        # sagt darüber nichts.
        gezeigt = ["{} {} %".format(t["item_id"], t.get("score", "?"))
                   for t in alle[:3]]
        if len(alle) > 3:
            gezeigt.append("+{}".format(len(alle) - 3))

        # Dieselbe Figur zweimal hintereinander? Im Stream der Regelfall: Der
        # Verkäufer dreht sie, das Bild kommt erneut zur Ruhe, der Wächter
        # löst wieder aus. Zwei gleiche Zeilen sagen nicht mehr als eine – und
        # sie schieben die Figur davor aus dem Blick. Also dieselbe Zeile
        # weiterführen, mit Zähler und neuer Uhrzeit.
        ids = [t["item_id"] for t in alle]
        oben = self.verlauf_daten[0] if self.verlauf_daten else None
        # Dieselbe Figur aus einem anderen Winkel? Zwei Anzeichen zusammen:
        # Es ging schnell hintereinander, und die Vorschläge überschneiden
        # sich. Genau das passiert auf einer Drehscheibe – jede Ansicht
        # liefert etwas anderes, aber selten etwas völlig anderes.
        #
        # Sicher lässt sich das nicht unterscheiden: Zwei Figuren auf
        # demselben Ständer haben denselben Ständer in den Vorschlägen. Es
        # ist aber auch nicht schlimm, wenn einmal falsch zusammengefasst
        # wird – **verworfen wird nichts**, die Liste wird nur länger, und
        # die getroffene Auswahl bleibt stehen.
        wiederholung = (oben is not None
                        and time.time() - (oben.get("zeit") or 0)
                        < ANSICHT_FENSTER
                        and bool(set(ids) & set(oben.get("ids") or [])))
        if wiederholung:
            # Den bestehenden Datensatz weiterbenutzen, nicht ersetzen: Auf
            # ihn zeigt schon die Verlaufszeile.
            eintrag = oben
            eintrag["mal"] = eintrag.get("mal", 1) + 1
            vorher_gewuenscht = {t["item_id"]
                                 for t in eintrag.get("kandidaten") or []
                                 if _gewuenscht(t.get("_info") or {})}
            alle, verbessert = _ansichten_vereinen(
                eintrag.get("kandidaten") or [], alle)
            eintrag["kandidaten"] = alle
            eintrag["ids"] = [t["item_id"] for t in alle]
            eintrag["zeit"] = time.time()
            # Jede Ansicht wird aufgehoben – welche die schönste ist, sieht
            # man selbst, und beim Buchen darf man aussuchen.
            eintrag.setdefault("bilder", [])
            eintrag.setdefault("bilder_an", set())
            if self.letztes_bild is not None:
                ansicht_dazulegen(eintrag, self.letztes_bild)
                # Vorgewählt ist die Ansicht, in der die jetzt oberste Figur
                # am deutlichsten zu sehen war – aus ihr stammt die beste
                # Quote. Wer es anders will, klickt es anders.
                if alle and alle[0]["item_id"] in verbessert:
                    eintrag["bilder_an"] = {len(eintrag["bilder"]) - 1}
                else:
                    self.letztes_bild = eintrag["bilder"][
                        min(eintrag["bilder_an"], default=0)]
                    self._vorschau_zeigen(self.letztes_bild)
            gezeigt = ["{} {} %".format(t["item_id"], t.get("score", "?"))
                       for t in alle[:3]]
            if len(alle) > 3:
                gezeigt.append("+{}".format(len(alle) - 3))
            # Das ⏱ bleibt, sobald **eine** der Ansichten vom Wächter kam –
            # sonst verschwände es, nur weil man zuletzt selbst ausgelöst hat,
            # und die Zeile behauptete, alles sei von Hand gewesen.
            eintrag["auto"] = eintrag.get("auto") or self.auto_lauf
            self._verlauf_ersetzen(0, "{}{}  ⟳{}".format(
                "⏱ " if eintrag["auto"] else "", " · ".join(gezeigt),
                eintrag["mal"]))
            self.melden("Ansicht {} – {} Vorschläge zusammen".format(
                eintrag["mal"], len(alle)))
        else:
            # Der Datensatz, der an dieser Verlaufszeile hängt: Mit ihm kommt
            # man später hierher zurück. Die Aufnahme gehört dazu – ohne sie
            # hinge beim Zurückspringen ein fremdes Bild neben dem
            # Katalogbild, und ein nachträglich mitgespeichertes Foto zeigte
            # die falsche Figur.
            eintrag = {"kandidaten": alle, "index": 0, "ids": ids,
                       "zeit": time.time(),
                       "bilder": [self.letztes_bild]
                       if self.letztes_bild is not None else [],
                       "bilder_an": {0} if self.letztes_bild is not None
                       else set(), "auto": self.auto_lauf}
            vorher_gewuenscht = set()
            # Hinterher will man sehen, was der Wächter von sich aus geholt
            # hat und was man selbst ausgelöst hat – gerade um die
            # Empfindlichkeit danach einzustellen.
            self.melden(("⏱ " if self.auto_lauf else "")
                        + " · ".join(gezeigt), True, eintrag)
        self.eintrag = eintrag
        self.bilder = eintrag.setdefault("bilder", [])
        self.bilder_an = eintrag.setdefault("bilder_an", set())
        self._ansichten_aufbauen()
        # Bei einer Wiederholung bleibt es still und dunkel: Man hat die Figur
        # eben erst gesehen, und ein Ton, der zweimal für dasselbe kommt,
        # verliert genau die Bedeutung, für die er da ist.
        #
        # Der Ton gilt dem **ganzen Scan**, nicht nur dem gewählten Vorschlag:
        # Bei Varianten liegt der Wunsch oft auf Platz zwei, und wer im Stream
        # gerade nicht hersieht, bekäme genau den nie mit. Er sagt „schau
        # hin"; welche Zeile gemeint ist, sagt danach das ☆ und der goldene
        # Grund. Vor dem Aufbau der Liste, damit er sofort kommt.
        # Bei weiteren Ansichten zählt nur, was **neu** hinzugekommen ist:
        # Taucht der Wunsch erst in der dritten Ansicht auf, muss es klingen –
        # war er schon in der ersten dabei, hat man ihn längst gehört.
        neue_wuensche = [t for t in alle
                         if _gewuenscht(t.get("_info") or {})
                         and t["item_id"] not in vorher_gewuenscht]
        if neue_wuensche and self.ton.get():
            ton_spielen()
        # Der frische Scan ist jetzt der Stand, auf dem wir stehen – die
        # Markierung im Verlauf soll das zeigen, auch wenn man vorher
        # zurückgesprungen war.
        self.verlauf.selection_clear(0, "end")
        self.verlauf.selection_set(0)
        self.verlauf.see(0)
        # Bei einer weiteren Ansicht bleibt stehen, was gewählt war – auch
        # wenn die Sortierung sich geändert hat. Sonst risse eine Umdrehung
        # der Scheibe genau den Treffer weg, auf den man gerade zielt, und
        # der Klick auf „＋ Sammlung" legte etwas anderes an. Nur wenn der
        # gewählte Vorschlag verschwunden ist, geht es auf den besten.
        wohin = 0
        if wiederholung and self.gewaehlt is not None:
            wohin = next((i for i, t in enumerate(alle)
                          if t is self.gewaehlt), 0)
        self._liste_fuellen(alle, wohin,
                            blinken=bool(neue_wuensche) or not wiederholung)

    def _verlauf_ersetzen(self, i: int, text: str):
        """Eine Verlaufszeile neu schreiben – Markierung bleibt, wo sie war."""
        markiert = i in self.verlauf.curselection()
        self.verlauf.delete(i)
        self.verlauf.insert(i, time.strftime("%H:%M  ") + text)
        if markiert:
            self.verlauf.selection_set(i)
        self._verlauf_sichern()

    def _zeilen_schreiben(self, alle: list):
        """Die Vorschläge in die Liste schreiben – ohne etwas auszuwählen.

        Getrennt vom Auswählen, weil die Zeilen auch neu geschrieben werden,
        wenn nur der Bestand nachgezogen wurde: Dann sollen die 🛒-Marken
        stimmen, ohne dass Katalogbild und Preis noch einmal geholt werden.
        """
        self.kandidaten = alle
        self.liste.delete(0, "end")
        for i, t in enumerate(alle):
            info = t.get("_info") or {}
            eingeplant = _schon_da(info)
            wunsch = _gewuenscht(info)
            # Die Art nur nennen, wenn es keine Figur ist. Bei einer von Hand
            # gesuchten Nummer stehen Set und Teil nebeneinander – ohne das
            # Wort wüsste niemand, welche Zeile welche ist. Bei erkannten
            # Vorschlägen sind es fast immer Figuren, da wäre es Balast.
            art = {"set": " [Set]", "part": " [Teil]"}.get(t.get("item_type"), "")
            # Beide Marken können zusammen auftreten: Man kann sich eine
            # zweite ausdrücklich wünschen.
            # Das zweite Zeichen sagt jetzt, **warum** die Zeile grün ist:
            # ✔ in der Sammlung, 📦 in einem eigenen Set, 🛒 auf einer Liste.
            marke = ("☆" if wunsch else " ") + _schon_da_marke(info)
            # Getippte Zeilen tragen ein ✎ statt einer Zahl. Sie stehen in
            # derselben Liste wie die erkannten, und dort wäre „100 %" die
            # unehrlichste Zahl von allen – geraten hat da niemand.
            quote = "  ✎  " if t.get("_getippt") \
                else "{:>3} %".format(t.get("score", "?"))
            # Aus wie vielen Ansichten dieselbe Figur kam. Das ist die
            # verlässlichere Zahl als die Trefferquote: Zweimal aus
            # verschiedenen Winkeln gefunden schlägt einmal knapp erkannt.
            gesehen = t.get("_ansichten", 1)
            name = (t.get("name") or "")[:44 if gesehen < 2 else 38]
            if gesehen > 1:
                name += "  ({}×)".format(gesehen)
            self.liste.insert("end", "{} {}  {}{}  ·  {}".format(
                marke, quote, t["item_id"], art, name))
            # Die Fläche gilt immer nur für den **gewählten** Vorschlag.
            # Steht die eingeplante – oder gewünschte – Figur auf Platz zwei,
            # bei Varianten der Regelfall, sähe man davon nichts, ohne jede
            # Zeile einzeln anzuklicken. Deshalb trägt die Zeile die Marke.
            # „Schon da" färbt vor „Wunsch": Vor einem Doppelkauf zu warnen
            # wiegt schwerer, und die Marken zeigen ohnehin beides.
            if eingeplant:
                self.liste.itemconfig(i, background=GRUEN_ZEILE,
                                      foreground=GRUEN_ZEILE_SCHRIFT,
                                      selectbackground=RAHMEN_AN,
                                      selectforeground="#ffffff")
            elif wunsch:
                self.liste.itemconfig(i, background=WUNSCH_ZEILE,
                                      foreground=WUNSCH_ZEILE_SCHRIFT,
                                      selectbackground=WUNSCH_AN,
                                      selectforeground="#ffffff")

    def _liste_fuellen(self, alle: list, index: int = 0,
                       blinken: bool = True):
        """Vorschläge zeigen und einen davon wählen – samt Bild und Preis.

        Denselben Weg nehmen der frische Scan und der Rücksprung in den
        Verlauf. Sonst sähe eine zurückgeholte Trefferliste anders aus als
        dieselbe Liste zehn Minuten vorher, und der Unterschied wäre nichts
        als eine zweite Stelle, die dasselbe halb macht.
        """
        self._zeilen_schreiben(alle)
        index = min(max(index, 0), len(alle) - 1)
        self.liste.selection_clear(0, "end")
        self.liste.selection_set(index)
        self.liste.see(index)
        self.gewaehlt = alle[index]
        # Auch das gehört zum Stand dieser Verlaufszeile – sonst führte ein
        # Rücksprung auf die nachgetragene Nummer wieder zum erkannten
        # Vorschlag zurück, den man ja gerade verworfen hat.
        if self.eintrag is not None:
            self.eintrag["index"] = index
        self._treffer_zeigen(alle[index], blinken=blinken)
        self._referenz_holen(alle[index])
        self._preis_nachfragen(alle[index])

    def _auswahl_geaendert(self, _ereignis=None):
        gewaehlt = self.liste.curselection()
        if not gewaehlt or not self.kandidaten:
            return
        treffer = self.kandidaten[gewaehlt[0]]
        if treffer is self.gewaehlt:
            return
        self.gewaehlt = treffer
        # Die gewählte Variante gehört zum Stand dieser Verlaufszeile: Wer
        # später hierher zurückspringt, will die Zeile wiederfinden, die er
        # ausgesucht hatte – nicht wieder den Vorschlag mit der höchsten
        # Trefferquote, den er ja gerade verworfen hat.
        if self.eintrag is not None:
            self.eintrag["index"] = gewaehlt[0]
        self._treffer_zeigen(treffer)
        self._referenz_holen(treffer)
        self._preis_nachfragen(treffer)

    def _verlauf_geklickt(self, _ereignis=None):
        """Zurück zu einem früheren Scan – mit allem, was dazugehörte.

        Im Stream geht es schnell: Man scannt weiter, während der Verkäufer
        redet, und merkt zwei Figuren später, dass die vorletzte doch auf die
        Liste sollte. Bisher war sie unwiederbringlich weg – die Aufnahme
        besonders, die es kein zweites Mal gibt.

        Der Rücksprung ist ungefährlich, weil der Weg zurück derselbe ist:
        Der aktuelle Scan steht ja selbst als oberste Zeile im Verlauf.
        """
        wahl = self.verlauf.curselection()
        if not wahl:
            return
        eintrag = self.verlauf_daten[wahl[0]] \
            if wahl[0] < len(self.verlauf_daten) else None
        if eintrag is None:
            self.melden("Zu dieser Zeile gibt es keinen Treffer – "
                        "die blassen sind Buchungen und Meldungen.")
            return
        if eintrag is self.eintrag:
            return                        # da stehen wir schon
        self.eintrag = eintrag
        # Die Aufnahme von damals gehört dazu: Sie steht links neben dem
        # Katalogbild, sie wandert bei „📷 Foto mitspeichern" an den Artikel,
        # und sie ist es, die in die Zwischenablage geht.
        self.bilder = eintrag.setdefault("bilder", [])
        self.bilder_an = eintrag.setdefault("bilder_an", set())
        self.letztes_bild = self.bilder[min(self.bilder_an, default=0)] \
            if self.bilder else None
        if self.letztes_bild:
            self._vorschau_zeigen(self.letztes_bild)
            self.k_ablage.config(state="normal")
        else:
            self._vorschaubild = None
            self.vorschau.config(image="", text="Aufnahme\nnicht mehr\nda",
                                 foreground=FARBEN["still"], width=17, height=9)
            self.k_ablage.config(state="disabled")
        self._ansichten_aufbauen()
        self._liste_fuellen(eintrag["kandidaten"], eintrag.get("index", 0))
        self._bestand_auffrischen(eintrag["kandidaten"])
        # Nach `_liste_fuellen`, nicht davor: Das schreibt selbst in die
        # Statuszeile, und der Hinweis, dass man in der Vergangenheit steht,
        # ist der wichtigere von beiden.
        self.melden("↩ Stand von {} – Buchen legt diesen Treffer an.".format(
            self.verlauf.get(wahl[0])[:5]))

    def _bestand_auffrischen(self, alle: list):
        """Beim Rücksprung „habt ihr schon" neu holen.

        Der Datensatz hält fest, was vor zehn Minuten galt – und genau in
        diesen zehn Minuten kann die Figur in der Sammlung gelandet sein,
        womöglich durch den Klick, der direkt auf diesen Scan folgte. Wer
        dann auf die alten Zahlen schaut, kauft ein zweites Mal; das ist die
        eine Frage, für die es dieses Werkzeug gibt.

        Nur die schnelle Auskunft aus der eigenen Datenbank – nach BrickLink
        ist beim ersten Mal schon gefragt worden, und der Preis von damals
        gilt noch.
        """
        frage = [{"item_id": t["item_id"],
                  "item_type": t.get("item_type") or "minifig"} for t in alle]

        def lauf():
            neu = self.instanz.infos(frage)
            if not neu:
                return
            for t in alle:
                # Leere Felder überschreiben nichts: Die kurze Auskunft kennt
                # weder `all_sets` noch die Preise von BrickLink, und die
                # sollen beim Auffrischen nicht verschwinden.
                frisch = {k: v for k, v
                          in (neu.get(t["item_id"]) or {}).items()
                          if v is not None}
                if frisch:
                    t["_info"] = {**(t.get("_info") or {}), **frisch}
            self.post.put(("auffrischen", alle))
        threading.Thread(target=lauf, daemon=True).start()

    def _referenz_holen(self, treffer: dict):
        """Das Katalogbild der gewählten Figur nachladen – im Hintergrund,
        damit die Auswahl nicht darauf wartet."""
        self.post.put(("fuer", (treffer, "referenz", None)))
        adresse = treffer.get("img_url") or ""
        if not adresse:
            return

        def lauf():
            roh = self.instanz.katalogbild(adresse)
            # Der Weiterleiter gibt JPEG – Tk will PNG.
            self.post.put(("fuer", (treffer, "referenz",
                                    als_png(roh) if roh else None)))
        threading.Thread(target=lauf, daemon=True).start()

    def _preis_nachfragen(self, treffer: dict):
        """Bei BrickLink nachfragen – nur für den gerade Gewählten.

        Für alle Kandidaten auf einmal wäre es eine Abfrage je Figur, und
        das für Vorschläge, die man gar nicht will.
        """
        if treffer["item_id"].startswith(("fig-", "manuell-", "custom-")):
            return
        if treffer.get("_genauer"):
            return                       # schon einmal gefragt
        frage = [{"item_id": treffer["item_id"],
                  "item_type": treffer.get("item_type") or "minifig"}]

        def lauf():
            self.post.put(("fuer", (treffer, "stand",
                                    "Frage BrickLink nach dem Preis …")))
            genauer = self.instanz.infos(frage, bei_bricklink=True).get(
                treffer["item_id"])
            treffer["_genauer"] = True
            zusatz = dict(genauer or {})
            # Die Sets im selben Durchgang: Es ist dieselbe Wartezeit, und
            # die Antwort liegt auf der Instanz ohnehin im Speicher.
            if (treffer.get("item_type") or "minifig") == "minifig" \
                    and not zusatz.get("all_sets"):
                sets = self.instanz.sets_der_figur(treffer["item_id"])
                if sets:
                    zusatz["all_sets"] = sets
            # Die volle Preisangabe wie im Steckbrief der App. Kommt sie
            # nicht (Instanz ohne BrickLink, Fehler), bleibt die kurze Zeile.
            preise = self.instanz.preise(treffer.get("item_type") or "minifig",
                                         treffer["item_id"])
            if preise.get("new") or preise.get("used"):
                treffer["_preise"] = preise
                treffer["_waehrung"] = (self.instanz.einstellungen()
                                        .get("currency") or "EUR")
            if zusatz or treffer.get("_preise"):
                treffer["_info"] = {**(treffer.get("_info") or {}), **zusatz}
                self.post.put(("fuer", (treffer, "treffer", treffer)))
            else:
                self.post.put(("fuer", (treffer, "stand",
                                        "BrickLink hat keinen Preis.")))
        threading.Thread(target=lauf, daemon=True).start()

    def _treffer_leeren(self):
        """Alles vom vorigen Treffer wegräumen – ohne die eigene Aufnahme.

        Die bleibt bewusst stehen: Man will sehen, **was** man geschickt hat,
        wenn nichts erkannt wurde. Alles andere gehört zur Figur von eben und
        wäre jetzt eine Falschaussage – vor allem die drei Knöpfe.
        """
        self.treffer = None
        self.gewaehlt = None
        # Der Verlauf behält seine Zeilen – nur stehen wir auf keiner mehr.
        # Die Markierung geht mit, sonst leuchtete eine Zeile, deren Stand
        # gerade weggeräumt wurde.
        self.eintrag = None
        self.verlauf.selection_clear(0, "end")
        self.kandidaten = []
        self.liste.delete(0, "end")
        self.name.config(text="—")
        for label in (self.unter, self.besitz, self.woanders, self.setliste):
            label.config(text="")
        self._preise_zeigen(None)
        self._referenzbild = None
        self._referenz_roh = None
        self.referenz.config(image="", text="—", foreground=FARBEN["still"],
                             width=17, height=9)
        self._blinken_beenden(self.rahmen_aus)
        for k in (self.k_sammlung, self.k_merken, self.k_liste):
            k.config(state="disabled")
        self._stern_setzen(False)

    def _preise_zeigen(self, preise, waehrung: str = "EUR"):
        """Den Preisblock füllen – oder leeren, wenn es (noch) keine gibt."""
        for kind in self.preisblock.winfo_children():
            kind.destroy()
        if not preise:
            return
        zeilen = preis_zeilen(preise, waehrung)
        reihe = 0
        for schild, fett, dahinter, darunter, art in zeilen:
            # Das Schild in festen Farben: Gelb mit dunkler Schrift ist in
            # beiden Modi lesbar, und so steht es auch in der App. Angebote
            # blasser – es ist eine andere Zahl als der Verkaufspreis.
            tk.Label(self.preisblock, text=schild,
                     font=("Helvetica", 10, "bold"),
                     background="#FFD500" if art == "verkauf" else "#FFF0A0",
                     foreground="#1D1D1B", padx=6, pady=0).grid(
                row=reihe, column=0, sticky="nw", padx=(0, 8), pady=(2, 0))
            oben = ttk.Frame(self.preisblock)
            oben.grid(row=reihe, column=1, sticky="w", pady=(1, 0))
            if fett:
                ttk.Label(oben, text=fett, font=("Helvetica", 12, "bold"),
                          foreground=FARBEN["klar"]).pack(side="left")
            if dahinter:
                ttk.Label(oben, text=dahinter,
                          foreground=FARBEN["leise" if not fett else "kraeftig"]
                          ).pack(side="left", padx=(6 if fett else 0, 0))
            reihe += 1
            if darunter:
                ttk.Label(self.preisblock, text=darunter,
                          foreground=FARBEN["leise"]).grid(
                    row=reihe, column=1, sticky="w")
                reihe += 1
        hinweis = "Ø-Verkaufspreise, letzte 6 Monate (BrickLink)"
        if any(z[4] == "angebot" for z in zeilen):
            hinweis += " · „ab“: billigstes Angebot gerade jetzt"
        ttk.Label(self.preisblock, text=hinweis, foreground=FARBEN["matt"],
                  font=("Helvetica", 10),
                  wraplength=getattr(self, "_letzte_breite", 330)
                  ).grid(row=reihe, column=0,
                                               columnspan=2, sticky="w",
                                               pady=(3, 0))

    def _stern_setzen(self, gemerkt: bool):
        """☆ oder ★ – steht die Figur schon auf der Wunschliste?"""
        self.k_merken.config(text="★" if gemerkt else "☆", an=gemerkt)

    def _treffer_zeigen(self, treffer: dict, still: bool = False,
                        blinken: bool = True):
        # `still` heißt: nur neu zeichnen, nichts melden. Beim Auffrischen
        # nach einem Rücksprung stünde sonst „gewählt“ in der Statuszeile und
        # überschriebe den Hinweis, dass man in der Vergangenheit steht.
        #
        # Derselbe Treffer kommt zweimal: einmal sofort, einmal wenn der
        # Preis von BrickLink da ist. In den Verlauf gehört er nur einmal.
        schon_da = self.treffer is treffer
        self.treffer = treffer
        info = treffer.get("_info") or {}
        self.name.config(text=treffer.get("name") or treffer["item_id"])
        teile = [treffer["item_id"],
                 "von Hand eingetragen" if treffer.get("_getippt")
                 else f"{treffer.get('score', '?')} % sicher"]
        if info.get("year"):
            teile.append(str(info["year"]))
        preise = treffer.get("_preise")
        if not preise:
            # Bis die vollen Preise da sind, die kurze Form wie bisher.
            for label, schluessel in (("Ø neu", "new"), ("Ø gebr.", "used")):
                wert = info.get(schluessel)
                if wert is not None:
                    teile.append(f"{label} {geld(wert)}")
        self.unter.config(text="  ·  ".join(teile))
        self._preise_zeigen(preise, treffer.get("_waehrung") or "EUR")
        self.besitz.config(**_besitz_zeile(info))
        # „Habe ich das schon?" hat mehr als eine Antwort: Wunschliste,
        # Einkaufsliste und die eigenen Sets zählen genauso. Alles davon
        # steht längst in der Antwort der App – es stand nur nirgends.
        self.woanders.config(text=_woanders(info))
        self.setliste.config(text=_alle_sets(info))
        grund = RAHMEN_AN if _schon_da(info) else self.rahmen_aus
        self._blinken_beenden(grund)
        # Blinken nur beim **ersten** Zeigen: Derselbe Treffer kommt ein
        # zweites Mal, wenn der Preis von BrickLink eintrifft, und ein Wunsch,
        # der zweimal hintereinander losblinkt, wird zum Flackern.
        if _gewuenscht(info) and not schon_da and not still and blinken:
            self._wunsch_blinken(grund)
        for k in (self.k_sammlung, self.k_merken, self.k_liste):
            k.config(state="normal")
        self._stern_setzen(bool(info.get("wanted")))
        if still:
            return
        if schon_da:
            self.melden("Preis von BrickLink da.")
        else:
            self.melden(f"{treffer['item_id']} gewählt")

    def _zustand_merken(self, *_egal):
        """Auf einem Flohmarkt ist fast alles gebraucht – die einmal
        getroffene Wahl soll den nächsten Start überdauern."""
        self.daten["zustand"] = self.zustand.get()
        schreiben(self.daten)

    def _preis_lesen(self):
        """Gibt (in Ordnung, Wert) zurück. Leer ist erlaubt – dann kommt
        `None`, und die App trägt keinen Preis ein."""
        roh = self.preisfeld.get().strip().replace(",", ".")
        if not roh:
            return True, None
        try:
            wert = float(roh)
        except ValueError:
            return False, None
        if wert < 0:
            return False, None
        return True, round(wert, 2)

    def _tun(self, arbeit, was: str):
        if not self.treffer:
            return
        treffer = self.treffer
        # Alle ausgesuchten Ansichten – auf einer Drehscheibe können das
        # mehrere sein, und welche taugen, hat der Anwender entschieden.
        bilder = [self.bilder[i] for i in sorted(self.bilder_an)
                  if 0 <= i < len(self.bilder)] if self.mitschicken.get() \
            else []

        def lauf():
            try:
                ergebnis = arbeit(treffer)
            except Fehler as e:
                self.post.put(("verlauf", f"{was} misslungen: {e}"))
                return
            # Das Foto hängt am **Artikel**, nicht am Eintrag. Wer erst
            # „＋ Sammlung" und dann „🛒 drauf" drückt, bekam bisher zweimal
            # dasselbe Bild in die Galerie – der Kommentar an dieser Stelle
            # behauptete das Gegenteil, der Code hängte es trotzdem jedes Mal
            # an. Einmal je Artikel und Aufnahme genügt; eine **neue**
            # Aufnahme derselben Figur kommt sehr wohl dazu, denn dann hat man
            # bewusst noch einmal fotografiert.
            neu = doppelt = 0
            fehler = ""
            for bild in bilder:
                merkmal = (treffer["item_id"], hashlib.sha1(bild).digest())
                if merkmal in self.fotos:
                    doppelt += 1
                    continue
                try:
                    self.instanz.foto_anhaengen(treffer, bild)
                    self.fotos.add(merkmal)
                    neu += 1
                except Fehler as e:
                    fehler = str(e)
                    break
            zusatz = ""
            if neu == 1:
                zusatz = " (mit Foto)"
            elif neu > 1:
                zusatz = " (mit {} Fotos)".format(neu)
            elif doppelt:
                zusatz = " (Foto hängt schon dran)"
            if fehler:
                zusatz += " (Foto misslungen: {})".format(fehler)
            self.post.put(("verlauf",
                           f"{treffer['item_id']} – {ergebnis}{zusatz}"))
            self.post.put(("preis-leeren", None))
            if was == "Merken":
                self.post.put(("gemerkt", treffer))
            elif was == "Liste" and (treffer.get("_info") or {}).get("wanted"):
                # Gekauft heißt meist: nicht mehr gewünscht. Aber nur nach
                # Rückfrage – vielleicht will man noch ein zweites Exemplar.
                self.post.put(("wunsch-fragen", treffer))
            self.post.put(("nachbuchen", treffer))
        threading.Thread(target=lauf, daemon=True).start()

    def in_ablage(self):
        """Den anderen Weg gehen: Bild in die Zwischenablage, Rest in der App."""
        if not self.letztes_bild:
            return
        if in_zwischenablage(self.letztes_bild):
            self.melden("In der Zwischenablage – in der App ins Scannen-Feld "
                        "klicken und ⌘V drücken.", True)
        else:
            self.melden("Zwischenablage hat nicht mitgespielt.")

    def zur_sammlung(self):
        gut, preis = self._preis_lesen()
        if not gut:
            self.melden("Einkauf bitte als Zahl, z. B. 4,50")
            return
        zustand = self.zustand.get()
        self._tun(lambda t: self.instanz.in_sammlung(t, zustand, preis),
                  "Sammlung")

    def merken(self):
        """☆ merkt, ★ nimmt wieder weg – nach Rückfrage."""
        if not self.treffer:
            return
        if (self.treffer.get("_info") or {}).get("wanted"):
            self._wunsch_abgeben_fragen(self.treffer)
            return
        self._tun(self.instanz.auf_wunschliste, "Merken")

    def _wunsch_abgeben_fragen(self, treffer: dict):
        """Fragen, ob der Artikel von der Wunschliste darf – und es tun."""
        name = _kurz(treffer.get("name") or treffer["item_id"], 60)
        if not messagebox.askyesno(
                "Von der Wunschliste nehmen?",
                "»{}« ({}) steht auf der Wunschliste.\n\n"
                "Von der Wunschliste nehmen?".format(name, treffer["item_id"]),
                parent=self.wurzel):
            return

        def lauf():
            try:
                ergebnis = self.instanz.von_wunschliste(treffer)
            except Fehler as e:
                self.post.put(("verlauf", f"Von der Wunschliste nehmen "
                                          f"misslungen: {e}"))
                return
            self.post.put(("verlauf", f"{treffer['item_id']} – {ergebnis}"))
            self.post.put(("entmerkt", treffer))
            self.post.put(("nachbuchen", treffer))
        threading.Thread(target=lauf, daemon=True).start()

    def _listenknopf_beschriften(self):
        """Der Hauptknopf sagt, wohin es geht."""
        name = self.listenwahl.get()
        self.k_liste.config(text="🛒 Auf »{}«".format(_kurz(name, 34))
                            if name else "🛒 Auf die Liste")

    def auf_liste(self):
        passend = [l for l in self.listen
                   if l["name"] == self.listenwahl.get()]
        if not passend:
            # Noch keine Liste? Dann gleich eine anlegen – der Artikel wird
            # sonst verpasst, während man in die App wechselt.
            self.melden("Noch keine Liste – leg eine an, dann noch einmal 🛒.")
            self.liste_anlegen()
            return
        gut, preis = self._preis_lesen()
        if not gut:
            self.melden("Einkauf bitte als Zahl, z. B. 4,50")
            return
        nummer = passend[0]["id"]
        zustand = self.zustand.get()
        self._tun(lambda t: self.instanz.auf_liste(nummer, t, zustand, preis),
                  "Liste")


REPO = "Melle79/brickfolio-livescan"


def fassungszahlen(text: str) -> tuple:
    """»v1.5.2« → (1, 5, 2). Was sich nicht lesen lässt, wird zu 0.

    Nicht als Text vergleichen: »1.10.0« käme sonst vor »1.9.0«.
    """
    zahlen = []
    for teil in (text or "").lstrip("vV").split(".")[:3]:
        ziffern = "".join(z for z in teil if z.isdigit())
        zahlen.append(int(ziffern) if ziffern else 0)
    while len(zahlen) < 3:
        zahlen.append(0)
    return tuple(zahlen)


def neuere_fassung(jetzt: str = "") -> tuple | None:
    """Gibt es eine neuere Fassung? (Fassung, Seite, Paket) oder None.

    **Schweigt bei jedem Problem** – kein Netz, GitHub ausgelastet: Ein
    Werkzeug für Auktions-Streams darf nicht mit Fehlern über sich selbst
    stören.

    **Nicht über die API.** Die erlaubt ohne Anmeldung 60 Abfragen je
    Stunde und Internetanschluss – geteilt mit jedem anderen Gerät
    dahinter. Am 25.09.2026 war das aufgebraucht, und der Hinweis auf 1.9.0
    blieb aus. Ein Zugangstoken kommt nicht in Frage: Es wäre in jedem
    ausgelieferten Programm mit drin. Die Release-Seite leitet dagegen auf
    die neueste Fassung weiter und zählt nicht mit (`neueste_ueber_seite`).

    »Paket« ist die Adresse, von der der Scanner sich selbst erneuern kann;
    fehlt sie, bleibt der Weg über die Seite.
    """
    jetzt = jetzt or VERSION
    try:
        gefunden = neueste_ueber_seite(jetzt)
    except Exception:
        return None
    if not gefunden:
        return None
    kennung, seite, paket = gefunden
    if not kennung or fassungszahlen(kennung) <= fassungszahlen(jetzt):
        return None
    return (kennung.lstrip("vV"), seite, paket)


_WEITER = (301, 302, 303, 307, 308)


class _NichtFolgen(urllib.request.HTTPRedirectHandler):
    """Eine Weiterleitung melden statt ihr zu folgen."""

    def redirect_request(self, *_a, **_k):
        return None


def weiterleitung(adresse: str, jetzt: str = "") -> tuple:
    """(Status, Ziel) einer Adresse – **ohne** der Weiterleitung zu folgen.

    Folgen hieße beim Paket: 22 MB laden, nur um zu erfahren, dass es da
    ist. Die Antwort von github.com selbst genügt – 302 heißt „liegt dort".
    """
    oeffner = urllib.request.build_opener(_NichtFolgen)
    antrag = urllib.request.Request(adresse, method="HEAD", headers={
        "User-Agent": "Brickfolio-Live-Scanner/%s" % (jetzt or VERSION)})
    try:
        with oeffner.open(antrag, timeout=15) as antwort:
            return antwort.status, ""
    except urllib.error.HTTPError as e:
        return e.code, (e.headers.get("Location", "") if e.headers else "")


def neueste_ueber_seite(jetzt: str = "") -> tuple | None:
    """(Kennung, Seite, Paket) über die Webseite statt über die API.

    `github.com/<repo>/releases/latest` leitet auf die neueste Fassung
    weiter; die Kennung steht im Ziel. Ob das Paket für dieses System
    schon dranhängt, verrät die Download-Adresse: Weiterleitung heißt ja,
    404 heißt nein – dann bleibt das Paket leer wie bei der API.
    """
    code, ziel = weiterleitung(
        "https://github.com/%s/releases/latest" % REPO, jetzt)
    if code not in _WEITER or "/releases/tag/" not in ziel:
        return None
    kennung = urllib.parse.unquote(
        ziel.rsplit("/releases/tag/", 1)[1]).split("?")[0].split("#")[0]
    if not kennung:
        return None
    seite = "https://github.com/%s/releases/tag/%s" % (REPO, kennung)
    paket = "https://github.com/%s/releases/download/%s/%s" % (
        REPO, kennung, paket_name())
    code, _ = weiterleitung(paket, jetzt)
    return kennung, seite, (paket if code in _WEITER or code == 200 else "")

def paket_name() -> str:
    """Wie das Paket für dieses System im Release heißt."""
    return ("Brickfolio-Live-Scanner-Windows-x64.zip" if IST_WINDOWS
            else "Brickfolio-Live-Scanner-macOS-arm64.zip")


def eigener_ort(ausfuehrbar: str = "", art: object = "?") -> str:
    """Was ersetzt werden müsste – oder "" beim Lauf aus dem Quelltext.

    macOS: …/Brickfolio Live-Scanner.app/Contents/MacOS/<Programm>
    – drei Ebenen höher liegt das Bündel.
    Windows: …\\Brickfolio Live-Scanner\\<Programm>.exe
    – der Ordner drumherum ist es.

    Beides kommt als Parameter herein statt aus `sys`, damit sich der Weg
    für **beide** Systeme auf jedem einzelnen prüfen lässt. Gerechnet wird
    darum mit `ntpath` statt `os.path`: Das versteht **beide** Trenner, wo
    `os.path` unter Windows aus einem Mac-Pfad Backslashes machte und die
    Probe dort scheitern ließ, ohne dass am Programm etwas falsch war.
    """
    ausfuehrbar = ausfuehrbar or sys.executable
    if art == "?":
        art = getattr(sys, "frozen", None)
    if not art:
        # Aus dem Quelltext gestartet: Da ist nichts zu tauschen, und wer so
        # startet, holt sich die neue Fassung mit git.
        return ""
    ordner = ntpath.dirname(ausfuehrbar)
    if art == "macosx_app":
        buendel = ntpath.dirname(ntpath.dirname(ordner))
        return buendel if buendel.endswith(".app") else ""
    return ordner


def kennmal(pfad: str) -> str:
    """Die »designated requirement« einer App – oder "".

    Das ist der Fingerabdruck, an dem macOS eine App wiedererkennt; bei uns
    steht das Zertifikat darin, mit dem gebaut wurde. Sie ist der Grund,
    warum die Bildschirmaufnahme-Freigabe ein Update überlebt – und sie ist
    der Maßstab dafür, ob ein geladenes Paket wirklich von uns kommt.
    """
    try:
        fertig = subprocess.run(["codesign", "-d", "-r-", pfad],
                                capture_output=True, text=True, timeout=60)
    except Exception:
        return ""
    for zeile in (fertig.stdout + fertig.stderr).splitlines():
        # Ein »#« davor heißt nur: nicht eingetragen, sondern abgeleitet.
        # Die Kennung dahinter ist dieselbe, und genau die wollen wir.
        zeile = zeile.strip().lstrip("#").strip()
        if zeile.startswith("designated =>"):
            return zeile.split("=>", 1)[1].strip()
    return ""


def paket_pruefen(neu: str, alt: str) -> str:
    """Darf das eingespielt werden? Leerer Text heißt ja, sonst der Grund.

    **Auf dem Mac wird nicht geglaubt, sondern nachgesehen.** Das Paket kam
    zwar über HTTPS von GitHub, eingespielt wird es aber nur, wenn es
    dasselbe Kennmal trägt wie die laufende Fassung – also mit unserem
    Zertifikat signiert ist. Trägt die laufende keins (Eigenbau ohne
    Signatur), reicht eine gültige Signatur am neuen Paket.

    Unter Windows gibt es nichts zu prüfen, dort ist nichts signiert; die
    Sicherheit ist dieselbe wie beim Laden von Hand – HTTPS zu GitHub.
    """
    if IST_WINDOWS:
        exe = os.path.join(neu, "Brickfolio Live-Scanner.exe")
        return "" if os.path.exists(exe) else "Im Paket steckt kein Programm."
    try:
        fertig = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", neu],
            capture_output=True, text=True, timeout=300)
    except Exception as e:
        return "Signatur nicht prüfbar (%s)." % e
    if fertig.returncode != 0:
        return "Die Signatur des Pakets stimmt nicht."
    neues = kennmal(neu)
    if not neues:
        return "Das Paket ist nicht signiert."
    altes = kennmal(alt)
    if altes and altes != neues:
        return "Das Paket ist von jemand anderem signiert."
    return ""


def paket_laden(adresse: str, ziel: str, melden=None) -> None:
    """Holt das Paket – **ohne Browser**, und genau darum geht es.

    Das Quarantäne-Merkmal, an dem Gatekeeper den Start verweigert, hängt
    der Browser an, nicht das Netz. Was das Programm selbst holt, trägt es
    nicht: Die neue Fassung startet danach ohne Nachfrage und ohne den
    Umweg über die Systemeinstellungen.
    """
    antrag = urllib.request.Request(
        adresse,
        headers={"User-Agent": "Brickfolio-Live-Scanner/%s" % VERSION,
                 "Accept": "application/octet-stream"})
    with urllib.request.urlopen(antrag, timeout=120) as antwort:
        ganz = int(antwort.headers.get("Content-Length") or 0)
        geholt = 0
        with open(ziel, "wb") as datei:
            while True:
                brocken = antwort.read(65536)
                if not brocken:
                    break
                datei.write(brocken)
                geholt += len(brocken)
                if melden:
                    melden(geholt, ganz)


def paket_auspacken(paket: str, ordner: str) -> str:
    """Packt aus und gibt zurück, was drin lag.

    Auf dem Mac mit `ditto`: In einem Bündel stecken Verweise und Rechte,
    die `zipfile` verliert – mit Bordmitteln ausgepackt startet die App
    nicht. Unter Windows liegt der **Inhalt** des Programmordners im Paket,
    ohne den Ordner selbst; da ist das Ziel der Ordner.
    """
    if IST_WINDOWS:
        with zipfile.ZipFile(paket) as archiv:
            archiv.extractall(ordner)
        return ordner
    subprocess.run(["ditto", "-x", "-k", paket, ordner],
                   check=True, capture_output=True, timeout=600)
    for name in sorted(os.listdir(ordner)):
        if name.endswith(".app"):
            return os.path.join(ordner, name)
    raise Fehler("Im Paket steckt keine App.")


_TAUSCH_MAC = """#!/bin/sh
# Wartet, bis der Scanner beendet ist, tauscht und startet ihn neu.
ziel="$1"; neu="$2"; pid="$3"
i=0
while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 300 ]; do
    sleep 0.2
    i=$((i + 1))
done
alt="$ziel.vorher"
rm -rf "$alt"
mv "$ziel" "$alt" || exit 1
if ditto "$neu" "$ziel"; then
    rm -rf "$alt"
else
    # Misslungen: lieber die alte Fassung zurueck als gar keine.
    rm -rf "$ziel"
    mv "$alt" "$ziel"
fi
# Nur was ein Programm ist, wird auch wieder gestartet.
case "$ziel" in *.app) open "$ziel";; esac
"""

_TAUSCH_WINDOWS = """@echo off
rem Wartet, bis der Scanner beendet ist, tauscht und startet ihn neu.
:warten
tasklist /fi "PID eq %~3" 2>nul | findstr /i "%~3" >nul
if not errorlevel 1 (
    ping -n 2 127.0.0.1 >nul
    goto warten
)
robocopy "%~2" "%~1" /MIR /NFL /NDL /NJH /NJS /R:2 /W:1 >nul
if exist "%~1\\Brickfolio Live-Scanner.exe" start "" "%~1\\Brickfolio Live-Scanner.exe"
"""


def tausch_starten(ziel: str, neu: str, ordner: str,
                   warten_auf: int = 0) -> None:
    """Startet den Helfer, der tauscht, sobald dieses Programm weg ist.

    Ein laufendes Programm kann sich nicht selbst ersetzen: Unter Windows
    ist die eigene Datei gesperrt, auf dem Mac zöge man dem eigenen Prozess
    den Boden weg. Also übernimmt ein kleines Skript den letzten Schritt –
    es wartet auf unser Ende, tauscht, und startet neu.

    Es läuft **losgelöst** weiter (`start_new_session`), sonst nähme es
    unser Ende mit und käme nie bis zum Tauschen.

    `warten_auf` gibt es nur, damit sich der Tausch prüfen lässt: Mit der
    eigenen Kennzahl müsste die Probe sich selbst beenden, um ihn zu sehen.
    """
    name = "tausch.cmd" if IST_WINDOWS else "tausch.sh"
    helfer = os.path.join(ordner, name)
    with open(helfer, "w", encoding="utf-8", newline="") as datei:
        datei.write(_TAUSCH_WINDOWS if IST_WINDOWS else _TAUSCH_MAC)
    os.chmod(helfer, 0o755)
    befehl = ([helfer] if IST_WINDOWS else ["/bin/sh", helfer]) \
        + [ziel, neu, str(warten_auf or os.getpid())]
    subprocess.Popen(befehl, close_fds=True,
                     start_new_session=not IST_WINDOWS,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def handbuch_pfad():
    """Wo das Handbuch liegt - im Buendel oder neben dem Quelltext."""
    if getattr(sys, "frozen", None) == "macosx_app":
        ort = os.path.join(os.path.dirname(sys.executable),
                           os.pardir, "Resources", "README.md")
    else:
        ort = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "README.md")
    ort = os.path.normpath(ort)
    return ort if os.path.exists(ort) else None


def handbuch_zeigen():
    """Haengt am Hilfe-Menue von macOS.

    Ohne diesen Befehl antwortet macOS mit "Help isn't available for
    Brickfolio Live-Scanner" - das Menue ist naemlich immer da, nur ohne
    Hinterlegung. Das Handbuch ist das README; es reist im Buendel mit,
    damit die Hilfe auch ohne Netz und ohne Zugriff auf das (private)
    Repo etwas zeigt.
    """
    ort = handbuch_pfad()
    if ort and IST_WINDOWS:
        os.startfile(ort)          # noqa: S606 – gibt es nur unter Windows
    elif ort:
        subprocess.run(["open", ort], check=False)
    else:
        webbrowser.open("https://github.com/Melle79/brickfolio-livescan#readme")


def main():
    # **Ganz vorn, vor jedem Fenster.** Danach nimmt Windows es nicht mehr
    # an – und ohne das rechnet es hinter unserem Ruecken um.
    dpi_weg = windows_dpi_beachten()

    # Apples mitgeliefertes Tk 8.5 zeichnet auf heutigem macOS nur ein weißes
    # Fenster und kann kein PNG. Lieber offen sagen, was fehlt, als den
    # Anwender vor eine leere Fläche setzen.
    if tk.TkVersion < 8.6:
        print("Dieses Python bringt Tk %s mit – zu alt.\n"
              "Damit gäbe es nur ein weißes Fenster.\n"
              "Nehmt ein neueres Python, etwa aus Homebrew:\n"
              "  brew install python-tk\n"
              "oder startet über start.sh, das sucht selbst eines."
              % tk.TkVersion, file=sys.stderr)
        raise SystemExit(2)
    # Was ein früherer Absturz an Ausschnitten liegen ließ, kommt jetzt weg.
    reste_aufraeumen()
    wurzel = tk.Tk()
    if IST_WINDOWS:
        # Jetzt rechnet niemand mehr fuer uns um – also muss die Schrift
        # selbst mitwachsen, sonst steht auf einem 150-%-Bildschirm alles
        # winzig da.
        try:
            wurzel.tk.call("tk", "scaling",
                           wurzel.winfo_fpixels("1i") / 72.0)
        except tk.TclError:
            pass
    # Muss vor mainloop stehen; danach fragt macOS nicht mehr nach.
    wurzel.createcommand("::tk::mac::ShowHelp", handbuch_zeigen)
    app = LiveScanner(wurzel)
    if app.instanz.token:
        app.listen_laden()
        app.melden("Bereit – Rahmen ziehen und senden.")
    wurzel.mainloop()


if __name__ == "__main__":
    main()
