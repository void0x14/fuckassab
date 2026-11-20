# Nerede kaldık?

| Gerçek OpenCode koşusu | Kaynak | Sonuç |
|---|---:|---|
| 16 Kasım 2026, küçük kaynak | 3 dosya · 6.778 bayt | 6.778 bayt doğrulandı. 1 yanıt kabul edildi. |
| 17 Kasım 2026, son büyük deneme | 1.019 dosya · 9.412.029 bayt | 4 pencere için iletim olayı var. Kabul edilen yanıt: 0/4. Tam kapsam: hayır. |

Son koşuda iki ajan `HTTP 400 / context_length_exceeded` aldı; diğer ikisi kesildi. Araç çağrısının kayda geçmesi, sağlayıcının isteği kabul ettiği anlamına gelmedi.

## Sıradaki işler

1. **Pencere boyutu:** Sağlayıcı sınırı aşılınca reddedilen pencereyi böl. Son kabul edilen bayttan sürdür; aynı aralığı iki kez sayma.
2. **Kayıt:** “Araç verdi”, “sağlayıcı reddetti” ve “yanıt kabul edildi” durumlarını ayrı göster. Eksik koşu da kapanış raporu bıraksın.
3. **Kabul:** Büyük ağacı yeniden çalıştır. Beklenen: `9.412.029/9.412.029`, aralık boşluğu veya çakışma yok, her ajan için kabul edilmiş yanıt var.
4. **Özdenetim:** İki eski kontrol `yerel_kopru.ozet` ve `yerel_kopru.durdur` çağırıyor; bu işlevler artık yok. Çift sayım ve iptal kontrolleri güncel girişlerden yapılmalı.

Bayt kapsamı ile dosyalar arası davranış ayrı konular. Birincisi tam olsa bile ikincisi için ayrı inceleme gerekir.
