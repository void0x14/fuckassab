"""OpenCode eklenti girişini bağla; mevcut bir kurulumu ezme."""
import json
import os
from pathlib import Path

kaynak = Path(__file__).resolve().parent / 'denetleyici' / 'yerel_baglanti.js'
dizin = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'opencode/plugins'
dizin.mkdir(parents=True, exist_ok=True)
hedef = dizin / 'tam_kod_okuma.js'
giris = 'export { default } from ' + json.dumps(kaynak.as_uri()) + ';\n'
try:
    with hedef.open('x', encoding='utf-8') as dosya:
        dosya.write(giris)
except FileExistsError:
    if hedef.read_text(encoding='utf-8') != giris:
        raise SystemExit(f'Mevcut eklenti korunuyor: {hedef}')
print(hedef)
