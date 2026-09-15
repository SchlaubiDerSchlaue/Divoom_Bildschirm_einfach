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
        font = _load_font(font_size)

        if speed > 0:
            # Scroll-Text: animierte Frames über den Buffer-Mechanismus
            bg = last_fill_color

            def _do_scroll():
                try:
                    # Textbreite messen
                    tmp = Image.new('RGB', (1, 1))
                    draw_tmp = ImageDraw.Draw(tmp)
                    bbox = draw_tmp.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]

                    total_distance = text_width + 64
                    step = max(1, speed // 5)
                    delay = 0.05

                    for offset in range(0, total_distance, step):
                        if pixoo is None:
                            break
                        frame = Image.new('RGB', (64, 64), bg)
                        ImageDraw.Draw(frame).text(
                            (64 - offset, y), text, fill=color, font=font
                        )
                        pixoo.draw_image(frame)
                        pixoo.push()
                        time.sleep(delay)
                except Exception:
                    pass

            threading.Thread(target=_do_scroll, daemon=True).start()
        else:
            # Statischer Text: letzte Vollfarbe als Hintergrund
            img = Image.new('RGB', (64, 64), last_fill_color)
            ImageDraw.Draw(img).text((x, y), text, fill=color, font=font)
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
        global last_fill_color
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

        # --- Animiertes GIF: auf Disk speichern, Pixoo lädt es selbst per HTTP ---
        if img.format == 'GIF':
            try:
                img.seek(1)
                is_animated = True
                img.seek(0)
            except EOFError:
                is_animated = False

            if is_animated:
                gif_path = os.path.join(UPLOAD_DIR, 'anim.gif')
                frame_count = _resize_and_save_gif(img, gif_path)
                if frame_count == 0:
                    return jsonify({'success': False, 'message': 'GIF enthält keine Frames'})

                # Der Pixoo ruft die Datei selbst vom Flask-Server ab
                lan_ip  = _get_lan_ip()
                gif_url = f'http://{lan_ip}:{PORT}/static/uploads/anim.gif'
                pixoo.play_net_gif(gif_url)
                return jsonify({'success': True, 'message': f'GIF gesendet ({frame_count} Frames)'})

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
