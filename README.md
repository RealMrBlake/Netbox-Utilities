# NetBox Utilities

Plugin für **NetBox 4.6.5** mit zwei Funktionen:

- Jeder Benutzer kann die Menüs der linken Navigation verschieben oder ausblenden.
- Ein Dropdown in der Kopfleiste setzt einen sitzungsweiten Mandantenfilter für mandantenfähige Listen und die globale Suche.

Die Navigationseinstellungen sind benutzerbezogen. Der aktive Mandant wird in der jeweiligen Browser-Session gespeichert.

## Kompatibilität

- NetBox `>=4.6.5,<4.7`
- Python `>=3.12`

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
  "git+https://git.mrblake.cc/MrBlake/Netbox-Utilities.git@v0.1.0"
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
        "tenant_filter_enabled": True,
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

### Navigation personalisieren

Unter **Plugins > NetBox Utilities > Navigation personalisieren** sieht der Benutzer alle Menüs, für die er aktuell Berechtigungen besitzt. Die Pfeiltasten ändern die Reihenfolge; der Schalter blendet ein Menü aus. **Zurücksetzen** stellt die NetBox-Reihenfolge wieder her.

Die Funktion kann installationsweit über `navigation_customization_enabled = False` in `PLUGINS_CONFIG` abgeschaltet werden.

### Globaler Mandantenfilter

Das Gebäude-Symbol in der Kopfleiste öffnet die Mandantenauswahl. Zur Auswahl stehen nur Mandanten, die der angemeldete Benutzer gemäß NetBox-Objektberechtigungen sehen darf. **Alle Mandanten** hebt den Filter auf.

Der Filter:

- erzwingt `tenant_id` in allen NetBox-Listen, deren FilterSet dieses Feld unterstützt;
- beschränkt die Mandantenliste auf den gewählten Mandanten;
- beschränkt Ergebnisse der globalen NetBox-Suche;
- gilt auch für HTMX-Tabellenupdates und Exporte aus einer gefilterten Liste;
- verändert keine REST- oder GraphQL-Anfrage.

Superuser können die Funktion unter **Plugins > NetBox Utilities > Einstellungen** zur Laufzeit deaktivieren. Zusätzlich kann `tenant_filter_enabled = False` in `PLUGINS_CONFIG` sie hart abschalten; diese Konfiguration hat Vorrang vor der Einstellung in der Oberfläche.

## Wichtige Semantik

Der Mandantenfilter ist ein **Ansichtsfilter und keine Zugriffskontrolle**. Direkte Objekt-URLs werden nicht gesperrt. NetBox-Objektberechtigungen bleiben die maßgebliche Sicherheitsgrenze.

Nur Modelle mit einer Mandantenzuordnung werden eingeschränkt. Globale Referenzdaten wie Hersteller, Rollen oder Plattformen bleiben sichtbar, weil sie keinem Mandanten gehören und für die Darstellung bzw. Bearbeitung mandantengebundener Objekte benötigt werden.

Die Seitenleisten-Personalisierung nutzt NetBox' offizielle globale `PluginTemplateExtension`, ordnet aber bereits gerenderte Core-Menüs im Browser neu. Sie ändert weder Core-Templates noch NetBox-Dateien.

## Entwicklung und Tests

In einer NetBox-4.6.5-Entwicklungsumgebung:

```bash
pip install -e /pfad/zu/Netbox-Utilities
python netbox/manage.py test netbox_utilities
```
