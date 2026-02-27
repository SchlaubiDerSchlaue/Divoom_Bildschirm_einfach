# Divoom Pixoo64 Webapp

Eine Webanwendung zum Steuern des Divoom Pixoo64 LED-Displays, basierend auf der [pixoo](https://pypi.org/project/pixoo/) Python-Bibliothek.

## Features

- Text senden (statisch mit TrueType-Font oder scrollend mit nativer Divoom-API)
- Farbauswahl, Position und Schriftgröße anpassbar
- Bilder hochladen (JPG statisch, animiertes GIF mit mehreren Frames)
- Bildschirm ein-/ausschalten
- Helligkeit regeln (0–100 %)
- Kanal wechseln (Uhren, Cloud, Visualizer, Custom)
- Vollfarbe auf Display ausgeben
- Bildschirm löschen

## Voraussetzungen

- Python 3.10 oder höher
- Divoom Pixoo64 im gleichen Netzwerk
- IP-Adresse des Pixoo64 (findest du in der Divoom App unter Einstellungen)

## Installation

```bash
# Virtuelle Umgebung erstellen (empfohlen)
python -m venv .venv
source .venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt
```

## Verwendung

```bash
python app.py
```

Browser öffnen: [http://localhost:5000](http://localhost:5000)

1. IP-Adresse des Pixoo64 eingeben und **Verbinden** klicken
2. Gewünschte Aktion ausführen

## API-Endpunkte

| Methode | Endpunkt | Beschreibung |
|---------|----------|--------------|
| POST | `/api/connect` | Verbindung herstellen (`{"ip": "192.168.1.x"}`) |
| POST | `/api/send-text` | Text anzeigen |
| POST | `/api/clear` | Bildschirm löschen (schwarz) |
| POST | `/api/fill` | Bildschirm mit Farbe füllen |
| POST | `/api/brightness` | Helligkeit setzen (`{"level": 0–100}`) |
| POST | `/api/screen` | Display an/aus (`{"on": true/false}`) |
| POST | `/api/channel` | Kanal wechseln (`{"channel": "faces|cloud|visualizer|custom"}`) |
| POST | `/api/upload-image` | Bild hochladen und anzeigen (JPG oder GIF, multipart/form-data) |
| GET  | `/api/status` | Verbindungsstatus abfragen |

### Text-Parameter (`/api/send-text`)

```json
{
  "text":      "Hallo Welt",
  "color":     "#ff6600",
  "x":         0,
  "y":         0,
  "font_size": 12,
  "speed":     0
}
```

- `font_size`: Pixel-Größe der TrueType-Schrift (nur bei `speed = 0`)
- `speed`: `0` = statisch (PIL-Rendering), `1–100` = scrollend (natives Divoom-API)

## Technische Details

| Komponente | Beschreibung |
|------------|--------------|
| [pixoo](https://pypi.org/project/pixoo/) | Kommunikation mit dem Gerät |
| Flask | Web-Framework |
| Pillow | TrueType-Text-Rendering für statischen Text |

**Bild-Upload:**
- *JPEG*: Wird serverseitig auf 64×64 px skaliert (Lanczos) und per `pixoo.draw_image()` + `pixoo.push()` übertragen.
- *Animiertes GIF*: Alle Frames werden auf 64×64 skaliert und als neue GIF-Datei unter `static/uploads/anim.gif` gespeichert. Der Pixoo ruft die Datei dann selbst per HTTP vom Flask-Server ab (`pixoo.play_net_gif(url)`). Flask läuft daher im `threaded`-Modus, damit der asynchrone Abruf des Pixoo nicht blockiert.
- *Nicht-animiertes GIF*: Wird wie ein JPEG als Standbild gesendet.

**Text-Rendering:**
- *Statisch*: PIL rendert den Text mit einer TrueType-Schrift in ein 64×64-Bild, das per `pixoo.draw_image()` + `pixoo.push()` übertragen wird.
- *Scrollend*: Natives Divoom-Kommando `Draw/SendHttpText` über `pixoo.send_text()` mit eingebautem Divoom-Font.
