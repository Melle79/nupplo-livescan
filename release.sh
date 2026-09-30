#!/bin/sh
# Baut das macOS-Paket und haengt es ans fertige Release.
#
# **Warum von Hand und nicht im Workflow.** Der Bau-Runner hat den
# privaten Schluessel nicht und unterschreibt ad hoc; die designierte
# Anforderung ist dann nur ein Fingerabdruck des jeweiligen Baus. Fuer
# eine hier gebaute Installation ist so ein Paket ein *fremdes* - die
# Selbsterneuerung lehnt es ab ("Das Paket ist von jemand anderem
# signiert"), und eingespielt haette es ausserdem die Freigabe fuer die
# Bildschirmaufnahme gekostet.
#
# Den Schluessel zu GitHub zu legen wuerde beides zusammenfallen lassen:
# Wer das Repo beherrscht, koennte dann auch unterschreiben - und ein
# untergeschobenes Paket erbte still die Aufnahme-Freigabe. Genau die
# Trennung ist der Schutz. Also bleibt der Schluessel hier, und dieser
# Befehl macht daraus einen Handgriff.
#
# Der Workflow baut weiter mit und beweist, dass der Bau geht. Er haengt
# das macOS-Paket nur nicht mehr an - siehe .github/workflows/bauen.yml.
#
# Aufruf im Wurzelverzeichnis, nachdem das Release angelegt ist:
#
#     sh release.sh            # bauen, pruefen, hochladen
#     sh release.sh --probe    # alles ausser dem Hochladen
#
set -e

PROBE=""
[ "$1" = "--probe" ] && PROBE="ja"

# Der Fingerabdruck der Zertifikatswurzel, an der macOS die App
# wiedererkennt. Aendert der sich, ist es fuer jedes System eine *andere*
# App: Die Freigabe fuer die Bildschirmaufnahme ist dann einmal fuer alle
# weg und muss von Hand neu erteilt werden. Steht hier, damit ein
# versehentlich anderes Zertifikat auffaellt, bevor das Paket hinausgeht.
ERWARTET='58d8776280a5087873a1053ba38bd189c4f39cbe'

APP="dist/Brickfolio Live-Scanner.app"
PAKET="Brickfolio-Live-Scanner-macOS-arm64.zip"
REPO="Melle79/brickfolio-livescan"

[ -f livescan.py ] || { echo "Bitte im Wurzelverzeichnis aufrufen." >&2; exit 1; }

VERSION=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' livescan.py | head -1)
[ -n "$VERSION" ] || { echo "VERSION nicht aus livescan.py zu lesen." >&2; exit 1; }
MARKE="v$VERSION"
echo "Fassung $VERSION"

# **Erst nachsehen, dann bauen.** Ein halbes Release ist schlimmer als
# gar keins: Der Scanner zeigt dann einen Knopf, der ins Leere fuehrt.
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "FEHLER: Es liegen ungesicherte Aenderungen. So weiss niemand," >&2
    echo "        was in dem Paket steckt." >&2
    exit 1
fi
# **Verglichen wird der Quelltext, nicht der Commit.** Verlangte die Wache
# HEAD genau auf der Marke, liesse sich nach dem Setzen nichts mehr am
# Repo aendern - nicht einmal diese Datei hier. Entscheidend ist allein,
# ob das, was in die App wandert, noch das von der Marke ist.
if ! git rev-parse "$MARKE^{commit}" >/dev/null 2>&1; then
    echo "FEHLER: Die Marke $MARKE gibt es nicht." >&2
    exit 1
fi
QUELLEN="livescan.py setup.py livescan.icns bauen.sh"
if ! git diff --quiet "$MARKE" HEAD -- $QUELLEN; then
    echo "FEHLER: Seit $MARKE hat sich der Quelltext der App geaendert:" >&2
    git diff --stat "$MARKE" HEAD -- $QUELLEN >&2
    echo "        Das Paket traege sonst eine Fassungsnummer, die zu" >&2
    echo "        anderem Quelltext gehoert." >&2
    exit 1
fi
if ! gh release view "$MARKE" --repo "$REPO" >/dev/null 2>&1; then
    echo "FEHLER: Zu $MARKE gibt es kein Release. Erst anlegen." >&2
    exit 1
fi

# Ohne Zertifikat braucht der Rest gar nicht erst zu laufen: bauen.sh
# faellt sonst still auf ad hoc zurueck, und das Paket waere fuer jede
# bestehende Installation wertlos.
IDENT="${BFLS_SIGNATUR:-Brickfolio Selbstsigniert}"
if ! security find-certificate -c "$IDENT" >/dev/null 2>&1; then
    echo "FEHLER: Zertifikat »$IDENT« liegt nicht im Schluesselbund." >&2
    echo "        Ohne das ist dieses Paket fuer bestehende Installationen" >&2
    echo "        ein fremdes und wird abgelehnt." >&2
    exit 1
fi

echo "== Bauen =="
rm -rf build dist
PYTHON="${PYTHON:-.venv-bau/bin/python}" sh bauen.sh

echo "== Unterschrift pruefen =="
ANFORDERUNG=$(codesign -d -r- "$APP" 2>&1 \
    | sed -n 's/.*designated => //p')
echo "$ANFORDERUNG"
case "$ANFORDERUNG" in
    *"certificate root = H\"$ERWARTET\""*) ;;
    *)
        echo "FEHLER: Das Buendel traegt nicht die erwartete Wurzel." >&2
        echo "        Erwartet: $ERWARTET" >&2
        echo "        Mit einer anderen verlieren alle die Aufnahme-Freigabe." >&2
        exit 1
        ;;
esac
codesign --verify --deep --strict "$APP"

# **Laeuft es ueberhaupt?** py2app haelt den Prozess auch bei einem
# Startfehler am Leben und zeigt nur einen Dialog - "Prozess lebt noch"
# beweist deshalb nichts.
echo "== Startbeweis =="
"${PYTHON:-.venv-bau/bin/python}" pruefe_buendel.py "$APP"

# ditto statt zip: nur ditto erhaelt Symlinks und Rechte im Buendel.
echo "== Einpacken =="
( cd dist && ditto -c -k --keepParent --sequesterRsrc \
    "Brickfolio Live-Scanner.app" "$PAKET" )
ls -lh "dist/$PAKET"

if [ -n "$PROBE" ]; then
    echo
    echo "Probelauf: Das Paket liegt unter dist/$PAKET und ist geprueft."
    echo "Ans Release gehaengt wurde nichts."
    exit 0
fi

echo "== Ans Release haengen =="
gh release upload "$MARKE" "dist/$PAKET" --repo "$REPO" --clobber

# **Beide Namen, und das ist keine Bequemlichkeit.** Fassungen bis 1.11.0
# fragen zuerst nach dem Nupplo-Namen und halten dabei eine Weiterleitung
# faelschlich fuer „Paket ist da" - nach der Umbenennung des Ordners
# antwortet GitHub naemlich auch auf ein FEHLENDES Paket mit 301. Haengt
# der zweite Name nicht dran, laden sie anschliessend eine 404 und der
# Rueckfall auf den alten Namen kommt nie zum Zug.
#
# Der Fehler steckt in der jeweils anderen Seite und laesst sich dort
# nicht mehr reparieren; hier kostet er zwei Zeilen. Faellt weg, wenn
# niemand mehr auf 1.11.0 oder aelter sitzt.
ZWEITNAME=$(echo "$PAKET" | sed 's/^Brickfolio-/Nupplo-/')
if [ "$ZWEITNAME" != "$PAKET" ]; then
    cp "dist/$PAKET" "dist/$ZWEITNAME"
    gh release upload "$MARKE" "dist/$ZWEITNAME" --repo "$REPO" --clobber
    echo "   auch als $ZWEITNAME"
fi

# **Nachsehen, nicht hoffen.** Was hochgeladen wurde, wird wieder geholt
# und geprueft - genau so, wie der Scanner es spaeter holt. Ein Paket,
# das unterwegs kaputtgeht, faellt hier auf und nicht beim Anwender.
#
# **Ueber browser_download_url, nicht ueber `gh release download`.** Das
# ist der Weg, den `paket_waehlen()` im Scanner nimmt - und nur der zaehlt.
# `gh` geht statt dessen ueber die Kennung des Anhangs aus der API, und
# die kann veraltet sein: Am 23.09.2026 meldete die API nach dem Hochladen
# minutenlang noch den alten Anhang samt Kennung, Groesse und Zeit, waehrend
# die Auslieferung laengst das neue Paket gab. Ein `gh release download`
# lief dabei ins 404, und wer den Metadaten glaubt, haelt eine gelungene
# Auslieferung fuer kaputt.
echo "== Gegenprobe am Release =="
PRUEFORT=$(mktemp -d)
ADRESSE=$(gh api "repos/$REPO/releases/tags/$MARKE" \
    --jq ".assets[] | select(.name == \"$PAKET\") | .browser_download_url")
[ -n "$ADRESSE" ] || { echo "FEHLER: Kein Anhang »$PAKET« am Release." >&2; exit 1; }
curl -sSfL -o "$PRUEFORT/$PAKET" "$ADRESSE"
ditto -x -k "$PRUEFORT/$PAKET" "$PRUEFORT/aus"
GELADEN=$(codesign -d -r- "$PRUEFORT/aus/Brickfolio Live-Scanner.app" 2>&1 \
    | sed -n 's/.*designated => //p')
codesign --verify --deep --strict "$PRUEFORT/aus/Brickfolio Live-Scanner.app"
rm -rf "$PRUEFORT"
if [ "$GELADEN" != "$ANFORDERUNG" ]; then
    echo "FEHLER: Das Paket am Release traegt ein anderes Kennmal." >&2
    echo "        Hier:    $ANFORDERUNG" >&2
    echo "        Geladen: $GELADEN" >&2
    exit 1
fi

# **dist/ muss weg.** Der Bau-Ordner bleibt sonst liegen und ist fuer
# macOS eine zweite App mit derselben Kennung - man schaltet die eine in
# der Freigabeliste frei und startet die andere. Das hat schon einmal
# Stunden gekostet.
rm -rf build dist

echo
echo "Fertig. $MARKE traegt jetzt ein Paket, das bestehende"
echo "Installationen als ihresgleichen erkennen - der Knopf im Scanner"
echo "funktioniert. build/ und dist/ sind weggeraeumt."
