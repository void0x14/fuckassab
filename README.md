# fuckassab

Sözde yapay zekaların, sözde kod basei okudum şu şu şu bu bu bu laflarını, deterministik olarak %100 ezen ve gerçekten kod basei %100 okumaya redakte eden hardcoded betik suite'i.

ab= aptalbotlar
aiların tamamına artık ai yerine ab diyoruz, çünkü abler.

## Kur

Linux, Python 3, Bun ve eklentinin kullandığı `command.transform` / `session.hook` arayüzlerini sunan bir OpenCode kurulumu gerekir. Her OpenCode sürümüyle uyum iddiası yoktur.

```sh
git clone https://github.com/void0x14/fuckassab.git
cd fuckassab
python3 kur.py
export OPENCODE_SOURCE=/tam/yol/opencode-kaynak-agaci
```

`OPENCODE_SOURCE`, `packages/core/src/util/token.ts` içeren **OpenCode kaynak ağacıdır**; okunacak proje değildir. OpenCode’u bu değişkenle başlat. `kur.py` başka bir eklentinin üzerine yazmaz.

## Kullan

1. OpenCode’u **okunacak projenin dizininde** aç. `/tam-okuma` yaz.
2. Örneğin “Bu projenin tamamını oku” de. Aynı komut modu kapatır.
3. `denetleyici/taramalar/` içindeki ilgili koşunun `oturum-ozeti.md` dosyasına bak.

| Kayıt | Ne gösterir? |
|---|---|
| `olaylar.jsonl` | Hangi pencere ne zaman istendi ve iletildi? |
| `ajan-kaydi.json` | Sıra nerede kaldı, hangi ajan bitirdi? |
| `kapsama-denetimi.json` | Kaç bayt doğrulandı? Eksik aralık var mı? |

Kaydı tekrar denetlemek için: `python3 denetleyici/oturum_raporu.py <koşu-dizini>`. Özetleri yeniler; tam kapsamda `0`, eksik kapsamda `2` döner.

Kaynak pencereleri **seçtiğin model sağlayıcısına** gider. Ham kod ve yanıtlar yerel tarama dizinine de yazılır; Git bunları izlemez. [Son ölçüm ve açık işler](DURUM.md).
