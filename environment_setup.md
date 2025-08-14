# 🔧 Environment Variables Konfigürasyonu

Pethome projesinin tüm özelliklerini aktif etmek için aşağıdaki environment variable'ları ayarlayın:

## 🔒 Güvenlik

```bash
# Güvenli secret key (zorunlu değil, otomatik generate edilir)
SECRET_KEY=your-super-secret-key-here

# Admin email adresi (düşük stok bildirimleri için)
ADMIN_EMAIL=admin@pethome.com
```

## 📧 Email Bildirimleri (Opsiyonel)

Email bildirimlerini aktif etmek için:

```bash
# SMTP Server ayarları
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_FROM=noreply@pethome.com
```

### Gmail için App Password Alma:
1. Google Account > Security > 2-Step Verification > App passwords
2. "Mail" için app password oluşturun
3. Bu password'u `EMAIL_PASSWORD` olarak kullanın

## 📱 SMS Bildirimleri (Opsiyonel)

SMS bildirimlerini aktif etmek için (Türkiye SMS servisleri):

```bash
# SMS API ayarları (Netgsm, İletimerkezi, vb.)
SMS_API_KEY=your-sms-api-key
SMS_SENDER=Pethome
```

## 🚀 Aktif Özellikler

Environment variable'lar ayarlandığında otomatik aktif olan özellikler:

### ✅ Hemen Çalışan Özellikler:
- ✅ Marka filtreleme sistemi
- ✅ Arama autocomplete
- ✅ Gelişmiş stok yönetimi
- ✅ Kargo takip sistemi
- ✅ Image lazy loading & WebP optimization
- ✅ Enhanced caching & performance
- ✅ Security hardening & rate limiting
- ✅ Database optimization with indexes

### 📧 Email Ayarı Gerekli:
- Sipariş durumu bildirimleri
- Sipariş onay emaili
- Düşük stok uyarıları (admin)

### 📱 SMS API Gerekli:
- SMS sipariş bildirimleri
- SMS durumu güncellemeleri

## 🔧 Production Deployment

### Render.com için:
```bash
# Environment variables'ı Render dashboard'dan ekleyin
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
ADMIN_EMAIL=admin@pethome.com
```

### Heroku için:
```bash
heroku config:set SMTP_SERVER=smtp.gmail.com
heroku config:set EMAIL_USER=your-email@gmail.com
heroku config:set EMAIL_PASSWORD=your-app-password
```

### VPS için:
```bash
export SMTP_SERVER=smtp.gmail.com
export EMAIL_USER=your-email@gmail.com
export EMAIL_PASSWORD=your-app-password
```

## 📋 Test Etme

1. Email test için bir sipariş verin
2. Admin panelden sipariş durumunu değiştirin
3. Email gelmezse console loglarını kontrol edin
4. SMS için external service entegrasyonu gerekli

## 🎯 Sonuç

**Environment variable'lar olmadan bile tüm core özellikler çalışır!**

- Email/SMS bildirimler console'a log olur
- Diğer tüm optimizasyonlar aktif
- Production'da sadece SMTP ayarı yapın = tam özellik!