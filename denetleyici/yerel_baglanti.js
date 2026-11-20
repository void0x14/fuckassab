/** Tam okuma modu: baslangicta kapali, yalniz cagiran oturum ve cocuklari. */
import { randomUUID, createHash } from 'node:crypto';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const KOK=path.dirname(fileURLToPath(import.meta.url));
const ARAC='tam_kod_okuma';
const OKUMA_ARACI='tam_okuma_penceresi';
export default {
 id:'tam-kod-okuma',
 async setup(baglam){
  const etkin=new Set(),kusaklar=new Map(),kayitlar=[],calisan=new Map(),kapanis=new Map(),ajan_turlari=new Map();
  // Yeni yukleme kapali baslar; baska yuklemelerin sahipli izinlerini degistirmez.
  function izin_yaz(oturum,acik){const dizin=path.join(KOK,"yerel-izinler");mkdirSync(dizin,{recursive:true});writeFileSync(path.join(dizin,oturum+".json"),JSON.stringify({acik,kusak:kusaklar.get(oturum),konum:baglam.location.directory}));}
  function istek_yaz(olay,govde){const alanlar=['max_tokens','max_completion_tokens','max_output_tokens'].filter(k=>Number.isInteger(govde[k]));if(!alanlar.length)throw new Error('Ajan isteğinde çıkış sınırı bulunamadı.');for(const k of alanlar)govde[k]=Math.min(govde[k],65536);const cikis=Math.min(...alanlar.map(k=>govde[k]));const basliklar=new Headers(olay.request.headers);basliklar.delete('content-length');olay.request=new Request(olay.request,{headers:basliklar,body:JSON.stringify(govde)});return cikis;}
  function etkin_kayit(oturum){try{const kok=path.join(KOK,'taramalar','ajanli-'+oturum),gosterge=JSON.parse(readFileSync(path.join(kok,'etkin-okuma.json'),'utf8'));return JSON.parse(readFileSync(path.join(kok,gosterge.istek,'ajan-kaydi.json'),'utf8'));}catch{return null;}}
  function kaynak_bul(oturum,metin,varsayilan){for(const bulunan of String(metin||'').matchAll(/\/(?:[^\s]+)/g)){const aday=bulunan[0].replace(/[),.;>]+$/,'');try{if(statSync(aday).isDirectory())return path.resolve(aday);}catch{}}const kayit=etkin_kayit(oturum);if(kayit&&(kayit.hata||kayit.ajanlar?.some(a=>!a.son_inceleme)))return kayit.kaynak;return varsayilan;}
  function eylem_bul(oturum,kaynak,metin){if(/\b(yeniden|baştan|sıfırdan)\b/i.test(metin))return 'baslat';const durum=/\b(durum|ilerleme|ne kadar|ne oldu|çıktı|cikti)\b/i.test(metin)&&!/\b(oku|tara|incele|başlat|baslat|devam)\b/i.test(metin);if(durum)return 'durum';const kayit=etkin_kayit(oturum),suruyor=kayit&&(Boolean(kayit.hata)||kayit.ajanlar?.some(a=>!a.son_inceleme));return kayit&&path.resolve(kaynak)===kayit.kaynak&&suruyor?'devam':'baslat';}
  const bilgi=kimlik=>baglam.session.get({sessionID:kimlik});
  async function sahip(kimlik){
   const gorulen=new Set();
   while(kimlik&&!gorulen.has(kimlik)){
    if(etkin.has(kimlik))return kimlik;
    gorulen.add(kimlik);const oturum=await bilgi(kimlik);kimlik=oturum.parentID;
   }
  }
function kanit(ad,veri){const dizin=path.join(KOK,'kanitlar','yerel-kancalar');mkdirSync(dizin,{recursive:true});writeFileSync(path.join(dizin,ad.replace(/[^a-zA-Z0-9_-]/g,'_')+'.json'),JSON.stringify(veri,null,2));}
function tuiRaporu(x){
 const d=x.kapsama_denetcisi||{},satirlar=[`İnceleme: ${x.okuma_tamam?'kaynak okuma ve ajan cevapları tamam':'TAMAMLANMADI'}`,
  `Kaynak: ${x.kaynak_dosya_sayisi} dosya, ${x.teslim_edilen_bayt}/${x.kaynak_bayt_sayisi} bayt; ajan: ${x.ajan_sayisi}; seçili ajan: ${x.secim?.agent}; model: ${x.secim?.model?.providerID}/${x.secim?.model?.id} (${x.secim?.model?.variant})`,
  `Bayt denetimi: ${d.kapsama_tam?'tam geçti':'GEÇMEDİ'}; aralık: ${d.aralik_sayisi??0}; kayıtlı ham cevap: ${d.ham_cevap_dosyasi_sayisi??0}; hata: ${d.hatalar?.length??0}`,'','Ajanların gerçek cevapları:'];
 for(const [i,a] of (x.ajanlar||[]).entries()){
  const t=a.opencode_kullanimi||{},c=t.cache||{},toplam=Number.isInteger(a.gercek_kullanim_tokeni)?`${a.gercek_kullanim_tokeni} token`:'OpenCode kullanım sayısı yok';satirlar.push(`\n${i+1}. ajan ${a.oturum}: pencere metni tahmini ${a.pencere_metni_tahmini??'—'}; gerçek kullanım ${toplam} (girdi ${t.input??'—'}, çıktı ${t.output??'—'}, akıl yürütme ${t.reasoning??'—'}, önbellek ${c.read??'—'}/${c.write??'—'})`);
  for(const n of x.inceleme_notlari||[])if(n.oturum===a.oturum)satirlar.push(n.not);
 }
 satirlar.push('','Kayıtlar:',`Ham: ${x.ham_kayit||x.ayrintili_cikti||''}`,`Okunur özet: ${x.oturum_ozeti||''}`,`Makine denetimi: ${x.kapsama_json||''}`,`İlerleme günlüğü: ${x.olay_gunlugu||'bu eski oturumda yok'}`);
 return satirlar.join('\n');
}
function tuiSonucu(x){
 const d=x.kapsama_denetcisi||{},ajanlar=x.ajanlar||[],olculen=ajanlar.filter(a=>Number.isInteger(a.gercek_kullanim_tokeni));
 const toplam=olculen.reduce((n,a)=>n+a.gercek_kullanim_tokeni,0),sayi=n=>Number(n||0).toLocaleString('tr-TR');
 const satirlar=[`Tam okuma: ${x.okuma_tamam?'TAMAM':'TAMAMLANMADI'}`,
  `Kaynak: ${d.dosya_sayisi??x.kaynak_dosya_sayisi} dosya; ${sayi(d.aktarilan_bayt)}/${sayi(d.kaynak_bayti)} bayt. Ajan: ${ajanlar.length}. Seçili: ${x.secim?.agent}; ${x.secim?.model?.providerID}/${x.secim?.model?.id} (${x.secim?.model?.variant}).`,
  `OpenCode gerçek kullanımı: ${olculen.length?sayi(toplam):'yok'} token (${olculen.length}/${ajanlar.length} ajan kullanım sayısı verdi).`,
  `Bayt denetimi: ${d.kapsama_tam?'GEÇTİ':'GEÇMEDİ'}; hata: ${d.hatalar?.length??0}.`];
 for(const [i,a] of ajanlar.length<=8?ajanlar.entries():ajanlar.slice(-8).entries()){
  const t=a.opencode_kullanimi||{},c=t.cache||{};
  satirlar.push(`Ajan ${ajanlar.length<=8?i+1:ajanlar.length-7+i} (${a.oturum}): pencere metni tahmini ${a.pencere_metni_tahmini??'yok'}; gerçek ${Number.isInteger(a.gercek_kullanim_tokeni)?sayi(a.gercek_kullanim_tokeni):'yok'}; giriş/çıkış/akıl yürütme/önbellek ${t.input??'—'}/${t.output??'—'}/${t.reasoning??'—'}/${c.read??'—'}/${c.write??'—'}.`);
 }
 satirlar.push(`Tam ayrıntı: ${x.oturum_ozeti||''}`,`Makine kaydı: ${x.kapsama_json||''}`,`Ham kayıt: ${x.ham_kayit||x.ayrintili_cikti||''}`);
 return satirlar.join('\n');
}
function tuiBasligi(x){
 const d=x.kapsama_denetcisi||{},ajanlar=x.ajanlar||[],olculen=ajanlar.filter(a=>Number.isInteger(a.gercek_kullanim_tokeni));
 const toplam=olculen.reduce((n,a)=>n+a.gercek_kullanim_tokeni,0),sayi=n=>Number(n||0).toLocaleString('tr-TR');
 const ayrinti=ajanlar.length<=5?ajanlar:ajanlar.slice(-5);
 const bas=ajanlar.length-ayrinti.length;
 const ajan_tokeni=ayrinti.map((a,i)=>`A${bas+i+1}: ${Number.isInteger(a.gercek_kullanim_tokeni)?sayi(a.gercek_kullanim_tokeni):'yok'}`).join(' · ');
 const tahmin=ajanlar.reduce((n,a)=>n+(Number.isInteger(a.pencere_metni_tahmini)?a.pencere_metni_tahmini:0),0);
 return `Tam okuma ${x.okuma_tamam?'TAMAM':'EKSİK'} · ${sayi(d.aktarilan_bayt)}/${sayi(d.kaynak_bayti)} bayt · ${x.secim?.agent||'ajan yok'} · ${x.secim?.model?.id||'model yok'}\nPencere metni tahmini: ${sayi(tahmin)} · OpenCode gerçek kullanımı: ${olculen.length?sayi(toplam):'yok'} token (${olculen.length}/${ajanlar.length} ajan)\nAjan tokenleri: ${ajan_tokeni||'yok'}${ajanlar.length>ayrinti.length?` · son ${ayrinti.length} ajan gösteriliyor`:''}\nAyrıntı: ${x.oturum_ozeti||x.ham_kayit||''}`;
}
  async function kopru(istek,cagri,sahipli){
   return new Promise((coz,reddet)=>{
    const surec=spawn('python3',['-B',path.join(KOK,'yerel_kopru.py')],{cwd:KOK,stdio:['pipe','pipe','pipe']});
    if(sahipli)sahipli.surec=surec;
    let cikti='',hata='',satir='';surec.stdout.on('data',veri=>{cikti+=veri.toString();});surec.stderr.on('data',veri=>{
     satir+=veri.toString();let son;
     while((son=satir.indexOf('\n'))>=0){const metin=satir.slice(0,son);satir=satir.slice(son+1);try{const ilerleme=JSON.parse(metin);if(cagri){const not=ilerleme.inceleme_notlari?.slice(-1)[0]?.not||'';const adet=ilerleme.planlanan_ajan_sayisi||ilerleme.ajan_sayisi||0;const label=[`${ilerleme.tamamlanan_ajan_sayisi||0}/${adet} ajan`,ilerleme.asama,not.slice(0,220)].filter(Boolean).join(' — ');void cagri.progress({label,tamamlanan_ajan:ilerleme.tamamlanan_ajan_sayisi||0,ajan_sayisi:adet,okuma_tamam:ilerleme.okuma_tamam,teslim_edilen_bayt:ilerleme.teslim_edilen_bayt,kaynak_bayt_sayisi:ilerleme.kaynak_bayt_sayisi}).catch(()=>{});}}catch{hata=(hata+'\n'+metin).slice(-2000);}}
    });
    const kes=()=>{surec.kill('SIGTERM');reddet(new Error('Sahipli tam okuma cagrisi iptal edildi.'));};
    cagri?.signal.addEventListener('abort',kes,{once:true});surec.on('error',reddet);
    surec.on('close',kod=>{
     // Native interrupt uygulanana kadar eski cagriyi bitirme: normal araclarla devam edemesin.
     if(sahipli?.iptal&&!cagri.signal.aborted)return;
     cagri?.signal.removeEventListener('abort',kes);
     if(kod!==0)return reddet(new Error('Denetleyici tamamlanamadi: '+(hata||cikti).slice(-1500)));
     try{coz(JSON.parse(cikti));}catch{reddet(new Error('Denetleyici cevabi okunamadi.'));}
    });surec.stdin.end(JSON.stringify(istek));
   });
  }
  kayitlar.push(await baglam.command.transform(duzenleyici=>duzenleyici.add({
   name:'tam-okuma',description:'Bu oturumda zorunlu tam kod okuma modunu ac veya kapat',
   async execute(cagri){
    const acik=!etkin.has(cagri.sessionID);
    if(acik){etkin.add(cagri.sessionID);kusaklar.set(cagri.sessionID,randomUUID());kapanis.set(cagri.sessionID,{istek:null,arac:false,tamam:false});}else{etkin.delete(cagri.sessionID);kapanis.delete(cagri.sessionID);}
    izin_yaz(cagri.sessionID,acik);
    let kesme_hatasi;
    const sahipli=[...(calisan.get(cagri.sessionID)||[])];
    if(!acik&&sahipli.length){
     for(const is of sahipli){is.iptal=true;is.kontrol?.abort();}
     try{
      await baglam.session.interrupt({sessionID:cagri.sessionID,resume:false});
      for(const is of sahipli)is.surec?.kill('SIGTERM');
      const kesme=await kopru({eylem:'durdur',oturum:cagri.sessionID,kusak:kusaklar.get(cagri.sessionID)});
      kanit('kapama-'+cagri.sessionID,kesme);
     }catch(hata){kesme_hatasi=hata;kanit('kapama-hatasi-'+cagri.sessionID,{hata:String(hata)});}
    }
    kanit('mod-'+cagri.sessionID,{oturum:cagri.sessionID,acik,izin_ajan_model_yazilmadi:true});
    await baglam.session.synthetic({sessionID:cagri.sessionID,text:acik?'Tam okuma modu ACIK. Proje icin normal is emrinizi verin.':'Tam okuma modu KAPALI. Yalniz bizim arac engelimiz kalkti; kendi izin ve secimleriniz korunuyor.',description:acik?'Tam okuma AÇIK':'Tam okuma KAPALI',resume:false});
    if(kesme_hatasi)throw new Error('Mod kapandi fakat sahipli is iptali basarisiz: '+kesme_hatasi.message);
   }
  })));
  kayitlar.push(await baglam.permission.hook('evaluate',async olay=>{
   const kok=await sahip(olay.sessionID);
   if(kok){const oturum=await bilgi(olay.sessionID),ajan=olay.sessionID!==kok&&oturum.parentID===kok&&oturum.metadata?.tam_okuma_ajan===true;
    if(!(olay.sessionID===kok&&olay.action===ARAC)&&!(ajan&&olay.action===OKUMA_ARACI)){olay.effect='deny';olay.message='Tam okuma modunda yalnız sabit sıradaki kaynak penceresi açıktır.';}}
  }));
  kayitlar.push(await baglam.tool.hook('execute.before',async olay=>{
   const kok=await sahip(olay.sessionID);
   if(kok){const oturum=await bilgi(olay.sessionID),ajan=olay.sessionID!==kok&&oturum.parentID===kok&&oturum.metadata?.tam_okuma_ajan===true;
    if(!(olay.sessionID===kok&&olay.tool===ARAC)&&!(ajan&&olay.tool===OKUMA_ARACI))throw new Error('Bu oturumda yalnız denetlenen tam okuma aracı kullanılabilir.');}
  }));
  kayitlar.push(await baglam.tool.transform(duzenleyici=>duzenleyici.add({
   name:ARAC,description:'Kodu OpenCode yerlesik token tahminiyle baglam pencerelerine boler; her pencere bir alt ajana gider ve pencereler paralel calisir. Gercek kullanim OpenCode iletilerinden okunur. Kucuk is kuyrugu ve otomatik tekrar yoktur.',
   input:{type:'object',properties:{eylem:{type:'string',enum:['baslat','devam','durum','cikti']},kaynak:{type:'string',description:'Kullanicinin belirttigi proje dizini'}},required:['eylem'],additionalProperties:false},
   options:{codemode:false,permission:ARAC},
   async execute(girdi,cagri){
    if(!etkin.has(cagri.sessionID))throw new Error('Bu oturumda /tam-okuma kapali.');
    const yaprak=kapanis.get(cagri.sessionID);
    const ana=await bilgi(cagri.sessionID);
    if(!ana.model||!ana.agent)throw new Error('Cagiran oturumun secili model ve ajani bulunamadi; secim uydurulmadi.');
    let eylem=girdi.eylem;
    if(girdi.kaynak&&yaprak?.metin?.includes(girdi.kaynak)){
     try{const kok=path.join(KOK,'taramalar','ajanli-'+cagri.sessionID),gosterge=JSON.parse(readFileSync(path.join(kok,'etkin-okuma.json'),'utf8')),kayit=JSON.parse(readFileSync(path.join(kok,gosterge.istek,'ajan-kaydi.json'),'utf8'));const suruyor=Boolean(kayit.hata)||kayit.ajanlar.some(a=>!a.son_inceleme);eylem=path.resolve(girdi.kaynak)===kayit.kaynak&&suruyor?'devam':'baslat';}
     catch{eylem='baslat';}
    }
    const istek={...girdi,eylem,oturum:cagri.sessionID,kusak:kusaklar.get(cagri.sessionID),istek_kimligi:yaprak?.istek,kaynak:girdi.kaynak||(eylem==='baslat'?ana.location.directory:null)};
    await cagri.progress({asama:'Native cocuklarla denetleyici calisiyor',oturum:ana.id});
    const sahipli={id:cagri.id,iptal:false};
    const acik_isler=calisan.get(cagri.sessionID)||new Set();acik_isler.add(sahipli);calisan.set(cagri.sessionID,acik_isler);
    let sonuc;
    try{sonuc=await kopru(istek,cagri,sahipli);}catch(hata){
     if(etkin.has(cagri.sessionID)&&!cagri.signal.aborted){
      await baglam.session.synthetic({sessionID:cagri.sessionID,text:String(hata.message),description:'Tam okuma HATA; otomatik tekrar durdu',resume:false});
      await baglam.session.interrupt({sessionID:cagri.sessionID,resume:false});
     }
     throw hata;
    }finally{acik_isler.delete(sahipli);if(!acik_isler.size)calisan.delete(cagri.sessionID);}
    if(yaprak&&kapanis.get(cagri.sessionID)===yaprak){yaprak.arac=true;yaprak.arac_kimligi=cagri.id;yaprak.tarama=sonuc.tarama;yaprak.tamam=sonuc.istek_kimligi===yaprak.istek&&sonuc.okuma_tamam===true&&sonuc.ajan_incelemeleri_tamam===true&&sonuc.asil_kapsam_tamam===true;}
    kanit(cagri.id,{istek,secim:{model:ana.model,agent:ana.agent},sonuc});
    const durum=tuiBasligi(sonuc);
    await baglam.session.synthetic({sessionID:cagri.sessionID,text:tuiSonucu(sonuc),description:durum,resume:false});
    // Yalniz content kullanilir: output alaninin semasiz donmesi native sozlesmeye aykiridir.
    return {content:tuiRaporu(sonuc),metadata:{truncated:false,tarama:sonuc.tarama,okuma_tamam:sonuc.okuma_tamam}};
   }
  })));
  kayitlar.push(await baglam.tool.transform(duzenleyici=>duzenleyici.add({
   name:OKUMA_ARACI,description:'Bu ajan için denetleyicinin sıraya koyduğu tek kaynak penceresini oku. Dosya veya aralık seçilemez.',
   input:{type:'object',properties:{},required:[],additionalProperties:false},
   options:{codemode:false,permission:OKUMA_ARACI},
   async execute(_girdi,cagri){
    const ana=await sahip(cagri.sessionID),oturum=await bilgi(cagri.sessionID),tur=ajan_turlari.get(cagri.sessionID);
    if(!ana||ana===cagri.sessionID||oturum.parentID!==ana||oturum.metadata?.tam_okuma_ajan!==true)throw new Error('Bu araç yalnız atanmış tam okuma ajanına açık.');
    if(!tur||tur.gonderim_sayisi<1||tur.gonderim_sayisi>2)throw new Error('Bu ajan turunda yalnız sabit kaynak penceresi açıktır.');
    if(tur.kod_icerigi){if(tur.tekrar_cagrisi)throw new Error('Aynı kaynak penceresi ikinci kez açılmaz.');tur.tekrar_cagrisi=true;}
    else if(tur.okuma_cagrisi)throw new Error('Aynı ajan turunda ikinci kaynak penceresi açılamaz.');
    const izin=JSON.parse(readFileSync(path.join(KOK,'yerel-izinler',ana+'.json'),'utf8'));
    if(!izin.acik||izin.kusak!==tur.kusak)throw new Error('Tam okuma modu kapalı veya bu çağrı eski.');
    await cagri.progress({label:'Sabit kaynak penceresi okunuyor'});
    const veri=await kopru({eylem:'kod_penceresi',oturum:cagri.sessionID,kusak:tur.kusak,arac_cagrisi:cagri.id},{signal:cagri.signal,progress:cagri.progress});
    const guncel=JSON.parse(readFileSync(path.join(KOK,'yerel-izinler',ana+'.json'),'utf8'));
    if(!guncel.acik||guncel.kusak!==tur.kusak)throw new Error('Tam okuma kapandı; kaynak penceresi teslim edilmedi.');
    if(tur.kod_icerigi)tur.tekrar_arac_cagrisi=cagri.id;else tur.arac_cagrisi=cagri.id;
    await cagri.progress({label:`${veri.dosya} dosyanın ${veri.bayt} baytı açıldı`});
    return {content:veri.icerik,metadata:{truncated:false,dosya:veri.dosya,bayt:veri.bayt,arac_cagrisi:cagri.id,yinelendi:veri.yinelendi===true}};
   }
  })));
  kayitlar.push(await baglam.tool.hook('execute.after',async olay=>{
   if(olay.tool!==OKUMA_ARACI||olay.status!=='completed')return;
   const oturum=await bilgi(olay.sessionID),tur=ajan_turlari.get(olay.sessionID);
   if(!oturum.metadata?.tam_okuma_ajan||!tur)throw new Error('Kaynak araci cevabi atanmamis ajan istegiyle eslesmiyor');
   if(tur.tekrar_arac_cagrisi===olay.id){if(olay.result.metadata?.yinelendi!==true)throw new Error('Tekrarlanan kaynak çağrısı yeni kod döndürdü');return;}
   if(tur.gonderim_sayisi!==1||olay.id!==tur.arac_cagrisi)throw new Error('Kaynak araci cevabi atanmamis ajan istegiyle eslesmiyor');
   if(olay.result.metadata?.truncated!==false)throw new Error('Kaynak penceresi kesilmis; teslim kabul edilmedi');
   const blok=olay.result.content,icerik=typeof blok==='string'?blok:Array.isArray(blok)?blok.map(x=>x.text||'').join(''):'';
   if(!icerik)throw new Error('Kaynak okuma araci bos icerik dondurdu');
   tur.arac_cagrisi=olay.id;tur.kod_icerigi=icerik;
  }));
  kayitlar.push(await baglam.session.hook('prompt',async olay=>{
   if(etkin.has(olay.sessionID)){
    const yaprak={istek:olay.messageID,metin:olay.prompt.text,arac:false,tamam:false};kapanis.set(olay.sessionID,yaprak);
    const ana=await bilgi(olay.sessionID),kaynak=kaynak_bul(olay.sessionID,olay.prompt.text,ana.location.directory),eylem=eylem_bul(olay.sessionID,kaynak,olay.prompt.text),kontrol=new AbortController(),sahipli={id:olay.messageID,iptal:false,kontrol};
    const isler=calisan.get(olay.sessionID)||new Set();isler.add(sahipli);calisan.set(olay.sessionID,isler);
    try{
     await baglam.session.synthetic({sessionID:olay.sessionID,text:`Tam okuma ${eylem==='devam'?'sürüyor':'başladı'}: ${kaynak}`,description:'Tam okuma başlıyor',resume:false});
     const sonuc=await kopru({eylem,kaynak,oturum:olay.sessionID,kusak:kusaklar.get(olay.sessionID),istek_kimligi:olay.messageID},{signal:kontrol.signal,progress:async x=>{
      const ajan=`${x.tamamlanan_ajan_sayisi||0}/${x.planlanan_ajan_sayisi||x.ajan_sayisi||0} ajan`,bayt=`${Number(x.teslim_edilen_bayt||0).toLocaleString('tr-TR')}/${Number(x.kaynak_bayt_sayisi||0).toLocaleString('tr-TR')} bayt`;
      await baglam.session.synthetic({sessionID:olay.sessionID,text:[x.asama,ajan,bayt].filter(Boolean).join(' · '),description:'Tam okuma ilerliyor',resume:false});
     }},sahipli);
     yaprak.arac=true;yaprak.tarama=sonuc.tarama;yaprak.tamam=sonuc.istek_kimligi===olay.messageID&&sonuc.okuma_tamam===true&&sonuc.ajan_incelemeleri_tamam===true&&sonuc.asil_kapsam_tamam===true;
     olay.prompt.text=`${olay.prompt.text}\n\nDenetimli tam okuma sonucu:\n${tuiRaporu(sonuc)}\n\nSonucu Türkçe, açıkça özetle. Araç çağırma. Kapsam denetimi tam değilse tamamlandı deme.`;
     await baglam.session.synthetic({sessionID:olay.sessionID,text:tuiBasligi(sonuc),description:tuiBasligi(sonuc).split('\n')[0],resume:false});
    }catch(hata){
     if(etkin.has(olay.sessionID)){
      yaprak.arac=true;yaprak.tamam=false;
      await baglam.session.synthetic({sessionID:olay.sessionID,text:String(hata.message),description:'Tam okuma HATA; tamamlanmadı',resume:false});
      await baglam.session.interrupt({sessionID:olay.sessionID,resume:false});
     }
     throw hata;
    }finally{isler.delete(sahipli);if(!isler.size)calisan.delete(olay.sessionID);}
   }
   const oturum=await bilgi(olay.sessionID);
   if(oturum.metadata?.tam_okuma_ajan){
    const izin=JSON.parse(readFileSync(path.join(KOK,'yerel-izinler',oturum.parentID+'.json'),'utf8'));
    let onceki_kod=false;
    try{const kok=path.join(KOK,'taramalar','ajanli-'+oturum.parentID),gosterge=JSON.parse(readFileSync(path.join(kok,'etkin-okuma.json'),'utf8')),gorev=JSON.parse(readFileSync(path.join(kok,gosterge.istek,'ajan-gorevleri',oturum.id+'.json'),'utf8'));onceki_kod=gorev.okundu===true&&gorev.modele_iletildi===true;}catch{}
    ajan_turlari.set(olay.sessionID,{ileti:olay.messageID,kusak:izin.kusak,gonderim_sayisi:0,okuma_cagrisi:false,onceki_kod});
   }
  }));
  kayitlar.push(await baglam.session.hook('http.request',async olay=>{
   const oturum=await bilgi(olay.sessionID);
   if(etkin.has(olay.sessionID)){
    const yaprak=kapanis.get(olay.sessionID);if(!yaprak)throw new Error('Tam okuma isteği bulunamadı.');
    const govde=await olay.request.clone().json();govde.tool_choice=yaprak.arac?'none':'required';const cikis=istek_yaz(olay,govde);kanit('ana-model-istegi-'+olay.sessionID,{istek:yaprak.istek,arac_gerekli:!yaprak.arac,cikis_siniri:cikis});return;
   }
   if(!oturum.metadata?.tam_okuma_ajan)return;
   const tur=ajan_turlari.get(olay.sessionID);
   const ana=oturum.parentID?await bilgi(oturum.parentID):undefined;
   const izni_oku=()=>JSON.parse(readFileSync(path.join(KOK,'yerel-izinler',oturum.parentID+'.json'),'utf8'));
   const izin=izni_oku();
   if(olay.kind!=='primary'||!tur||!ana||oturum.model?.providerID!==ana.model?.providerID||oturum.model?.id!==ana.model?.id||oturum.model?.variant!==ana.model?.variant||oturum.agent!==ana.agent||!izin.acik||izin.kusak!==tur.kusak)throw new Error('Secili ajan/model veya acik okuma gorevi degisti.');
   const sira=tur.gonderim_sayisi+1;
   const govde=await olay.request.clone().json(),metinler=[];
   function topla(deger,alan){
    if(typeof deger==='string'){if(['text','content','output','reasoning_content','instructions'].includes(alan))metinler.push(deger);return;}
    if(Array.isArray(deger)){for(const v of deger)topla(v,alan);return;}
    if(deger&&typeof deger==='object')for(const [k,v] of Object.entries(deger))topla(v,k);
   }
   topla(govde.messages||govde.input,'content');if(govde.instructions)topla(govde.instructions,'instructions');if(govde.system)topla(govde.system,'system');
   govde.tool_choice=tur.onceki_kod||sira>1?'none':'required';const cikis=istek_yaz(olay,govde);
   if(sira>=2&&!tur.onceki_kod){
    if(!metinler.some(m=>m.includes(tur.kod_icerigi)))throw new Error('Sabit kaynak penceresi OpenCode model isteginde yok; teslim kabul edilmedi.');
    if(sira===2)await kopru({eylem:'kod_teslimini_onayla',oturum:olay.sessionID,kusak:tur.kusak,arac_cagrisi:tur.arac_cagrisi,icerik_parmagi:createHash('sha256').update(tur.kod_icerigi).digest('hex')},{signal:olay.request.signal,progress:async()=>{}});
   }
   if(olay.request.signal.aborted)throw new Error('Sahipli model istegi iptal edildi.');
   const son_izin=izni_oku();if(!son_izin.acik||son_izin.kusak!==tur.kusak||olay.request.signal.aborted)throw new Error('Model istegi gonderilmeden mod kapandi.');
   tur.gonderim_sayisi=sira;if(sira===2)tur.okuma_cagrisi=true;
   kanit('gonderim-'+olay.sessionID+'-'+tur.gonderim_sayisi,{oturum:olay.sessionID,ileti:tur.ileti,istek_sirasi:tur.gonderim_sayisi,atanmis_kod_istege_eklendi:sira>=2||tur.onceki_kod,arac_secimi:govde.tool_choice,cikis_siniri:cikis,onceki_kod:tur.onceki_kod});
  }));
  kayitlar.push(await baglam.session.hook('retry',async olay=>{
   const oturum=await bilgi(olay.sessionID);
   if(etkin.has(olay.sessionID)||oturum.metadata?.tam_okuma_iscisi)olay.decision={retry:false};
  }));
  kayitlar.push(await baglam.session.hook('compaction',async olay=>{
   const oturum=await bilgi(olay.sessionID);
   if(!oturum.metadata?.tam_okuma_ajan)return;
   // Native ozetleme yerine ayni TAM mesaj penceresini sakla; ham kaynak kaybolmasin.
   olay.result={summary:'Tam kaynak penceresi eksiksiz korundu.',native:{messages:JSON.parse(JSON.stringify(olay.messages))}};
  }));
  kayitlar.push(await baglam.session.hook('experimental.idle',async olay=>{
   if(!etkin.has(olay.sessionID))return;
   const yaprak=kapanis.get(olay.sessionID);
   if(yaprak?.arac&&yaprak.tamam){kanit('bitis-kabulu-'+olay.sessionID,{oturum:olay.sessionID,istek:yaprak.istek,arac_kimligi:yaprak.arac_kimligi,tarama:yaprak.tarama,okuma_ajan_incelemeleri_ham_kapsam_onayli:true});return;}
   kanit('bitis-reddi-'+olay.sessionID,{oturum:olay.sessionID,istek:yaprak?.istek,arac_cagrildi:yaprak?.arac===true,okuma_ve_ajan_incelemesi_tamam:false});
   await baglam.session.synthetic({sessionID:olay.sessionID,text:'Kaynak teslimi veya alt ajan incelemesi tamamlanmadi. Bu is tamamlanmis sayilmadi.',description:'Tam okuma TAMAMLANMADI',resume:false});
   await baglam.session.interrupt({sessionID:olay.sessionID,resume:false});
  }));
  kayitlar.push(await baglam.session.hook('context',async olay=>{
   const kok=await sahip(olay.sessionID),oturum=await bilgi(olay.sessionID);
   const isci=oturum.metadata?.tam_okuma_iscisi===true&&kok&&oturum.parentID===kok,ajan=oturum.metadata?.tam_okuma_ajan===true&&kok&&oturum.parentID===kok;
   const tur=ajan_turlari.get(olay.sessionID);
   const rootDone=olay.sessionID===kok&&kapanis.get(olay.sessionID)?.arac===true;
   const once=Object.keys(olay.tools);
   if(!kok&&!isci){
    const baz_araclar=once.filter(ad=>ad!==ARAC&&ad!==OKUMA_ARACI);
    const baz_sistem=createHash('sha256').update(JSON.stringify(olay.system)).digest('hex');
    delete olay.tools[ARAC];delete olay.tools[OKUMA_ARACI];
    kanit('kapali-baglam-'+olay.sessionID,{oturum:olay.sessionID,baz_araclar,etkin_araclar:Object.keys(olay.tools),baz_sistem,son_sistem:createHash('sha256').update(JSON.stringify(olay.system)).digest('hex'),ek_yonlendirme_yok:true});return;
   }
   for(const ad of Object.keys(olay.tools))if(rootDone||(isci?ad!==OKUMA_ARACI:ajan?tur?.onceki_kod||ad!==OKUMA_ARACI:olay.sessionID!==kok||ad!==ARAC))delete olay.tools[ad];
   const yonerge=ajan?tur?.onceki_kod?'Önceki turda bu ajana atanmış tam kaynak penceresi gönderildi. Konuşma geçmişindeki o kodu kullanıp incelemeyi bitir; yeni araç çağırma. Kodun işleyişini kendi akıl yürütmenle değerlendir. Hazır çıktı kalıbı yok; Türkçe ve açık yaz.':'Atanmış kod penceresini almak için tam_okuma_penceresi aracını bir kez çağır. Kaynak sırasını veya dosyayı sen seçmezsin. Sonra kodun gerçek akışını kendin çöz. Bağlantıyı yalnız kod destekliyorsa kur. Hazır çıktı kalıbı yok; Türkçe ve açık yaz. Kusur uydurma.':isci?'Denetleyicinin verdiği görevi uygula.':rootDone?'Denetleyici kaynak taramasını yaptı. Kullanıcıya ekli sonuçları Türkçe ve açık biçimde anlat. Kapsam denetimi tam değilse tamamlandı deme. Araç çağırma.':'Tam okuma modu AÇIK. Betik kullanıcı işini yürütür ve ajanları yönetir. Hazır çıktı kalıbı yok. Türkçe ve açık yaz. Normal işler için bu kuralı kullanma.';
   olay.system.push({type:'text',text:yonerge});
   kanit('baglam-'+olay.sessionID,{oturum:olay.sessionID,sahip:kok,model:olay.model,agent:olay.agent,onceki_araclar:once,etkin_araclar:Object.keys(olay.tools),isci});
  }));
  return async()=>{for(const oturum of etkin)izin_yaz(oturum,false);etkin.clear();for(const kayit of kayitlar)await kayit.dispose();};
 }
};
