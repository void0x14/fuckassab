"""OpenCode'un yerlesik baglam olcusuyle sirali kaynak akisi."""
import hashlib
import concurrent.futures
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import time
import uygulama
import calisma_ortami
import yerlesik_sayim

KOK=Path(__file__).resolve().parent

def kullanim(cevap):
    jeton=cevap.get('tokens',{});onbellek=jeton.get('cache',{})
    alanlar=[jeton.get('input'),onbellek.get('read',0),onbellek.get('write',0),jeton.get('output',0),jeton.get('reasoning',0)]
    if any(type(x) is not int or x<0 for x in alanlar) or sum(alanlar[:3])==0:return None
    return sum(alanlar)

def alan(sinir,kullanilan):
    pencere=sinir['context']
    cevap=min(sinir['output'], max(32768, pencere//8))
    sistem=max(16384,pencere//16)
    bos=pencere-kullanilan-cevap-sistem
    if pencere<=cevap+sistem:raise ValueError('Model baglami kaynak ve cevap icin yeterli degil')
    return max(0,int(bos/1.15))

def dilimle(dosyalar,oku,imlec,tavan):
    """UTF-8 baytlarini atlamadan sirayla alir; bir teslim yeni ajan demek degildir."""
    sira,bas=imlec;teslimler=[];kalan=tavan
    while sira<len(dosyalar) and kalan>0:
        d=dosyalar[sira];veri=oku(d)
        if hashlib.sha256(veri).hexdigest()!=d['parmak']:raise ValueError('Sabit kaynak degisti')
        baslik=len(f"\nDOSYA {d['yol']} | BAYT [{bas},{len(veri)})\nKAYNAK BASI\n\nKAYNAK SONU\n".encode())
        if kalan<=baslik:break
        son=min(len(veri),bas+kalan-baslik)
        while son<len(veri) and son>bas and veri[son]&0xC0==0x80:son-=1
        if son==bas and bas<len(veri):break
        teslimler.append({'yol':d['yol'],'parmak':d['parmak'],'bas':bas,'son':son,'metin':veri[bas:son].decode('utf-8')})
        kalan-=son-bas+baslik
        if son==len(veri):sira+=1;bas=0
        else:bas=son;break
    return teslimler,[sira,bas]

def bildirim(kayit,asama):
    o=ozet(kayit);o['asama']=asama
    with (Path(kayit['tarama'])/'olaylar.jsonl').open('a',encoding='utf-8') as olaylar:
        olaylar.write(json.dumps({k:o[k] for k in ('zaman','asama','istek_kimligi','ajan_sayisi','kaynak_dosya_sayisi','kaynak_bayt_sayisi','teslim_edilen_bayt','tamamlanan_dosya','ajanlar','okuma_tamam','hata')},ensure_ascii=False)+'\n')
    print(json.dumps(o,ensure_ascii=False),file=sys.stderr,flush=True)

def ozet(kayit):
    tamam=kayit['imlec'][0]==len(kayit['dosyalar']) and not kayit.get('bekleyen')
    son=all(a.get('son_inceleme') for a in kayit['ajanlar'])
    notlar=[]
    for a in kayit['ajanlar']:
        notlar.extend({'oturum':a['oturum'],'not':n} for n in a.get('notlar',[]))
    plan=kayit.get('ajan_plani',[])
    ajan_ozetleri=[]
    for i,a in enumerate(kayit['ajanlar']):
        token=a.get('opencode_kullanimi') or {}
        tahmin=plan[i].get('yerlesik_tahmin') if i<len(plan) else None
        ajan_ozetleri.append({'oturum':a['oturum'],'gercek_kullanim_tokeni':a.get('kullanilan'),'pencere_metni_tahmini':tahmin,
            'opencode_kullanimi':token,'eski_api_kaydi':a.get('api_jetonlari'),'son_inceleme':a.get('son_inceleme',False)})
    return {'tarama':kayit['tarama'],'istek_kimligi':kayit.get('son_is_istegi',kayit['istek_kimligi']),'secim':kayit.get('secim'),'duzen':'ajan_basina_dolu_baglam',
        'ajan_sayisi':len(kayit['ajanlar']),'kaynak_dosya_sayisi':len(kayit['dosyalar']),
        'tamamlanan_ajan_sayisi':sum(bool(a.get('son_inceleme')) for a in kayit['ajanlar']),
        'kaynak_bayt_sayisi':sum(d['bayt'] for d in kayit['dosyalar']),
        'teslim_edilen_bayt':sum(t['son']-t['bas'] for t in kayit['teslimler']),
        'tamamlanan_dosya':kayit['imlec'][0],'model_baglam_siniri':kayit['sinir']['context'],
        'ajanlar':ajan_ozetleri,'zaman':datetime.now(timezone.utc).isoformat(),
        'okuma_tamam':tamam and son,'asil_kapsam_tamam':tamam,'ajan_incelemeleri_tamam':tamam and son,
        'hata':kayit.get('hata'),'ayrintili_cikti':str(Path(kayit['tarama'])/'ajan-kaydi.json'),
        'inceleme_notlari':notlar[:100],'inceleme_notu_sayisi':len(notlar),
        'planlanan_ajan_sayisi':len(kayit.get('ajan_plani',[])) or None,'toplam_pencere_metni_tahmini':kayit.get('toplam_yerlesik_girdi_tahmini'),
        'token_sayim_notu':'Pencere tahmini OpenCode yerlesik olcusudur; sistem ve arac tanimlarini kapsamaz. Gercek kullanim tamamlanan OpenCode mesajlarindan alinir.',
        'dagitim':kayit.get('dagitim','opencode_yerlesik_plan'),
        'sinir':'Pencere boyutu OpenCode yerlesik tahminidir; gerçek kullanım tamamlanan OpenCode iletilerinden alınır. Kod teslimi anlama veya kusur kanıtı değildir. Ajanlar arası bağlantılar tamamlanmış sayılmaz.'}

def kaynak_denetle(kayit):
    guncel=uygulama.envanter(Path(kayit['kaynak']),['.git'])
    if guncel!=kayit['envanter']:raise ValueError('Kaynak agaci degisti; eski kapsama devam edilmedi')

def girdi(kayit,kimlik,teslimler,son):
    return (f"Kullanıcının işi: {kayit['amac']}\n"
        f"Bu ajan penceresini almak için tam_okuma_penceresi aracını bir kez çağır. Kod ilk iletiye konmaz; araç sabit sıradaki kod penceresini döndürür.\n"
        "Bu pencere sana atanan kaynakların tamamıdır; başka dosya isteme. Kodun nasıl çalıştığını kendi akıl yürütmenle çöz: verinin girişinden koşullara, çağrılara, sonuçlara ve hata yollarına kadar iz sür. Dosyalar arasındaki bağı ancak kod gösteriyorsa kur. Hazır başlık, JSON, puanlama, zorunlu bulgu sayısı veya rapor kalıbı yok; cevabın şeklini sen seç. Olmayan kusur uydurma. Kodun göstermediği bir şey varsa hangi parçanın eksik olduğunu söyle. Türkçe ve anlaşılır yaz; Axiom personası ve İngilizce hitap kullanma.")

def pencere_metni(kayit,teslimler):
    tarama=Path(kayit['tarama']);parcalar=[]
    for t in teslimler:
        ham=uygulama.sabit_oku(tarama/'sabitler'/t['parmak'])
        if hashlib.sha256(ham).hexdigest()!=t['parmak'] or not 0<=t['bas']<=t['son']<=len(ham):
            raise ValueError(f"Sabit kod penceresi yanlis: {t['yol']} [{t['bas']},{t['son']})")
        kod=ham[t['bas']:t['son']]
        ilk=ham[:t['bas']].count(b'\n')+1
        son_satir=ham[:t['son']].count(b'\n')+int(t['son']>0 and ham[t['son']-1]!=10)
        son_satir=max(ilk,son_satir)
        parcalar.append(f"KAYNAK {t['yol']} | SATIR {ilk}-{son_satir} | BAYT [{t['bas']},{t['son']})\n{kod.decode('utf-8')}")
    return '\n'.join(parcalar)

def sayim_girdisi(kayit,kimlik,teslimler,son):
    return girdi(kayit,kimlik,[],son)+'\n'+pencere_metni(kayit,teslimler)

def gorev_baslat(kayit,ajan,plan):
    dizin=Path(kayit['tarama'])/'ajan-gorevleri';dizin.mkdir(parents=True,exist_ok=True)
    yol=dizin/(ajan['oturum']+'.json')
    if yol.exists():raise ValueError('Ajan kaynak görevi zaten var; ikinci görev açılmadı')
    gorev={'ajan':ajan['oturum'],'ana':kayit['secim']['parentID'],'kusak':kayit.get('kusak'),
        'teslimler':plan['teslimler'],'okundu':False,'fisler':[]}
    uygulama.json_yaz(yol,gorev)

def pencereyi_oku(kayit_dizini,ajan,cagri):
    tarama=Path(kayit_dizini);yol=tarama/'ajan-gorevleri'/(ajan+'.json')
    if not yol.is_file():raise ValueError('Bu ajan için sabit kaynak penceresi atanmadı')
    with uygulama.kilit(yol.with_suffix('.kilit')):
        gorev=json.loads(yol.read_text(encoding='utf-8'))
        if gorev.get('ajan')!=ajan:raise ValueError('Bu ajan için kaynak görevi eşleşmedi')
        if gorev.get('okundu'):return {'icerik':'Bu sabit kaynak penceresi aynı ajan oturumunda zaten okundu. Önceki araç çıktısını kullanıp incelemeyi tamamla.','fisler':gorev['fisler'],'bayt':sum(f['bayt'] for f in gorev['fisler']),'dosya':len(gorev['fisler']),'yinelendi':True}
        kayit={'tarama':str(tarama)};metin=pencere_metni(kayit,gorev['teslimler']);fisler=[]
        for t in gorev['teslimler']:
            ham=uygulama.sabit_oku(tarama/'sabitler'/t['parmak']);kod=ham[t['bas']:t['son']]
            fisler.append({'yol':t['yol'],'parmak':t['parmak'],'bas':t['bas'],'son':t['son'],'bayt':len(kod),
                'kod_parmagi':hashlib.sha256(kod).hexdigest(),'arac_cagrisi':cagri})
        gorev.update(okundu=False,arac_hazirlandi=True,fisler=fisler,arac_cagrisi=cagri,
            icerik_parmagi=hashlib.sha256(metin.encode('utf-8')).hexdigest(),okuma_zamani=datetime.now(timezone.utc).isoformat())
        uygulama.json_yaz(yol,gorev)
    return {'icerik':metin,'fisler':fisler,'bayt':sum(f['bayt'] for f in fisler),'dosya':len(fisler)}

def pencere_teslimini_onayla(kayit_dizini,ajan,kusak,cagri,icerik_parmagi):
    tarama=Path(kayit_dizini);yol=tarama/'ajan-gorevleri'/(ajan+'.json')
    with uygulama.kilit(yol.with_suffix('.kilit')):
        gorev=json.loads(yol.read_text(encoding='utf-8'))
        if gorev.get('ajan')!=ajan or gorev.get('kusak')!=kusak or gorev.get('arac_cagrisi')!=cagri:
            raise ValueError('Kaynak penceresi, ajan veya acik calistirmayla eslesmiyor')
        kayit={'tarama':str(tarama)};metin=pencere_metni(kayit,gorev['teslimler'])
        parmak=hashlib.sha256(metin.encode('utf-8')).hexdigest()
        if not gorev.get('arac_hazirlandi') or parmak!=gorev.get('icerik_parmagi') or parmak!=icerik_parmagi:
            raise ValueError('OpenCode model istegindeki kaynak, atanmis tam pencereyle eslesmiyor')
        gorev.update(okundu=True,modele_iletildi=True,iletim_zamani=datetime.now(timezone.utc).isoformat())
        uygulama.json_yaz(yol,gorev)
    with (tarama/'olaylar.jsonl').open('a',encoding='utf-8') as olaylar:
        olaylar.write(json.dumps({'olay':'ajan_kod_araciyla_okudu','ajan':ajan,'arac_cagrisi':cagri,
            'icerik_parmagi':parmak,'bayt':sum(f['bayt'] for f in gorev['fisler']),'dosya':len(gorev['fisler']),
            'model_isteginde_teslim_edildi':True},ensure_ascii=False)+'\n')
    return {'okundu':True,'icerik_parmagi':parmak}

def gorev_okundu(kayit,ajan):
    yol=Path(kayit['tarama'])/'ajan-gorevleri'/(ajan+'.json')
    if not yol.is_file():return False
    gorev=json.loads(yol.read_text(encoding='utf-8'))
    return gorev.get('ajan')==ajan and gorev.get('okundu') is True and len(gorev.get('fisler',[]))==len(gorev.get('teslimler',[]))

def gorev_fisleri(kayit,ajan):
    yol=Path(kayit['tarama'])/'ajan-gorevleri'/(ajan+'.json')
    if not yol.is_file():return []
    return json.loads(yol.read_text(encoding='utf-8')).get('fisler',[])

def hazirla(bag,ana,model,kaynak,tarama,istek_kimligi):
    tarama.mkdir(parents=True,exist_ok=False);(tarama/'sabitler').mkdir();(tarama/'teslimler').mkdir()
    def sakla(d,veri):
        p=tarama/'sabitler'/d['parmak']
        if not p.exists():p.write_bytes(veri)
    envanter=uygulama.envanter(kaynak,['.git'],sakla)
    engeller=[d for d in envanter if d['durum']=='engel']
    if engeller:raise ValueError('Kaynak envanterinde engel var: '+str(engeller[:3]))
    kullanicilar=[m for m in iletiler(bag,ana['id']) if m['type']=='user']
    simdi=next((m for m in kullanicilar if m['id']==istek_kimligi),kullanicilar[-1] if kullanicilar else None)
    if not simdi or not simdi.get('text'):raise ValueError('Kullanicinin asil is emri bulunamadi')
    amac=simdi['text']
    if kullanicilar[0]['id']!=simdi['id']:amac='ILK IS EMRI:\n'+kullanicilar[0]['text']+'\nSIMDIKI IS EMRI:\n'+amac
    kayit={'surum':4,'tarama':str(tarama),'kaynak':str(kaynak),'secim':{'agent':ana['agent'],'model':ana['model'],'parentID':ana['id']},
        'sinir':model['limit'],'envanter':envanter,'dosyalar':[d for d in envanter if d['durum']=='dahil'],
        'amac':amac,'istek_kimligi':simdi['id'],'imlec':[0,0],'teslimler':[],'ajanlar':[],'bekleyen':None}
    uygulama.json_yaz(tarama/'ajan-kaydi.json',kayit);return kayit

def iletiler(bag,oturum):
    return uygulama.iletileri_oku(oturum,bag=bag)

def plani_hazirla(kayit,sayac):
    """Ajan pencerelerini OpenCode'un yerlesik token tahminiyle ayirir."""
    if kayit.get('ajanlar'):return
    tarama=Path(kayit['tarama']);kayit['sinir']['context']=min(kayit['sinir']['context'],sayac.sinir)
    bicim=sayac.bicim
    if kayit.get('planlama_tamam') and kayit.get('sayim_bicimi')==bicim:return
    if kayit.get('sayim_bicimi')!=bicim:
        if kayit.get('ajan_plani'):uygulama.json_yaz(tarama/'onceki-sayim-plani.json',{'ajan_plani':kayit['ajan_plani'],'gerekce':'OpenCode yerlesik tahmin bicimi degisti; ajan acilmadan yenilendi'})
        kayit['ajan_plani']=[];kayit.pop('sayim_iletisi',None);kayit['sayim_bicimi']=bicim
    tavan=alan(kayit['sinir'],0);plan=kayit.get('ajan_plani',[]);imlec=plan[-1]['imlec'] if plan else [0,0]
    kayit['dagitim']='opencode_baglam_plani';kayit['planlama_tamam']=False
    onbellek=kayit.setdefault('yerlesik_sayim_onbellegi',{})
    def olc(metin):
        anahtar=hashlib.sha256((bicim+'\n'+metin).encode()).hexdigest()
        if anahtar not in onbellek:
            onbellek[anahtar]=sayac.say(metin);uygulama.json_yaz(tarama/'ajan-kaydi.json',kayit)
        return onbellek[anahtar]
    oku=lambda d:uygulama.sabit_oku(tarama/'sabitler'/d['parmak'])
    kaynak_denetle(kayit)
    while imlec[0]<len(kayit['dosyalar']):
        kimlik=kayit.setdefault('sayim_iletisi','msg_'+secrets.token_hex(16))
        uygulama.json_yaz(tarama/'ajan-kaydi.json',kayit)
        butun_bayt=sum(d['bayt']+len(d['yol'].encode())+200 for d in kayit['dosyalar'][imlec[0]:])+4096
        hepsi,son_imlec=dilimle(kayit['dosyalar'],oku,imlec,butun_bayt)
        tam_metin=sayim_girdisi(kayit,kimlik,hepsi,True);bildirim(kayit,'Ajan penceresi OpenCode yerlesik olcusuyla hazirlaniyor')
        sayi=olc(tam_metin)
        if sayi<=tavan:en_iyi=(hepsi,son_imlec,tam_metin,sayi)
        else:
            alt=0;ust=butun_bayt;en_iyi=None;orta=min(tavan,butun_bayt)
            for _ in range(8):
                teslimler,sonra=dilimle(kayit['dosyalar'],oku,imlec,orta)
                if not teslimler:ust=orta;orta=(alt+ust)//2;continue
                metin=sayim_girdisi(kayit,kimlik,teslimler,True)
                adet=olc(metin)
                if adet<=tavan:
                    en_iyi=(teslimler,sonra,metin,adet);alt=orta
                    if tavan-adet<=8192:break
                else:ust=orta
                aday=int(orta*tavan/adet*.995)
                orta=aday if alt<aday<ust else (alt+ust)//2
            if en_iyi is None:raise ValueError('Istek ve kaynak secili OpenCode baglamina sigmiyor')
        teslimler,sonra,metin,adet=en_iyi
        if sonra==imlec:raise ValueError('Ajan pencere plani ilerlemiyor')
        plan.append({'kimlik':kimlik,'teslimler':[{k:v for k,v in t.items() if k!='metin'} for t in teslimler],
            'imlec':sonra,'son':True,'yerlesik_tahmin':adet})
        imlec=sonra;kayit['ajan_plani']=plan;kayit.pop('sayim_iletisi',None)
        uygulama.json_yaz(tarama/'ajan-kaydi.json',kayit);bildirim(kayit,f"OpenCode yerlesik olcusuyle {len(plan)} ajan penceresi ayrildi")
    kayit['ajan_plani']=plan;kayit['planlama_tamam']=True;kayit['dagitim']='paralel_opencode';kayit['toplam_yerlesik_girdi_tahmini']=sum(a['yerlesik_tahmin'] for a in plan)
    uygulama.json_yaz(tarama/'ajan-kaydi.json',kayit)

def ajani_ac(bag,kayit,plan):
    ajan={'oturum':'ses_'+secrets.token_hex(16),'kullanilan':0,'son_inceleme':False}
    bilgi=bag.istek('POST','/api/session',{'id':ajan['oturum'],'title':f"Tam okuma ajan {len(kayit['ajanlar'])+1}",**kayit['secim'],
        'metadata':{'tam_okuma_iscisi':True,'tam_okuma_ajan':True},'permissions':calisma_ortami.AJAN_OKUMA_IZNI})['data']
    if any(bilgi.get(k)!=kayit['secim'][k] for k in ['agent','model','parentID']) or bilgi.get('permissions')!=calisma_ortami.AJAN_OKUMA_IZNI:raise ValueError('Alt ajan secimi veya yalniz-okuma izni korunmadi')
    gorev_baslat(kayit,ajan,plan)
    kayit['ajanlar'].append(ajan);return ajan

def teslimi_kaydet(kayit,ajan,bekleyen,veri,kullanilan,jetonlar):
    if kullanilan is not None and kullanilan>kayit['sinir']['context']:raise ValueError('OpenCode kullanim sayaci model baglamini asti')
    tarama=Path(kayit['tarama'])
    fisler=gorev_fisleri(kayit,ajan['oturum'])
    if not gorev_okundu(kayit,ajan['oturum']):raise ValueError('Ajan kaynak penceresini araçla tamamlamadan sonuç vermedi')
    uygulama.json_yaz(tarama/'teslimler'/(bekleyen['kimlik']+'.json'),{'oturum':ajan['oturum'],'girdi':bekleyen['metin'],
        'kaynak_iletisi':bekleyen.get('kaynak_iletisi',bekleyen['kimlik']),'kaynak_girdisi':bekleyen.get('kaynak_girdisi',bekleyen['metin']),
        'aktarim_yontemi':'yalniz_okuma_araci','okuma_fisleri':fisler,'cevap':veri,'opencode_kullanimi':jetonlar})
    kayit['teslimler'].extend(dict(t,oturum=ajan['oturum'],ileti=bekleyen['kimlik']) for t in bekleyen['teslimler'])
    ajan['kullanilan']=kullanilan;ajan['opencode_kullanimi']=jetonlar;ajan['son_inceleme']=bekleyen['son'];ajan.setdefault('notlar',[]).extend(veri['notlar'])

def sur_paralel(bag,kayit,acik,cevapla):
    tarama=Path(kayit['tarama']);yol=tarama/'ajan-kaydi.json'
    if kayit.get('hata'):raise ValueError('Otomatik tekrar kapali: '+kayit['hata'])
    kaynak_denetle(kayit)
    for sira,plan in enumerate(kayit['ajan_plani']):
        if not acik():raise ValueError('Mod kapandi; yeni ajan acilmadi')
        if sira>=len(kayit['ajanlar']):
            ajan=ajani_ac(bag,kayit,plan);ajan['bekleyen']={**plan,'metin':girdi(kayit,plan['kimlik'],plan['teslimler'],True),'oturum':ajan['oturum']};uygulama.json_yaz(yol,kayit)
    bekleyenler=[a for a in kayit['ajanlar'] if not a.get('son_inceleme')]
    if not bekleyenler:return ozet(kayit)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(bekleyenler)) as havuz:
        etkin={havuz.submit(cevapla,bag,kayit,a,a['bekleyen'],acik):a for a in bekleyenler}
        try:
            bildirim(kayit,'Dolu ajan pencereleri ayni anda okunuyor')
            for gelecek in concurrent.futures.as_completed(etkin):
                ajan=etkin[gelecek];bekleyen=ajan['bekleyen'];veri,kullanilan,jetonlar=gelecek.result()
                teslimi_kaydet(kayit,ajan,bekleyen,veri,kullanilan,jetonlar);ajan['bekleyen']=None
                imlec=[0,0]
                for sira,a in enumerate(kayit['ajanlar']):
                    if not a.get('son_inceleme'):break
                    imlec=kayit['ajan_plani'][sira]['imlec']
                kayit['imlec']=imlec;uygulama.json_yaz(yol,kayit);bildirim(kayit,'Bir ajan tam kaynak penceresini bitirdi')
        except BaseException as hata:
            kayit['hata']=str(hata);uygulama.json_yaz(yol,kayit)
            for ajan in bekleyenler:
                if ajan.get('son_inceleme'):continue
                try:bag.istek('POST',f"/api/session/{ajan['oturum']}/interrupt",{'resume':False})
                except OSError:pass
            raise
    kaynak_denetle(kayit);return ozet(kayit)

def devami_hazirla(bag,kayit,istek_kimligi):
    """Yalniz yeni kullanici devam emri, yarim teslimi ayni ajanda surdurur."""
    kaynak_denetle(kayit)
    if istek_kimligi==kayit['istek_kimligi'] or istek_kimligi in kayit.get('devam_istekleri',[]):
        if kayit.get('hata') or kayit.get('duraklatildi'):raise ValueError('Otomatik tekrar kapali; yeni kullanici devam emri gerekli')
        return
    bekleyenler=([kayit['bekleyen']] if kayit.get('bekleyen') else [])+[a['bekleyen'] for a in kayit['ajanlar'] if a.get('bekleyen')]
    for bekleyen in bekleyenler:
        mesajlar=iletiler(bag,bekleyen['oturum'])
        kaynak_kimligi=bekleyen.get('kaynak_iletisi',bekleyen['kimlik'])
        kaynak_girdisi=bekleyen.get('kaynak_girdisi',bekleyen['metin'])
        asil=next((m for m in mesajlar if m['type']=='user' and m['id']==kaynak_kimligi),None)
        if asil and asil.get('text')!=kaynak_girdisi:raise ValueError('Devam edilecek native ham kaynak farkli')
        bas=next((i for i,m in enumerate(mesajlar) if m['type']=='user' and m['id']==bekleyen['kimlik']),None)
        bitisler=[] if bas is None else [m for m in mesajlar[bas:] if m['type']=='idle']
        hazir=False
        if bitisler and bitisler[-1].get('outcome')=='succeeded':
            try:hazir=tamamlanan_yanit(mesajlar,kayit,bekleyen) is not None
            except (ValueError,KeyError,TypeError):pass
        if not hazir:
            yeni='msg_'+secrets.token_hex(16)
            if asil:
                metin=f"Kullanıcı aynı kaynak incelemesini sürdürmeni istedi. Kaynak penceresi bu ajan oturumunda kayıtlı. Önceki kod incelemesini kendi akıl yürütmenle tamamla; kaynak eksikse tam_okuma_penceresi aracını çağır. KULLANICININ İŞİ:\n{kayit['amac']}\nHazır başlık, JSON veya rapor kalıbı kullanma; kodun nasıl çalıştığını kanıtına dayanarak Türkçe açıkla."
                bekleyen.update(kaynak_iletisi=kaynak_kimligi,kaynak_girdisi=kaynak_girdisi,metin=metin,kimlik=yeni)
            else:
                bekleyen['metin']=girdi(kayit,yeni,bekleyen['teslimler'],bekleyen['son']);bekleyen['kimlik']=yeni
    kayit.pop('hata',None);kayit['duraklatildi']=False;kayit['son_is_istegi']=istek_kimligi;kayit.setdefault('devam_istekleri',[]).append(istek_kimligi)
    uygulama.json_yaz(Path(kayit['tarama'])/'ajan-kaydi.json',kayit)

def tamamlanan_yanit(mesajlar,kayit,bekleyen):
    bas=next((i for i,m in enumerate(mesajlar) if m['type']=='user' and m['id']==bekleyen['kimlik']),None)
    if bas is None:return None
    donus=mesajlar[bas:];sonlar=[m for m in donus if m['type']=='idle']
    if not sonlar:return None
    if sonlar[-1].get('outcome')!='succeeded':raise ValueError('Alt ajan basarili bitmedi')
    yanitlar=[m for m in donus if m['type']=='assistant']
    if not yanitlar:raise ValueError('Alt ajandan cevap gelmedi')
    cevap=yanitlar[-1]
    if cevap.get('finish')!='stop' or cevap.get('error') or not cevap.get('time',{}).get('completed'):raise ValueError('Alt ajan cevabi kesik veya hatali')
    if any(m.get('model')!=kayit['secim']['model'] for m in yanitlar):raise ValueError('Alt ajan secili model disina cikti')
    if donus[0].get('text')!=bekleyen['metin']:raise ValueError('Native ham kaynak eslesmedi')
    if not gorev_okundu(kayit,bekleyen['oturum']):raise ValueError('Alt ajan kaynak penceresini okuma araciyle almadan bitirdi')
    ham=''.join(p['text'] for p in cevap['content'] if p['type']=='text').strip()
    if not ham:raise ValueError('Alt ajan içerikli inceleme cevabı vermedi')
    jetonlar=[m.get('tokens') or {} for m in yanitlar]
    cache={'read':sum((x.get('cache') or {}).get('read',0) for x in jetonlar),'write':sum((x.get('cache') or {}).get('write',0) for x in jetonlar)}
    toplam={'input':sum(x.get('input',0) or 0 for x in jetonlar),'output':sum(x.get('output',0) or 0 for x in jetonlar),
        'reasoning':sum(x.get('reasoning',0) or 0 for x in jetonlar),'cache':cache}
    return {'metin':ham,'notlar':[ham]},kullanim({'tokens':toplam}),toplam

def cevabi_oku(bag,kayit,ajan,bekleyen,acik,sure=300):
    oturum=ajan['oturum'];kimlik=bekleyen['kimlik'];metin=bekleyen['metin']
    once=iletiler(bag,oturum)
    if bekleyen.get('kaynak_iletisi'):
        asil=next((m for m in once if m['type']=='user' and m['id']==bekleyen['kaynak_iletisi']),None)
        if not asil or asil.get('text')!=bekleyen['kaynak_girdisi']:raise ValueError('Devam icin gerekli tam native kaynak bulunamadi')
    kullanici=next((m for m in once if m['type']=='user' and m['id']==kimlik),None)
    if kullanici and kullanici.get('text')!=metin:raise ValueError('Native kaynak teslimi degisti')
    if not kullanici:
        kuyruk=bag.istek('GET',f'/api/session/{oturum}/inbox')['data']
        varsa=next((m for m in kuyruk if m['id']==kimlik),None)
        if varsa and varsa.get('payload',{}).get('text')!=metin:raise ValueError('Native kuyruk girdisi farkli')
        if not varsa:
            if not acik():raise ValueError('Mod kapali; yeni kaynak gonderilmedi')
            bag.istek('POST',f'/api/session/{oturum}/prompt',{'id':kimlik,'text':metin})
    bitis=time.monotonic()+sure
    while time.monotonic()<bitis:
        if not acik():raise ValueError('Mod kapandi; kaynak akisi durdu')
        mesajlar=iletiler(bag,oturum)
        sonuc=tamamlanan_yanit(mesajlar,kayit,bekleyen)
        if sonuc is not None:return sonuc
        time.sleep(.5)
    raise TimeoutError('Alt ajan cevap suresi doldu; otomatik tekrar yapilmadi')

def sur(bag,kayit,acik,cevapla=cevabi_oku):
    if not kayit.get('ajan_plani'):
        raise ValueError('OpenCode yerleşik ölçüsüyle kaynak pencere planı hazırlanmadı')
    if not kayit.get('planlama_tamam'):
        raise ValueError('OpenCode yerleşik sayım planı yarım; kaynak aktarımı başlamadı')
    return sur_paralel(bag,kayit,acik,cevapla)

def durdur(bag,tarama):
    yol=tarama/'ajan-kaydi.json'
    if not yol.exists():return {'durum':'iptal','kesilen_cocuklar':[]}
    kayit=json.loads(yol.read_text());kesilen=[]
    for ajan in kayit['ajanlar']:
        if ajan.get('son_inceleme'):continue
        bilgi=bag.istek('GET','/api/session/'+ajan['oturum'])['data']
        if bilgi.get('parentID')!=kayit['secim']['parentID'] or not bilgi.get('metadata',{}).get('tam_okuma_iscisi'):raise ValueError('Kesilecek oturum bu taramaya ait degil')
        bekleyen=ajan.get('bekleyen') or kayit.get('bekleyen')
        if bekleyen and bekleyen['oturum']==ajan['oturum']:
            for ileti in bag.istek('GET','/api/session/'+ajan['oturum']+'/inbox')['data']:
                if ileti['id']==bekleyen['kimlik']:bag.istek('DELETE',f"/api/session/{ajan['oturum']}/inbox/{ileti['id']}")
        bag.istek('POST','/api/session/'+ajan['oturum']+'/interrupt',{'resume':False});kesilen.append(ajan['oturum'])
    kayit['duraklatildi']=True;uygulama.json_yaz(yol,kayit)
    return {'durum':'iptal','kesilen_cocuklar':kesilen,'yarim_is_tamam_sayilmadi':True}
