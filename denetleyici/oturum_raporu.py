#!/usr/bin/env python3
"""Saklanan ajan oturumunu bayt, yanit ve token kullanimi acisindan denetler."""
import hashlib
import json
from pathlib import Path
import re
import sys

ISARET = b'\nKAYNAK SONU\n'
BASLIK = re.compile(rb'\nDOSYA (.*?) \| BAYT \[(\d+),(\d+)\)\nKAYNAK BASI\n')


def bloklari_oku(metin):
    veri = metin.encode('utf-8')
    sonuc = []
    for eslesme in BASLIK.finditer(veri):
        yol = eslesme.group(1).decode('utf-8')
        bas = int(eslesme.group(2))
        son = int(eslesme.group(3))
        cagri_bas = eslesme.end()
        kaynak = veri[cagri_bas:cagri_bas + son - bas]
        isaret_bas = cagri_bas + son - bas
        if len(kaynak) != son - bas or veri[isaret_bas:isaret_bas + len(ISARET)] != ISARET:
            raise ValueError(f'Kaynak blogu bozuk: {yol} [{bas},{son})')
        sonuc.append({'yol':yol,'bas':bas,'son':son,'bayt':kaynak})
    return sonuc


def _token_toplami(tokenler):
    cache = tokenler.get('cache') or {}
    return sum(x for x in (tokenler.get('input'),cache.get('read',0),cache.get('write',0),tokenler.get('output'),tokenler.get('reasoning')) if type(x) is int and x >= 0)


def denetle(tarama):
    tarama = Path(tarama)
    kayit = json.loads((tarama/'ajan-kaydi.json').read_text(encoding='utf-8'))
    hatalar = []
    dosyalar = {x['yol']:x for x in kayit.get('dosyalar',[])}
    envanter_durumlari = {}
    for oge in kayit.get('envanter',[]):
        envanter_durumlari[oge.get('durum','bilinmiyor')] = envanter_durumlari.get(oge.get('durum','bilinmiyor'),0)+1

    sabitler = {}
    for yol,dosya in dosyalar.items():
        p = tarama/'sabitler'/dosya['parmak']
        if not p.is_file():
            hatalar.append(f'Sabit kaynak yok: {yol}')
            continue
        ham = p.read_bytes()
        if hashlib.sha256(ham).hexdigest() != dosya['parmak'] or len(ham) != dosya['bayt']:
            hatalar.append(f'Sabit kaynak parmak izi tutmuyor: {yol}')
            continue
        sabitler[yol] = ham

    aktarimlar = kayit.get('teslimler',[])
    iletiler = {}
    for aralik in aktarimlar:
        iletiler.setdefault(aralik.get('ileti',''),[]).append(aralik)
    raw_sayisi = 0
    opencode_jetonlari = {}
    eski_api_jetonlari = {}
    aktarim_yontemleri = {}
    for ileti, araliklar in iletiler.items():
        p = tarama/'teslimler'/(ileti+'.json')
        if not p.is_file():
            hatalar.append(f'Ajanin ham cevabi yok: {ileti}')
            continue
        raw_sayisi += 1
        raw = json.loads(p.read_text(encoding='utf-8'))
        if raw.get('oturum') and raw.get('opencode_kullanimi'):
            opencode_jetonlari[raw['oturum']] = raw['opencode_kullanimi']
        if raw.get('oturum') and raw.get('api_jetonlari'):
            eski_api_jetonlari[raw['oturum']] = raw['api_jetonlari']
        if raw.get('oturum'):
            aktarim_yontemleri[raw['oturum']] = raw.get('aktarim_yontemi','eski_prompt')
        cevap = raw.get('cevap')
        if not isinstance(cevap,dict) or not isinstance(cevap.get('notlar'),list):
            hatalar.append(f'Ajan cevabi okunamiyor: {ileti}')
        beklenen = sorted((x.get('yol'),x.get('bas'),x.get('son')) for x in araliklar)
        if raw.get('aktarim_yontemi')=='yalniz_okuma_araci':
            fisler=raw.get('okuma_fisleri',[])
            ajan=raw.get('oturum');gorev_yolu=tarama/'ajan-gorevleri'/(str(ajan)+'.json')
            try:gorev=json.loads(gorev_yolu.read_text(encoding='utf-8'))
            except (OSError,ValueError):gorev={}
            olaylar=[]
            try:olaylar=[json.loads(x) for x in (tarama/'olaylar.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
            except (OSError,ValueError):pass
            teslim=next((x for x in reversed(olaylar) if x.get('olay')=='ajan_kod_araciyla_okudu' and x.get('ajan')==ajan),None)
            if not gorev.get('okundu') or not gorev.get('modele_iletildi') or not teslim or not teslim.get('model_isteginde_teslim_edildi'):
                hatalar.append(f'Ajan kod penceresini model istegine tasidigini kanitlayan teslim fisi yok: {ajan}')
            elif (gorev.get('icerik_parmagi')!=teslim.get('icerik_parmagi') or gorev.get('arac_cagrisi')!=teslim.get('arac_cagrisi')
                  or any(f.get('arac_cagrisi')!=gorev.get('arac_cagrisi') for f in fisler)):
                hatalar.append(f'Ajanin model istegi teslim fisi kaynak penceresiyle eslesmiyor: {ajan}')
            sirali_beklenen=[(x.get('yol'),x.get('bas'),x.get('son')) for x in araliklar]
            bulunan=[(x.get('yol'),x.get('bas'),x.get('son')) for x in fisler]
            if bulunan!=sirali_beklenen:
                hatalar.append(f'Ajanin okuma araci fisleri kayitli kaynak araliklariyla eslesmiyor: {ileti}')
                continue
            for fis in fisler:
                tam=sabitler.get(fis.get('yol'));bas=fis.get('bas');son=fis.get('son')
                if tam is None or not isinstance(bas,int) or not isinstance(son,int) or not 0<=bas<=son<=len(tam):
                    hatalar.append(f'Okuma araci fisindeki kaynak araligi gecersiz: {fis.get("yol")}')
                    continue
                kod=tam[bas:son]
                if len(kod)!=fis.get('bayt') or hashlib.sha256(kod).hexdigest()!=fis.get('kod_parmagi'):
                    hatalar.append(f'Okuma araci fisindeki baytlar sabit kaynakla eslesmiyor: {fis.get("yol")} [{bas},{son})')
        else:
            metin = raw.get('kaynak_girdisi') or raw.get('girdi') or ''
            try:
                bloklar = bloklari_oku(metin)
            except (UnicodeError,ValueError) as exc:
                hatalar.append(str(exc))
                continue
            bulunan = sorted((x['yol'],x['bas'],x['son']) for x in bloklar)
            if beklenen != bulunan:
                hatalar.append(f'Ajan girdisindeki kaynak araliklari kayitla eslesmiyor: {ileti}')
                continue
            for blok in bloklar:
                tam = sabitler.get(blok['yol'])
                if tam is None or blok['son'] > len(tam) or blok['bas'] > blok['son'] or blok['bayt'] != tam[blok['bas']:blok['son']]:
                    hatalar.append(f'Ajana giden ham kod sabit kaynakla eslesmiyor: {blok["yol"]} [{blok["bas"]},{blok["son"]})')

    aralik_hatalari = []
    for yol,dosya in dosyalar.items():
        sirali = sorted((x['bas'],x['son']) for x in aktarimlar if x.get('yol') == yol)
        imlec = 0
        for bas,son in sirali:
            if bas != imlec or son < bas or son > dosya['bayt']:
                aralik_hatalari.append(f'{yol}: beklenen {imlec}, gelen [{bas},{son})')
                break
            imlec = son
        if imlec != dosya['bayt']:
            aralik_hatalari.append(f'{yol}: {imlec}/{dosya["bayt"]} bayt teslim edildi')
    hatalar.extend(aralik_hatalari)

    ajanlar = []
    for sira,ajan in enumerate(kayit.get('ajanlar',[])):
        plan = kayit.get('ajan_plani',[])
        token = plan[sira].get('yerlesik_tahmin') if sira < len(plan) else None
        native = ajan.get('opencode_kullanimi') or opencode_jetonlari.get(ajan.get('oturum'),{})
        eski = ajan.get('api_jetonlari') or eski_api_jetonlari.get(ajan.get('oturum'),{})
        ajanlar.append({'sira':sira+1,'oturum':ajan.get('oturum'),'ajan':kayit.get('secim',{}).get('agent'),
            'model':kayit.get('secim',{}).get('model'),'pencere_metni_tahmini':token,
            'gercek_kullanim_tokeni':ajan.get('kullanilan') if 'opencode_kullanimi' in ajan else None,
            'opencode_kullanimi':native,'eski_api_kaydi':eski,'yanit_kabul_edildi':ajan.get('son_inceleme') is True,
            'aktarim_yontemi':aktarim_yontemleri.get(ajan.get('oturum'),'kayit-yok'),
            'not_sayisi':len(ajan.get('notlar',[])),'notlar':ajan.get('notlar',[])})
        if ajan.get('son_inceleme') is not True:
            hatalar.append(f'Ajan yaniti kabul edilmedi: {ajan.get("oturum")}')
    dahil_olmayanlar = [x for x in kayit.get('envanter',[]) if x.get('durum') != 'dahil']
    bekleyen = len(dosyalar) != len(kayit.get('dosyalar',[])) or bool(kayit.get('bekleyen')) or bool(kayit.get('hata'))
    bayt_toplam = sum(x['bayt'] for x in dosyalar.values())
    teslim_bayti = sum(x['son']-x['bas'] for x in aktarimlar)
    bayt_tam = not aralik_hatalari and teslim_bayti == bayt_toplam and not dahil_olmayanlar
    yanitlar_tam = bool(ajanlar) and all(x['yanit_kabul_edildi'] for x in ajanlar) and not bekleyen
    return {'tarama':str(tarama),'kaynak':kayit.get('kaynak'),'secim':kayit.get('secim'),
        'dosya_sayisi':len(dosyalar),'envanter_durumlari':envanter_durumlari,'dahil_olmayanlar':[x.get('yol') for x in dahil_olmayanlar],
        'kaynak_bayti':bayt_toplam,'aktarilan_bayt':teslim_bayti,'aralik_sayisi':len(aktarimlar),
        'ajan_sayisi':len(ajanlar),'ajanlar':ajanlar,'ham_cevap_dosyasi_sayisi':raw_sayisi,
        'bayt_kapsami_tam':bayt_tam,'ajan_yanitlari_tam':yanitlar_tam,'kapsama_tam':bayt_tam and yanitlar_tam and not hatalar,
        'hatalar':hatalar,'anlam_siniri':'Bu denetim baytlarin sabit kaynaktan ajan girdilerine tam ulastigini ve yanitlarin kaydedildigini kanitlar; modelin her satiri anladigini veya her kusuru buldugunu kanitlamaz.'}


def ozet_yaz(sonuc,tarama):
    tarama = Path(tarama)
    (tarama/'kapsama-denetimi.json').write_text(json.dumps(sonuc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    secim = sonuc.get('secim') or {};model = secim.get('model') or {}
    satirlar=['# Tam okuma oturum ozeti','',f'- Kaynak: `{sonuc.get("kaynak")}`',
        f'- Sonuc: **{"BAYT KAPSAMI TAM" if sonuc["kapsama_tam"] else "EKSİK / DENETİM HATASI"}**',
        f'- Dosya: {sonuc["dosya_sayisi"]}; bayt: {sonuc["aktarilan_bayt"]}/{sonuc["kaynak_bayti"]}; kaynak araligi: {sonuc["aralik_sayisi"]}',
        f'- Ajan: `{secim.get("agent")}`; model: `{model.get("providerID")}/{model.get("id")}`; bicim: `{model.get("variant")}`',
        f'- Ham cevap dosyasi: {sonuc["ham_cevap_dosyasi_sayisi"]}',
        '- Not: Bayt aktarim kaniti, modelin her satiri anladigini veya butun kusurlari buldugunu gostermez.','',
        '| Ajan oturumu | Kod nasil ulasti | Pencere metni tahmini | Gercek kullanim | OpenCode girdi/cikti/akil yurutme/onbellek oku-yaz | Eski API kaydi | Yanit | Not |','|---|---|---:|---:|---|---|---|---:|']
    for a in sonuc['ajanlar']:
        t=a.get('opencode_kullanimi') or {};c=t.get('cache') or {};e=a.get('eski_api_kaydi') or {}
        ayrinti=f"{t.get('input','—')}/{t.get('output','—')}/{t.get('reasoning','—')}/{c.get('read','—')}/{c.get('write','—')}"
        eski=f"{e.get('input','—')}/{e.get('output','—')}" if e else 'yok'
        satirlar.append(f'| `{a["oturum"]}` | {a.get("aktarim_yontemi")} | {a["pencere_metni_tahmini"] if a["pencere_metni_tahmini"] is not None else "—"} | {a["gercek_kullanim_tokeni"] if a["gercek_kullanim_tokeni"] is not None else "—"} | {ayrinti} | {eski} | {"kabul" if a["yanit_kabul_edildi"] else "eksik"} | {a["not_sayisi"]} |')
    if sonuc['hatalar']:
        satirlar.extend(['','## Denetim hatalari','']+['- '+x for x in sonuc['hatalar']])
    satirlar.extend(['','## Ajan notlari',''])
    for a in sonuc['ajanlar']:
        satirlar.extend([f'### {a["sira"]}. ajan — `{a["oturum"]}`','']+['- '+n for n in a['notlar']]+[''])
    (tarama/'oturum-ozeti.md').write_text('\n'.join(satirlar)+'\n',encoding='utf-8')


def uret(tarama):
    sonuc=denetle(tarama);ozet_yaz(sonuc,tarama);return sonuc


if __name__=='__main__':
    if len(sys.argv)!=2:
        print('Kullanim: python3 oturum_raporu.py <tarama-dizini>',file=sys.stderr);raise SystemExit(2)
    sonuc=uret(sys.argv[1]);print(json.dumps(sonuc,ensure_ascii=False,indent=2));raise SystemExit(0 if sonuc['kapsama_tam'] else 2)
