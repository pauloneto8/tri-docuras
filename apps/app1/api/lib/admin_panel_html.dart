const adminPanelHtml = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tri Doçuras — Painel</title>
  <style>
    :root {
      --dark: #412414;
      --brown: #6A3A23;
      --cream: #FDEFE2;
      --card: #FFFBF6;
      --peach: #F7E3D0;
      --pink: #D67F7C;
      --success: #7C9473;
      --warning: #C98A3C;
      --disabled: #E6D9CC;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--cream);
      color: var(--dark);
    }
    .wrap { max-width: 960px; margin: 0 auto; padding: 16px; }
    h1 { font-size: 1.5rem; margin: 0 0 4px; }
    h2 { font-size: 1.1rem; margin: 0 0 12px; }
    .sub { color: var(--brown); margin: 0 0 20px; font-size: 0.95rem; }
    .card {
      background: var(--card);
      border: 1px solid rgba(65,36,20,.12);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 12px;
    }
    .login { max-width: 360px; margin: 48px auto; }
    label { display: block; font-size: 0.75rem; font-weight: 600; letter-spacing: .05em; margin-bottom: 6px; color: var(--brown); }
    input, select, textarea, button {
      font: inherit;
      border-radius: 10px;
      border: 1px solid rgba(65,36,20,.15);
      padding: 10px 12px;
    }
    input, select, textarea { width: 100%; background: #fff; }
    textarea { min-height: 72px; resize: vertical; }
    button {
      background: var(--pink);
      color: #fff;
      border: none;
      font-weight: 600;
      cursor: pointer;
      padding: 10px 16px;
    }
    button.secondary { background: var(--peach); color: var(--dark); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 16px; }
    .tabs, .main-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .tab, .main-tab {
      background: var(--peach);
      color: var(--dark);
      border: none;
      padding: 8px 14px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
    }
    .tab.active, .main-tab.active { background: var(--dark); color: #fff; }
    .badge {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      background: var(--warning);
      color: #fff;
    }
    .badge.paid { background: var(--success); }
    .badge.pending-payment { background: var(--warning); }
    .badge.preparing { background: #b07a4f; }
    .badge.ready { background: var(--pink); }
    .badge.completed { background: var(--disabled); color: var(--brown); }
    .badge.available { background: var(--success); }
    .badge.hidden-product { background: var(--disabled); color: var(--brown); }
    .order-head, .product-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
    .order-id, .product-name { font-weight: 700; font-size: 1.05rem; }
    .meta { color: var(--brown); font-size: 0.9rem; line-height: 1.5; }
    .items { margin: 10px 0; padding-left: 18px; }
    .items li { margin-bottom: 4px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .empty { text-align: center; color: var(--brown); padding: 32px 12px; }
    .error { color: #a33; font-size: 0.9rem; margin-top: 8px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
    a.wa { color: var(--pink); text-decoration: none; font-weight: 600; }
    .form-grid { display: grid; gap: 12px; }
    .form-row { display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }
    .checks { display: flex; flex-wrap: wrap; gap: 16px; align-items: center; }
    .checks label { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 0.9rem; letter-spacing: 0; }
    .checks input { width: auto; }
    .section-view[hidden] { display: none !important; }
    .product-thumb {
      width: 72px;
      height: 72px;
      border-radius: 50%;
      object-fit: cover;
      border: 2px solid var(--peach);
      background: var(--peach);
    }
    .product-row { display: flex; gap: 12px; align-items: flex-start; }
    .image-preview {
      width: 120px;
      height: 120px;
      border-radius: 50%;
      object-fit: cover;
      border: 2px solid var(--peach);
      background: var(--peach);
      display: none;
    }
    @media (max-width: 600px) {
      .wrap { padding: 12px; }
      .form-row { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div id="loginView" class="login card">
      <h1>Tri Doçuras</h1>
      <p class="sub">Painel da loja</p>
      <label for="password">SENHA</label>
      <input id="password" type="password" autocomplete="current-password" placeholder="Senha do painel">
      <div style="height:12px"></div>
      <button id="loginBtn" type="button" style="width:100%">Entrar</button>
      <div id="loginError" class="error"></div>
    </div>

    <div id="panelView" hidden>
      <div class="topbar">
        <div>
          <h1>Tri Doçuras</h1>
          <p class="sub">Gerencie pedidos e catálogo</p>
        </div>
        <button id="logoutBtn" type="button" class="secondary">Sair</button>
      </div>

      <div class="main-tabs" id="mainTabs" style="margin-bottom:16px">
        <button class="main-tab active" data-section="orders">Pedidos</button>
        <button class="main-tab" data-section="products">Produtos</button>
      </div>

      <div id="ordersView" class="section-view">
        <div class="toolbar">
          <div class="tabs" id="tabs">
            <button class="tab active" data-status="active">Fila</button>
            <button class="tab" data-status="paid">Pagos</button>
            <button class="tab" data-status="preparing">Em preparo</button>
            <button class="tab" data-status="ready">Prontos</button>
            <button class="tab" data-status="pending_payment">Aguardando Pix</button>
            <button class="tab" data-status="completed">Concluídos</button>
          </div>
          <button id="refreshBtn" type="button" class="secondary">Atualizar</button>
        </div>
        <div id="orders"></div>
        <div id="listError" class="error"></div>
      </div>

      <div id="productsView" class="section-view" hidden>
        <div class="toolbar">
          <button id="newProductBtn" type="button">Novo produto</button>
          <button id="refreshProductsBtn" type="button" class="secondary">Atualizar</button>
        </div>

        <div id="productFormCard" class="card" hidden>
          <h2 id="productFormTitle">Novo produto</h2>
          <form id="productForm" class="form-grid">
            <input type="hidden" id="productId" value="">
            <div>
              <label for="productName">NOME</label>
              <input id="productName" required maxlength="255" placeholder="Ex.: Brownie Tradicional">
            </div>
            <div>
              <label for="productDescription">DESCRIÇÃO</label>
              <textarea id="productDescription" placeholder="Descrição exibida no app"></textarea>
            </div>
            <div class="form-row">
              <div>
                <label for="productPrice">PREÇO (R$)</label>
                <input id="productPrice" type="number" min="0.01" step="0.01" required placeholder="12.00">
              </div>
              <div>
                <label for="productCategory">CATEGORIA</label>
                <select id="productCategory" required>
                  <option value="brownies">Brownies</option>
                  <option value="combos">Combos</option>
                </select>
              </div>
            </div>
            <div class="checks">
              <label><input id="productFeatured" type="checkbox"> Destaque no catálogo</label>
              <label><input id="productAvailable" type="checkbox" checked> Visível no app</label>
            </div>
            <div>
              <label for="productImage">FOTO DO PRODUTO</label>
              <input id="productImage" type="file" accept="image/jpeg,image/png,image/webp">
              <div style="height:8px"></div>
              <img id="productImagePreview" class="image-preview" alt="Prévia da foto">
            </div>
            <div class="actions">
              <button id="saveProductBtn" type="submit">Salvar</button>
              <button id="cancelProductBtn" type="button" class="secondary">Cancelar</button>
            </div>
          </form>
          <div id="productFormError" class="error"></div>
        </div>

        <div id="products"></div>
        <div id="productsError" class="error"></div>
      </div>
    </div>
  </div>

  <script>
    const TOKEN_KEY = "td_admin_token";
    let currentStatus = "active";
    let currentSection = "orders";
    let ordersTimer = null;

    const loginView = document.getElementById("loginView");
    const panelView = document.getElementById("panelView");
    const passwordInput = document.getElementById("password");
    const loginBtn = document.getElementById("loginBtn");
    const loginError = document.getElementById("loginError");
    const logoutBtn = document.getElementById("logoutBtn");
    const ordersEl = document.getElementById("orders");
    const listError = document.getElementById("listError");
    const refreshBtn = document.getElementById("refreshBtn");
    const ordersView = document.getElementById("ordersView");
    const productsView = document.getElementById("productsView");
    const productsEl = document.getElementById("products");
    const productsError = document.getElementById("productsError");
    const productFormCard = document.getElementById("productFormCard");
    const productForm = document.getElementById("productForm");
    const productFormTitle = document.getElementById("productFormTitle");
    const productFormError = document.getElementById("productFormError");
    const productIdInput = document.getElementById("productId");
    const productNameInput = document.getElementById("productName");
    const productDescriptionInput = document.getElementById("productDescription");
    const productPriceInput = document.getElementById("productPrice");
    const productCategoryInput = document.getElementById("productCategory");
    const productFeaturedInput = document.getElementById("productFeatured");
    const productAvailableInput = document.getElementById("productAvailable");
    const productImageInput = document.getElementById("productImage");
    const productImagePreview = document.getElementById("productImagePreview");

    function token() { return sessionStorage.getItem(TOKEN_KEY); }
    function setToken(value) {
      if (value) sessionStorage.setItem(TOKEN_KEY, value);
      else sessionStorage.removeItem(TOKEN_KEY);
    }

    function formatMoney(value) {
      return "R$ " + Number(value).toFixed(2).replace(".", ",");
    }

    function formatPhone(digits) {
      if (!digits || digits.length !== 11) return digits || "";
      return "(" + digits.slice(0,2) + ") " + digits.slice(2,7) + "-" + digits.slice(7);
    }

    function formatDate(value) {
      if (!value) return "";
      const d = new Date(value);
      return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    }

    function badgeClass(status) {
      return "badge " + status.replace(/_/g, "-");
    }

    function renderAddress(order) {
      if (!order.delivery_address) return order.delivery_label;
      const a = order.delivery_address;
      const parts = [
        a.street, a.number,
        a.complement ? "(" + a.complement + ")" : null,
        a.neighborhood,
        "Ref: " + a.reference
      ].filter(Boolean);
      return parts.join(" · ");
    }

    function renderOrder(order) {
      const items = (order.items || []).map(function(item) {
        const extras = [];
        if (item.size) extras.push(item.size);
        if (item.lactose_free) extras.push("sem lactose");
        const suffix = extras.length ? " (" + extras.join(", ") + ")" : "";
        return "<li>" + item.quantity + "× " + item.product_name + suffix + " — " + formatMoney(item.line_total) + "</li>";
      }).join("");

      const actions = (order.next_actions || []).map(function(action) {
        return '<button type="button" data-id="' + order.id + '" data-status="' + action.status + '">' + action.label + '</button>';
      }).join("");

      return '<article class="card">' +
        '<div class="order-head">' +
          '<div class="order-id">' + order.id + '</div>' +
          '<span class="' + badgeClass(order.status) + '">' + order.status_label + '</span>' +
        '</div>' +
        '<div class="meta">' +
          '<strong>' + order.customer_name + '</strong><br>' +
          '<a class="wa" href="' + order.whatsapp_link + '" target="_blank" rel="noopener">WhatsApp ' + formatPhone(order.whatsapp) + '</a><br>' +
          order.delivery_label + ' · ' + renderAddress(order) + '<br>' +
          'Total ' + formatMoney(order.total) + ' · ' + formatDate(order.created_at) +
        '</div>' +
        '<ul class="items">' + items + '</ul>' +
        '<div class="actions">' + actions + '</div>' +
      '</article>';
    }

    function renderProduct(product) {
      const badge = product.available
        ? '<span class="badge available">' + product.availability_label + '</span>'
        : '<span class="badge hidden-product">' + product.availability_label + '</span>';
      const featured = product.featured ? ' · Destaque' : '';
      const description = product.description
        ? '<div class="meta">' + product.description + '</div>'
        : '';
      const thumb = product.image_url
        ? '<img class="product-thumb" src="' + product.image_url + '" alt="">'
        : '<div class="product-thumb"></div>';

      return '<article class="card product-row">' +
        thumb +
        '<div style="flex:1">' +
        '<div class="product-head">' +
          '<div class="product-name">' + product.name + '</div>' +
          badge +
        '</div>' +
        description +
        '<div class="meta">' +
          formatMoney(product.price) + ' · ' + product.category_label + featured +
        '</div>' +
        '<div class="actions">' +
          '<button type="button" class="secondary" data-edit-product="' + product.id + '">Editar</button>' +
        '</div>' +
        '</div>' +
      '</article>';
    }

    async function api(path, options) {
      const headers = Object.assign({ "Content-Type": "application/json" }, options && options.headers || {});
      if (token()) headers.Authorization = "Bearer " + token();
      const response = await fetch(path, Object.assign({}, options, { headers }));
      const data = await response.json().catch(function() { return {}; });
      if (response.status === 401) {
        setToken(null);
        showLogin();
        throw new Error("Sessão expirada.");
      }
      if (!response.ok) throw new Error(data.error || "Erro na requisição.");
      return data;
    }

    async function login() {
      loginError.textContent = "";
      loginBtn.disabled = true;
      try {
        const data = await api("/api/admin/session", {
          method: "POST",
          body: JSON.stringify({ password: passwordInput.value })
        });
        setToken(data.token);
        showPanel();
        await refreshCurrentSection();
        startOrdersTimer();
      } catch (error) {
        loginError.textContent = error.message || "Não foi possível entrar.";
      } finally {
        loginBtn.disabled = false;
      }
    }

    async function loadOrders() {
      listError.textContent = "";
      ordersEl.innerHTML = '<div class="empty">Carregando…</div>';
      try {
        const data = await api("/api/admin/orders?status=" + encodeURIComponent(currentStatus));
        const orders = data.orders || [];
        if (!orders.length) {
          ordersEl.innerHTML = '<div class="empty">Nenhum pedido nesta aba.</div>';
          return;
        }
        ordersEl.innerHTML = orders.map(renderOrder).join("");
        ordersEl.querySelectorAll("button[data-status]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            updateStatus(btn.dataset.id, btn.dataset.status, btn);
          });
        });
      } catch (error) {
        ordersEl.innerHTML = "";
        listError.textContent = error.message;
      }
    }

    async function updateStatus(id, status, button) {
      button.disabled = true;
      try {
        await api("/api/admin/orders/" + encodeURIComponent(id) + "/status", {
          method: "POST",
          body: JSON.stringify({ status })
        });
        await loadOrders();
      } catch (error) {
        listError.textContent = error.message;
        button.disabled = false;
      }
    }

    function setProductImagePreview(url) {
      if (url) {
        productImagePreview.src = url;
        productImagePreview.style.display = "block";
      } else {
        productImagePreview.removeAttribute("src");
        productImagePreview.style.display = "none";
      }
    }

    function resetProductForm() {
      productIdInput.value = "";
      productNameInput.value = "";
      productDescriptionInput.value = "";
      productPriceInput.value = "";
      productCategoryInput.value = "brownies";
      productFeaturedInput.checked = false;
      productAvailableInput.checked = true;
      productImageInput.value = "";
      setProductImagePreview(null);
      productFormError.textContent = "";
      productFormTitle.textContent = "Novo produto";
    }

    function showProductForm(product) {
      productFormCard.hidden = false;
      productFormError.textContent = "";
      productImageInput.value = "";
      if (product) {
        productFormTitle.textContent = "Editar produto";
        productIdInput.value = product.id;
        productNameInput.value = product.name;
        productDescriptionInput.value = product.description || "";
        productPriceInput.value = Number(product.price).toFixed(2);
        productCategoryInput.value = product.category;
        productFeaturedInput.checked = !!product.featured;
        productAvailableInput.checked = !!product.available;
        setProductImagePreview(product.image_url || null);
      } else {
        resetProductForm();
      }
    }

    function hideProductForm() {
      productFormCard.hidden = true;
      resetProductForm();
    }

    function productPayload() {
      return {
        name: productNameInput.value.trim(),
        description: productDescriptionInput.value.trim(),
        price: Number(productPriceInput.value),
        category: productCategoryInput.value,
        featured: productFeaturedInput.checked,
        available: productAvailableInput.checked
      };
    }

    async function loadProducts() {
      productsError.textContent = "";
      productsEl.innerHTML = '<div class="empty">Carregando…</div>';
      try {
        const data = await api("/api/admin/products");
        const products = data.products || [];
        if (!products.length) {
          productsEl.innerHTML = '<div class="empty">Nenhum produto cadastrado.</div>';
          return;
        }
        productsEl.innerHTML = products.map(renderProduct).join("");
        productsEl.querySelectorAll("[data-edit-product]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            const id = Number(btn.getAttribute("data-edit-product"));
            const product = products.find(function(item) { return item.id === id; });
            if (product) showProductForm(product);
          });
        });
      } catch (error) {
        productsEl.innerHTML = "";
        productsError.textContent = error.message;
      }
    }

    async function uploadProductImage(id, file) {
      const form = new FormData();
      form.append("image", file);
      const response = await fetch("/api/admin/products/" + encodeURIComponent(id) + "/image", {
        method: "POST",
        headers: { Authorization: "Bearer " + token() },
        body: form
      });
      const data = await response.json().catch(function() { return {}; });
      if (response.status === 401) {
        setToken(null);
        showLogin();
        throw new Error("Sessão expirada.");
      }
      if (!response.ok) throw new Error(data.error || "Erro ao enviar imagem.");
      return data.product;
    }

    async function saveProduct(event) {
      event.preventDefault();
      productFormError.textContent = "";
      const saveBtn = document.getElementById("saveProductBtn");
      saveBtn.disabled = true;
      try {
        const payload = productPayload();
        const editingId = productIdInput.value;
        let product;
        if (editingId) {
          const data = await api("/api/admin/products/" + encodeURIComponent(editingId), {
            method: "PUT",
            body: JSON.stringify(payload)
          });
          product = data.product;
        } else {
          const data = await api("/api/admin/products", {
            method: "POST",
            body: JSON.stringify(payload)
          });
          product = data.product;
        }
        const file = productImageInput.files[0];
        if (file) {
          product = await uploadProductImage(product.id, file);
        }
        hideProductForm();
        await loadProducts();
      } catch (error) {
        productFormError.textContent = error.message;
      } finally {
        saveBtn.disabled = false;
      }
    }

    function showSection(section) {
      currentSection = section;
      document.querySelectorAll(".main-tab").forEach(function(el) {
        el.classList.toggle("active", el.dataset.section === section);
      });
      ordersView.hidden = section !== "orders";
      productsView.hidden = section !== "products";
      if (section === "orders") {
        loadOrders();
        startOrdersTimer();
      } else {
        stopOrdersTimer();
        loadProducts();
      }
    }

    async function refreshCurrentSection() {
      if (currentSection === "orders") await loadOrders();
      else await loadProducts();
    }

    function startOrdersTimer() {
      stopOrdersTimer();
      if (currentSection === "orders") {
        ordersTimer = setInterval(loadOrders, 30000);
      }
    }

    function stopOrdersTimer() {
      if (ordersTimer) {
        clearInterval(ordersTimer);
        ordersTimer = null;
      }
    }

    function showLogin() {
      stopOrdersTimer();
      loginView.hidden = false;
      panelView.hidden = true;
    }

    function showPanel() {
      loginView.hidden = true;
      panelView.hidden = false;
      showSection(currentSection);
    }

    document.getElementById("tabs").addEventListener("click", function(event) {
      const tab = event.target.closest(".tab");
      if (!tab) return;
      document.querySelectorAll(".tab").forEach(function(el) { el.classList.remove("active"); });
      tab.classList.add("active");
      currentStatus = tab.dataset.status;
      loadOrders();
    });

    document.getElementById("mainTabs").addEventListener("click", function(event) {
      const tab = event.target.closest(".main-tab");
      if (!tab) return;
      showSection(tab.dataset.section);
    });

    loginBtn.addEventListener("click", login);
    passwordInput.addEventListener("keydown", function(event) {
      if (event.key === "Enter") login();
    });
    logoutBtn.addEventListener("click", function() {
      setToken(null);
      showLogin();
    });
    refreshBtn.addEventListener("click", loadOrders);
    document.getElementById("refreshProductsBtn").addEventListener("click", loadProducts);
    document.getElementById("newProductBtn").addEventListener("click", function() {
      showProductForm(null);
    });
    document.getElementById("cancelProductBtn").addEventListener("click", hideProductForm);
    productForm.addEventListener("submit", saveProduct);
    productImageInput.addEventListener("change", function() {
      const file = productImageInput.files[0];
      if (!file) {
        setProductImagePreview(null);
        return;
      }
      const reader = new FileReader();
      reader.onload = function(event) {
        setProductImagePreview(event.target.result);
      };
      reader.readAsDataURL(file);
    });

    if (token()) {
      showPanel();
    } else {
      showLogin();
    }
  </script>
</body>
</html>''';
