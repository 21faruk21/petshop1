// Universal Theme Toggle System - Pethome
// Bu script tüm sayfalarda aynı şekilde çalışır

(function() {
  'use strict';
  
  // Tema değiştirme fonksiyonu
  function toggleTheme() {
    const body = document.body;
    const isDark = body.classList.contains('dark-mode');
    const newDark = !isDark;
    
    // Body class değiştir
    body.classList.toggle('dark-mode', newDark);
    
    // İkon güncelle
    const icon = document.getElementById('themeIcon');
    if (icon) {
      icon.className = newDark ? 'fa fa-sun' : 'fa fa-moon';
    }
    
    // LocalStorage'a kaydet
    localStorage.setItem('theme', newDark ? 'dark' : 'light');
    
    console.log('Tema değiştirildi:', newDark ? 'dark' : 'light');
  }
  
  // Tema uygulama fonksiyonu
  function applyTheme() {
    const savedTheme = localStorage.getItem('theme');
    const isDark = savedTheme === 'dark';
    
    if (isDark) {
      document.body.classList.add('dark-mode');
    }
    
    // İkon durumunu güncelle
    const icon = document.getElementById('themeIcon');
    if (icon) {
      icon.className = isDark ? 'fa fa-sun' : 'fa fa-moon';
    }
    
    console.log('Tema uygulandı:', isDark ? 'dark' : 'light');
  }
  
  // Sayfa yüklenir yüklenmez tema uygula (FOUC önleme)
  applyTheme();
  
  // DOM hazır olduğunda buton bağla
  function initThemeButton() {
    const button = document.getElementById('themeToggle');
    if (button) {
      console.log('🎨 Theme.js tema butonunu bağlıyor...');
      
      // Mevcut event listener'ları temizle
      const newButton = button.cloneNode(true);
      button.parentNode.replaceChild(newButton, button);
      const themeButton = document.getElementById('themeToggle');
      
      themeButton.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('🎨 Tema butonu tıklandı!');
        toggleTheme();
      });
      
      console.log('✅ Theme.js tema butonu aktif!');
    } else {
      console.log('⚠️ Tema butonu bulunamadı');
    }
  }
  
  // DOM hazır olduğunda veya hemen çalıştır
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initThemeButton);
  } else {
    // Kısa bir gecikme ile çakışmayı önle
    setTimeout(initThemeButton, 100);
  }
  
  // Global olarak erişilebilir yap
  window.PethomeTheme = {
    toggle: toggleTheme,
    apply: applyTheme
  };
  
})();