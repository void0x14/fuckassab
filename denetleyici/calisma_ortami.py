"""Yalniz cagiran oturumun mevcut native OpenCode sunucusuna baglanir."""
import base64
import contextlib
import json
import os
from pathlib import Path
import urllib.request
KOK=Path(__file__).resolve().parent
YASAK=[{'action':'*','resource':'*','effect':'deny'}]
OKUMA_ARACI='tam_okuma_penceresi'
AJAN_OKUMA_IZNI=YASAK+[{'action':OKUMA_ARACI,'resource':'*','effect':'allow'}]
class Baglanti:
    def __init__(kendisi,adres,parola):
        kendisi.adres=adres
        kendisi.baslik={'Authorization':'Basic '+base64.b64encode(('opencode:'+parola).encode()).decode(),'Content-Type':'application/json'}
    def istek(kendisi,yontem,yol,govde=None):
        istek=urllib.request.Request(kendisi.adres+yol,method=yontem,headers=kendisi.baslik,data=None if govde is None else json.dumps(govde,ensure_ascii=False).encode())
        with urllib.request.urlopen(istek,timeout=45) as yanit:veri=yanit.read()
        return json.loads(veri) if veri else None

def ortak_baglanti(oturum=None):
    if not oturum:raise ValueError('Cagiran native oturum kimligi zorunlu; sabit eski oturuma baglanilmaz')
    durum=Path(os.environ.get('XDG_STATE_HOME') or Path.home()/'.local/state')/'opencode'
    for yol in sorted(durum.glob('service*.json')):
        kayit=json.loads(yol.read_text())
        if 'url' not in kayit:continue
        bag=Baglanti(kayit['url'],kayit['password'])
        try:bag.istek('GET','/api/session/'+oturum);return bag
        except (OSError,ValueError):continue
    raise RuntimeError('Cagiran oturumun calisan native sunucusu bulunamadi; yeni motor acilmadi')

def model_bilgisi(bag,secim):
    veriler=bag.istek('GET','/api/model')['data']
    model=next((m for m in veriler if m['id']==secim['id'] and m['providerID']==secim['providerID']),None)
    if model is None or not model.get('limit',{}).get('context'):raise ValueError('Secili modelin gercek yerel limit kaydi yok; limit uydurulmadi')
    return model

@contextlib.contextmanager
def yerel_calisma(oturum):
    bag=ortak_baglanti(oturum);ana=bag.istek('GET','/api/session/'+oturum)['data']
    if not ana.get('model') or not ana.get('agent'):raise ValueError('Cagiran oturumun model ve ajan secimi eksik')
    yield bag,ana,model_bilgisi(bag,ana['model'])

def ozel_calisma():
    raise RuntimeError('Eski ayri motor yolu kapatildi; cagiran oturumla yerel_calisma kullanilir')

def salt_okunur_komut(ortam, komut, yazilabilir=()):
    sonuc=['bwrap','--die-with-parent','--ro-bind','/','/','--bind',str(ortam),str(ortam),
           '--proc','/proc','--dev','/dev','--tmpfs','/tmp']
    for yol in yazilabilir:sonuc+=['--bind',str(yol),str(yol)]
    return sonuc+['--']+list(komut)
