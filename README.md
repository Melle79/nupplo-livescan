# Brickfolio Live-Scanner

Ein kleines Fenster, das über allem liegt. Rahmen um die Figur ziehen,
fertig – der Treffer steht mit Nummer, Ø-Preisen und „habt ihr schon" da,
und auf Knopfdruck landet er in der Sammlung, auf der Wunschliste oder auf
einer Einkaufsliste.

Gedacht für Auktions-Streams: eBay Live läuft im einen Fenster, dieses
liegt daneben. Statt Bildschirmfoto machen, Dateien suchen, ins
Scannen-Feld ziehen – ein Klick, ein Rahmen.

Läuft auf **macOS** (Apple Silicon) und auf **Windows**.



## Es gehört nicht zur App

Brickfolio bleibt unberührt. Dieses Programm benutzt nur die **Schnittstelle**
der App, genau wie es der Browser tut:

| Weg | wofür |
|---|---|
| `POST /api/login` | einmal anmelden, Token merken |
| `POST /api/scan` | den Ausschnitt erkennen lassen |
| `POST /api/suggest_info` | Jahr, Ø-Preise, „wie oft habt ihr das schon" |
| `GET /api/price/{typ}/{nr}` | die vollen Preise wie im Steckbrief der App |
| `GET /api/config` | Währung und ob „Angebotspreise“ eingeschaltet ist |
| `POST /api/collection` | ＋ Zur Sammlung |
| `POST /api/wanted` | ☆ (Merken) |
| `GET/POST /api/lists…` | 🛒 auf eine Einkaufsliste |

Ändert sich an der App nichts, ändert sich hier auch nichts.

## Starten

**Brickfolio Live-Scanner** aus dem Programme-Ordner – siehe *Einbauen*
weiter unten. Die App bringt Python und Tk selbst mit.

Aus dem Quelltext heraus, zum Entwickeln:

```bash
sh start.sh
```

Es braucht **keine** Fremdbibliotheken – aber ein Python mit **Tk 8.6 oder
neuer**. Nur dieser Weg, nicht die fertige App.

> ⚠️ **Nicht das Python aus macOS nehmen.** `/usr/bin/python3` bringt
> **Tk 8.5** mit, Apples altes und auf heutigem macOS kaputtes Fenster-Werk:
> Man bekommt nur ein **weißes Fenster**. Und PNG kann es auch nicht (das kam
> erst mit 8.6), also gäbe es weder Vorschau noch Bereichsauswahl.
>
> `start.sh` probiert deshalb der Reihe nach durch und nimmt das erste
> taugliche – hier das aus Homebrew (Tk 9.0). Die fertige App hat das
> Problem nicht, sie trägt ihr Tk 9.0 im Bündel. Startet ihr
> `livescan.py` direkt mit einem zu alten Python, sagt es das und beendet
> sich, statt dich vor eine leere Fläche zu setzen.

Beim ersten Start fragt es nach Adresse, Benutzername und Passwort. Der
Zugang landet in `~/.brickfolio-livescan.json`, nur für dich lesbar (0600).
Gespeichert wird der **Token**, nicht das Passwort.

> **Berechtigung.** Beim ersten Bildschirmfoto fragt macOS nach
> *Bildschirmaufnahme* – und zwar für das Programm, aus dem ihr das hier
> startet, meist Terminal. Ohne sie kommt ein schwarzes Bild. Zu finden
> unter *Systemeinstellungen → Datenschutz & Sicherheit →
> Bildschirmaufnahme*.

## Bedienen

**▣ Rahmen ziehen und senden** – der eine Knopf, um den es geht. Das Fenster
verschwindet kurz, du ziehst mit der Maus einen Rahmen um die Figur, und
genau dieser Ausschnitt geht zur Erkennung. Das ist macOS' eigene Auswahl:
Maße stehen dabei, Leertaste verschiebt den Rahmen, **Esc** bricht ab.
Die **Eingabetaste** löst dasselbe aus.

**🎯 Bereich merken** und **📷 Aus Bereich** – für Serien aus demselben
Fleck. Einmal markieren, danach genügt ein Klick ohne Ziehen. Praktisch,
wenn der Verkäufer die Figuren immer an derselben Stelle hochhält. Ist ein
Bereich gemerkt, könnt ihr den Scanner auch [von selbst auslösen
lassen](#von-selbst-auslösen).

## Wenn mehrere Versionen erkannt werden

Die Erkennung liefert selten genau eine Antwort – meist eine **Liste mit
Trefferquoten**. Gerade bei Varianten derselben Figur (anderer Umhang, andere
Beine, andere Kopfbedruckung) liegt die richtige oft auf Platz zwei.

Deshalb stehen alle Vorschläge untereinander:

```
 77 %  sw0417   ·  Mace Windu (Cape)
 71 %  sw0417a  ·  Mace Windu - Dark Purple Robes
 64 %  sw0056   ·  Mace Windu (Ep. 2)
```

Der beste ist vorausgewählt; ein Klick auf eine andere Zeile wechselt, und
Preise, „habt ihr schon" und die drei Knöpfe beziehen sich ab dann auf
**diese** Figur. Bei BrickLink nachgefragt wird nur für die gerade gewählte
– sonst wären es Abfragen für Vorschläge, die man gar nicht will.

**Ein 🛒 vor einer Zeile** und ihr blasser grüner Grund heißen: *diese*
Variante habt ihr schon – in der Sammlung, auf einer Liste oder in einem
deiner Sets. Ein **☆** und ein goldener Grund heißen das Gegenteil: Die steht
auf deiner Wunschliste. Ohne die Marken sähe man das erst nach dem Anklicken,
und gerade bei Varianten steht die richtige oft nicht obenauf:

```
     83 %  sw1158   ·  Boba Fett - Repainted Beskar Armor
 🛒  61 %  sw0863   ·  Vice Admiral Holdo
☆    58 %  sw0417a  ·  Mace Windu - Dark Purple Robes
```

Beide Marken zusammen (**☆🛒**) gibt es auch – wer sich ausdrücklich ein
zweites Exemplar wünscht.

## Bedienen

Darüber stehen **zwei Bilder nebeneinander**: links deine Aufnahme, rechts
das **Katalogbild von BrickLink** zur gewählten Figur. So seht ihr auf einen
Blick, ob der Vorschlag passt – bei zwei Varianten mit 77 % und 71 % sagt
die Zahl allein wenig, das Bild dagegen sofort. Wechselt ihr die Zeile in
der Liste, wechselt auch das Katalogbild.

Bei eigenen Figuren gibt es keins; dann steht dort „kein Katalogbild" statt
einer leeren Fläche.

**Ein Klick auf ein Bild zeigt es groß** – bis zu 1100 px statt der 250 in der
Übersicht, mittig auf dem Bildschirm. Bei zwei Varianten derselben Figur
hängt die Entscheidung an der Bedruckung, und die sieht man im Daumennagel
nicht.

Es ist ein rahmenloses Popup, kein Fenster: **Der nächste Klick schließt es**,
egal ob darauf oder daneben, und **Esc** genauso. Du musst also nichts
wegklicken, bevor es weitergeht — im Stream zählt jede Sekunde.

**Wird die ganze Fläche hinter beiden Bildern grün**, heißt das schlicht:
**Habt ihr schon.** Drei Gründe lösen es aus – die Figur steht in der
Sammlung, sie liegt auf einer offenen Einkaufsliste, oder sie steckt in einem
Set, das bei dir daheim steht. Im Stream schaut man auf das Bild, nicht auf
die Zeile darunter, und eine Farbfläche sieht man aus dem Augenwinkel,
während der Verkäufer schon weiterredet.

Bewusst **nicht** grün wird sie bei der Wunschliste: Ein Wunsch ist ein Grund
zu kaufen, kein Grund es zu lassen. Wäre die Fläche dort auch grün, hieße sie
zweierlei und damit nichts.

### Steht sie auf der Wunschliste, blinkt es

Der Wunsch bekommt deshalb ein **eigenes** Signal, und ein lauteres: Die
Fläche hinter den Bildern **blinkt zwei Sekunden lang golden**, und es
**klingt** dazu. Grün darf man übersehen — das schlimmste ist ein Doppelkauf.
Einen Wunsch zu verpassen ist teurer: Er ist der Grund, aus dem ihr überhaupt
zuschaut, und er kommt vielleicht monatelang nicht wieder.

Geblinkt wird gegen den jeweiligen Grund, nicht gegen Grau. Steht die Figur
auf der Wunschliste **und** in einem deiner Sets, bleibt das Grün also
sichtbar und das Gold läuft darüber — beide Nachrichten bleiben lesbar.

**Der Ton gilt dem ganzen Scan, nicht nur dem obersten Vorschlag.** Bei
Varianten liegt der Wunsch oft auf Platz zwei, und wer im Stream gerade nicht
hersieht, bekäme genau den nie mit. Der Ton sagt „schau hin"; welche Zeile
gemeint ist, sagt danach das **☆** davor und ihr goldener Grund:

```
     91 %  sw0100   ·  Nicht gewünscht
☆    64 %  sw0101   ·  Der Wunsch
☆🛒  85 %  sw0300   ·  habt ihr schon – und wollt noch eins
```

Geblinkt wird für den **gewählten** Vorschlag. Klickt ihr die goldene Zeile
an, blinkt es auch für sie.

**🔔 Ton bei Wunschliste** neben dem Foto-Haken schaltet den Ton ab; das
Blinken bleibt. Beim Einschalten spielt er einmal, damit ihr die Lautstärke
hört, bevor es darauf ankommt.

### Die Preise

Unter dem Namen stehen die Preise so wie im Steckbrief der App:

```
[Neu]        Ø 5,95 €  (4,50 € – 7,99 €) · 13× verkauft 🇩🇪
[Gebraucht]  Ø 3,70 €  (2,10 € – 5,49 €) · 41× verkauft 🇩🇪 · 18 im Angebot ab 2,99 € 🇩🇪
```

Je Zustand **eine Zeile**; umgebrochen wird nur, wenn das Fenster zu schmal
ist, und dann eingerückt neben dem Schild. Ø ist der Durchschnitt der
Verkäufe der letzten sechs Monate bei BrickLink, dahinter die Spanne – sie
fällt weg, wenn beide Enden gleich sind. Die Fahne sagt, aus welchem Gebiet
der Preis stammt; unter Windows steht dort ein Kürzel wie `(DE)`, weil
Windows keine Flaggen-Zeichen kennt. **„im Angebot ab“** ist das billigste
Angebot gerade jetzt, kein Verkaufswert; es erscheint nur, wenn in der App
unter Mehr → Angebotspreise eingeschaltet ist. Bis die vollen Preise da
sind, steht die kurze Form („Ø neu … · Ø gebr. …“) in der Zeile mit der
Nummer.

### Habt ihr das schon?

Unter dem Namen stehen drei Zeilen, und sie beantworten drei verschiedene
Fragen:

```
✔ 2× in deiner Sammlung
☆ auf der Wunschliste   🛒 auf »Flohmarkt 02.08.«   🧩 steckt in deinem Set 75168-1 (Yoda's Jedi Starfighter)
📦 aus 4 Sets: 75233-1 Droid Gunship,  75142-1 Homing Spider Droid,  75255-1 Yoda,  +1 weitere
```

Die **erste** Zeile ist der Bestand – grün, wenn ihr die Figur habt, sonst
gelb. Die **zweite** sagt, ob du sie dir schon irgendwo vorgemerkt hast:
Wunschliste, offene Einkaufslisten (mit Namen) und die Sets aus **deiner**
Sammlung, in denen sie steckt. Die **dritte** ist der Katalog – aus welchen
Sets die Figur überhaupt stammt.

Das ist der Unterschied, auf den es beim Mitbieten ankommt: Zeile 2 ist dein
Bestand, Zeile 3 ist Allgemeinwissen. Eine Figur, die schon auf einer Liste
liegt, kauft man sonst zum zweiten Mal.

Zeile 1 und 2 stehen sofort da; Zeile 3 kommt mit dem Preis nach ein bis zwei
Sekunden. Leer bleibt eine Zeile, wenn es nichts zu sagen gibt.

**Auf einem kleinen Bildschirm scrollt die Karte.** Reicht die Höhe nicht,
erscheint rechts eine Bildlaufleiste, und das Mausrad schiebt den Inhalt –
über der Trefferliste und über dem Verlauf scrollen dagegen diese selbst.
Ist Platz übrig, verschwindet die Leiste, und der Verlauf unten wächst wie
gehabt mit.

> Früher stand hier eine Mindesthöhe in Höhe der ganzen Karte. Sie sollte
> verhindern, dass unten etwas heraushängt – auf einem kleineren Bildschirm
> bewirkte sie das Gegenteil: Das Fenster ließ sich nicht kleiner ziehen als
> der Schirm hoch ist, der untere Teil blieb unerreichbar, und scrollen ging
> nicht. Die Mindesthöhe ist jetzt 300 px.

**Zieht das Fenster breit** – die Zeilen brechen dort um, wo das Fenster
endet, nicht an einer festen Marke. Bei einer Figur aus dreißig Sets stehen
trotzdem nicht alle da: Zeile 2 zeigt vier deiner Sets, Zeile 3 acht aus dem
Katalog, dahinter jeweils „und N weitere".

**Zustand und Einkauf** stehen darüber und gelten für 🛒 und „＋ Sammlung"
– die Wunschliste kennt beides nicht und lässt es liegen:

```
[ Gebraucht | Neu ]   Einkauf: [ 7,00 ] €
[ Flohmarkt 24.09.            ▾ ]  [↻]  [＋ Liste]
[ 🛒 Auf »Flohmarkt 24.09.« ]  [☆]  [＋ Sammlung]
```

Der Preis darf leer bleiben, dann trägt die App keinen ein. Komma oder Punkt
ist egal. **Nach jedem Anlegen wird das Preisfeld geleert** – sonst erbte die
nächste Figur stumm den Preis der vorigen. Der **Zustand bleibt dagegen
stehen** und überdauert auch den Neustart: Auf einem Flohmarkt ist fast alles
gebraucht.

**Die Einkaufsliste ist die Hauptsache** (seit 1.9.3): Im Stream füllt man
vor allem Listen, in die Sammlung kommt ein Artikel erst, wenn er da ist.
Darum steht die Wahl der Liste direkt über dem breiten grünen Knopf, und der
Knopf sagt, wohin es geht. Gibt es noch keine Liste, öffnet er das Anlegen.
Daneben **☆** für die Wunschliste und **„＋ Sammlung"**.

**Der Stern geht in beide Richtungen.** Steht die Figur schon auf der
Wunschliste, ist er gefüllt und gelb (★); ein Tipp darauf fragt, ob sie
wieder herunter soll. **Legt ihr eine gewünschte Figur auf eine
Einkaufsliste**, fragt der Scanner ebenso – gekauft heißt meist: nicht mehr
gewünscht, aber vielleicht wollt ihr noch ein zweites Exemplar. Nach jeder
Buchung holt er „habt ihr schon" neu, die Karte zeigt also gleich, wo die
Figur jetzt steht.

Überhaupt trägt der Scanner seit 1.9.0 die Handschrift der App: dunkle
Kante, runde Ecken, Gelb für den Auslöser, Gebraucht/Neu und die
Empfindlichkeit als Pille. Die Knöpfe zeichnet er selbst – die Systemknöpfe
nehmen unter macOS weder Farbe noch Kante an. Nachts werden die weißen
Knöpfe dunkelgrau, Gelb und Grün bleiben.

**Der Verlauf unten** hält fest, was war – mit **Nummern**, nicht nur mit
Anzahlen:

```
22:40  sw0417 77 % · sw0056 64 %
22:37  sw0515 81 %
22:30  sw0413 – auf der Liste (mit Foto)
```

So sieht man hinterher, welche Figur wann durchgelaufen ist. Ab vier
Vorschlägen stehen die drei besten da und dahinter, wie viele noch kamen.

**Mehrere Ansichten derselben Figur werden zusammengefasst** — dazu unten
mehr:

```
22:41  sw0417 79 % · sw0056 55 % · +1  ⟳3
22:37  sw0515 81 %
```

Das **⟳3** heißt: drei Ansichten, eine Figur. Zusammengefasst wird nur, was
**direkt** aufeinander folgt und sich in den Vorschlägen überschneidet. Kommt
etwas ganz anderes dazwischen oder bucht ihr, fängt die nächste Begegnung eine
eigene Zeile an — sonst verschwände, dass ihr sie inzwischen gekauft habt.

**Deine eigene Aufnahme zählt mit.** Wenn der Wächter eine Figur nur mäßig
erkannt hat und ihr von Hand nachhelft, gehört das zur selben Figur und
landet in derselben Zeile. Dafür ist mehr Zeit als beim Wächter: Der nimmt
25 Sekunden, von Hand sind es drei Minuten — Fenster weg, Rahmen ziehen,
überlegen, das dauert. Ein **⏱** bleibt an der Zeile stehen, sobald eine der
Ansichten vom Wächter kam.

**Die letzten 20 Zeilen überstehen das Schließen.** Beim nächsten Start stehen
sie unter einem Strich:

```
17:02  sw0332 74 %
── vorige Sitzung vom 08.08. ──
22:41  sw0417 79 % · sw0417a 70 %  ×3
```

Der Strich ist kein Zierrat: In den Zeilen steht nur die Uhrzeit, und ohne ihn
sähe „22:41" von gestern aus wie von eben. Der Rücksprung funktioniert auch
dort — **nur die Aufnahme fehlt**, denn ein Bildschirmausschnitt hat auf der
Platte nichts verloren. Statt ihrer steht „Aufnahme nicht mehr da", und
„📋 Zwischenablage" ist für diese Zeilen aus.

### Zurückspringen

**Ein Klick auf eine Verlaufszeile holt den ganzen Stand von damals zurück** –
die Trefferliste, die Variante, die ihr ausgesucht hattet, und die Aufnahme.
Im Stream geht es schnell: Man scannt weiter, während der Verkäufer redet,
und merkt zwei Figuren später, dass die vorletzte doch auf die Liste sollte.
Bisher war sie weg, die Aufnahme besonders – die gibt es kein zweites Mal.

Danach tun die drei Knöpfe genau das, was sie damals getan hätten, und
„📷 Foto mitspeichern" hängt **die Aufnahme von damals** an den Artikel, nicht
die letzte. In der Statuszeile steht dabei, wo du bist:

```
↩ Stand von 22:37 – Buchen legt diesen Treffer an.
```

Der Weg zurück ist derselbe: Der aktuelle Scan steht ja selbst als oberste
Zeile im Verlauf. Und **„habt ihr schon" wird frisch geholt** – zwischen dem
Scan und dem Rücksprung kann die Figur in der Sammlung gelandet sein,
womöglich durch den Klick direkt danach. Auf alte Zahlen zu schauen, hieße
sie ein zweites Mal zu kaufen.

**Blasse Zeilen führen nirgendwohin** – das sind Buchungen, Fehler und
angelegte Listen, keine Scans. Und der Verlauf reicht 200 Zeilen weit, die
**Aufnahmen** aber nur die letzten 30: Ein Ausschnitt wiegt schnell ein halbes
Megabyte, und 200 davon im Speicher zu halten wäre ein schlechter Tausch für
Zeilen, zu denen niemand mehr zurückspringt. Ältere zeigen die Karte dann
ohne das Bild.

**↻ neben der Listenauswahl** holt die Einkaufslisten neu – wer in der App
eine anlegt, bekommt sie hier ohne Neustart. Die gerade gewählte Liste
bleibt dabei stehen, sofern es sie noch gibt: Sonst spränge die Auswahl
mitten im Abarbeiten auf eine andere.

**＋ Liste** legt eine neue an, ohne dass ihr in die App wechseln müsst. Genau
das ist im Stream der Engpass: Man kauft bei jemand Neuem, hat keine Liste
dafür, und bis eine angelegt ist, ist der Artikel weg. Im Namensfeld steht
schon das heutige Datum, so wie deine Listen ohnehin heißen („Flohmarkt 04.08.") –
davor nur noch den Verkäufer tippen. Die neue Liste ist danach gleich
ausgewählt.

**📷 Foto mitspeichern** (Haken, standardmäßig an) – landet der Treffer in
Sammlung, Wunschliste oder auf einer Liste, wird der Ausschnitt zusätzlich als
**eigenes Foto** an den Artikel gehängt. Das ist dieselbe Funktion wie das
Kästchen über den Scan-Treffern in der App: Das Katalogbild bleibt, dein Foto
kommt in der Galerie daneben.

**Einmal je Artikel und Aufnahme, nicht je Buchung.** Wer dieselbe Figur erst
in die Sammlung und dann auf eine Liste legt, bekam sonst zweimal dasselbe
Bild in die Galerie. Im Verlauf steht dann „(Foto hängt schon dran)". Eine
**neue** Aufnahme derselben Figur kommt sehr wohl dazu – dann habt ihr ja
bewusst noch einmal fotografiert.

### Bei mehreren Ansichten sucht ihr aus

Kam die Figur aus mehreren Winkeln, stehen alle Aufnahmen als Daumennägel
unter den Bildern:

```
✓ wird angehängt (2 von 3):
 [ 1 ]  [✓2 ]  [✓3 ]
```

**Grüner Rand und ✓ in der Ecke sind zusammen *eine* Markierung, nicht zwei:**
dieses Bild wandert beim Buchen in die Galerie. Das Häkchen liegt über dem
Bild, weil eine Randfarbe allein in einer Reihe aus sechs Daumennägeln
untergeht – im Stream schaut man nicht zweimal hin. Darüber steht in Worten,
wie viele es gerade sind.

Ein Klick zeigt die Ansicht groß **und** schaltet sie an oder ab – zwei Dinge
auf einen Klick, weil jeder zusätzliche Handgriff einer zu viel ist. Mehrere
dürfen es sein, keines auch; dann kommt kein Foto mit.

Es werden **sechs** Aufnahmen je Figur gehalten – so viele, wie nebeneinander
passen. Kommt eine siebte, fliegt die älteste **nicht ausgesuchte** heraus;
was ihr angehakt habt, bleibt.

Vorgewählt ist die Ansicht, in der die oberste Figur am deutlichsten zu sehen
war – aus ihr stammt die beste Trefferquote. Welche wirklich die schönste ist,
sieht man selbst; der Rechner nicht.

Im Verlauf steht danach „(mit 2 Fotos)". Bei nur einer Aufnahme bleibt die
Reihe weg – sie wäre eine Auswahl ohne Wahl.

## Der andere Weg: in der App weitermachen

Wer den gewohnten Ablauf der App lieber mag, nimmt **📋 Bild in die
Zwischenablage**. Danach in der App ins Scannen-Feld klicken und **⌘V** –
von da an läuft alles wie immer, mit allen Knöpfen, dem Kästchen fürs eigene
Foto und der Reihum-Suche bei mehreren Figuren.

Dafür braucht die App nichts Neues zu können: Einfügen mit ⌘V beherrscht ihr
Scannen-Feld ohnehin. Das Werkzeug spart dir nur das Bildschirmfoto, den
Finder und das Ziehen.

## Von selbst auslösen

**⏱ Von selbst auslösen** – der Haken unter den Bereichsknöpfen. Ist er gesetzt, schaut der Scanner dem gemerkten Bereich zu
und schickt den Ausschnitt, sobald dort eine neue Figur hochgehalten wird.
Du musst nichts mehr drücken.

Das ist nicht nur bequemer, es trifft auch besser: Ausgelöst wird erst, wenn
das Bild **still steht**. Von Hand drückt man, wenn man die Figur sieht – und
das ist oft, während sie noch bewegt wird. Bewegungsunschärfe kostet mehr
Treffer als schlechtes Licht.

```
⏱ still  ·  Bewegung 0.4  ·  3 Anfragen in der Minute
```

Diese Zeile sagt jederzeit, was der Wächter sieht. **Empfindlichkeit** direkt
hinter dem Haken (hoch · mittel · niedrig) stellt ein – blass, solange der
Haken aus ist, denn nur dafür gilt sie –, ab wann eine Änderung eine ist – ein Bildschirmabzug ist
pixelgenau, ein Videobild rauscht immer ein wenig. Steht in der Zeile dauernd
Bewegung, obwohl nichts passiert: eine Stufe unempfindlicher. Reagiert er auf
neue Figuren nicht: eine Stufe empfindlicher.

Im Verlauf tragen die selbst geholten Zeilen ein **⏱** vorneweg – so seht ihr
hinterher, was der Wächter getan hat und was ihr selbst ausgelöst habt.

> **Das Fenster darf nicht über dem Bereich liegen.** Es wird beim
> automatischen Auslösen nicht weggeblendet – sonst flackerte es alle paar
> Sekunden –, und dann fotografierte der Scanner sich selbst. Er prüft das
> beim Einschalten und sagt es, statt dir eine Reihe sinnloser Erkennungen
> zu bescheren.

**Gebucht wird nie von selbst.** In Sammlung, Wunschliste oder auf eine Liste
kommt nur, was du anklickst. Der Wächter nimmt dir das Drücken ab, nicht das
Entscheiden.

## Es überschwemmt die Erkennung nicht

**Ein Auslöser = eine Anfrage**, auch mit Automatik. Die Erkennung dahinter
(Brickognize) wird kostenlos bereitgestellt, und ein Videostream hätte 25
Bilder je Sekunde, von denen 24 dasselbe zeigen. Deine Instanz bremst
zusätzlich bei 40 Erkennungen je Minute.

Deshalb verlässt beim Zuschauen **kein einziges Bild diesen Rechner**.
Verglichen wird hier: Der Ausschnitt wird auf 24 × 24 Punkte eingedampft und
mit dem vorigen verglichen. Erst wenn sich etwas geändert hat, das Bild
danach still steht und nicht dasselbe zeigt wie beim letzten Mal, geht eine
Anfrage hinaus – höchstens zwölf je Minute und nie zwei binnen drei Sekunden.
Das sind weniger, als ein Mensch auslöst, der im Zweifel zweimal drückt.

## Nummer von Hand nachtragen

Unter der Trefferliste steht immer ein Feld:

```
✎ Nr. nachtragen: [ sw0402 ]  [Suchen]   z. B. sw0402, 75192, 3001
```

Das reicht oft schneller zum Ziel als ein zweiter Versuch — die Nummer wird in
vielen Streams angesagt oder eingeblendet. Danach ist alles wie bei einem
erkannten Treffer: Katalogbild, Preise, „habt ihr schon", die drei Knöpfe.
Auch dein Ausschnitt bleibt stehen, das mitgespeicherte Foto hängt also an der
richtigen Figur.

**Es kommt zu den Vorschlägen dazu, es ersetzt sie nicht.** Der häufigere Fall
ist nämlich nicht „gar nichts erkannt", sondern „etwas erkannt, aber das
Falsche": Steht die Figur auf einem runden Ständer, erkennt die Erkennung gern
den Ständer.

```
     62 %  11833 [Teil]  ·  Plate, Round 4 x 4 with 2 x 2 Round Open Center
     59 %  60474 [Teil]  ·  Plate, Round 4 x 4 with Hole
 ✎         sw0011        ·  Chewbacca
```

Die nachgetragene Zeile ist gleich ausgewählt und trägt ein **✎** statt einer
Trefferquote — geraten hat da ja niemand. Die Vorschläge bleiben stehen, falls
du dich vertippt hast, und im Verlauf steht eine eigene Zeile, die zu genau
diesem Stand zurückführt.

Das Feld stand früher **nur** da, wenn gar nichts erkannt wurde. Solange
nichts erkannt wird, springt der Eingabestrich weiterhin von selbst hinein —
außer der Wächter hat ausgelöst, denn dann tippt ihr vielleicht gerade einen
Preis.

**Geraten wird nicht.** `3001` ist bei BrickLink sowohl das Set *Propeller
Buggy* als auch der Stein *2 × 4*. Deshalb werden Figur, Set und Teil
nachgeschlagen und alle Treffer zur Auswahl gestellt, mit der Art dahinter:

```
100 %  3001-1 [Set]   ·  Propeller Buggy
100 %  3001 [Teil]    ·  Brick 2 x 4
```

Bei erkannten Vorschlägen steht die Art nicht dabei — das sind fast immer
Figuren, da wäre es nur Ballast.

## Wenn der Verkäufer die Figur dreht

Viele drehen die Figur in der Hand, manche stellen sie auf eine **Drehscheibe**.
Beides sah der Scanner früher als lauter einzelne Begegnungen — und auf einer
Drehscheibe löste er überhaupt nicht aus, weil er auf Stillstand wartete, der
nie kam. Zwei Dinge greifen jetzt ineinander.

### Er löst auch aus, während sich etwas dreht

Bewegt sich das Bild lange gleichmäßig weiter, ohne je stillzustehen, dann
dreht sich offenbar etwas — und dann wird mittendrin geschickt, statt ewig zu
warten. In der Wächterzeile steht dabei *dreht sich* statt *still*.

Ein **Sprung** gilt weiterhin nicht als Drehen: Wenn jemand ins Bild greift
oder etwas Neues hinstellt, ändert sich zu viel auf einmal. Genau daran
erkennt der Scanner den Artikelwechsel — und fängt an, für den neuen Artikel
Ansichten zu sammeln.

Höchstens **vier Ansichten je Artikel**. Danach ist Ruhe, bis der nächste
Artikel kommt. Eine Drehscheibe würde sonst endlos Anfragen erzeugen.

> **Bewegung ist nicht gleich Drehung.** Der Wächter kann eine Drehscheibe
> nicht von irgendetwas anderem unterscheiden, das sich anhaltend bewegt –
> eine Laufschrift, ein Countdown, ein scrollender Chat im gemerkten Bereich
> sehen für ihn genauso aus. Deshalb gibt er auf: **Waren drei Anfragen
> hintereinander ergebnislos, hört der Dreh-Auslöser auf.** Wo dreimal nichts
> zu erkennen war, bringt ein viertes Bild desselben Flecks auch nichts. In
> der Wächterzeile steht dann, worauf er wartet.
>
> Es geht von selbst weiter, sobald sich wirklich etwas ändert: Ein Sprung im
> Bild gilt als neuer Artikel und gibt ihm eine neue Chance. Und **der
> Stillstand-Auslöser bleibt die ganze Zeit scharf** – wer die Figur ruhig
> hält, bekommt seinen Versuch, sonst wäre der Bereich für den Rest des
> Abends tot.

### Die Ansichten werden zu einer Trefferliste vereint

Das ist der eigentliche Gewinn. Drei Ansichten sind drei Erkennungsversuche
derselben Figur, und die Erkennung antwortet aus jedem Winkel etwas anderes.
Statt die vorige Antwort wegzuwerfen, kommt alles in **eine** Liste:

```
    78 %  sw0417   ·  Mace Windu  (2×)
    64 %  11833 [Teil]  ·  Ständer
    55 %  sw0056   ·  Mace Windu Ep2
```

Was mehrfach gefunden wurde, steht oben — und das **(2×)** ist die
verlässlichere Zahl als die Trefferquote daneben. Eine Figur, die aus zwei
Winkeln mit 62 % und 58 % kommt, ist mit sehr viel höherer Wahrscheinlichkeit
die richtige als eine, die einmal mit 83 % aufblitzt und danach nie wieder.
Von der Trefferquote bleibt die beste stehen.

Als Aufnahme bleibt die Ansicht stehen, in der die oberste Figur am
deutlichsten zu sehen war — aus ihr stammt die beste Quote, und sie ist es,
die später als Foto am Artikel hängt.

### Was ihr gewählt habt, bleibt gewählt

**Eine neue Ansicht reißt die Auswahl nicht weg.** Habt ihr auf die zweite
Variante geklickt, bleibt sie ausgewählt, auch wenn die Sortierung sich
ändert. Das ist keine Bequemlichkeit, sondern Sicherheit: Sonst drehte sich
die Scheibe genau in dem Moment weiter, in dem ihr auf „＋ Zur Sammlung" zielt,
und der Klick legte etwas anderes an.

Ebenso bleibt es **still**: Ein Wunsch klingt nur, wenn er **neu**
hinzukommt. War er schon in der ersten Ansicht dabei, habt ihr ihn längst
gehört; taucht er erst in der dritten auf, klingt es dann.

> **Sicher unterscheiden lässt sich das nicht.** Zwei verschiedene Figuren auf
> demselben Ständer haben denselben Ständer in den Vorschlägen, und dann hält
> der Scanner sie für eine. Schlimm ist das nicht: Es wird **nichts
> verworfen**, die Liste wird nur länger, und die getroffene Auswahl bleibt
> stehen. Nach 25 Sekunden ohne Nachschub gilt der nächste Scan ohnehin als
> neuer Artikel.

## 🧍 Nur Figuren

Der Haken neben den anderen beiden. Ist er gesetzt, kommen **nur Minifiguren**
in die Trefferliste; Sets und Teile werden aussortiert. Bei einem
Figuren-Stream ist das der halbe Ärger weniger — die Erkennung greift sonst
gern nach dem Ständer, dem Sockel oder der Platte in der Hand.

Wird dabei alles aussortiert, steht das auch da:

```
Keine Figur darunter – alle 2 Vorschläge waren Sets oder Teile.
Haken »Nur Figuren« aus, oder die Nummer eintippen.
```

Wichtig, denn „Nichts erkannt" wäre gelogen — man suchte den Fehler beim
Rahmen statt beim Haken.

**Für getippte Nummern gilt er nicht.** Wer eine Setnummer eintippt, meint das
Set; der Haken ist gegen Fehlerkennungen da, nicht gegen deinen eigenen Willen.
Und für ältere Verlaufszeilen gilt er auch nicht rückwirkend — was einmal in
der Liste stand, bleibt beim Zurückspringen auffindbar.

## Wenn die Erkennung das Falsche findet

Sie sucht **ein** Objekt im Bild und entscheidet sich für das größte oder
deutlichste. Steht die Figur auf einem Ständer oder einer Platte, ist das oft
nicht die Figur. Drei Wege aus der Lage, in dieser Reihenfolge:

0. **[🧍 Nur Figuren](#-nur-figuren)** ankreuzen, wenn ohnehin nur Figuren
   kommen – dann fällt der Ständer von selbst weg.
1. **Enger rahmen** und noch einmal auslösen – nur die Figur, nicht die halbe
   Auslage.
2. **[Nummer nachtragen](#nummer-von-hand-nachtragen)**, wenn sie angesagt oder
   eingeblendet wird. Der kürzeste Weg.
3. **📋 Bild in die Zwischenablage** und in der App weitermachen, wo die
   Reihum-Suche mehrere Figuren im selben Bild durchgeht.

## Wenn nichts erkannt wird

Dieselben Regeln wie beim Scannen in der App: Die Erkennung sucht **ein**
Objekt im Bild. Rahmt also eine Figur, nicht die halbe Auslage – und zieht
den Rahmen erst, wenn die Figur einen Moment still gehalten wird.
Bewegungsunschärfe kostet mehr Treffer als schlechtes Licht.

## Was liegen bleibt – und was nicht

**Kein Bild wird gespeichert.** Die Aufnahmen im Verlauf liegen nur im
Arbeitsspeicher, und auch dort nur die letzten 30; mit dem Schließen des
Fensters sind sie weg.

Die **Zeilen** des Verlaufs überleben dagegen – die letzten 20, in
`~/.brickfolio-livescan-verlauf.json` (0600). Darin stehen Uhrzeit,
Katalognummern, Namen und Trefferquoten, also dasselbe, was im Fenster zu
lesen ist. Wer das nicht will, löscht die Datei; das Programm legt sie beim
nächsten Beenden neu an und kommt ohne sie einwandfrei zurecht.

Zwischendurch entstehen Dateien – anders geht es nicht, `screencapture` und
`sips` arbeiten auf der Platte. Jede davon wird sofort nach Gebrauch wieder
gelöscht, auch wenn dabei etwas schiefgeht. Beim Zuschauen sind das drei
Dateien je Takt, und keine überlebt ihn.

Nur bei einem **harten Abbruch** – Absturz, „Sofort beenden", Abmelden mitten
im Takt – bleibt genau der gerade laufende Abzug liegen. Deshalb räumt das
Programm beim Start seine eigenen Reste weg, sofern sie älter als eine Stunde
sind. Die Stunde schützt ein zweites, gleichzeitig laufendes Fenster.

Auf der Platte bleibt damit nur:

| | |
|---|---|
| `~/.brickfolio-livescan.json` | Adresse, Benutzername, **Token** (nicht das Passwort), gemerkter Bereich, Zustand, Empfindlichkeit, Haken. Nur für dich lesbar (0600). |
| `~/.brickfolio-livescan-verlauf.json` | die letzten 20 Verlaufszeilen – Uhrzeit, Nummern, Namen, Trefferquoten. **Keine Bilder.** Ebenfalls 0600. |
| deine Instanz | die Fotos, die du mit **📷 Foto am Artikel mitspeichern** bewusst an einen Artikel gehängt hast |

## Prüfen, ob noch alles stimmt

```bash
/opt/homebrew/bin/python3 /Users/nutzer/dev/brickfolio-livescan/pruefung.py
```

Über hundert Proben am **verborgenen** Fenster: kein Bildschirmfoto, keine
Anfrage an die Instanz, keine Änderung an deinen Einstellungen. Statt der
Instanz steht eine Attrappe, statt der Bildschirmabzüge ein Drehbuch. Läuft in
ein paar Sekunden durch und sagt am Ende, was durchgefallen ist.

## Lizenz

MIT, wie Brickfolio selbst.

## Neue Fassungen — der Scanner erneuert sich selbst

Beim Start fragt der Scanner einmal im Hintergrund bei GitHub nach, ob es
eine neuere Fassung gibt. Nur wenn es eine gibt, erscheint unten rechts
eine Zeile. Gibt es nichts Neues, ändert sich am Bild nichts.

**Gefragt wird die Release-Seite, nicht die GitHub-API** (seit 1.9.2).
Die API erlaubt ohne Anmeldung nur 60 Abfragen je Stunde – für den ganzen
Internetanschluss, also alle Geräte dahinter zusammen. War das aufgebraucht,
blieb der Hinweis einfach aus. `…/releases/latest` leitet dagegen auf die
neueste Fassung weiter und zählt nicht mit; ob das Paket schon dranhängt,
verrät die Download-Adresse, ohne dass es geladen wird.

Ein Klick darauf öffnet ein kleines Fenster mit **Jetzt aktualisieren**.
Der Scanner holt das Paket dann selbst, packt es aus, prüft es und tauscht
sich aus; danach startet er neu. Ein Klick, sonst nichts.

**Warum nicht einfach die Seite aufmachen?** Weil das auf dem Mac in einer
Sackgasse endet. Der Browser hängt jedem Download das Quarantäne-Merkmal
an, und an dem verweigert macOS den Start:

> „Apple konnte nicht überprüfen, ob »Brickfolio Live-Scanner« frei von
> Schadsoftware ist" — mit den Knöpfen *In den Papierkorb legen* und
> *Fertig*, aber ohne einen zum Freigeben.

Holt das Programm die Datei dagegen selbst, entsteht das Merkmal gar nicht
erst — nachgemessen hängt am selbst geladenen Paket nur
`com.apple.provenance`. Der Weg über die Seite steht im Fenster trotzdem
daneben, für den Fall, dass hier etwas klemmt.

**Eingespielt wird nur, was von uns kommt.** Vor dem Tausch vergleicht der
Scanner das Kennmal des Pakets — die *designated requirement*, in der
unser Zertifikat steht — mit seinem eigenen. Weicht es ab oder fehlt die
Signatur, bleibt alles, wie es war. Unter Windows ist nichts signiert; dort
bleibt es bei HTTPS zu GitHub, also derselben Sicherheit wie beim Laden von
Hand.

**Den letzten Schritt macht ein Helfer.** Ein laufendes Programm kann sich
nicht selbst ersetzen: Unter Windows ist die eigene Datei gesperrt, auf dem
Mac zöge man dem eigenen Prozess den Boden weg. Also schreibt der Scanner
ein kurzes Skript, das wartet, bis er beendet ist, tauscht und ihn neu
startet. Misslingt der Tausch, kommt die alte Fassung zurück — lieber die
alte als gar keine.

Aus dem Quelltext gestartet fehlt der Knopf, und im Fenster steht, warum:
Da gibt es nichts zu ersetzen, das macht `git`.

Bei jedem Problem — kein Netz, GitHub ausgelastet — **schweigt** die
Abfrage. Ein Werkzeug für Auktions-Streams hat nicht mit Fehlern über sich
selbst zu stören.

Wer gar nicht gefragt werden will, trägt in `~/.brickfolio-livescan.json`
ein:

    "updates_pruefen": false

## Mit mehreren Bildschirmen

Beide Systeme nehmen den Rahmen über **alle** Bildschirme auf. Läuft der
Stream auf dem zweiten Monitor, lässt er sich genauso einrahmen und
merken wie auf dem ersten.

Gerechnet wird mit dem Ursprung des Gesamtbilds: Ein Monitor **links** oder
**über** dem Hauptbildschirm hat negative Koordinaten. Und mit Kommazahlen,
denn Bildschirmskalierung ist selten eine ganze Zahl.

> Auf dem Mac wird dafür der Finder nach den Gesamtmaßen gefragt. Beim
> ersten Mal fragt macOS nach der Erlaubnis dafür. Wer sie verweigert,
> bekommt weiterhin nur den Hauptbildschirm zu sehen — alles andere
> funktioniert unverändert.

## Wenn die Instanz hinter Cloudflare Access steht

Dann kommt auf jede Anfrage eine **Anmeldeseite** statt Daten. Die kann
dieses Werkzeug nicht ausfüllen – es liest ja kein Postfach und tippt
keinen Zugangscode ab. Der Scanner erkennt das und sagt es beim Namen,
statt „Unerwartete Antwort der Instanz" zu melden.

Zwei Wege hindurch. Im Heimnetz braucht es **keinen** davon: Wer die
Instanz direkt über ihre lokale Adresse erreicht, kommt an Cloudflare
ohnehin vorbei.

### Weg 1: Dienst-Token — für fremde Rechner

Eine **zusätzliche** Richtlinie neben der bestehenden. Wer sich im Browser
mit E-Mail und Zugangscode anmeldet, merkt davon nichts.

1. In **Cloudflare Zero Trust → Access → Service Auth → Service Tokens**
   einen Token anlegen. Client-ID und Client-Secret erscheinen **einmal** –
   das Secret gibt es später nicht wieder zu sehen.
2. Bei der Anwendung (`brickfolio.example`) unter **Policies** eine neue
   anlegen: Aktion **Service Auth**, Bedingung **Service Token** → der eben
   erzeugte. Die vorhandene E-Mail-Richtlinie bleibt daneben stehen.
3. Im Scanner unter **Zugang …** beide Werte eintragen.

Braucht keine zusätzliche Software, läuft nicht ab, funktioniert auch
unter Windows. Der Preis: Ein langlebiges Geheimnis liegt in
`~/.brickfolio-livescan.json` – so wie der Instanz-Token auch.

### Weg 2: der Knopf im Zugangsfenster — ohne neue Richtlinie

Unter **Zugang …** steht **🌐 Über Cloudflare anmelden …**. Ein Klick, der
Browser öffnet sich, du meldest dich **wie gewohnt** mit E-Mail und
Zugangscode an — fertig. Danach auf *Anmelden*.

**`cloudflared` reist im Paket mit** – es ist nichts nachzuinstallieren.
Der Scanner sucht zuerst die mitgelieferte Fassung, dann eine selbst
installierte an den üblichen Orten.

> Das war nicht immer so. Zuerst wurde nur der Suchpfad befragt – und ein
> Programm aus dem Programme-Ordner erbt nicht die Pfade der Shell.
> `/opt/homebrew/bin` steht dort nicht drin, und `cloudflared` galt als
> nicht installiert, obwohl es lag.

Von Hand ginge es auch:

    cloudflared access login https://brickfolio.example

Der Scanner glaubt der Rückmeldung von `cloudflared` dabei **nicht**
ungeprüft: Er sieht hinterher nach, ob wirklich eine Sitzung entstanden
ist, und meldet nur dann Erfolg. Danach findet der Scanner die Sitzung von selbst und
schickt sie mit; er fragt `cloudflared` höchstens alle zehn Minuten
erneut, damit nicht bei jedem Bild ein Programm startet.

Dafür muss `cloudflared` auf jedem Rechner liegen, und die Sitzung läuft
nach der in Cloudflare eingestellten Dauer ab – dann ist die Anmeldung zu
wiederholen.

**Liegt beides vor, gewinnt der Dienst-Token**, weil er nicht abläuft.

### Noch etwas: der Scanner sagt jetzt, wer er ist

Ohne eigene Kennung schickt Python `Python-urllib/3.x`, und Cloudflares
Bot-Schutz weist das ab – noch bevor Access überhaupt zum Zuge kommt
(„The site owner has blocked access based on your browser's signature").
Der Scanner meldet sich deshalb als `Brickfolio-Live-Scanner/<Fassung>`.

## Einbauen unter Windows

Unter [Releases](https://github.com/Melle79/brickfolio-livescan/releases)
liegt neben dem Mac-Paket ein
`Brickfolio-Live-Scanner-Windows-x64.zip`. Entpacken, den Ordner ablegen,
wo er bleiben soll, und `Brickfolio Live-Scanner.exe` starten.

**Beim ersten Start warnt SmartScreen** („Der Computer wurde durch
Windows geschützt"). Das Programm ist nicht signiert – dafür bräuchte es
ein Zertifikat, das Geld kostet. Auf **Weitere Informationen** klicken,
dann **Trotzdem ausführen**. Danach kommt die Warnung nicht wieder.

Es braucht **keine** Berechtigung für Bildschirmaufnahmen – anders als
auf dem Mac fragt Windows danach nicht.

### Was dort anders ist

| | macOS | Windows |
|---|---|---|
| Rahmen ziehen | Apples eigene Auswahl, wie ⌘⇧4 | Abbild des Bildschirms, Rahmen mit der Maus |
| Ton | Klang aus dem System | Systemklang |
| Bildarbeit | `sips`, im System enthalten | Pillow, im Paket enthalten |

Der Rahmen fühlt sich also etwas anders an: Statt eines durchsichtigen
Auswahlfelds erscheint ein Fenster mit einem Abbild des Bildschirms, und
darin zieht man. Es ist derselbe Weg, den auch der Mac bei „Bereich
merken" nimmt.

**Zur Bildschirmskalierung.** Der Scanner meldet sich bei Windows als
**DPI-bewusst** an. Das klingt nach Kleinkram, ist aber die Grundlage
dafür, dass der Rahmen trifft: Ohne diese Anmeldung liefert Windows
*logische* Maße, während die Bildschirmaufnahme *echte* Bildpunkte
liefert. Bei einem Bildschirm fällt das kaum auf; bei zweien mit
unterschiedlicher Skalierung geht die eine Achse auf und die andere nicht.

Gerechnet wird deshalb mit Kommazahlen (125 %, 150 %, 175 % sind keine
ganzen Zahlen), über **alle** Bildschirme, und mit dem Ursprung des
Desktops – ein Monitor links oder über dem ersten hat negative
Koordinaten.

Im Auswahlfenster stehen die Zahlen, mit denen gerechnet wird: Abbild,
Desktopmaße, Vorschau, beide Faktoren, die Lage der Bildschirme und
welcher DPI-Weg gegriffen hat. Wenn etwas nicht trifft, ist das der
Anfang jeder Fehlersuche.

## Einbauen auf dem Mac

Unter [Releases](https://github.com/Melle79/brickfolio-livescan/releases)
liegt bei jeder Fassung ein ZIP. Die App bringt Python und Tk selbst mit,
es muss nichts weiter installiert sein.

> **Nur beim ersten Mal.** Ab Fassung 1.7.0 erneuert sich der Scanner
> selbst — siehe [Neue Fassungen](#neue-fassungen--der-scanner-erneuert-sich-selbst).
> Der Weg hier ist der für den Anfang und für den Fall, dass etwas klemmt.

### Der bequeme Weg: am Terminal laden

    gh release download --repo Melle79/brickfolio-livescan \
        --pattern '*.zip' --clobber --dir /tmp/bfls
    ditto -x -k /tmp/bfls/*.zip /tmp/bfls/neu
    rm -rf "/Applications/Brickfolio Live-Scanner.app"
    mv "/tmp/bfls/neu/Brickfolio Live-Scanner.app" /Applications/

**Die Reihenfolge ist Absicht.** Erst auspacken, dann die alte Fassung
weg, dann hinüberschieben. Andersherum – löschen und danach auspacken –
steht man ohne App da, wenn das Auspacken schiefgeht. Genau das ist am
30.08.2026 passiert.

Danach startet sie **ohne jede Nachfrage**. Der Grund ist unscheinbar,
aber der ganze Unterschied: Das Quarantäne-Merkmal, an dem sich macOS
stört, setzt weder GitHub noch die Datei – es setzt der **Browser** beim
Herunterladen. `gh` und `curl` tun das nicht, also entsteht es nie.

Nachgemessen: Am Browser-Download hängt `com.apple.quarantine`, am
Terminal-Download nur ein harmloses `com.apple.provenance`. `spctl`
verweigert die App zwar in beiden Fällen (sie ist nicht notarisiert),
aber dieses Urteil wird nur bei Dateien *mit* Quarantäne-Merkmal
vollstreckt.

Das gilt auch für jede spätere Fassung, die über den Browser käme – der
Dialog erschiene jedes Mal wieder. Genau deshalb lädt der Scanner seine
Aktualisierungen inzwischen **selbst**: Was das Programm holt, trägt kein
Quarantäne-Merkmal, und die Sperre kommt gar nicht erst.

### Über den Browser

Herunterladen, entpacken, die App nach **Programme** ziehen. Dann greift
die Sperre, siehe unten.

**Beim allerersten Start** blockt macOS ab: „Apple konnte nicht überprüfen,
ob *Brickfolio Live-Scanner* frei von Schadsoftware ist", mit den Knöpfen
*In den Papierkorb legen* und *Fertig*. Das ist zu erwarten – die App ist
nicht bei Apple notarisiert, das setzt ein Entwicklerkonto für 99 €/Jahr
voraus. Es ist ein Preisschild, kein Fehler.

**Nicht** in den Papierkorb legen, sondern **Fertig** klicken. Dann:

**Systemeinstellungen → Datenschutz & Sicherheit** → ganz nach unten
scrollen. Dort steht jetzt eine Zeile mit **Dennoch öffnen**. Der Knopf
erscheint nur, wenn man es vorher einmal versucht hat.

Oder in einem Rutsch im Terminal:

    xattr -dr com.apple.quarantine "/Applications/Brickfolio Live-Scanner.app"

**Rechtsklick → Öffnen hilft hier nicht.** Das war bis macOS 14 der Weg;
seit macOS 15 hat Apple diese Abkürzung für genau diesen Dialog
abgeschafft. Anleitungen im Netz, die es noch empfehlen, sind veraltet.

Wer die App **selbst baut** (siehe unten), sieht davon gar nichts: Die
Quarantäne hängt am Download, nicht an der App.

Die App ist für **Apple Silicon** gebaut (M1 und neuer). Auf Intel-Macs
läuft sie nicht; dort startet man `livescan.py` von Hand.

### Beim ersten Start
Der Scanner fragt nach der Adresse deiner Brickfolio-Instanz und einem
Token. Beides landet in `~/.brickfolio-livescan.json` – im Benutzerordner,
nicht in der App. Ein Austausch der App lässt die Anmeldung also stehen.

macOS fragt außerdem einmal nach der **Bildschirmaufnahme**
(Systemeinstellungen → Datenschutz). Ohne diese Freigabe kommt statt des
Ausschnitts ein schwarzes Bild.

## Selbst bauen

    python3 -m venv .venv-bau
    .venv-bau/bin/python -m pip install py2app
    sh bauen.sh

Danach liegt `dist/Brickfolio Live-Scanner.app`.

### Warum örtlich gebaut besser ist

`bauen.sh` unterschreibt mit dem selbst ausgestellten Zertifikat
**Brickfolio Selbstsigniert** aus dem Anmeldeschlüsselbund. Das klingt
nach Formalie, entscheidet aber darüber, ob die Freigabe für die
**Bildschirmaufnahme** ein Update überlebt:

| Unterschrift | Woran macOS die App wiedererkennt |
|---|---|
| ad hoc | `cdhash H"…"` – der Fingerabdruck, **neu bei jedem Bau** |
| Zertifikat | `identifier … and certificate root = H"…"` – **bleibt** |

Ist sie ad hoc unterschrieben, hält macOS jede neue Fassung für eine
fremde App. Der Eintrag in *Datenschutz & Sicherheit* bleibt stehen,
gehört aber zu nichts mehr, und Umschalten bewirkt nichts. Man muss dann
jedes Mal aufräumen:

    tccutil reset ScreenCapture cc.brickfolio.livescan

**Der Bau-Runner hat den privaten Schlüssel nicht** und unterschreibt
deshalb ad hoc. Das ZIP am Release wird daher örtlich gebaut und
hochgeladen; der Runner prüft weiterhin jeden Stand.

Gegen die Gatekeeper-Sperre beim Herunterladen hilft das Zertifikat
**nicht** – dafür bräuchte es ein Apple-Entwicklerkonto (99 €/Jahr).

### Das Zertifikat neu anlegen

Falls es einmal fehlt – `bauen.sh` fällt dann auf ad hoc zurück und sagt
es auch:

    openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
        -keyout schluessel.pem -out zert.pem \
        -subj "/CN=Brickfolio Selbstsigniert/O=Melle79" \
        -addext "basicConstraints=critical,CA:false" \
        -addext "keyUsage=critical,digitalSignature" \
        -addext "extendedKeyUsage=critical,codeSigning"
    security import zert.pem -k ~/Library/Keychains/login.keychain-db
    security import schluessel.pem -k ~/Library/Keychains/login.keychain-db \
        -T /usr/bin/codesign

Und dann – **dieser Schritt ist der entscheidende**:

    security add-trusted-cert -r trustRoot -p codeSign \
        -k ~/Library/Keychains/login.keychain-db zert.pem

> ⚠️ **Nicht weglassen, auch wenn `codesign` ohne ihn funktioniert.**
> Genau daran bin ich am 30.08.2026 gescheitert: Ich hatte geprüft, dass
> `codesign` das Zertifikat zum *Unterschreiben* nimmt, und daraus
> geschlossen, das Vertrauen sei entbehrlich. Zum Unterschreiben ist es
> das auch. Aber macOS merkt sich die Freigabe für die Bildschirmaufnahme
> als Anforderung an die **Zertifikatskette** – und die lässt sich ohne
> Vertrauen nicht bestätigen. Die Freigabe hielt deshalb überhaupt nicht
> mehr, schlechter als mit ad hoc.
>
> Die Probe darauf ist `security verify-cert -c zert.pem -p codeSign`.
> Solange dort `CSSMERR_TP_NOT_TRUSTED` steht, ist es nicht getan.
> `security find-identity -v -p codesigning` muss danach
> *1 valid identities found* melden, nicht 0.

Das Vertrauen gilt nur für **deinen Benutzer** und nur für
**Codesignatur**, nicht allgemein. Die beiden `.pem`-Dateien danach
löschen – der Schlüssel liegt im Schlüsselbund. Gebraucht wird ein Python
mit brauchbarem Tk – das Python aus macOS bringt ein zu altes mit und
zeichnet nur ein weißes Fenster. Unter Homebrew: `brew install python-tk`.

## Prüfen

    python3 pruefung.py

Läuft ohne Netz und ohne Instanz; die Proben bauen echte Fenster und
räumen hinterher auf. Wer etwas ändert, lässt sie vorher und nachher
laufen – und macht die Gegenprobe: Ohne die Änderung *muss* eine Probe
fehlschlagen, sonst prüft sie nichts.

## Quellen und Rechtliches

Preise, Namen und Bilder stammen von **BrickLink** über deren offizielle
Schnittstelle, mit einem Zugang, der auf deinen Namen läuft. Die Seiten von
BrickLink werden nicht abgerufen – deren Nutzungsbedingungen erlauben das
nicht.

LEGO® ist eine Marke der LEGO Gruppe, die dieses Werkzeug weder
unterstützt noch autorisiert hat. Ebenso wenig BrickLink.

## Lizenz und Haftung

MIT – siehe [LICENSE](LICENSE). Im Klartext: Mach damit, was du willst.
Aber es ist ein Feierabendwerkzeug für den eigenen Gebrauch, keine
geprüfte Software. Es kommt **ohne jede Gewährleistung**; für Schäden,
verlorene Daten, falsche Preise oder Fehlkäufe haftet niemand. Wer damit
auf einer Auktion mitbietet, entscheidet selbst – der Scanner zeigt nur
an, was BrickLink gerade sagt, und der kann irren.
