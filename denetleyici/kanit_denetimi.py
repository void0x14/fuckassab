#!/usr/bin/env python3
"""Native cocuklarin secim mirasini ve sunucudaki eksiksiz girdi teslimini denetler."""
import sys
sys.dont_write_bytecode=True
import json
from pathlib import Path
import uygulama
import calisma_ortami
KOK=uygulama.KOK

def denetle(tarama):
    kayit=uygulama.kaynak_denetle(tarama);secim=kayit['secim']
    if not secim.get('parentID') or not secim.get('agent'):raise ValueError('Eski ayri motor kaydi native kabul sayilmaz')
    bag=calisma_ortami.ortak_baglanti(secim['parentID']);uygulama.BAGLANTI=bag
    ana=bag.istek('GET','/api/session/'+secim['parentID'])['data'];durum=uygulama.durum(tarama)
    if not durum['baglanti_tamam']:raise ValueError('Native okuma veya baglanti incelemesi henuz tamamlanmadi')
    if ana.get('model')!=secim['model'] or ana.get('agent')!=secim['agent']:raise ValueError('Secim degisti; eski secim guncel secim diye sunulmadi')
    teslimler=[];ham_dizini=KOK/'kanitlar/yerel-cocuklar';ham_dizini.mkdir(parents=True,exist_ok=True)
    with uygulama.veritabani(tarama) as veri:isler=[dict(i) for i in veri.execute('SELECT * FROM isler ORDER BY kimlik')]
    for is_kaydi in isler:
        if is_kaydi['durum']!='tamam':raise ValueError('Tamamlanmamis is var')
        kimlik=is_kaydi['oturum'];bilgi=bag.istek('GET','/api/session/'+kimlik)['data']
        if bilgi.get('parentID')!=ana['id'] or bilgi.get('agent')!=secim['agent'] or bilgi.get('model')!=secim['model'] or bilgi.get('permissions')!=calisma_ortami.YASAK:raise ValueError('Native parent/secim/izin devri uyusmuyor')
        iletiler=uygulama.iletileri_oku(kimlik);bas=next(s for s,i in enumerate(iletiler) if i['id']==is_kaydi['ileti'])
        son=next((s for s in range(bas+1,len(iletiler)) if iletiler[s]['type']=='user'),len(iletiler));bolum=iletiler[bas:son]
        girdi=(tarama/'denemeler'/f"{is_kaydi['kimlik']}-{is_kaydi['deneme']}"/'girdi.txt').read_text()
        if bolum[0].get('text')!=girdi:raise ValueError('Sunucuda saklanan tam prompt eslesmiyor')
        for parca in uygulama.girdi_parcalari(is_kaydi):
            if uygulama.parca_oku(tarama,kayit['parcalar'][parca-1]).decode() not in girdi:raise ValueError('Ham kaynak girdide eksik')
        uygulama.yaniti_denetle(bolum,is_kaydi,secim['model'])
        cevap=next(i for i in bolum if i['type']=='assistant')
        if not cevap.get('tokens',{}).get('output'):raise ValueError('Gercek cikarim jeton kaydi yok')
        uygulama.json_yaz(ham_dizini/(kimlik+'.json'),{'oturum':bilgi,'iletiler':iletiler})
        teslimler.append({'is':is_kaydi['kimlik'],'tur':is_kaydi['tur'],'oturum':kimlik,'parentID':bilgi['parentID'],'agent':bilgi['agent'],'model':bilgi['model'],'girdi_parmagi':uygulama.parmak(girdi.encode()),'girdi_bayti':len(girdi.encode()),'tam_girdi_eslesmesi':True,'ham_parcalar':uygulama.girdi_parcalari(is_kaydi),'bitis':cevap['finish'],'jetonlar':cevap['tokens'],'maliyet':cevap.get('cost')})
    defter=uygulama.kapsam_defterini_yaz(tarama)
    if not defter['tum_baytlar_teslim']:raise ValueError('Tum baytlarin teslimi tamam degil')
    sonuc={'sonuc':'gecti','tur':'mevcut_sunucuda_gercek_yerel_cikarim','tarama':str(tarama),'cagiran_oturum':ana['id'],'secim':secim,'teslimler':teslimler,'kaynak_bayti':sum(d['bayt'] for d in kayit['dosyalar'] if d['durum']=='dahil'),'kaynak_satiri':sum(d['satir'] for d in kayit['dosyalar'] if d['durum']=='dahil'),'tam_kapsam':True,'baglanti_tamam':True,'anlam':'Sunucuda saklanan prompt ve ham kaynak eslesir; her satirin anlasilmasi veya kusur kaniti garantisi degildir. Kucuk kabul ornegidir, Malachite tam taramasi degildir.'}
    uygulama.json_yaz(KOK/'kanitlar/yerel-teslim-kabulu.json',sonuc);return sonuc

def ana():
    ayrac=uygulama.TurkceAyrac(description=__doc__,add_help=False,formatter_class=uygulama.TurkceYardim)
    ayrac.add_argument('--yardim',action='help',help='Yardimi goster');ayrac.add_argument('--tarama',required=True,type=Path,help='Native kabul taramasinin dizini')
    sec=ayrac.parse_args();print(json.dumps(denetle(sec.tarama.resolve()),ensure_ascii=False,indent=2));return 0
if __name__=='__main__':
    try:sys.exit(ana())
    except Exception as hata:print('HATA: '+str(hata),file=sys.stderr);sys.exit(1)
