#!/usr/bin/env python3
"""/tam-okuma aracinin OpenCode yerlesik olcumlu ajan akisina girisi."""
import sys
sys.dont_write_bytecode=True
import json
from pathlib import Path
import re
import ajanli_okuma
import calisma_ortami
import uygulama
import yerlesik_sayim
import oturum_raporu
KOK=Path(__file__).resolve().parent

def rapora_ekle(sonuc,tarama):
    try:
        denetim=oturum_raporu.uret(tarama)
        sonuc.update(kapsama_denetcisi=denetim,oturum_ozeti=str(Path(tarama)/'oturum-ozeti.md'),
            kapsama_json=str(Path(tarama)/'kapsama-denetimi.json'),ham_kayit=str(Path(tarama)/'ajan-kaydi.json'),
            olay_gunlugu=str(Path(tarama)/'olaylar.jsonl') if (Path(tarama)/'olaylar.jsonl').is_file() else None)
        if sonuc['olay_gunlugu'] is None:sonuc['olay_gunlugu_notu']='Bu eski kayit olay gunlugu eklenmeden once olusturulmus; ham cevaplar ve token kullanimi kayitli.'
        sonuc['okuma_tamam']=bool(sonuc.get('okuma_tamam') and denetim.get('kapsama_tam'))
        sonuc['ajan_incelemeleri_tamam']=bool(sonuc.get('ajan_incelemeleri_tamam') and denetim.get('ajan_yanitlari_tam'))
        sonuc['asil_kapsam_tamam']=bool(sonuc.get('asil_kapsam_tamam') and denetim.get('bayt_kapsami_tam'))
    except Exception as hata:
        sonuc.update(okuma_tamam=False,ajan_incelemeleri_tamam=False,asil_kapsam_tamam=False,
            rapor_hatasi=str(hata),ham_kayit=str(Path(tarama)/'ajan-kaydi.json'))
    return sonuc

def kod_penceresi(ajan_oturumu,kusak,arac_cagrisi):
    bag=calisma_ortami.ortak_baglanti(ajan_oturumu)
    ajan=bag.istek('GET','/api/session/'+ajan_oturumu)['data']
    ana=ajan.get('parentID')
    if not ana or not ajan.get('metadata',{}).get('tam_okuma_ajan'):raise ValueError('Kaynak okuma araci yalniz tam okuma ajanina acik')
    izin_yolu=KOK/'yerel-izinler'/(ana+'.json')
    izin=json.loads(izin_yolu.read_text(encoding='utf-8'))
    if izin.get('acik') is not True or izin.get('kusak')!=kusak:raise ValueError('Tam okuma kapali veya eski cagri')
    kok=KOK/'taramalar'/('ajanli-'+ana)
    gosterge=json.loads((kok/'etkin-okuma.json').read_text(encoding='utf-8'))
    if gosterge.get('kusak')!=kusak:raise ValueError('Okuma gorevinin kusagi degisti')
    tarama=kok/gosterge['istek'];kayit=json.loads((tarama/'ajan-kaydi.json').read_text(encoding='utf-8'))
    gorev_yolu=tarama/'ajan-gorevleri'/(ajan_oturumu+'.json')
    gorev=json.loads(gorev_yolu.read_text(encoding='utf-8'))
    if gorev.get('ana')!=ana or gorev.get('kusak')!=kusak or ajan.get('model')!=kayit['secim']['model'] or ajan.get('agent')!=kayit['secim']['agent']:
        raise ValueError('Ajan, istek veya secili model kayitli kaynak goreviyle eslesmiyor')
    veri=ajanli_okuma.pencereyi_oku(tarama,ajan_oturumu,arac_cagrisi)
    son_izin=json.loads(izin_yolu.read_text(encoding='utf-8'))
    if son_izin.get('acik') is not True or son_izin.get('kusak')!=kusak:raise ValueError('Kaynak penceresi teslim edilmeden tam okuma kapandi')
    return veri

def kod_teslimini_onayla(ajan_oturumu,kusak,arac_cagrisi,icerik_parmagi):
    bag=calisma_ortami.ortak_baglanti(ajan_oturumu)
    ajan=bag.istek('GET','/api/session/'+ajan_oturumu)['data'];ana=ajan.get('parentID')
    if not ana or not ajan.get('metadata',{}).get('tam_okuma_ajan'):raise ValueError('Teslim yalniz atanmis tam okuma ajanina acik')
    izin_yolu=KOK/'yerel-izinler'/(ana+'.json');izin=json.loads(izin_yolu.read_text(encoding='utf-8'))
    if izin.get('acik') is not True or izin.get('kusak')!=kusak:raise ValueError('Tam okuma kapali veya eski teslim')
    kok=KOK/'taramalar'/('ajanli-'+ana);gosterge=json.loads((kok/'etkin-okuma.json').read_text(encoding='utf-8'))
    if gosterge.get('kusak')!=kusak:raise ValueError('Okuma gorevinin kusagi degisti')
    tarama=kok/gosterge['istek'];kayit=json.loads((tarama/'ajan-kaydi.json').read_text(encoding='utf-8'))
    if ajan.get('model')!=kayit['secim']['model'] or ajan.get('agent')!=kayit['secim']['agent']:
        raise ValueError('Ajanin secili model veya ajan kimligi degisti')
    sonuc=ajanli_okuma.pencere_teslimini_onayla(tarama,ajan_oturumu,kusak,arac_cagrisi,icerik_parmagi)
    son= json.loads(izin_yolu.read_text(encoding='utf-8'))
    if son.get('acik') is not True or son.get('kusak')!=kusak:raise ValueError('Model istegi oncesinde tam okuma kapandi')
    return sonuc

def yurut(istek):
    oturum=istek.get('oturum','');eylem=istek.get('eylem')
    if not re.fullmatch(r'ses_[A-Za-z0-9_-]+',oturum):raise ValueError('Gecersiz kullanici oturumu')
    if eylem=='kod_penceresi':return kod_penceresi(oturum,istek.get('kusak'),istek.get('arac_cagrisi'))
    if eylem=='kod_teslimini_onayla':return kod_teslimini_onayla(oturum,istek.get('kusak'),istek.get('arac_cagrisi'),istek.get('icerik_parmagi'))
    kok=KOK/'taramalar'/('ajanli-'+oturum);gosterge=kok/'etkin-okuma.json'
    once=json.loads(gosterge.read_text()) if gosterge.exists() else None
    if once and not re.fullmatch(r'msg_[A-Za-z0-9_-]+',once.get('istek','')):raise ValueError('Okuma kaydi kimligi gecersiz')
    tarama=kok/once['istek'] if once else kok;yol=tarama/'ajan-kaydi.json'
    if eylem=='durdur':
        return ajanli_okuma.durdur(calisma_ortami.ortak_baglanti(oturum),tarama)
    if eylem not in ['baslat','devam','durum','cikti']:raise ValueError('Gecersiz islem; eski kucuk gorev kuyrugu kullanilmiyor')
    def acik():
        try:
            izin=json.loads((KOK/'yerel-izinler'/(oturum+'.json')).read_text())
            return izin.get('acik') is True and izin.get('kusak')==istek.get('kusak')
        except (OSError,ValueError):return False
    if not acik():raise ValueError('Tam okuma modu kapali veya cagri eski calistirmaya ait')
    if eylem in ['durum','cikti']:
        if not yol.is_file():return {'okuma_tamam':False,'aciklama':'Bu oturumda yeni ajanli okuma henuz baslatilmadi.'}
        sonuc=rapora_ekle(ajanli_okuma.ozet(json.loads(yol.read_text())),tarama)
        if sonuc['istek_kimligi']!=istek.get('istek_kimligi'):
            sonuc.update(onceki_okuma_tamam=sonuc['okuma_tamam'],okuma_tamam=False,ajan_incelemeleri_tamam=False,aciklama='Bu onceki is emrinin kaydidir. Guncel kullanici isi icin baslat gerekli; eski sonuc yeni isi tamamlamaz.')
        return sonuc
    kok.mkdir(parents=True,exist_ok=True)
    with uygulama.kilit(kok/'calisma.kilit'),calisma_ortami.yerel_calisma(oturum) as (bag,ana,model):
        istek_kimligi=istek.get('istek_kimligi')
        if not istek_kimligi or not re.fullmatch(r'msg_[A-Za-z0-9_-]+',istek_kimligi):raise ValueError('Guncel kullanici is emri kimligi gerekli')
        yeni=eylem=='baslat' and (not once or once['istek']!=istek_kimligi or once.get('kusak')!=istek.get('kusak'))
        if yeni:
            kok.mkdir(parents=True,exist_ok=True)
            tarama=kok/istek_kimligi;yol=tarama/'ajan-kaydi.json'
            if yol.exists():raise ValueError('Bu is emri daha once baslatildi; ayni istekte otomatik yeni tarama acilmaz')
        elif once and once.get('kusak')!=istek.get('kusak') and eylem!='devam':raise ValueError('Eski calistirma kendiliginden surdurulmez; yeni is emri gerekli')
        if yol.is_file():
            kayit=json.loads(yol.read_text())
            if kayit['secim']!={'agent':ana['agent'],'model':ana['model'],'parentID':oturum}:raise ValueError('Secili model veya ajan degisti; eski secimle devam edilmedi')
            kaynak=istek.get('kaynak')
            if kaynak and str(Path(kaynak).expanduser().resolve())!=kayit['kaynak']:raise ValueError('Bu oturumun okuma kaynagi farkli; yol degistirilerek yeniden baslatilamaz')
        else:
            kaynak=Path(istek.get('kaynak') or ana['location']['directory']).expanduser().resolve()
            if not kaynak.is_dir() or kaynak in (Path('/'),Path.home()):raise ValueError('Kodun bulundugu proje dizini gerekli')
            if kaynak==tarama or kaynak in tarama.parents:raise ValueError('Kaynak ve tarama kaydi ic ice olamaz')
            kayit=ajanli_okuma.hazirla(bag,ana,model,kaynak,tarama,istek_kimligi)
        if yeni:uygulama.json_yaz(gosterge,{'istek':istek_kimligi,'kusak':istek.get('kusak')})
        with uygulama.kilit(tarama/'surucu.kilit'):
            kayit['kusak']=istek.get('kusak')
            if eylem=='devam':
                ajanli_okuma.devami_hazirla(bag,kayit,istek_kimligi)
                uygulama.json_yaz(gosterge,{'istek':once['istek'] if once else kayit['istek_kimligi'],'kusak':istek.get('kusak')})
            if not kayit['ajanlar'] and not kayit.get('planlama_tamam'):
                sayac=yerlesik_sayim.bul(kayit['sinir'])
                if not sayac:raise ValueError('OpenCode yerlesik sayaci veya model baglam siniri yok')
                try:ajanli_okuma.plani_hazirla(kayit,sayac)
                finally:sayac.kapat()
            sonuc=ajanli_okuma.sur(bag,kayit,acik)
            if eylem=='devam':sonuc.update(surdurulen_is_emri=kayit['istek_kimligi'],istek_kimligi=istek_kimligi)
            return rapora_ekle(sonuc,tarama)

if __name__=='__main__':
    try:print(json.dumps(yurut(json.load(sys.stdin)),ensure_ascii=False))
    except (Exception,KeyboardInterrupt) as hata:print('HATA: '+str(hata),file=sys.stderr);sys.exit(1)
