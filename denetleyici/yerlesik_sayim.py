"""OpenCode'un yerlesik token tahminini kullanan yerel sayac."""
import json
from pathlib import Path
import subprocess

KOK=Path(__file__).resolve().parent

class Sayac:
    bicim='opencode_token_estimate'

    def __init__(self,sinir):
        self.sinir=sinir['context']
        self.cikis=sinir['output']
        self.surec=subprocess.Popen(
            ['bun',str(KOK/'yerlesik_sayim.js')],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            text=True,encoding='utf-8',bufsize=1)

    def say(self,metin):
        if self.surec.poll() is not None:raise RuntimeError('OpenCode yerlesik sayaci kapandi')
        self.surec.stdin.write(json.dumps(metin,ensure_ascii=False)+'\n');self.surec.stdin.flush()
        satir=self.surec.stdout.readline()
        try:sayi=int(satir)
        except (TypeError,ValueError):raise RuntimeError('OpenCode yerlesik sayaci sayi dondurmedi')
        if sayi<0:raise RuntimeError('OpenCode yerlesik sayaci metni hesaplayamadi')
        return sayi

    def kapat(self):
        if self.surec.poll() is None:
            self.surec.stdin.close();self.surec.wait(timeout=5)

def bul(sinir):
    if not isinstance(sinir,dict) or min(sinir.get('context',0),sinir.get('output',0))<=0:return None
    return Sayac(sinir)
