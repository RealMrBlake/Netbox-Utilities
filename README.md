# NetBox Utilities

Plugin für **NetBox 4.6.5 bis 4.6.7** mit zehn Funktionen:

- Jeder Benutzer kann die Menüs der linken Navigation verschieben oder ausblenden.
- Ein Dropdown in der Kopfleiste setzt einen sitzungsweiten Filter für einen Mandanten oder eine Mandantengruppe.
- Optional verpflichtende Mandantenzuordnung für alle mandantenfähigen Objekte.
- Automatische Vorbelegung von Mandant und Mandantengruppe aus dem Objekt- oder Filterkontext.
- Automatische 1:1-Verknüpfung von Front- und Rearports auf Geräten mit der Rolle `Patchpanel`.
- Geräte mit optionaler Teilbreite können sich dieselbe Höheneinheit teilen.
- Die Rack-Ansicht von MrBlakes optionalem Topology-Views-Plugin stellt Teilbreitengeräte korrekt dar.
- Mehrere Bilder in einem Schritt im Bilder-Tab eines Objekts hochladen.
- Mehrere Module desselben Typs in einem Schritt in freie Modulschächte einbauen.
- Optionale Mehrfachspeicherung für verschobene Geräte aus NetBox Reorder Rack.

Die Navigationseinstellungen sind benutzerbezogen. Die aktive Mandanten- oder Gruppenauswahl wird in der jeweiligen Browser-Session gespeichert.

## Kompatibilität

- NetBox `>=4.6.5,<4.7`
- Python `>=3.12`
- optional: NetBox Reorder Rack `1.1.4`
- optional: [MrBlake NetBox Topology Views](https://git.mrblake.cc/MrBlake/mrb-netbox-topology-views) mit Rack-Ansicht

Andere NetBox-Versionen werden vom Plugin absichtlich abgelehnt, da die Anpassung der Core-Navigation von deren HTML-Struktur abhängt.

## Installation aus Gitea

Das Plugin kann direkt aus dem `main`-Branch installiert werden:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@main"
```

Für eine reproduzierbare Produktivinstallation sollte statt `main` ein
bereits veröffentlichter Release-Tag oder eine bestimmte Commit-ID verwendet
werden. `COMMIT-ID` wird dabei durch den gewünschten Stand ersetzt:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@COMMIT-ID"
```

Alternativ kann hinter dem `@` die vollständige Commit-ID stehen.

Damit das Plugin bei zukünftigen NetBox-Upgrades automatisch erneut
installiert wird, wird derselbe Eintrag in `/opt/netbox/local_requirements.txt`
hinterlegt:

```text
git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@main
```

Bei einem privaten Gitea-Repository benötigt der NetBox-Server einen
Deploy-Token oder einen SSH-Key. Für SSH lautet der Eintrag beispielsweise:

```text
git+ssh://git@git.mrblake.cc/MrBlake/Netbox-Utilities.git@main
```

### NetBox-Konfiguration

Das Plugin wird in `/opt/netbox/netbox/netbox/configuration.py` aktiviert:

```python
PLUGINS = [
    "netbox_utilities",
]

PLUGINS_CONFIG = {
    "netbox_utilities": {
        "navigation_customization_enabled": True,
        "reorder_rack_bulk_save_enabled": True,
        "topology_views_rack_width_enabled": True,
        "tenant_filter_enabled": True,
        "tenant_required": True,
    },
}
```

Wenn bereits andere Plugins eingetragen sind, wird `netbox_utilities` zu den
bestehenden Listen beziehungsweise Dictionaries hinzugefügt; deren Inhalt darf
nicht überschrieben werden.

### Installation abschließen

Migrationen und statische Dateien werden nach der Installation verarbeitet:

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_utilities
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

Alternativ erledigt das NetBox-Upgrade-Skript die Installation aus
`local_requirements.txt`, Migrationen und `collectstatic` gemeinsam:

```bash
sudo /opt/netbox/upgrade.sh
sudo systemctl restart netbox netbox-rq
```

Nach Änderungen an JavaScript oder CSS kann ein Hard-Reload des Browsers mit
`Strg+F5` erforderlich sein.

Ab Version `0.9.3` werden Rack-SVG und Reorder direkt aus allen Geräten des
Racks aufgebaut. Dadurch können mehrere Geräte derselben HE nicht mehr durch
NetBox' native Ein-Gerät-pro-HE-Darstellung verloren gehen. Die Adapter werden
auch dann eingebunden, wenn keine Teilbreitengeräte gefunden wurden. Nach
diesem Update ist `collectstatic` deshalb zwingend erforderlich;
die Dateien `topology-rack-width.js` und `reorder-rack-width.js` müssen unter
`/opt/netbox/netbox/static/netbox_utilities/` vorhanden sein.

Reorder ersetzt seine nativen Gerätekacheln erst, nachdem ein vollständiger
und zur JavaScript-Version passender Datensatz geprüft wurde. Bei einer
gemischten Installation aus altem Python-Code und neuen statischen Dateien
bleibt deshalb die native Ansicht erhalten, statt ein leeres Rack zu zeigen.
Ab Version `0.9.4` werden vorhandene Reorder-Kacheln außerdem direkt auf das
12-Spalten-Raster erweitert und nicht mehr vorsorglich neu erzeugt. Nur ein
zweites, von NetBox' Ein-Gerät-pro-HE-Darstellung unterschlagenes Gerät wird
aus den Plugin-Daten ergänzt. Das verhindert browserabhängige leere Racks.
Ab Version `0.9.5` rendert das Plugin das vollständige 12-Spalten-Rack bereits
serverseitig in die Reorder-Seite. Die sichtbaren Geräte sind dadurch nicht
mehr vom Ladezeitpunkt des Browseradapters abhängig. Für die optionale
Topology-Rack-Ansicht wird die Teilbreitengeometrie zusätzlich als
serverseitiges CSS ausgegeben; JavaScript wird dort nur noch für Exporte und
ergänzende Metadaten benötigt.
Bereits vorhandene Geräte, die dieselbe HE und Rackseite belegen, aber noch
keine Plugin-Platzierungszeile besitzen, werden in Rack-SVG, Reorder und der
Topology-Rack-Ansicht ohne Datenbankänderung gleichmäßig nebeneinander
dargestellt. Explizit gespeicherte Rackbreiten und Breitenpositionen haben
stets Vorrang vor dieser Anzeige-Ableitung.

Die Installation lässt sich anschließend mit diesen Befehlen kontrollieren:

```bash
/opt/netbox/venv/bin/python -c \
  "import netbox_utilities; print(netbox_utilities.__version__, netbox_utilities.__file__)"

test -f /opt/netbox/netbox/static/netbox_utilities/reorder-rack-width.js
test -f /opt/netbox/netbox/static/netbox_utilities/topology-rack-width.js
grep -q "schema_version !== 3" \
  /opt/netbox/netbox/static/netbox_utilities/reorder-rack-width.js

cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py shell -c \
  "from django.urls import reverse; print(reverse('dcim:rack_reorder', kwargs={'pk': 1})); print(reverse('plugins:netbox_topology_views:rack_elevation'))"
```

Die letzten beiden Routen müssen auflösbar sein. Die Topology-Rack-Route ist
im getesteten MrBlake-Develop-Stand `86a8daf45ef380d57ac73b461dbc47a16bb831ba`
enthalten, aber nicht im gleich bezeichneten öffentlichen Tag `v4.5.1`.

Für Rack `2` kann zusätzlich geprüft werden, welche gespeicherten Breiten das
Plugin findet. Zwei Geräte derselben HE dürfen dabei unterschiedliche oder
noch leere Plugin-Werte besitzen; leere Werte werden ab `0.9.3` für die
Darstellung abgeleitet:

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py shell -c "
from dcim.models import Device
print(list(Device.objects.filter(rack_id=2).order_by('position', 'id').values(
    'id', 'name', 'position', 'face',
    'netbox_utilities_rack_placement__width',
    'netbox_utilities_rack_placement__horizontal_position',
)))
"
```

## Aktualisierung

Bei einer Installation aus dem `main`-Branch wird das Paket erneut aus Gitea
installiert und anschließend NetBox aktualisiert:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@main"

cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate netbox_utilities
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
sudo systemctl restart netbox netbox-rq
```

`--force-reinstall` stellt sicher, dass Änderungen aus einem Branch auch dann
installiert werden, wenn die interne Paketversion noch nicht erhöht wurde.

Wird ein Release-Tag in `/opt/netbox/local_requirements.txt` verwendet, muss
dieser Eintrag vor dem Update auf den neuen Tag geändert werden. Danach genügt:

```bash
sudo /opt/netbox/upgrade.sh
sudo systemctl restart netbox netbox-rq
```

Vor Produktivupdates sollte der neue Stand in einer Testumgebung geprüft
werden. Ein Backup der NetBox-Datenbank bleibt unabhängig vom Plugin dringend
empfohlen.

## Verwendung

### Mehrere Geräte nebeneinander in derselben HE

Auf der normalen Seite zum **Anlegen oder Bearbeiten eines Geräts** stehen
direkt nach **Position** zwei neue optionale Felder zur Verfügung. Dafür wird
kein separates Plugin-Menü benötigt:

- **Rackbreite**: volle, halbe, Drittel- oder Viertelbreite;
- **Breitenposition**: Position 1 bis 4, von links gezählt.

Für eine Fritzbox und ein zweites Gerät in derselben HE wird bei beiden
Geräten beispielsweise **1/2 Rackbreite** gewählt. Die Fritzbox erhält
**Position 1 (links)**, das andere Gerät **Position 2**. Rack, HE und Rackseite
dürfen anschließend identisch sein. Die Kollisionsprüfung berücksichtigt
sowohl die Gerätehöhe als auch die Breite und verhindert horizontale oder
vertikale Überschneidungen. Mehrere HE hohe Geräte werden ebenfalls
unterstützt.

Nach einer Änderung der Rackbreite wird die **Breitenposition** unmittelbar
aktualisiert; ein Zwischenspeichern oder Neuladen ist nicht erforderlich.

Ohne Breitenangabe belegt ein Gerät wie bisher die volle Rackbreite. Ausnahme
ist eine bereits vorhandene gemeinsame Belegung derselben HE und Rackseite:
Fehlen dort Plugin-Platzierungen, teilt die Darstellung den verfügbaren Platz
gleichmäßig auf die zwei bis vier vorhandenen Geräte auf. Diese Ableitung
ändert keine Datenbankwerte und dient nur dazu, bereits gemeinsam eingepflegte
Geräte wieder sichtbar zu machen. Es findet keine Migration bestehender
Platzierungen statt. Explizit gewählte Teilbreite und Position werden auf der
Geräteseite angezeigt und in der Rackgrafik nebeneinander dargestellt.

NetBox besitzt standardmäßig eine Datenbank-Eindeutigkeit für Rack, HE und
Rackseite. Die Plugin-Migration `0007` entfernt ausschließlich diese
Core-Eindeutigkeit, damit mehrere Geräte dieselbe HE verwenden können. Das
Plugin übernimmt dafür die breitenabhängige Prüfung beim Speichern. Vor einem
späteren Entfernen des Plugins müssen geteilte Höheneinheiten wieder aufgelöst
werden; die Core-Eindeutigkeit wird bei einer Deinstallation nicht automatisch
wiederhergestellt.

Die Zusatzfelder werden derzeit im NetBox-Webformular gepflegt. REST- oder
CSV-Vorgänge ohne diese Felder behandeln neue Geräte als volle Rackbreite.

### Teilbreiten in MrBlake NetBox Topology Views

Ist
[MrBlake NetBox Topology Views](https://git.mrblake.cc/MrBlake/mrb-netbox-topology-views)
mit seiner **Rack-Ansicht** installiert, erkennt NetBox Utilities das Plugin
automatisch. Teilbreitengeräte werden dort anhand ihrer Rackbreite und
Breitenposition nebeneinander dargestellt. Die aktuelle Rack-Ansicht wird auch
bei ihren Exporten nach **SVG**, **PNG** und **draw.io** unterstützt. Die
Kabeltopologie bleibt unverändert, da sie Geräte als frei verschiebbare Knoten
und nicht als physische Rackflächen darstellt.

Das Topology-Plugin bleibt eine optionale Abhängigkeit. Eine reproduzierbare
Installation des derzeit getesteten MrBlake-Stands erfolgt über dessen
Commit-ID:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/mrb-netbox-topology-views.git@86a8daf45ef380d57ac73b461dbc47a16bb831ba"
```

Für automatische NetBox-Updates wird derselbe Git-Eintrag zusätzlich in
`/opt/netbox/local_requirements.txt` aufgenommen. Anschließend müssen beide
Plugins aktiviert sein; ihre Reihenfolge ist beliebig:

```python
PLUGINS = [
    "netbox_topology_views",
    "netbox_utilities",
]
```

Die Integration ändert keine Dateien von Topology Views und erzeugt keine
zusätzlichen Datenbankeinträge. Sie wird ausschließlich auf dessen Rack-Seite
geladen und kann mit
`topology_views_rack_width_enabled = False` in `PLUGINS_CONFIG` deaktiviert
werden. Ist Topology Views nicht installiert oder enthält der installierte
Stand keine Rack-Ansicht, bleibt NetBox Utilities unverändert nutzbar.

### Front- und Rearports von Patchpaneln automatisch verknüpfen

Geräte, deren NetBox-Geräterolle `Patchpanel` heißt, werden automatisch als
Patchfeld erkannt. Groß- und Kleinschreibung spielen bei der Rollenbezeichnung
keine Rolle. Das Plugin verknüpft ausschließlich Ports mit derselben Kennung
auf Portposition 1: `Front 1` mit `Rear 1`, `Front 2` mit `Rear 2` und so
weiter. Auch Kurzformen wie `F01` und `R1` werden als dieselbe Kennung erkannt.
Fehlt die passende Gegenseite, bleibt der Port unverknüpft; die nachfolgenden
Nummern rutschen nicht auf.

Die Zuordnung wird ausschließlich beim erstmaligen Anlegen eines Patchpanels,
beim Einbau eines neuen Moduls sowie beim Anlegen eines neuen Front- oder
Rearports hergestellt. Das Bearbeiten eines vorhandenen Patchpanels, Moduls
oder Ports löst die Automatik nicht aus.

Bei Installation oder Update findet kein automatischer Bestandslauf statt.
Vorhandene Patchpanel-Geräte und deren Kabelpfade bleiben unverändert. Die
Automatik greift erst, wenn ein betreffendes Gerät, Modul oder ein Front-/Rearport
neu angelegt wird.

### Mehrere Geräte mit NetBox Reorder Rack verschieben

Wenn `netbox-reorder-rack` in Version `1.1.4` installiert und aktiviert ist,
erweitert NetBox Utilities dessen vorhandenen Speichervorgang automatisch.
In der Drag-and-drop-Ansicht können mehrere Geräte verschoben oder miteinander
getauscht und anschließend gemeinsam über **Save** gespeichert werden.
Teilbreitengeräte werden dort ebenfalls nebeneinander angezeigt. Das
12-spaltige Raster bildet volle, halbe, Drittel- und Viertelbreite exakt ab.
Beim horizontalen Verschieben rastet ein Gerät auf einer für seine Breite
gültigen Position ein; **Save** speichert Höhe, Rackseite und Breitenposition
gemeinsam in derselben Transaktion. Die gewählte Rackbreite selbst wird in der
Reorder-Ansicht nicht verändert und weiterhin auf der Geräte-Neu- oder
Bearbeitungsseite gepflegt.

Die optionale Abhängigkeit wird separat installiert und für spätere NetBox-
Updates in `/opt/netbox/local_requirements.txt` aufgenommen:

```bash
/opt/netbox/venv/bin/pip install "netbox-reorder-rack==1.1.4"
echo "netbox-reorder-rack==1.1.4" | sudo tee -a /opt/netbox/local_requirements.txt
```

Beide Plugins müssen in NetBox aktiviert sein; ihre Reihenfolge ist beliebig:

```python
PLUGINS = [
    "netbox_reorder_rack",
    "netbox_utilities",
]
```

NetBox Utilities verändert keine Dateien des Reorder-Plugins. Stattdessen wird
dessen Oberfläche und API beim Start kompatibel erweitert. Beim Speichern
werden alle betroffenen Geräte und das Rack gesperrt, die alten Positionen gemeinsam
freigegeben und danach sämtliche Zielpositionen mit der normalen
NetBox-Modellvalidierung geprüft. Der Vorgang läuft in einer Transaktion: Bei
einem Platz-, Validierungs- oder Berechtigungsfehler bleibt das gesamte Rack
unverändert. Für jedes tatsächlich verschobene Gerät entsteht weiterhin ein
normaler NetBox-Änderungseintrag.

Die Integration kann mit
`reorder_rack_bulk_save_enabled = False` in `PLUGINS_CONFIG` deaktiviert werden.
Andere Versionen als `1.1.4` werden aus Sicherheitsgründen nicht automatisch
verändert und erzeugen lediglich einen Hinweis im NetBox-Log. Das
Reorder-Projekt selbst weist derzeit offiziell nur Kompatibilität bis NetBox
4.5 aus; die Erweiterung in diesem Plugin ist gezielt für die hier unterstützte
NetBox-Versionen 4.6.5 bis 4.6.7 umgesetzt und getestet.

### Mehrere Bilder hochladen

Im **Bilder**-Tab eines unterstützten NetBox-Objekts wird der bisherige
Einzel-Upload durch **Mehrere Bilder hochladen** ersetzt. Im Dateidialog können
bis zu 50 Bilder gemeinsam ausgewählt werden. Vor dem Speichern zeigt das
Plugin Vorschaubilder und die jeweiligen Dateinamen an.

Jede Datei wird genau einmal mit NetBox' eigener Bildvalidierung geprüft. Ist
eine Datei ungültig, wird kein Bild aus dieser Auswahl gespeichert. Eine
optionale gemeinsame Beschreibung kann auf alle Bilder angewendet werden; als
Anzeigename bleibt der jeweilige ursprüngliche Dateiname erhalten. Benötigt
werden weiterhin die NetBox-Berechtigung zum Hinzufügen von Bildanhängen und
eine Leseberechtigung für das Zielobjekt.

### Module mehrfach einbauen

Unter **Plugins > NetBox Utilities > Module mehrfach einbauen** kann ein
Benutzer ein Gerät, einen Modultyp und mehrere freie Modulschächte auswählen.
Auf Geräteseiten mit freien Modulschächten steht dieselbe Funktion zusätzlich
über die Schaltfläche **Module mehrfach einbauen** zur Verfügung; das Gerät ist
dort bereits vorausgewählt. Das funktioniert sowohl für modulare Patchpanels
als auch für andere NetBox-Geräte mit Modulschächten.

Der Benutzer kann entweder bestimmte freie Modulschächte auswählen oder über
**Anzahl (1–x)** eine Menge eingeben. Bei der Mengenangabe verwendet das Plugin
die ersten freien Modulschächte in der natürlichen NetBox-Reihenfolge. Beide
Eingabearten können nicht miteinander kombiniert werden.

Alle gewählten Schächte erhalten denselben Modultyp, Status und dieselbe
Beschreibung. Optional werden die Komponenten aus den Vorlagen des Modultyps
für jedes Modul repliziert. NetBox prüft dabei jeden Einbau mit derselben Logik
wie beim einzelnen Modul. Der Vorgang ist atomar: Ist ein Schacht inzwischen
belegt oder entsteht ein Komponenten-/Namenskonflikt, wird keines der Module
gespeichert. Individuelle Seriennummern und Asset-Tags werden anschließend an
den einzelnen Modulen gepflegt.

Benötigt wird die NetBox-Berechtigung zum Hinzufügen von Modulen. Geräte,
Modultypen und Modulschächte werden zusätzlich durch die bestehenden
NetBox-Objektberechtigungen des Benutzers eingeschränkt.

### Navigation personalisieren

Unter **Plugins > NetBox Utilities > Navigation personalisieren** sieht der
Benutzer alle Menüs, für die er aktuell Berechtigungen besitzt. Die Pfeiltasten
ändern die Reihenfolge; der Schalter blendet ein Menü aus.

Zusätzlich kann jeder Benutzer die Desktop-Navigation direkt an der rechten
Kante zwischen 216 und 408 Pixeln breiter oder schmaler ziehen. Ein kleiner
Pfeilgriff in der Mitte dieser Kante klappt sie auf einen reinen **Icon-Modus**
ein und wieder aus. Dafür gibt es kein zusätzliches Bedienmenü. Beim Ziehen
wird die neue Breite nach dem Loslassen im Benutzerprofil gespeichert. Im
Icon-Modus öffnen sich die Menüinhalte als seitliches Flyout; auf kleinen
beziehungsweise mobilen Ansichten bleibt das normale NetBox-Menü erhalten.
Das Flyout schließt sich bei Auswahl eines Eintrags, bei erneutem Klick auf
das aktive Icon, bei einem Klick außerhalb und mit der Escape-Taste. Nach
einem Seitenwechsel oder Neuladen startet es immer geschlossen.

**Zurücksetzen** stellt neben Reihenfolge und Sichtbarkeit auch die normale
ausgeklappte Breite von 288 Pixeln wieder her.

Die Funktion kann installationsweit über `navigation_customization_enabled = False` in `PLUGINS_CONFIG` abgeschaltet werden.

### Globaler Mandanten- und Gruppenfilter

Das Gebäude-Symbol in der Kopfleiste öffnet die Auswahl. Zur Auswahl stehen
Mandanten und Mandantengruppen, die der angemeldete Benutzer gemäß
NetBox-Objektberechtigungen sehen darf. Eine Mandantengruppe umfasst auch die
Mandanten ihrer untergeordneten Gruppen. **Alle Mandanten** hebt den Filter auf.

Der Filter:

- erzwingt je nach Auswahl `tenant_id` oder `tenant_group_id` in unterstützten NetBox-Listen;
- beschränkt die Mandantenliste auf den gewählten Mandanten beziehungsweise die gewählte Gruppe;
- beschränkt Ergebnisse der globalen NetBox-Suche;
- gilt auch für HTMX-Tabellenupdates und Exporte aus einer gefilterten Liste;
- verändert keine REST- oder GraphQL-Anfrage.

Superuser können die Funktion unter **Plugins > NetBox Utilities > Einstellungen** zur Laufzeit deaktivieren. Zusätzlich kann `tenant_filter_enabled = False` in `PLUGINS_CONFIG` sie hart abschalten; diese Konfiguration hat Vorrang vor der Einstellung in der Oberfläche.

### Verpflichtende Mandantenzuordnung

Standardmäßig ist unter **Plugins > NetBox Utilities > Einstellungen** die
verpflichtende Mandantenzuordnung aktiviert. Bei allen Objekttypen, die in
NetBox ein `tenant`-Feld besitzen, wird dieses Feld als Pflichtfeld behandelt.
Die Prüfung greift in Formularen, CSV-Importen, der REST-API und bei normalen
Aufrufen von `Model.save()` aus Skripten.

Bestehende Objekte ohne Mandant bleiben nach Aktivierung zunächst bestehen.
Beim nächsten Speichern eines solchen Objekts muss ein Mandant ergänzt werden.
Globale Referenzmodelle ohne `tenant`-Feld sind nicht betroffen.

Beim Öffnen eines NetBox-Formulars versucht das Plugin, fehlende Zuordnungen
vorsichtig vorzubelegen. Vorrang hat ein bereits erkennbares Elternobjekt, zum
Beispiel Rack, Standort, Gerät oder Cluster. Ist dort keine Zuordnung
erkennbar, wird der global ausgewählte Mandant verwendet. Felder für eine
Mandantengruppe werden aus dem erkannten Mandanten oder der global ausgewählten
Mandantengruppe vorbelegt. Bereits vorhandene Werte werden nicht überschrieben.

Bei Kabeln werden die ausgewählten Anschlüsse beider Kabelenden ausgewertet.
Gehören die Anschlüsse beziehungsweise ihre Geräte, Stromverteiler oder
Schaltkreise eindeutig zu demselben Mandanten, übernimmt das Kabel diesen
Mandanten automatisch. Ist nur an einem Ende eine Zuordnung herleitbar, wird
diese verwendet. Bei widersprüchlichen Mandanten an den beiden Enden nimmt das
Plugin keine automatische Zuordnung vor.

Bleibt ein automatisch gesetzter Mandant bis zum Speichern unverändert, fragt
der Browser unmittelbar nach dem Klick auf **Speichern** noch einmal nach einer
ausdrücklichen Bestätigung. Wird der Mandant manuell geändert, entfällt diese
zusätzliche Rückfrage.

Die Einstellung kann durch einen Superuser deaktiviert werden. Mit
`tenant_required = False` in `PLUGINS_CONFIG` wird sie installationsweit fest
deaktiviert; diese Konfiguration hat Vorrang vor der Admin-Oberfläche.

## Wichtige Semantik

Der Mandantenfilter ist ein **Ansichtsfilter und keine Zugriffskontrolle**. Direkte Objekt-URLs werden nicht gesperrt. NetBox-Objektberechtigungen bleiben die maßgebliche Sicherheitsgrenze. Die verpflichtende Mandantenzuordnung ist dagegen eine serverseitige Datenvalidierung.

Nur Modelle mit einer Mandantenzuordnung werden eingeschränkt. Globale Referenzdaten wie Hersteller, Rollen oder Plattformen bleiben sichtbar, weil sie keinem Mandanten gehören und für die Darstellung bzw. Bearbeitung mandantengebundener Objekte benötigt werden.

Die Seitenleisten-Personalisierung nutzt NetBox' offizielle globale `PluginTemplateExtension`, ordnet aber bereits gerenderte Core-Menüs im Browser neu. Sie ändert weder Core-Templates noch NetBox-Dateien.

## Entwicklung und Tests

In einer NetBox-4.6.5-Entwicklungsumgebung:

```bash
pip install -e /pfad/zu/Netbox-Utilities
python netbox/manage.py test netbox_utilities
```
