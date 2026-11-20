#!/usr/bin/env python3
"""Saglayici cagrisi yapmayan Turkce ozdenetimler."""
import sys
sys.dont_write_bytecode = True
import concurrent.futures
import contextlib
import io
import json
import re
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
import urllib.error
import uygulama
import calisma_ortami

class Denetimler(unittest.TestCase):
    def setUp(kendisi):
        kendisi.gecici=tempfile.TemporaryDirectory(dir=uygulama.KOK,prefix='sinama-')
        kendisi.alan=Path(kendisi.gecici.name);kendisi.kaynak=kendisi.alan/'kaynak';kendisi.kaynak.mkdir()
        (kendisi.kaynak/'bir.py').write_bytes(('α = 1\r\n'*608+'末尾'*100+'\n'+'😀'*3000+'son').encode())
        (kendisi.kaynak/'bos').write_bytes(b'');(kendisi.kaynak/'ikili').write_bytes(b'\0\xff')
        kendisi.tarama=kendisi.alan/'tarama'
        kendisi.model={'limit':{'context':1000000,'output':384000}}
        kendisi.secim={'model':{'id':'sinama','providerID':'sinama'},'agent':'secili','parentID':'ses_sinama'}
        uygulama.hazirla(kendisi.kaynak,kendisi.tarama,kendisi.secim,kendisi.model,64,9)
    def tearDown(kendisi):kendisi.gecici.cleanup()
    def yanit(kendisi,is_kaydi,baglantilar=None):
        return {'is_kimligi':is_kaydi['kimlik'],'aciklamalar':[{'parca_kimligi':k,'aciklama':'Verilen kaynak bolumunun somut davranisi.'} for k in uygulama.isle_ilgili_parcalar(is_kaydi)],'baglantilar':baglantilar or [],'varsayimlar':[]}
    def sinama_kapali_mod_yeni_is_dagitmaz(kendisi):
        with mock.patch.object(uygulama,'isi_calistir') as calistir,contextlib.redirect_stdout(io.StringIO()):
            uygulama.sur(kendisi.tarama,2,2,0,10,lambda:False)
            calistir.assert_not_called()
    def sinama_sabit_oturum_ve_ayri_motor_kapali(kendisi):
        with kendisi.assertRaises(ValueError):calisma_ortami.ortak_baglanti()
        with kendisi.assertRaises(RuntimeError):calisma_ortami.ozel_calisma()
    def sinama_acik_is_kapaninca_sonraki_dagitilmaz(kendisi):
        acik=[True]
        def calistir(*_):acik[0]=False;return 'Devam eden is gozlemi korundu'
        with mock.patch.object(uygulama,'isi_calistir',side_effect=calistir) as c,contextlib.redirect_stdout(io.StringIO()):
            uygulama.sur(kendisi.tarama,1,2,0,10,lambda:acik[0])
            kendisi.assertEqual(c.call_count,1)
    def sinama_eski_kusak_yeniden_acilinca_yurumez(kendisi):
        import yerel_kopru
        izin=kendisi.alan/'yerel-izinler';izin.mkdir()
        (izin/'ses_sinama.json').write_text(json.dumps({'acik':True,'kusak':'yeni'}))
        with mock.patch.object(yerel_kopru,'KOK',kendisi.alan),mock.patch.object(calisma_ortami,'yerel_calisma') as bag:
            with kendisi.assertRaises(ValueError):yerel_kopru.yurut({'oturum':'ses_sinama','eylem':'devam','kusak':'eski'})
            bag.assert_not_called()
    def sinama_etkin_kodda_sabit_saglayici_ve_sunucu_yok(kendisi):
        import inspect
        kod=inspect.getsource(calisma_ortami)
        for yasak in ['DASHSCOPE','alibaba-cn','deepseek-v4.1','ses_e20f','subprocess.Popen','OPENCODE_CONFIG_CONTENT']:
            kendisi.assertNotIn(yasak,kod)
    def sinama_kapama_yalniz_sahipli_cocugu_keser(kendisi):
        import yerel_kopru
        tarama=kendisi.alan/'taramalar/yerel-ses_sinama';tarama.parent.mkdir();shutil.copytree(kendisi.tarama,tarama)
        is_kaydi=uygulama.isi_al(tarama,2)
        with uygulama.veritabani(tarama) as veri:veri.execute('UPDATE isler SET oturum=?,ileti=? WHERE kimlik=?',('ses_sahipli','msg_sahipli',is_kaydi['kimlik']))
        cagrilar=[]
        def yanit(yontem,yol,govde=None):
            cagrilar.append((yontem,yol,govde))
            if yol=='/api/session/ses_sahipli':return {'data':{'parentID':'ses_sinama','metadata':{'tam_okuma_iscisi':True}}}
            if yol.endswith('/inbox'):return {'data':[{'id':'msg_sahipli'},{'id':'msg_diger'}]}
            return {'interrupted':True}
        sahte=mock.Mock();sahte.istek.side_effect=yanit
        with mock.patch.object(yerel_kopru,'KOK',kendisi.alan),mock.patch.object(calisma_ortami,'ortak_baglanti',return_value=sahte):sonuc=yerel_kopru.durdur('ses_sinama')
        kendisi.assertEqual(sonuc['kesilen_cocuklar'],['ses_sahipli'])
        kendisi.assertIn(('POST','/api/session/ses_sahipli/interrupt',{'resume':False}),cagrilar)
        kendisi.assertIn(('DELETE','/api/session/ses_sahipli/inbox/msg_sahipli',None),cagrilar)
        kendisi.assertFalse(any('msg_diger' in yol or 'ses_normal' in yol for _,yol,_ in cagrilar))
        durum=uygulama.durum(tarama);kendisi.assertFalse(durum['okuma_tamam']);kendisi.assertTrue(any(i['durum']=='hata' for i in durum['isler']))
    def sinama_bir_kaynak_parcasi_iki_isle_cift_sayilmaz(kendisi):
        import yerel_kopru
        kaynak=kendisi.alan/'sayim-kaynagi';kaynak.mkdir();ham=b'sayi = 1\nsayi += 1\nprint(sayi)\n';(kaynak/'hesap.py').write_bytes(ham)
        tarama=kendisi.alan/'sayim-taramasi';uygulama.hazirla(kaynak,tarama,kendisi.secim,kendisi.model)
        with uygulama.veritabani(tarama) as bag:
            bag.execute("INSERT INTO isler(tur,parcalar,sahip) VALUES('baglanti','[1]','baglanti-sayim')")
            bag.execute("UPDATE isler SET durum='tamam',deneme=1")
            isler=[dict(i) for i in bag.execute('SELECT * FROM isler ORDER BY kimlik')]
        for is_kaydi in isler:
            dizin=tarama/'denemeler'/f"{is_kaydi['kimlik']}-1";dizin.mkdir();uygulama.json_yaz(dizin/'gecerli.json',kendisi.yanit(is_kaydi))
        ozet=yerel_kopru.ozet(tarama)
        kendisi.assertEqual(ozet['is_sayisi'],2)
        kendisi.assertEqual(ozet['benzersiz_kaynak_parca_sayisi'],1)
        kendisi.assertEqual(ozet['teslim_edilen_kaynak_parca_sayisi'],1)
        kendisi.assertEqual(ozet['kaynak_dosya_sayisi'],1)
        kendisi.assertEqual(ozet['kaynak_satir_sayisi'],3)
        kendisi.assertEqual(ozet['kaynak_bayt_sayisi'],len(ham))
        kendisi.assertEqual([a['tur'] for a in ozet['aciklamalar']],['okuma','baglanti'])
        kendisi.assertEqual([a['parca_sayisi'] for a in ozet['aciklamalar']],[1,1])
    def sinama_bayt_satir_ve_buyuk_utf8(kendisi):
        kayit=uygulama.kaynak_denetle(kendisi.tarama)
        for dosya in kayit['dosyalar']:
            if dosya['durum']!='dahil':continue
            veri=(kendisi.kaynak/dosya['yol']).read_bytes();parcalar=[p for p in kayit['parcalar'] if p['yol']==dosya['yol']]
            kendisi.assertEqual(b''.join(uygulama.parca_oku(kendisi.tarama,p) for p in parcalar),veri)
            for parca in parcalar:
                uygulama.parca_oku(kendisi.tarama,parca).decode('utf-8')
                kendisi.assertEqual(parca['ilk_satir'],veri[:parca['bas']].count(b'\n')+1)
                son=veri[:parca['son']];satir=son.count(b'\n')+int(bool(son) and not son.endswith(b'\n'))
                kendisi.assertEqual(parca['son_satir'],max(parca['ilk_satir'],satir))
    def sinama_degisiklik(kendisi):
        (kendisi.kaynak/'bir.py').write_text('degisti')
        with kendisi.assertRaises(ValueError):uygulama.kaynak_denetle(kendisi.tarama)
    def sinama_yeni_dosya(kendisi):
        (kendisi.kaynak/'yeni').write_text('yeni')
        with kendisi.assertRaises(ValueError):uygulama.kaynak_denetle(kendisi.tarama)
    def sinama_sembolik_bag_ve_acik_kapsam(kendisi):
        (kendisi.kaynak/'bag').symlink_to('/etc/hostname')
        kendisi.assertTrue(any(k['durum']=='engel' for k in uygulama.envanter(kendisi.kaynak,[])))
        with kendisi.assertRaises(ValueError):uygulama.kaynak_denetle(kendisi.tarama)
    def sinama_ic_bag_hedefi_bir_kez_okunur(kendisi):
        (kendisi.kaynak/'ic-bag').symlink_to('bir.py')
        (kendisi.kaynak/'ana-dizine-bag').symlink_to('.')
        tarama=kendisi.alan/'bagli-tarama'
        uygulama.hazirla(kendisi.kaynak,tarama,kendisi.secim,kendisi.model)
        kayit=uygulama.kaynak_denetle(tarama)
        baglar=[d for d in kayit['dosyalar'] if d['durum']=='ic-bag']
        kendisi.assertEqual({d['hedef'] for d in baglar},{'bir.py','.'})
        kendisi.assertEqual(sum(d['durum']=='dahil' and d['yol']=='bir.py' for d in kayit['dosyalar']),1)
        kendisi.assertFalse(any(p['yol'] in ('ic-bag','ana-dizine-bag') for p in kayit['parcalar']))
    def sinama_dongulu_bag_sessiz_atlanmaz(kendisi):
        (kendisi.kaynak/'dongu').symlink_to('dongu')
        kayit=uygulama.envanter(kendisi.kaynak,[])
        engel=next(d for d in kayit if d['yol']=='dongu')
        kendisi.assertEqual(engel['durum'],'engel');kendisi.assertIn('dongulu',engel['gerekce'])
    def sinama_sabit_ve_envanter_bozulmasi(kendisi):
        kayit=uygulama.envanteri_oku(kendisi.tarama);parca=kayit['parcalar'][0]
        (kendisi.tarama/'sabitler'/parca['dosya_parmagi']).write_bytes(b'bozuk')
        with kendisi.assertRaises(ValueError):uygulama.parca_oku(kendisi.tarama,parca)
        (kendisi.tarama/'envanter.json').write_text('{}')
        with kendisi.assertRaises(ValueError):uygulama.envanteri_oku(kendisi.tarama)
    def sinama_ayni_dosya_sirali_diger_sahipler_paralel(kendisi):
        ilk=uygulama.isi_al(kendisi.tarama,2)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as havuz:
            digerleri=list(havuz.map(lambda _:uygulama.isi_al(kendisi.tarama,2),range(8)))
        alinmis=[i for i in digerleri if i]
        kendisi.assertTrue(alinmis)
        kendisi.assertTrue(all(i['sahip']!=ilk['sahip'] for i in alinmis))
        kimlikler=[ilk['kimlik']]+[i['kimlik'] for i in alinmis];kendisi.assertEqual(len(kimlikler),len(set(kimlikler)))
        uygulama.tamamla(kendisi.tarama,ilk,kendisi.yanit(ilk),uygulama.envanteri_oku(kendisi.tarama))
        sonraki=uygulama.isi_al(kendisi.tarama,2);kendisi.assertEqual(sonraki['sahip'],ilk['sahip'])
    def sinama_okuma_bitmeden_baglanti_yok(kendisi):
        with uygulama.veritabani(kendisi.tarama) as bag:bag.execute("INSERT INTO isler(tur,parcalar,sahip) VALUES('baglanti','[1]','baglanti-sinama')")
        kendisi.assertFalse(uygulama.durum(kendisi.tarama)['baglanti_tamam'])
        for _ in range(3):
            is_kaydi=uygulama.isi_al(kendisi.tarama,2)
            if is_kaydi:kendisi.assertEqual(is_kaydi['tur'],'okuma')
        with uygulama.veritabani(kendisi.tarama) as bag:
            bag.execute("UPDATE isler SET durum='hata',deneme=2 WHERE tur='okuma'")
        kendisi.assertIsNone(uygulama.isi_al(kendisi.tarama,2))
    def sinama_baglanti_notu_yeni_is_acmaz(kendisi):
        with uygulama.veritabani(kendisi.tarama) as bag:
            bag.execute("UPDATE isler SET durum='tamam' WHERE tur='okuma'")
            bag.execute("INSERT INTO isler(tur,parcalar,sahip) VALUES('baglanti','[1]','baglanti-sinama')")
        is_kaydi=uygulama.isi_al(kendisi.tarama,2);kayit=uygulama.envanteri_oku(kendisi.tarama)
        yanit=kendisi.yanit(is_kaydi,[{'yol':'bir.py','ilk_satir':1,'son_satir':2,'gerekce':'Mevcut baglanti notu'}])
        uygulama.tamamla(kendisi.tarama,is_kaydi,yanit,kayit)
        with uygulama.veritabani(kendisi.tarama) as bag:
            kendisi.assertEqual(bag.execute("SELECT count(*) FROM isler WHERE tur='baglanti' AND durum!='bekliyor'").fetchone()[0],1)
            kendisi.assertEqual(bag.execute('SELECT durum FROM baglantilar').fetchone()[0],'baglam')
    def sinama_baglanti_tam_kodu_alir(kendisi):
        kayit=uygulama.envanteri_oku(kendisi.tarama)
        is_kaydi={'kimlik':1,'tur':'baglanti','parcalar':'[1,2]'}
        girdi=uygulama.girdiyi_hazirla(kendisi.tarama,is_kaydi,kayit)
        for parca in kayit['parcalar'][:2]:kendisi.assertIn(uygulama.parca_oku(kendisi.tarama,parca).decode(),girdi)
    def sinama_bitis_nedeni_ve_tam_aciklama(kendisi):
        is_kaydi=uygulama.isi_al(kendisi.tarama,2);yanit=kendisi.yanit(is_kaydi)
        cevap={'type':'assistant','time':{'completed':1},'finish':'stop','model':kendisi.secim['model'],'content':[{'type':'text','text':json.dumps(yanit)}]}
        iletiler=[cevap,{'type':'idle','outcome':'succeeded'}]
        uygulama.yaniti_denetle(iletiler,is_kaydi,kendisi.secim['model'])
        for bitis in ['length','error','unknown','tool-calls']:
            cevap['finish']=bitis
            with kendisi.assertRaises(ValueError):uygulama.yaniti_denetle(iletiler,is_kaydi,kendisi.secim['model'])
        cevap['finish']='stop';yanit['aciklamalar']=[];cevap['content'][0]['text']=json.dumps(yanit)
        with kendisi.assertRaises(ValueError):uygulama.yaniti_denetle(iletiler,is_kaydi,kendisi.secim['model'])
    def sinama_okuyucu_araci_reddeder(kendisi):
        is_kaydi=uygulama.isi_al(kendisi.tarama,2)
        iletiler=[{'type':'assistant','time':{'completed':1},'finish':'stop','model':kendisi.secim['model'],'content':[{'type':'tool'}]},{'type':'idle','outcome':'succeeded'}]
        with kendisi.assertRaises(ValueError):uygulama.yaniti_denetle(iletiler,is_kaydi,kendisi.secim['model'])
    def sinama_cift_surucu(kendisi):
        with uygulama.kilit(kendisi.tarama/'sinama.kilit'):
            with kendisi.assertRaises(ValueError):
                with uygulama.kilit(kendisi.tarama/'sinama.kilit'):pass
    def sinama_eski_tamamlanma_reddedilir(kendisi):
        is_kaydi=uygulama.isi_al(kendisi.tarama,2);kayit=uygulama.envanteri_oku(kendisi.tarama)
        uygulama.tamamla(kendisi.tarama,is_kaydi,kendisi.yanit(is_kaydi),kayit)
        with kendisi.assertRaises(ValueError):uygulama.tamamla(kendisi.tarama,is_kaydi,kendisi.yanit(is_kaydi),kayit)
    def sinama_kuru_kota_ve_model_limiti(kendisi):
        plan=uygulama.kota_plani(kendisi.tarama);kendisi.assertGreater(plan['okuma_istegi'],1)
        kendisi.assertGreater(plan['okuma_girdi_bayti'],plan['kaynak_bayt'])
        kendisi.assertEqual(uygulama.butce(kendisi.model)['cikis_payi'],384000)
        with kendisi.assertRaises(ValueError):uygulama.butce({'limit':{}})
    def sinama_kuru_boyut_gercek_utf8_girdiyle_ayni(kendisi):
        is_kaydi=uygulama.isi_al(kendisi.tarama,2);kayit=uygulama.envanteri_oku(kendisi.tarama)
        metin=uygulama.girdiyi_hazirla(kendisi.tarama,is_kaydi,kayit)
        kendisi.assertEqual(len(metin.encode()),uygulama.girdiyi_hazirla(kendisi.tarama,is_kaydi,kayit,yalniz_boyut=True))
    def sinama_oturum_donus_kuru_plani(kendisi):
        kaynak=kendisi.alan/'uzun-kaynak';kaynak.mkdir()
        (kaynak/'buyuk.rs').write_text(''.join(f'// satir {sira} α😀\n' for sira in range(2400)))
        tarama=kendisi.alan/'donuslu-tarama'
        plan=uygulama.hazirla(kaynak,tarama,kendisi.secim,{'limit':{'context':60000,'output':4000}},3000,8000)
        kendisi.assertEqual(plan['baglam_engelleri'],[])
        kendisi.assertGreaterEqual(plan['okuma_oturumu'],3)
        kendisi.assertEqual(plan['zorunlu_sinir_incelemesi'],plan['oturum_donus_sayisi'])
    def sinama_tasan_sinir_girdisi_kirpilmaz(kendisi):
        kayit=uygulama.envanteri_oku(kendisi.tarama)
        is_kaydi={'kimlik':1,'tur':'okuma','parcalar':'[1]','baglam':json.dumps([p['kimlik'] for p in kayit['parcalar']])}
        kayit['butce']['girdi_bayt_tavani']=1000
        with kendisi.assertRaisesRegex(ValueError,'kesilmedi'):uygulama.girdiyi_hazirla(kendisi.tarama,is_kaydi,kayit)
    def sinama_oturum_donus_tam_teslim_sira_ve_devam(kendisi):
        kaynak=kendisi.alan/'donus-kaynagi';kaynak.mkdir()
        asil=''.join(f'// kaynak {sira} α😀\n' for sira in range(2400)).encode()
        (kaynak/'buyuk.rs').write_bytes(asil)
        tarama=kendisi.alan/'uc-oturum'
        plan=uygulama.hazirla(kaynak,tarama,kendisi.secim,{'limit':{'context':60000,'output':4000}},3000,8000)
        kayit=uygulama.envanteri_oku(tarama);oturumlar={};gonderimler=[];asil_teslim={};sira=[]
        def sahte_istek(yontem,yol,govde=None):
            if yontem=='GET' and yol.endswith('/inbox'):return {'data':[]}
            if yontem=='GET':
                oturum=yol.rsplit('/',1)[-1]
                if oturum not in oturumlar:raise urllib.error.HTTPError(yol,404,'yok',None,None)
                return {'data':oturumlar[oturum]['bilgi']}
            if yol=='/api/session':
                oturumlar[govde['id']]={'bilgi':{'permissions':calisma_ortami.YASAK,'model':kendisi.secim['model'],'agent':kendisi.secim['agent'],'parentID':kendisi.secim['parentID']},'iletiler':[]}
                return {'data':oturumlar[govde['id']]['bilgi']}
            if yol.endswith('/prompt'):
                oturum=yol.split('/')[3];metin=govde['text'];kimlik=int(re.search(r'Gorev ([0-9]+)',metin).group(1))
                with uygulama.veritabani(tarama) as bag:
                    is_kaydi=dict(bag.execute('SELECT * FROM isler WHERE kimlik=?',(kimlik,)).fetchone())
                    kendisi.assertFalse(bag.execute("SELECT 1 FROM isler WHERE sahip=? AND kimlik<? AND durum!='tamam'",(is_kaydi['sahip'],kimlik)).fetchone())
                kendisi.assertLessEqual(len(metin.encode()),kayit['butce']['girdi_bayt_tavani'])
                for k in uygulama.girdi_parcalari(is_kaydi):kendisi.assertIn(uygulama.parca_oku(tarama,kayit['parcalar'][k-1]).decode(),metin)
                gonderimler.append((kimlik,oturum,metin));sira.append(kimlik)
                if is_kaydi['tur']=='okuma':
                    for k in uygulama.isle_ilgili_parcalar(is_kaydi):asil_teslim[k]=uygulama.parca_oku(tarama,kayit['parcalar'][k-1])
                iletiler=oturumlar[oturum]['iletiler']
                iletiler.append({'type':'user','id':govde['id'],'text':metin})
                # Gercek motor degil: yuksek sentetik kullanim ek bir erken donusu zorlar.
                iletiler.extend([{'type':'assistant','time':{'completed':1},'finish':'stop','model':kendisi.secim['model'],
                  'tokens':{'input':23000,'output':100},'content':[{'type':'text','text':json.dumps(kendisi.yanit(is_kaydi))}]},{'type':'idle','outcome':'succeeded'}])
                return {'data':{'id':govde['id']}}
            return None
        cokme_sinandi=False;okuma_oturumlari=set()
        with mock.patch.object(uygulama,'istek',side_effect=sahte_istek),mock.patch.object(uygulama,'iletileri_oku',side_effect=lambda o:oturumlar[o]['iletiler']):
            while True:
                is_kaydi=uygulama.isi_al(tarama,2)
                if not is_kaydi:break
                if is_kaydi['tur']=='baglanti':
                    kendisi.assertTrue(uygulama.durum(tarama)['okuma_tamam'])
                    kendisi.assertFalse(uygulama.durum(tarama)['baglanti_tamam'])
                if is_kaydi['tur']=='okuma' and json.loads(is_kaydi.get('baglam','[]')) and not cokme_sinandi:
                    with mock.patch.object(uygulama,'tamamla',side_effect=SystemExit('sentetik cokme')):
                        with kendisi.assertRaises(SystemExit):uygulama.isi_calistir(tarama,is_kaydi,3)
                    adet=len(gonderimler);uygulama.kurtar(tarama);is_kaydi=uygulama.isi_al(tarama,2)
                    sonuc=uygulama.isi_calistir(tarama,is_kaydi,3)
                    kendisi.assertEqual(len(gonderimler),adet);cokme_sinandi=True
                else:sonuc=uygulama.isi_calistir(tarama,is_kaydi,3)
                kendisi.assertIn('tamam',sonuc,sonuc)
        with uygulama.veritabani(tarama) as bag:
            okuma_oturumlari={i[0] for i in bag.execute("SELECT DISTINCT oturum FROM isler WHERE tur='okuma'")}
        kendisi.assertGreaterEqual(len(okuma_oturumlari),3);kendisi.assertTrue(cokme_sinandi)
        kendisi.assertEqual(b''.join(asil_teslim[k] for k in sorted(asil_teslim)),asil)
        kendisi.assertTrue(uygulama.kapsam_defterini_yaz(tarama)['tum_baytlar_teslim'])
        kendisi.assertTrue(uygulama.durum(tarama)['baglanti_tamam'])
        sinirlar=uygulama.oturum_sinirlari(tarama)
        kendisi.assertTrue(sinirlar);kendisi.assertTrue(all(s['inceleme_durumu']=='tamam' for s in sinirlar))
        kendisi.assertGreater(len(sinirlar),plan['oturum_donus_sayisi'])
        uygulama.json_yaz(kendisi.alan/'oturum-donus-sentetik.json',{'kanit_turu':'Sentetik; gercek saglayici cagrisi yok',
            'kaynak_bayt':len(asil),'okuma_oturumu':len(okuma_oturumlari),'oturum_siniri':len(sinirlar),'tum_baytlar_teslim':True,
            'ham_sinir_baglami_denetlendi':True,'sira_korundu':True,'sinir_incelemeleri_tamam':True,'cokme_devam_ayni_girdi':cokme_sinandi})
    def sinama_kucuk_dosyalar_gruplanir(kendisi):
        yeni=kendisi.alan/'kucuk';yeni.mkdir()
        for sira in range(20):(yeni/f'bolum-{sira}.py').write_text('deger = 1\n')
        tarama=kendisi.alan/'gruplu'
        plan=uygulama.hazirla(yeni,tarama,kendisi.secim,kendisi.model)
        kendisi.assertEqual(plan['okuma_istegi'],1)
    def sinama_cokme_sonrasi_ayni_girdi_yeniden_gonderilmez(kendisi):
        is_kaydi=uygulama.isi_al(kendisi.tarama,2);oturumlar={};gonderim=[]
        def sahte_istek(yontem,yol,govde=None):
            if yontem=='GET' and yol.endswith('/inbox'):return {'data':[]}
            if yontem=='GET':
                oturum=yol.rsplit('/',1)[-1]
                if oturum not in oturumlar:raise urllib.error.HTTPError(yol,404,'yok',None,None)
                return {'data':oturumlar[oturum]}
            if yol=='/api/session':
                oturumlar[govde['id']]={'permissions':calisma_ortami.YASAK,'model':kendisi.secim['model'],'agent':kendisi.secim['agent'],'parentID':kendisi.secim['parentID']}
                return {'data':oturumlar[govde['id']]}
            if yol.endswith('/prompt'):gonderim.append(govde);return {'data':{'id':govde['id']}}
            return None
        def sahte_iletiler(oturum):
            if not gonderim:return []
            girdi=gonderim[-1]
            return [{'type':'user','id':girdi['id'],'text':girdi['text']},{'type':'assistant','time':{'completed':1},'finish':'stop','model':kendisi.secim['model'],
                'content':[{'type':'text','text':json.dumps(kendisi.yanit(is_kaydi))}]},{'type':'idle','outcome':'succeeded'}]
        with mock.patch.object(uygulama,'istek',side_effect=sahte_istek),mock.patch.object(uygulama,'iletileri_oku',side_effect=sahte_iletiler):
            with mock.patch.object(uygulama,'tamamla',side_effect=SystemExit('cokme')):
                with kendisi.assertRaises(SystemExit):uygulama.isi_calistir(kendisi.tarama,is_kaydi,2)
            uygulama.kurtar(kendisi.tarama);devam=uygulama.isi_al(kendisi.tarama,2)
            kendisi.assertIn('tamam',uygulama.isi_calistir(kendisi.tarama,devam,2));kendisi.assertEqual(len(gonderim),1)
    @unittest.skipUnless((uygulama.KOK/'kusur_dogrulama.py').is_file(),'Yerel kusur deneyi bu dağıtımda yok')
    def sinama_sabit_json_kusur_kaniti_degil(kendisi):
        import kusur_dogrulama
        with uygulama.veritabani(kendisi.tarama) as bag:
            bag.execute("UPDATE isler SET durum='tamam'")
            is_kimligi=bag.execute('SELECT kimlik FROM isler ORDER BY kimlik LIMIT 1').fetchone()[0]
            bag.execute('INSERT INTO varsayimlar(is_kimligi,iddia,curutme) VALUES(?,?,?)',(is_kimligi,'Kaynakla iliskisi olmayan sabit beyan','Kaynak cagrisi olmadigini incele'))
        alanlar=[];betikler=[]
        def sahte_istek(yontem,yol,govde=None):
            if yol=='/api/session':return {'data':{'id':'sentetik-oturum'}}
            if yol.endswith('/prompt'):
                betik=Path(re.search(r'(/[^ \n]+/yeniden_uretim.py)',govde['text']).group(1));alanlar.append(betik.parent)
                anahtar=re.search(r'"anahtar":"([a-z0-9]+)"',govde['text']).group(1)
                sabit={'anahtar':anahtar,'uretim':True,'beklenen':'kaynak sozlesmesi','gerceklesen':'5','aciklama':'Bu sabit beyan hicbir kaynak kodunu cagirmiyor.'}
                betikler.append('import json\nprint(json.dumps('+repr(sabit)+'))\n')
                return {'data':{'id':'sentetik-ileti'}}
            return {'data':{'id':'sentetik-oturum'}}
        iletiler=[{'type':'assistant','model':kendisi.secim['model'],'time':{'completed':1},'finish':'stop',
            'content':[{'type':'text','text':''}]},{'type':'idle','outcome':'succeeded'}]
        def sahte_yanit(_):
            iletiler[0]['content'][0]['text']=json.dumps({'betik':betikler[-1]});return iletiler
        try:
            with mock.patch.object(uygulama,'istek',side_effect=sahte_istek),mock.patch.object(uygulama,'iletileri_oku',side_effect=sahte_yanit):
                sonuc=kusur_dogrulama.dogrula(kendisi.tarama,1,2)
            kendisi.assertEqual(sonuc['durum'],'inceleme_bekliyor','Iki esit sabit JSON ciktisi kaynakla iliskili kusur kaniti sayilmamali')
            kendisi.assertEqual(sonuc['tekrar_sayisi'],2)
        finally:
            for alan in alanlar:shutil.rmtree(alan)
    def sinama_ortak_dosyaya_yazma_teknik_olarak_engellenir(kendisi):
        ortak=str(Path(sys.executable).resolve())
        kod='import os,errno;\ntry: os.close(os.open('+repr(ortak)+',os.O_WRONLY)); raise SystemExit(4)\nexcept OSError as hata: assert hata.errno==errno.EROFS; print("engellendi")'
        sonuc=subprocess.run(calisma_ortami.salt_okunur_komut(kendisi.alan,[sys.executable,'-B','-c',kod]),capture_output=True,text=True)
        kendisi.assertEqual(sonuc.returncode,0,sonuc.stderr);kendisi.assertEqual(sonuc.stdout.strip(),'engellendi')

def ana():
    yukleyici=unittest.TestLoader();yukleyici.testMethodPrefix='sinama_'
    topluluk=yukleyici.loadTestsFromTestCase(Denetimler);akis=io.StringIO()
    sonuc=unittest.TextTestRunner(stream=akis,verbosity=0).run(topluluk)
    ozet={'toplam':sonuc.testsRun,'atlanan':len(sonuc.skipped),'basarili':sonuc.testsRun-len(sonuc.failures)-len(sonuc.errors)-len(sonuc.skipped),
        'basarisiz':len(sonuc.failures),'hata':len(sonuc.errors),'sonuc':'gecti' if sonuc.wasSuccessful() else 'kalmadi'}
    if not sonuc.wasSuccessful():ozet['teknik_hatalar']=[metin for _,metin in sonuc.errors+sonuc.failures]
    print(json.dumps(ozet,ensure_ascii=False,indent=2));return 0 if sonuc.wasSuccessful() else 1

if __name__=='__main__':sys.exit(ana())
