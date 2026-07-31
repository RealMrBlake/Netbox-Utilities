# NetBox Utilities

Plugin für **NetBox 4.6.5** mit fünf Funktionen:

- Jeder Benutzer kann die Menüs der linken Navigation verschieben oder ausblenden.
- Ein Dropdown in der Kopfleiste setzt einen sitzungsweiten Filter für einen Mandanten oder eine Mandantengruppe.
- Optional verpflichtende Mandantenzuordnung für alle mandantenfähigen Objekte.
- Mehrere Module desselben Typs in einem Schritt in freie Modulschächte einbauen.
- Optionale Mehrfachspeicherung für verschobene Geräte aus NetBox Reorder Rack.

Die Navigationseinstellungen sind benutzerbezogen. Die aktive Mandanten- oder Gruppenauswahl wird in der jeweiligen Browser-Session gespeichert.

## Kompatibilität

- NetBox `>=4.6.5,<4.7`
- Python `>=3.12`
- optional: NetBox Reorder Rack `1.1.4`

Andere NetBox-Versionen werden vom Plugin absichtlich abgelehnt, da die Anpassung der Core-Navigation von deren HTML-Struktur abhängt.

## Installation aus Gitea

Das Plugin kann direkt aus dem `main`-Branch installiert werden:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@main"
```

Für eine reproduzierbare Produktivinstallation sollte statt `main` ein
Release-Tag oder ein bestimmter Commit verwendet werden:

```bash
/opt/netbox/venv/bin/pip install --upgrade --force-reinstall \
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@v0.4.0"
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

### Mehrere Geräte mit NetBox Reorder Rack verschieben

Wenn `netbox-reorder-rack` in Version `1.1.4` installiert und aktiviert ist,
erweitert NetBox Utilities dessen vorhandenen Speichervorgang automatisch.
In der Drag-and-drop-Ansicht können mehrere Geräte verschoben oder miteinander
getauscht und anschließend gemeinsam über **Save** gespeichert werden.

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
dessen API beim Start kompatibel erweitert. Beim Speichern werden alle
betroffenen Geräte und das Rack gesperrt, die alten Positionen gemeinsam
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
NetBox-Version 4.6.5 umgesetzt.

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

Unter **Plugins > NetBox Utilities > Navigation personalisieren** sieht der Benutzer alle Menüs, für die er aktuell Berechtigungen besitzt. Die Pfeiltasten ändern die Reihenfolge; der Schalter blendet ein Menü aus. **Zurücksetzen** stellt die NetBox-Reihenfolge wieder her.

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
