/**
 * Modern Petshop JavaScript - Optimized
 * Features: Performance monitoring, lazy loading, smooth interactions
 */

// Global app configuration
const PetShopApp = {
  config: {
    apiEndpoints: {
      filterProducts: '/api/filter_products',
      addToCart: '/add_to_cart/'
    },
    cache: new Map(),
    performance: {
      enabled: true,
      metrics: []
    }
  },
  
  // Performance monitoring
  performance: {
    mark: (name) => {
      if (PetShopApp.config.performance.enabled && window.performance && window.performance.mark) {
        performance.mark(name);
      }
    },
    
    measure: (name, startMark, endMark) => {
      if (PetShopApp.config.performance.enabled && window.performance && window.performance.measure) {
        performance.measure(name, startMark, endMark);
        const measure = performance.getEntriesByName(name)[0];
        PetShopApp.config.performance.metrics.push({
          name,
          duration: measure.duration,
          timestamp: Date.now()
        });
        
        // Log slow operations
        if (measure.duration > 100) {
          console.warn(`Slow operation: ${name} took ${measure.duration.toFixed(2)}ms`);
        }
      }
    }
  },
  
  // Theme system - DISABLED (using theme.js instead)
  theme: {
    initialized: false,
    init() {
      console.log('🎨 App.js tema sistemi devre dışı - theme.js kullanılıyor');
      this.initialized = true;
      return; // Tema sistemi theme.js'de
    },
    
    setTheme(isDark) {
      PetShopApp.performance.mark('theme-change-start');
      
      const elements = {
        body: document.body,
        mainBox: document.querySelector('.main-box'),
        siteTitle: document.querySelector('.site-title'),
        siteDesc: document.querySelector('.site-desc'),
        filterCard: document.querySelector('.filter-card'),
        productCards: document.querySelectorAll('.product-card'),
        buttons: document.querySelectorAll('.btn-outline-primary, .btn-primary, .cart-btn, .btn-light'),
        alerts: document.querySelectorAll('.alert-info'),
        forms: document.querySelectorAll('.form-control, .form-select, .form-label'),
        themeIcon: document.getElementById('themeIcon')
      };
      
      // Apply theme classes efficiently
      Object.keys(elements).forEach(key => {
        const element = elements[key];
        if (element) {
          if (element.length) {
            // NodeList
            element.forEach(el => el.classList.toggle('dark-mode', isDark));
          } else {
            // Single element
            element.classList.toggle('dark-mode', isDark);
          }
        }
      });
      
      // Update theme icon
      if (elements.themeIcon) {
        elements.themeIcon.className = isDark ? 'fa fa-sun' : 'fa fa-moon';
      }
      
      // Save theme preference
      localStorage.setItem('theme', isDark ? 'dark' : 'light');
      
      PetShopApp.performance.mark('theme-change-end');
      PetShopApp.performance.measure('theme-change', 'theme-change-start', 'theme-change-end');
    }
  },
  
  // Mega menu system
  megaMenu: {
    data: {
      'Köpek': {
        'Mama': ['Yavru Köpek Maması', 'Yetişkin Köpek Maması', 'Kısırlaştırılmış Köpek Maması', 'Konserve Köpek Maması'],
        'Ödül & Eğitim': ['Köpek Ödülleri', 'Köpek Eğitim Ürünleri'],
        'Bakım & Sağlık': ['Köpek Bakım Ürünleri', 'Köpek Sağlık Ürünleri'],
        'Aksesuar': ['Köpek Tasmaları', 'Köpek Mama ve Su Kapları', 'Köpek Kafesleri', 'Köpek Taşıma Çantaları', 'Köpek Yatakları', 'Köpek Oyuncakları'],
        'Marka': ['Acana', 'Advance', 'Brit Care', 'Pro Plan', 'Royal Canin', "Hill's", 'Orijen']
      },
      'Kedi': {
        'Mama': ['Yavru Kedi Maması', 'Yetişkin Kedi Maması', 'Kısırlaştırılmış Kedi Maması', 'Konserve Kedi Maması'],
        'Ödül & Eğitim': ['Kedi Ödülleri', 'Kedi Eğitim Ürünleri'],
        'Bakım & Sağlık': ['Kedi Bakım Ürünleri', 'Kedi Sağlık Ürünleri'],
        'Aksesuar': ['Kedi Kumları', 'Kedi Tuvaleti ve Ürünleri', 'Kedi Aksesuarları', 'Kedi Oyuncakları', 'Kedi Tasmaları', 'Kedi Mama ve Su Kapları', 'Kedi Kafesleri', 'Kedi Taşıma Çantaları', 'Kedi Tırmalamaları', 'Kedi Yatakları'],
        'Marka': ['Acana', 'Advance', 'Brit Care', 'Pro Plan', 'Royal Canin', "Hill's", 'Orijen']
      },
      'Kuş': {
        'Yem': ['Kuş Yemleri'],
        'Bakım & Sağlık': ['Kuş Vitaminleri', 'Kuş Sağlık Ürünleri'],
        'Aksesuar': ['Kuş Kafesleri', 'Kuş Oyuncakları', 'Kuş Aksesuarları', 'Kuş Banyosu'],
        'Marka': ['Acana', 'Advance', 'Brit Care', 'Pro Plan', 'Royal Canin', "Hill's", 'Orijen']
      },
      'Balık': {
        'Yem': ['Balık Yemleri'],
        'Bakım & Sağlık': ['Balık Sağlık Ürünleri'],
        'Aksesuar': ['Akvaryumlar', 'Akvaryum Ekipmanları', 'Balık Dekorasyon'],
        'Marka': ['Acana', 'Advance', 'Brit Care', 'Pro Plan', 'Royal Canin', "Hill's", 'Orijen']
      }
    },
    
    init() {
      this.setupCategoryButtons();
      this.setupDropdownHandlers();
    },
    
    setupCategoryButtons() {
      const selectedCategory = window.selectedCategory || 'Köpek';
      const categoryButtons = document.querySelectorAll('.category-btn');
      
      if (!this.data[selectedCategory]) {
        console.warn('Category data not found:', selectedCategory);
        return;
      }
      
      const categories = Object.keys(this.data[selectedCategory]);
      
      categoryButtons.forEach((button, index) => {
        if (categories[index]) {
          const categoryName = categories[index];
          button.setAttribute('data-category', categoryName);
          const textSpan = button.querySelector('.category-text');
          if (textSpan) {
            textSpan.textContent = categoryName;
          }
          
          // Add event listeners
          this.addButtonEvents(button, categoryName);
        }
      });
    },
    
    addButtonEvents(button, categoryName) {
      let hideTimeout;
      
      // Click handler
      button.addEventListener('click', () => {
        this.handleCategoryClick(button, categoryName);
      });
      
      // Hover handlers
      button.addEventListener('mouseenter', () => {
        clearTimeout(hideTimeout);
        this.showSubcategories(categoryName, button);
      });
      
      button.addEventListener('mouseleave', () => {
        hideTimeout = setTimeout(() => {
          this.hideSubcategories();
        }, 800); // 300ms'den 800ms'ye çıkardık - daha rahat navigasyon
      });
    },
    
    setupDropdownHandlers() {
      const dropdown = document.querySelector('.subcategory-dropdown');
      if (!dropdown) return;
      
      let hideTimeout;
      
      dropdown.addEventListener('mouseenter', () => {
        clearTimeout(hideTimeout);
      });
      
      dropdown.addEventListener('mouseleave', () => {
        hideTimeout = setTimeout(() => {
          this.hideSubcategories();
        }, 800); // Alt menüden çıkarken de 800ms bekle
      });
    },
    
    handleCategoryClick(button, categoryName) {
      // Visual feedback
      document.querySelectorAll('.category-btn').forEach(btn => {
        btn.style.opacity = '0.7';
      });
      button.style.opacity = '1';
      
      // Apply filter
      PetShopApp.products.filterByMainCategory(categoryName);
      
      // Show subcategories
      this.showSubcategories(categoryName, button);
    },
    
    showSubcategories(categoryName, button) {
      const dropdown = document.querySelector('.subcategory-dropdown');
      const selectedCategory = window.selectedCategory || 'Köpek';
      
      if (!dropdown || !this.data[selectedCategory] || !this.data[selectedCategory][categoryName]) {
        return;
      }
      
      const subcats = this.data[selectedCategory][categoryName];
      let html = `<div class='subcat-group'>`;
      html += `<div class='subcat-group-title'>${categoryName}</div>`;
      
      subcats.forEach(sub => {
        html += `<a href="#" class="subcat-link" data-subcat="${sub}" onclick="PetShopApp.megaMenu.navigateToSubcategory('${sub}')">${sub}</a>`;
      });
      html += `</div>`;
      
      dropdown.innerHTML = html;
      dropdown.style.display = 'block';
      
      // Position dropdown
      const rect = button.getBoundingClientRect();
      const containerRect = document.querySelector('.category-mega-menu').getBoundingClientRect();
      dropdown.style.left = (rect.left - containerRect.left) + 'px';
    },
    
    hideSubcategories() {
      const dropdown = document.querySelector('.subcategory-dropdown');
      if (dropdown) {
        dropdown.style.display = 'none';
      }
    },
    
    navigateToSubcategory(subcat) {
      const selectedCategory = window.selectedCategory || 'Köpek';
      
      if (this.data[selectedCategory]['Marka'].includes(subcat)) {
        PetShopApp.products.filter('', '', subcat);
      } else {
        PetShopApp.products.filter('', subcat, '');
      }
      
      this.hideSubcategories();
    }
  },
  
  // Search functionality
  search: {
    cache: new Map(),
    currentRequest: null,
    debounceTimer: null,
    
    init() {
      const searchInput = document.querySelector('.search-input');
      const searchBtn = document.querySelector('.search-btn');
      const suggestionsContainer = document.querySelector('.search-suggestions');
      
      if (!searchInput) return;
      
      // Real-time search with debouncing
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.trim();
        
        clearTimeout(this.debounceTimer);
        
        if (query.length < 2) {
          this.hideSuggestions();
          return;
        }
        
        this.debounceTimer = setTimeout(() => {
          this.getSuggestions(query);
        }, 300);
      });
      
      // Search on button click
      if (searchBtn) {
        searchBtn.addEventListener('click', () => {
          this.performSearch(searchInput.value.trim());
        });
      }
      
      // Search on Enter key
      searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          this.performSearch(e.target.value.trim());
        }
      });
      
      // Hide suggestions when clicking outside
      document.addEventListener('click', (e) => {
        if (!e.target.closest('.search-container')) {
          this.hideSuggestions();
        }
      });
    },
    
    async getSuggestions(query) {
      if (!query || query.length < 2) return;
      
      const cacheKey = `suggestions_${query}`;
      if (this.cache.has(cacheKey)) {
        this.displaySuggestions(this.cache.get(cacheKey));
        return;
      }
      
      try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&autocomplete=true`);
        const data = await response.json();
        
        if (data.suggestions) {
          this.cache.set(cacheKey, data.suggestions);
          this.displaySuggestions(data.suggestions);
        }
      } catch (error) {
        console.error('Suggestions error:', error);
      }
    },
    
    displaySuggestions(suggestions) {
      const container = document.querySelector('.search-suggestions');
      if (!container || !suggestions.length) {
        this.hideSuggestions();
        return;
      }
      
      container.innerHTML = suggestions.map(suggestion => 
        `<div class="suggestion-item" onclick="PetShopApp.search.selectSuggestion('${suggestion}')">${suggestion}</div>`
      ).join('');
      
      container.style.display = 'block';
    },
    
    hideSuggestions() {
      const container = document.querySelector('.search-suggestions');
      if (container) {
        container.style.display = 'none';
      }
    },
    
    selectSuggestion(suggestion) {
      const searchInput = document.querySelector('.search-input');
      if (searchInput) {
        searchInput.value = suggestion;
        this.performSearch(suggestion);
      }
      this.hideSuggestions();
    },
    
    async performSearch(query) {
      if (!query || query.length < 2) return;
      
      PetShopApp.performance.mark('search-start');
      
      // Cancel previous request
      if (this.currentRequest) {
        this.currentRequest.abort();
      }
      
      const cacheKey = `search_${query}`;
      
      // Check cache first
      if (this.cache.has(cacheKey)) {
        PetShopApp.products.displayProducts(this.cache.get(cacheKey));
        PetShopApp.performance.mark('search-end');
        PetShopApp.performance.measure('search-cached', 'search-start', 'search-end');
        return;
      }
      
      // Show loading state
      PetShopApp.products.showLoadingState();
      
      try {
        const controller = new AbortController();
        this.currentRequest = controller;
        
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
          signal: controller.signal
        });
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.products) {
          this.cache.set(cacheKey, data.products);
          PetShopApp.products.displayProducts(data.products);
          
          // Update product count
          const productCount = document.getElementById('productCount');
          if (productCount) {
            productCount.textContent = `${data.count} ürün bulundu`;
          }
        } else {
          PetShopApp.products.showNoResults();
        }
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Search error:', error);
          PetShopApp.products.showError('Arama sırasında bir hata oluştu');
        }
      } finally {
        this.currentRequest = null;
        PetShopApp.performance.mark('search-end');
        PetShopApp.performance.measure('search-network', 'search-start', 'search-end');
      }
    }
  },
  
  // Product filtering and display
  products: {
    cache: new Map(),
    currentRequest: null,
    
    init() {
      console.log('🛍️ Products module initialized');
      // Initialize lazy loading if needed
      this.initLazyLoading();
    },
    
    filterByMainCategory(mainCategory) {
      this.filter(mainCategory, '', '');
    },
    
    async filter(mainCategory = '', subcategory = '', brand = '', minPrice = '', maxPrice = '', sort = 'name') {
      PetShopApp.performance.mark('filter-start');
      
      // Cancel previous request
      if (this.currentRequest) {
        this.currentRequest.abort();
      }
      
      const params = new URLSearchParams();
      if (mainCategory) params.set('main_category', mainCategory);
      if (subcategory) params.set('subcategory', subcategory);
      if (brand) params.set('brand', brand);
      if (minPrice) params.set('min_price', minPrice);
      if (maxPrice) params.set('max_price', maxPrice);
      if (sort) params.set('sort', sort);
      
      const cacheKey = params.toString();
      
      // Check cache first
      if (this.cache.has(cacheKey)) {
        this.displayProducts(this.cache.get(cacheKey));
        this.updateProductCount(this.cache.get(cacheKey).length);
        PetShopApp.performance.mark('filter-end');
        PetShopApp.performance.measure('filter-cached', 'filter-start', 'filter-end');
        return;
      }
      
      // Show loading state
      this.showLoadingState();
      
      try {
        const controller = new AbortController();
        this.currentRequest = controller;
        
        const response = await fetch(`${PetShopApp.config.apiEndpoints.filterProducts}?${params.toString()}`, {
          signal: controller.signal
        });
        
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.products) {
          // Cache the result
          this.cache.set(cacheKey, data.products);
          this.displayProducts(data.products);
          this.updateProductCount(data.count || data.products.length);
        } else {
          this.showNoResults();
          this.updateProductCount(0);
        }
        
      } catch (error) {
        if (error.name !== 'AbortError') {
          console.error('Filter error:', error);
          this.showError('Filtreleme sırasında bir hata oluştu');
        }
      } finally {
        this.currentRequest = null;
        PetShopApp.performance.mark('filter-end');
        PetShopApp.performance.measure('filter-network', 'filter-start', 'filter-end');
      }
    },
    
    updateProductCount(count) {
      const productCount = document.getElementById('productCount');
      if (productCount) {
        productCount.textContent = `${count} ürün listeleniyor`;
      }
    },
    
    showLoadingState() {
      const productList = document.getElementById('productList');
      if (!productList) return;
      
      productList.innerHTML = `
        <div class="col-12 text-center py-5">
          <div class="loading-spinner mx-auto mb-3"></div>
          <p class="text-muted">Ürünler yükleniyor...</p>
        </div>
      `;
    },
    
    showNoResults() {
      const productList = document.getElementById('productList');
      if (!productList) return;
      
      productList.innerHTML = `
        <div class="col-12 text-center py-5">
          <i class="fa fa-search fa-3x text-muted mb-3"></i>
          <h5 class="text-muted">Ürün bulunamadı</h5>
          <p class="text-muted">Farklı filtreler deneyebilirsiniz.</p>
        </div>
      `;
    },
    
    showError(message) {
      const productList = document.getElementById('productList');
      if (!productList) return;
      
      productList.innerHTML = `
        <div class="col-12 text-center py-5">
          <i class="fa fa-exclamation-triangle fa-3x text-danger mb-3"></i>
          <h5 class="text-danger">Hata</h5>
          <p class="text-muted">${message}</p>
          <button class="btn btn-primary" onclick="location.reload()">Sayfayı Yenile</button>
        </div>
      `;
    },
    
    displayProducts(products) {
      PetShopApp.performance.mark('display-start');
      
      const productList = document.getElementById('productList');
      if (!productList || !products.length) {
        this.showNoResults();
        return;
      }
      
      const fragment = document.createDocumentFragment();
      
      products.forEach(product => {
        const productElement = this.createProductElement(product);
        fragment.appendChild(productElement);
      });
      
      productList.innerHTML = '';
      productList.appendChild(fragment);
      
      // Initialize enhanced lazy loading for new images
      this.initLazyLoading();
      
      PetShopApp.performance.mark('display-end');
      PetShopApp.performance.measure('display-products', 'display-start', 'display-end');
    },
    
    // Enhanced lazy loading with WebP support and optimization
    initLazyLoading() {
      PetShopApp.performance.mark('lazy-loading-start');
      
      if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const img = entry.target;
              const originalSrc = img.dataset.src || img.src;
              
              // WebP support detection and optimization
              if (this.supportsWebP() && originalSrc && !originalSrc.includes('.webp')) {
                const webpSrc = originalSrc.replace(/\.(jpg|jpeg|png)$/i, '.webp');
                
                // Try WebP first, fallback to original
                const webpImg = new Image();
                webpImg.onload = () => {
                  img.src = webpSrc;
                  img.classList.remove('lazy-load');
                  img.classList.add('loaded');
                };
                webpImg.onerror = () => {
                  img.src = originalSrc;
                  img.classList.remove('lazy-load');
                  img.classList.add('loaded');
                };
                webpImg.src = webpSrc;
              } else {
                img.src = originalSrc;
                img.classList.remove('lazy-load');
                img.classList.add('loaded');
              }
              
              observer.unobserve(img);
            }
          });
        }, {
          rootMargin: '50px', // Start loading 50px before image comes into view
          threshold: 0.1
        });
        
        document.querySelectorAll('.lazy-load').forEach(img => {
          imageObserver.observe(img);
        });
        
        // Also observe new images that might be added dynamically
        const mutationObserver = new MutationObserver((mutations) => {
          mutations.forEach((mutation) => {
            mutation.addedNodes.forEach((node) => {
              if (node.nodeType === 1) { // Element node
                const lazyImages = node.querySelectorAll ? node.querySelectorAll('.lazy-load') : [];
                lazyImages.forEach(img => imageObserver.observe(img));
              }
            });
          });
        });
        
        mutationObserver.observe(document.body, {
          childList: true,
          subtree: true
        });
        
      } else {
        // Fallback for browsers without Intersection Observer
        document.querySelectorAll('.lazy-load').forEach(img => {
          if (img.dataset.src) {
            img.src = img.dataset.src;
          }
          img.classList.remove('lazy-load');
        });
      }
      
      PetShopApp.performance.mark('lazy-loading-end');
      PetShopApp.performance.measure('lazy-loading-init', 'lazy-loading-start', 'lazy-loading-end');
    },
    
    // WebP support detection with caching
    supportsWebP() {
      if (this.webpSupport !== undefined) return this.webpSupport;
      
      // Check if browser supports WebP
      const canvas = document.createElement('canvas');
      canvas.width = 1;
      canvas.height = 1;
      try {
        const webpData = canvas.toDataURL('image/webp');
        this.webpSupport = webpData.indexOf('data:image/webp') === 0;
      } catch (e) {
        this.webpSupport = false;
      }
      
      // Store in localStorage for future visits
      localStorage.setItem('webp_support', this.webpSupport.toString());
      
      return this.webpSupport;
    },
    
    createProductElement(product) {
      const div = document.createElement('div');
      div.className = 'col-md-4 product-item';
      
      const subcategoryText = Array.isArray(product.subcategory) 
        ? product.subcategory.join(', ') 
        : product.subcategory || '';
      const brandBadge = product.brand 
        ? `<span class="badge bg-secondary ms-2">${product.brand}</span>` 
        : '';
      
      div.innerHTML = `
        <div class="card product-card h-100">
          <a href="/product/${product.id}">
            <img data-src="${product.image}" 
                 src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 300 200'%3E%3Crect fill='%23f0f0f0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23999'%3EYükleniyor...%3C/text%3E%3C/svg%3E"
                 class="card-img-top lazy-load" 
                 alt="${product.name}"
                 loading="lazy"/>
          </a>
          <div class="card-body d-flex flex-column">
            <h5 class="card-title">${product.name}${brandBadge}</h5>
            <p class="text-muted">${product.category} / ${subcategoryText}</p>
            <h6 class="text-success">${product.price} TL</h6>
            <div class="d-flex gap-2 mt-auto">
              <a href="/add_to_cart/${product.id}" 
                 class="btn add-to-cart-btn flex-grow-1"
                 onclick="PetShopApp.products.handleAddToCart(event, ${product.id})">
                 Sepete Ekle
              </a>
              <button class="btn btn-outline-danger wishlist-btn" 
                      onclick="PetShopApp.wishlist.toggle(${product.id}, this)"
                      title="Favorilere Ekle">
                <i class="fas fa-heart"></i>
              </button>
            </div>
          </div>
        </div>
      `;
      
      return div;
    },
    
    async handleAddToCart(event, productId) {
      event.preventDefault();
      const button = event.target;
      const originalText = button.textContent;
      
      // Visual feedback
      button.textContent = 'Ekleniyor...';
      button.disabled = true;
      
      try {
        // Simulate add to cart (in real app, this would be an API call)
        await new Promise(resolve => setTimeout(resolve, 500));
        
        // Navigate to add to cart endpoint
        window.location.href = `/add_to_cart/${productId}`;
        
      } catch (error) {
        console.error('Add to cart error:', error);
        button.textContent = 'Hata!';
        setTimeout(() => {
          button.textContent = originalText;
          button.disabled = false;
        }, 2000);
      }
    },
    
    initLazyLoading() {
      if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
          entries.forEach(entry => {
            if (entry.isIntersecting) {
              const img = entry.target;
              img.src = img.dataset.src || img.src;
              img.classList.remove('lazy-load');
              observer.unobserve(img);
            }
          });
        });
        
        document.querySelectorAll('.lazy-load').forEach(img => {
          imageObserver.observe(img);
        });
      }
    }
  },
  
  // Initialize the application
  init() {
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.initComponents());
    } else {
      this.initComponents();
    }
  },
  
  // Enhanced filters functionality
  filters: {
    currentFilters: {
      main_category: '',
      subcategory: '',
      brand: '',
      min_price: '',
      max_price: '',
      sort: 'name'
    },
    
    brandsCache: null,
    
    init() {
      const filterButtons = document.querySelectorAll('.filter-btn');
      const sortSelect = document.getElementById('sortSelect');
      
      // Filter button events
      filterButtons.forEach(btn => {
        btn.addEventListener('click', () => {
          // Remove active class from all buttons
          filterButtons.forEach(b => b.classList.remove('active'));
          // Add active class to clicked button
          btn.classList.add('active');
          
          const filter = btn.dataset.filter;
          this.applyQuickFilter(filter);
        });
      });
      
      // Sort dropdown events
      if (sortSelect) {
        sortSelect.addEventListener('change', (e) => {
          this.currentFilters.sort = e.target.value;
          this.applyAdvancedFilters();
        });
      }
      
      // Initialize advanced filters
      this.initAdvancedFilters();
      this.loadBrands();
    },
    
    async loadBrands() {
      try {
        if (this.brandsCache) {
          this.populateBrandFilter(this.brandsCache);
          return;
        }
        
        const response = await fetch('/api/brands');
        if (response.ok) {
          const data = await response.json();
          if (data.brands) {
            this.brandsCache = data.brands;
            this.populateBrandFilter(data.brands);
          }
        }
      } catch (error) {
        console.error('Brand loading error:', error);
      }
    },
    
    populateBrandFilter(brands) {
      const brandSelect = document.getElementById('brandFilter');
      if (!brandSelect) return;
      
      // Clear existing options except the first one
      brandSelect.innerHTML = '<option value="">Tüm Markalar</option>';
      
      brands.forEach(brand => {
        const option = document.createElement('option');
        option.value = brand;
        option.textContent = brand;
        brandSelect.appendChild(option);
      });
    },
    
    initAdvancedFilters() {
      const applyBtn = document.getElementById('applyFilters');
      const clearBtn = document.getElementById('clearFilters');
      const brandFilter = document.getElementById('brandFilter');
      const minPrice = document.getElementById('minPriceFilter');
      const maxPrice = document.getElementById('maxPriceFilter');
      
      if (applyBtn) {
        applyBtn.addEventListener('click', () => {
          this.currentFilters.brand = brandFilter?.value || '';
          this.currentFilters.min_price = minPrice?.value || '';
          this.currentFilters.max_price = maxPrice?.value || '';
          this.applyAdvancedFilters();
        });
      }
      
      if (clearBtn) {
        clearBtn.addEventListener('click', () => {
          this.clearAllFilters();
        });
      }
      
      // Auto-apply on Enter key
      [minPrice, maxPrice].forEach(input => {
        if (input) {
          input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
              applyBtn?.click();
            }
          });
        }
      });
    },
    
    applyAdvancedFilters() {
      PetShopApp.products.filter(
        this.currentFilters.main_category,
        this.currentFilters.subcategory,
        this.currentFilters.brand,
        this.currentFilters.min_price,
        this.currentFilters.max_price,
        this.currentFilters.sort
      );
    },
    
    clearAllFilters() {
      // Reset all filters
      this.currentFilters = {
        main_category: '',
        subcategory: '',
        brand: '',
        min_price: '',
        max_price: '',
        sort: 'name'
      };
      
      // Clear UI elements
      const brandFilter = document.getElementById('brandFilter');
      const minPrice = document.getElementById('minPriceFilter');
      const maxPrice = document.getElementById('maxPriceFilter');
      const sortSelect = document.getElementById('sortSelect');
      
      if (brandFilter) brandFilter.value = '';
      if (minPrice) minPrice.value = '';
      if (maxPrice) maxPrice.value = '';
      if (sortSelect) sortSelect.value = 'name';
      
      // Clear active buttons
      document.querySelectorAll('.filter-btn.active, .category-btn.active').forEach(btn => {
        btn.classList.remove('active');
      });
      
      // Apply cleared filters
      this.applyAdvancedFilters();
    },
    
    applyQuickFilter(filter) {
      const productItems = document.querySelectorAll('.product-item');
      const products = Array.from(productItems);
      
      switch (filter) {
        case 'price-low':
          products.sort((a, b) => {
            const priceA = parseFloat(a.querySelector('.text-success').textContent);
            const priceB = parseFloat(b.querySelector('.text-success').textContent);
            return priceA - priceB;
          });
          break;
        case 'price-high':
          products.sort((a, b) => {
            const priceA = parseFloat(a.querySelector('.text-success').textContent);
            const priceB = parseFloat(b.querySelector('.text-success').textContent);
            return priceB - priceA;
          });
          break;
        case 'newest':
        case 'popular':
          // For demo purposes, we'll shuffle the products
          products.sort(() => Math.random() - 0.5);
          break;
      }
      
      // Re-append products in new order
      const productList = document.getElementById('productList');
      if (productList) {
        products.forEach(product => {
          productList.appendChild(product);
        });
      }
    },
    
    applySorting(sortType) {
      const productItems = document.querySelectorAll('.product-item');
      const products = Array.from(productItems);
      
      switch (sortType) {
        case 'name':
          products.sort((a, b) => {
            const nameA = a.querySelector('.card-title').textContent.toLowerCase();
            const nameB = b.querySelector('.card-title').textContent.toLowerCase();
            return nameA.localeCompare(nameB);
          });
          break;
        case 'price-asc':
          products.sort((a, b) => {
            const priceA = parseFloat(a.querySelector('.text-success').textContent);
            const priceB = parseFloat(b.querySelector('.text-success').textContent);
            return priceA - priceB;
          });
          break;
        case 'price-desc':
          products.sort((a, b) => {
            const priceA = parseFloat(a.querySelector('.text-success').textContent);
            const priceB = parseFloat(b.querySelector('.text-success').textContent);
            return priceB - priceA;
          });
          break;
        case 'newest':
          products.reverse(); // Simple reverse for demo
          break;
      }
      
      // Re-append products in new order
      const productList = document.getElementById('productList');
      if (productList) {
        products.forEach(product => {
          productList.appendChild(product);
        });
      }
    }
  },

  initComponents() {
    PetShopApp.performance.mark('app-init-start');
    
    // Initialize components
    this.theme.init();
    this.megaMenu.init();
    this.search.init();
    this.filters.init();
    this.ux.init();
    this.products.initLazyLoading();
    
    // Setup global event listeners
    this.setupGlobalEvents();
    
    PetShopApp.performance.mark('app-init-end');
    PetShopApp.performance.measure('app-initialization', 'app-init-start', 'app-init-end');
    
    console.log('🚀 PetShop App initialized successfully with all optimizations!');
    console.log('📊 Performance monitoring enabled');
    console.log('🔍 Real-time search activated');
    console.log('📱 Mobile-responsive design ready');
    console.log('♿ Accessibility features enabled');
  },
  
  // UX enhancements
  ux: {
    init() {
      this.initBackToTop();
      this.initTooltips();
      this.initKeyboardNavigation();
    },
    
    initBackToTop() {
      const backToTopBtn = document.getElementById('backToTop');
      if (!backToTopBtn) return;
      
      // Show/hide button based on scroll position
      window.addEventListener('scroll', () => {
        if (window.pageYOffset > 300) {
          backToTopBtn.classList.add('show');
        } else {
          backToTopBtn.classList.remove('show');
        }
      });
      
      // Smooth scroll to top
      backToTopBtn.addEventListener('click', () => {
        window.scrollTo({
          top: 0,
          behavior: 'smooth'
        });
      });
    },
    
    initTooltips() {
      // Initialize Bootstrap tooltips if available
      if (window.bootstrap && bootstrap.Tooltip) {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
          return new bootstrap.Tooltip(tooltipTriggerEl);
        });
      }
    },
    
    initKeyboardNavigation() {
      // Enhanced keyboard navigation
      document.addEventListener('keydown', (event) => {
        // Alt + S for search focus
        if (event.altKey && event.key === 's') {
          event.preventDefault();
          const searchInput = document.querySelector('.search-input');
          if (searchInput) {
            searchInput.focus();
          }
        }
        
        // Alt + C for cart
        if (event.altKey && event.key === 'c') {
          event.preventDefault();
          const cartBtn = document.querySelector('.cart-btn');
          if (cartBtn) {
            cartBtn.click();
          }
        }
        
        // Arrow key navigation for product cards
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp' || 
            event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
          this.handleArrowNavigation(event);
        }
      });
    },
    
    handleArrowNavigation(event) {
      const focusedElement = document.activeElement;
      const productCards = Array.from(document.querySelectorAll('.product-card a, .add-to-cart-btn'));
      const currentIndex = productCards.indexOf(focusedElement);
      
      if (currentIndex === -1) return;
      
      let nextIndex;
      const cardsPerRow = Math.floor(window.innerWidth / 350); // Approximate cards per row
      
      switch (event.key) {
        case 'ArrowRight':
          nextIndex = Math.min(currentIndex + 1, productCards.length - 1);
          break;
        case 'ArrowLeft':
          nextIndex = Math.max(currentIndex - 1, 0);
          break;
        case 'ArrowDown':
          nextIndex = Math.min(currentIndex + cardsPerRow, productCards.length - 1);
          break;
        case 'ArrowUp':
          nextIndex = Math.max(currentIndex - cardsPerRow, 0);
          break;
      }
      
      if (nextIndex !== undefined && productCards[nextIndex]) {
        event.preventDefault();
        productCards[nextIndex].focus();
      }
    }
  },

  setupGlobalEvents() {
    // Handle clicks outside dropdown to close it
    document.addEventListener('click', (event) => {
      const dropdown = document.querySelector('.subcategory-dropdown');
      const categoryMenu = document.querySelector('.category-mega-menu');
      
      if (dropdown && dropdown.style.display === 'block' && 
          !categoryMenu.contains(event.target)) {
        this.megaMenu.hideSubcategories();
      }
    });
    
    // Handle keyboard navigation
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        this.megaMenu.hideSubcategories();
        PetShopApp.search.hideSuggestions();
      }
    });
    
    // Performance monitoring
    if (window.performance && window.performance.getEntriesByType) {
      window.addEventListener('load', () => {
        // Log Core Web Vitals
        this.logWebVitals();
      });
    }
    
    // Add loading indicator for slow connections
    window.addEventListener('beforeunload', () => {
      const loadingOverlay = document.getElementById('loadingOverlay');
      if (loadingOverlay) {
        loadingOverlay.style.display = 'flex';
      }
    });
  },
  
  logWebVitals() {
    // Log performance metrics after page load
    setTimeout(() => {
      const navigation = performance.getEntriesByType('navigation')[0];
      const paintEntries = performance.getEntriesByType('paint');
      
      console.group('Performance Metrics');
      console.log('Page Load Time:', navigation.loadEventEnd - navigation.loadEventStart, 'ms');
      console.log('DOM Content Loaded:', navigation.domContentLoadedEventEnd - navigation.domContentLoadedEventStart, 'ms');
      
      paintEntries.forEach(entry => {
        console.log(`${entry.name}:`, entry.startTime, 'ms');
      });
      
      console.log('Custom Metrics:', PetShopApp.config.performance.metrics);
      console.groupEnd();
    }, 1000);
  },
  
  // Wishlist system
  wishlist: {
    init() {
      console.log('❤️ Wishlist module initialized');
    },
    
    toggle(productId, button) {
      try {
        console.log('Wishlist toggle for product:', productId);
        
        // Simulate wishlist toggle
        if (button) {
          const icon = button.querySelector('i');
          if (icon) {
            const isActive = icon.classList.contains('fas');
            if (isActive) {
              icon.classList.remove('fas');
              icon.classList.add('far');
              console.log('Removed from wishlist:', productId);
            } else {
              icon.classList.remove('far');
              icon.classList.add('fas');
              console.log('Added to wishlist:', productId);
            }
          }
        }
        
        return true;
      } catch (error) {
        console.error('Wishlist toggle error:', error);
        return false;
      }
    }
  },
  
  // Main initialization
  init() {
    console.log('🚀 PetShopApp initializing...');
    
    // Initialize all modules
    if (this.theme) this.theme.init();
    if (this.megaMenu) this.megaMenu.init();
    if (this.search) this.search.init();
    if (this.products) this.products.init();
    if (this.ux) this.ux.init();
    if (this.wishlist) this.wishlist.init();
    
    console.log('✅ PetShopApp initialized successfully!');
  }
};

// Global functions for backward compatibility
window.handleCategoryClick = function(button) {
  const categoryName = button.dataset.category;
  PetShopApp.megaMenu.handleCategoryClick(button, categoryName);
};

window.filterProducts = function(mainCategory = '', subcategory = '', brand = '') {
  PetShopApp.products.filter(mainCategory, subcategory, brand);
};

window.selectedCategory = window.selectedCategory || 'Köpek';

// Initialize the app
PetShopApp.init();