from flask import Flask, render_template, request, jsonify
from pixoo import Pixoo, Channel, TextScrollDirection
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

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


def _load_font(size: int):
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


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
        return jsonify({'success': False, 'message': 'Keine IP-Adresse angegeben'})
    try:
        p = Pixoo(ip)
        if not p.validate_connection():
            return jsonify({'success': False, 'message': f'Keine Verbindung zu {ip}'})
        pixoo = p
        return jsonify({'success': True, 'message': f'Verbunden mit {ip}'})
    except Exception as e:
        pixoo = None
        return jsonify({'success': False, 'message': str(e)})


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
    color = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
    x         = int(data.get('x', 0))
    y         = int(data.get('y', 0))
    font_size = int(data.get('font_size', 12))
    speed     = int(data.get('speed', 0))

    try:
        if speed > 0:
            # Natives Divoom-Scrollen über Draw/SendHttpText
            # font 0-7 aus Schriftgröße ableiten
            font_id = min(7, max(0, (font_size - 6) // 2))
            pixoo.send_text(
                text,
                xy=(x, y),
                color=color,
                font=font_id,
                movement_speed=speed,
                direction=TextScrollDirection.LEFT,
            )
        else:
            # Statischer Text: TrueType-Font via PIL, dann als Bild pushen
            font = _load_font(font_size)
            img  = Image.new('RGB', (64, 64), (0, 0, 0))
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
        pixoo.fill_rgb(r, g, b)
        pixoo.push()
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


@app.route('/api/status', methods=['GET'])
def status():
    if pixoo is None:
        return jsonify({'connected': False})
    return jsonify({'connected': True, 'ip': pixoo.ip_address})


if __name__ == '__main__':
    print('=' * 50)
    print('Divoom Pixoo64 Webapp  –  pixoo library')
    print('=' * 50)
    print('http://localhost:5000')
    print('=' * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
