import os
import socket
import threading
import time

from flask import Flask, render_template, request, jsonify
from pixoo import Pixoo, PixooConfig, Channel, TextScrollDirection
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

# Umgebungsvariablen
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), 'static', 'uploads'))
os.makedirs(UPLOAD_DIR, exist_ok=True)

PORT = int(os.getenv("PORT", "5000"))

FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf',
    '/usr/share/fonts/TTF/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
    '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
]

CHANNELS = {
    'faces':      Channel.FACES,
    'cloud':      Channel.CLOUD,
    'visualizer': Channel.VISUALIZER,
    'custom':     Channel.CUSTOM,
}

pixoo: Pixoo | None = None
last_fill_color = (0, 0, 0)  # letzte Vollfarbe, wird bei Text als Hintergrund genutzt
animation_stop_flag = False  # wird gesetzt, um laufende Animationen (GIF/Scroll) zu stoppen


def _load_font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _get_lan_ip() -> str:
    """Ermittelt die LAN-IP des Servers, damit der Pixoo die GIF-Datei abrufen kann."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def _resize_and_save_gif(pil_gif: Image.Image, save_path: str) -> int:
    """Skaliert alle Frames eines GIFs auf 64×64 und speichert es als neue Datei.
    Gibt die Anzahl der Frames zurück."""
    frames = []
    durations = []
    try:
        while True:
            frame = pil_gif.copy().convert('RGB').resize((64, 64), Image.LANCZOS)
            frames.append(frame)
            durations.append(pil_gif.info.get('duration', 100))
            pil_gif.seek(pil_gif.tell() + 1)
    except EOFError:
        pass

    if not frames:
        return 0

    frames[0].save(
        save_path,
        format='GIF',
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=durations,
        optimize=False,
    )
    return len(frames)


def _require_pixoo():
    if pixoo is None:
        return jsonify({'success': False, 'message': 'Nicht verbunden'}), 400
    return None


# ------------------------------------------------------------------ routes

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/connect', methods=['POST'])
def connect():
    global pixoo
    data = request.json or {}
    ip = data.get('ip', '').strip()

    if not ip:
        return jsonify({
            'success': False,
            'message': 'Keine IP-Adresse angegeben'
        })

    try:
        config = PixooConfig(
            address=ip,
            size=64
        )

        p = Pixoo(config)
        pixoo = p

        return jsonify({
            'success': True,
            'message': f'Verbunden mit {ip}'
        })

    except Exception as e:
        pixoo = None
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/api/send-text', methods=['POST'])
def send_text():
    err = _require_pixoo()
    if err:
        return err

    data = request.json or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'success': False, 'message': 'Kein Text angegeben'}), 400

    color_hex = data.get('color', '#ffffff').lstrip('#')
    color     = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
    x         = int(data.get('x', 0))
    y         = int(data.get('y', 0))
    font_size = int(data.get('font_size', 12))
    speed     = int(data.get('speed', 0))

    try:
        global animation_stop_flag
        animation_stop_flag = True  # laufende Animationen stoppen
        time.sleep(0.1)  # kurz warten, damit Threads sich beenden können
        animation_stop_flag = False

        font = _load_font(font_size)

        if speed > 0:
            # Scroll-Text: animierte Frames über den Buffer-Mechanismus, endlos loopen
            bg = last_fill_color

            def _do_scroll():
                global animation_stop_flag
                try:
                    # Text in Zeilen aufteilen
                    lines = text.split('\n')
                    
                    # Maximale Textbreite über alle Zeilen messen
                    tmp = Image.new('RGB', (1, 1))
                    draw_tmp = ImageDraw.Draw(tmp)
                    max_width = 0
                    for line in lines:
                        bbox = draw_tmp.textbbox((0, 0), line, font=font)
                        line_width = bbox[2] - bbox[0]
                        max_width = max(max_width, line_width)

                    total_distance = max_width + 64
                    step = max(1, speed // 5)
                    delay = 0.05
                    
                    # Zeilenhöhe berechnen
                    line_height = font_size + 2

                    # Endlos loopen, bis Flag gesetzt oder Verbindung getrennt
                    while not animation_stop_flag and pixoo is not None:
                        for offset in range(0, total_distance, step):
                            if animation_stop_flag or pixoo is None:
                                break
                            frame = Image.new('RGB', (64, 64), bg)
                            draw = ImageDraw.Draw(frame)
                            
                            # Jede Zeile rendern
                            for i, line in enumerate(lines):
                                line_y = y + (i * line_height)
                                draw.text(
                                    (64 - offset, line_y), line, fill=color, font=font
                                )
                            
                            pixoo.draw_image(frame)
                            pixoo.push()
                            time.sleep(delay)
                except Exception:
                    pass

            threading.Thread(target=_do_scroll, daemon=True).start()
        else:
            # Statischer Text: mehrzeilig unterstützen
            lines = text.split('\n')
            img = Image.new('RGB', (64, 64), last_fill_color)
            draw = ImageDraw.Draw(img)
            
            # Zeilenhöhe berechnen
            line_height = font_size + 2
            
            # Jede Zeile rendern
            for i, line in enumerate(lines):
                line_y = y + (i * line_height)
                draw.text((x, line_y), line, fill=color, font=font)
            
            pixoo.draw_image(img)
            pixoo.push()

        return jsonify({'success': True, 'message': 'Text gesendet'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/clear', methods=['POST'])
def clear():
    err = _require_pixoo()
    if err:
        return err
    try:
        global animation_stop_flag
        animation_stop_flag = True  # laufende Animationen stoppen
        time.sleep(0.1)
        animation_stop_flag = False

        pixoo.fill_rgb(0, 0, 0)
        pixoo.push()
        return jsonify({'success': True, 'message': 'Bildschirm gelöscht'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/fill', methods=['POST'])
def fill_color():
    err = _require_pixoo()
    if err:
        return err
    data = request.json or {}
    color_hex = data.get('color', '#000000').lstrip('#')
    r, g, b = (int(color_hex[i:i+2], 16) for i in (0, 2, 4))
    try:
        global last_fill_color, animation_stop_flag
        animation_stop_flag = True  # laufende Animationen stoppen
        time.sleep(0.1)
        animation_stop_flag = False

        pixoo.fill_rgb(r, g, b)
        pixoo.push()
        last_fill_color = (r, g, b)
        return jsonify({'success': True, 'message': 'Farbe gesetzt'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/brightness', methods=['POST'])
def set_brightness():
    err = _require_pixoo()
    if err:
        return err
    data  = request.json or {}
    level = max(0, min(100, int(data.get('level', 50))))
    try:
        pixoo.set_brightness(level)
        return jsonify({'success': True, 'message': f'Helligkeit: {level} %'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/screen', methods=['POST'])
def toggle_screen():
    err = _require_pixoo()
    if err:
        return err
    on = request.json.get('on', True)
    try:
        pixoo.set_screen(bool(on))
        label = 'eingeschaltet' if on else 'ausgeschaltet'
        return jsonify({'success': True, 'message': f'Display {label}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/channel', methods=['POST'])
def set_channel():
    err = _require_pixoo()
    if err:
        return err
    name    = (request.json or {}).get('channel', 'custom').lower()
    channel = CHANNELS.get(name, Channel.CUSTOM)
    try:
        pixoo.set_channel(channel)
        return jsonify({'success': True, 'message': f'Kanal: {name}'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/upload-image', methods=['POST'])
def upload_image():
    err = _require_pixoo()
    if err:
        return err

    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'Keine Datei erhalten'}), 400

    file = request.files['file']
    ext  = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in {'jpg', 'jpeg', 'gif'}:
        return jsonify({'success': False, 'message': 'Nur JPG und GIF erlaubt'}), 400

    try:
        img = Image.open(file.stream)

        # --- Animiertes GIF: Frames extrahieren und über Buffer abspielen ---
        if img.format == 'GIF':
            try:
                img.seek(1)
                is_animated = True
                img.seek(0)
            except EOFError:
                is_animated = False

            if is_animated:
                frames = []
                durations = []
                try:
                    while True:
                        frame = img.copy().convert('RGB').resize((64, 64), Image.LANCZOS)
                        frames.append(frame)
                        durations.append(img.info.get('duration', 100))
                        img.seek(img.tell() + 1)
                except EOFError:
                    pass

                if not frames:
                    return jsonify({'success': False, 'message': 'GIF enthält keine Frames'})

                def _play_gif():
                    global animation_stop_flag
                    try:
                        # GIF endlos loopen, bis Flag gesetzt oder Verbindung getrennt
                        while not animation_stop_flag and pixoo is not None:
                            for i, frame in enumerate(frames):
                                if animation_stop_flag or pixoo is None:
                                    break
                                pixoo.draw_image(frame)
                                pixoo.push()
                                # duration ist in ms, sleep braucht Sekunden
                                time.sleep(max(durations[i], 50) / 1000.0)
                    except Exception:
                        pass

                threading.Thread(target=_play_gif, daemon=True).start()
                return jsonify({'success': True, 'message': f'GIF wird abgespielt ({len(frames)} Frames)'})

        # --- Statisches Bild (JPEG oder nicht-animiertes GIF) ---
        img_rgb = img.convert('RGB').resize((64, 64), Image.LANCZOS)
        pixoo.draw_image(img_rgb)
        pixoo.push()
        return jsonify({'success': True, 'message': 'Bild gesendet'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/status', methods=['GET'])
def status():
    if pixoo is None:
        return jsonify({'connected': False})
    return jsonify({'connected': True, 'ip': pixoo.ip_address})


if __name__ == '__main__':
    print('=' * 50)
    print('Divoom Pixoo64 Webapp  –  pixoo library')
    print('=' * 50)
    print(f'http://localhost:{PORT}')
    print('=' * 50)
    # threaded=True ist nötig: der Pixoo ruft das GIF asynchron vom
    # Flask-Server ab, während der Upload-Request noch verarbeitet wird
    app.run(debug=True, host='0.0.0.0', port=PORT, threaded=True)
