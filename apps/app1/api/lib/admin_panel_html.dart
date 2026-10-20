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
    .badge.cancelled { background: #a33; color: #fff; }
    .badge.expired { background: #888; color: #fff; }
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
    .not-owner .owner-only { display: none !important; }
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
    .finance-cards {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      margin-bottom: 12px;
    }
    .finance-card {
      background: var(--card);
      border: 1px solid rgba(65,36,20,.12);
      border-radius: 14px;
      padding: 16px;
    }
    .finance-card .value { font-size: 1.5rem; font-weight: 700; margin-top: 4px; }
    table.data { width: 100%; border-collapse: collapse; }
    table.data th, table.data td {
      text-align: left;
      padding: 8px 6px;
      border-bottom: 1px solid rgba(65,36,20,.08);
      font-size: 0.9rem;
    }
    table.data th { color: var(--brown); font-size: 0.75rem; letter-spacing: .05em; }
    table.data td.num, table.data th.num { text-align: right; }
    .category-pill { display: inline-flex; align-items: center; gap: 8px; margin: 4px 0; }
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
      <label for="email">E-MAIL</label>
      <input id="email" type="email" autocomplete="username" placeholder="Seu e-mail de acesso">
      <div style="height:12px"></div>
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
          <p class="sub">Gerencie pedidos, catálogo e financeiro</p>
        </div>
        <button id="logoutBtn" type="button" class="secondary">Sair</button>
      </div>

      <div class="main-tabs" id="mainTabs" style="margin-bottom:16px">
        <button class="main-tab active" data-section="orders">Pedidos</button>
        <button class="main-tab" data-section="products">Produtos</button>
        <button class="main-tab" data-section="finance">Financeiro</button>
        <button class="main-tab owner-only" data-section="settings">Loja</button>
        <button class="main-tab owner-only" data-section="users">Usuários</button>
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
            <button class="tab" data-status="cancelled">Cancelados</button>
            <button class="tab" data-status="expired">Expirados</button>
          </div>
        </div>
        <div class="toolbar">
          <input id="orderSearch" type="search" placeholder="Buscar por ID ou cliente" style="max-width:240px">
          <label style="margin:0;display:flex;align-items:center;gap:6px">
            <span>De</span>
            <input id="orderFrom" type="date" style="width:auto">
          </label>
          <label style="margin:0;display:flex;align-items:center;gap:6px">
            <span>Até</span>
            <input id="orderTo" type="date" style="width:auto">
          </label>
          <button id="clearOrderFiltersBtn" type="button" class="secondary">Limpar</button>
          <button id="refreshBtn" type="button" class="secondary">Atualizar</button>
        </div>
        <div id="orders"></div>
        <div id="listError" class="error"></div>
      </div>

      <div id="productsView" class="section-view" hidden>
        <div class="toolbar">
          <button id="newProductBtn" type="button">Novo produto</button>
          <button id="refreshProductsBtn" type="button" class="secondary">Atualizar</button>
          <button id="toggleCategoriesBtn" type="button" class="secondary">Categorias</button>
        </div>

        <div id="categoriesCard" class="card" hidden>
          <h2>Categorias</h2>
          <form id="categoryForm" class="form-grid">
            <input type="hidden" id="categoryId" value="">
            <div class="form-row">
              <div>
                <label for="categoryLabel">NOME</label>
                <input id="categoryLabel" required maxlength="100" placeholder="Ex.: Bolos">
              </div>
              <div>
                <label for="categorySort">ORDEM</label>
                <input id="categorySort" type="number" step="1" value="0">
              </div>
            </div>
            <div>
              <label for="categorySlug">IDENTIFICAÇÃO</label>
              <input id="categorySlug" maxlength="50" placeholder="gerada do nome (ex.: bolos)" pattern="[a-z0-9]+(-[a-z0-9]+)*">
            </div>
            <div class="checks">
              <label><input id="categoryActive" type="checkbox" checked> Ativa no app</label>
            </div>
            <div class="actions">
              <button id="saveCategoryBtn" type="submit">Salvar categoria</button>
              <button id="cancelCategoryBtn" type="button" class="secondary">Cancelar</button>
            </div>
          </form>
          <div id="categoryFormError" class="error"></div>
          <div id="categories"></div>
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
                <select id="productCategory" required></select>
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

      <div id="usersView" class="section-view" hidden>
        <div class="toolbar">
          <button id="newUserBtn" type="button">Novo usuário</button>
          <button id="refreshUsersBtn" type="button" class="secondary">Atualizar</button>
        </div>
        <div class="card">
          <h2>Usuários do painel</h2>
          <div id="usersList"></div>
          <div id="usersError" class="error"></div>
        </div>
        <div id="userFormCard" class="card" hidden>
          <h2 id="userFormTitle">Novo usuário</h2>
          <form id="userForm" class="form-grid">
            <input type="hidden" id="userId" value="">
            <div class="form-row">
              <div>
                <label for="userName">NOME</label>
                <input id="userName" required maxlength="100" placeholder="Ex.: Maria">
              </div>
              <div>
                <label for="userEmail">E-MAIL (LOGIN)</label>
                <input id="userEmail" type="email" required maxlength="200">
              </div>
            </div>
            <div class="form-row">
              <div>
                <label for="userRole">PAPEL</label>
                <select id="userRole">
                  <option value="atendente">Atendente: pedidos, produtos e financeiro</option>
                  <option value="dono">Dono: também usuários e loja</option>
                </select>
              </div>
              <div>
                <label for="userPassword" id="userPasswordLabel">SENHA INICIAL</label>
                <input id="userPassword" type="password" minlength="8" maxlength="72" autocomplete="new-password">
              </div>
            </div>
            <div class="checks">
              <label><input id="userActive" type="checkbox" checked> Ativo (pode entrar)</label>
            </div>
            <div class="actions">
              <button id="saveUserBtn" type="submit">Salvar usuário</button>
              <button id="cancelUserBtn" type="button" class="secondary">Cancelar</button>
            </div>
            <div id="userFormError" class="error"></div>
          </form>
        </div>
      </div>
      <div id="settingsView" class="section-view" hidden>
        <div class="card">
          <h2>Loja</h2>
          <form id="settingsForm" class="form-grid">
            <div class="form-row">
              <div>
                <label for="settingsFee">TAXA DE ENTREGA (R$)</label>
                <input id="settingsFee" type="number" min="0" max="100" step="0.01" required>
              </div>
              <div class="checks" style="align-self:end">
                <label><input id="settingsOpen" type="checkbox"> Loja aberta (aceita pedidos)</label>
              </div>
            </div>
            <div>
              <label for="settingsNotice">AVISO NO APP</label>
              <textarea id="settingsNotice" maxlength="300" placeholder="Ex.: Fechado no feriado. Voltamos dia 2."></textarea>
            </div>
            <div class="actions">
              <button id="saveSettingsBtn" type="submit">Salvar configurações</button>
            </div>
            <div id="settingsError" class="error"></div>
          </form>
        </div>
      </div>
      <div id="financeView" class="section-view" hidden>
        <div class="toolbar">
          <div class="tabs" id="financePresets">
            <button class="tab active" data-period="today">Hoje</button>
            <button class="tab" data-period="7d">7 dias</button>
            <button class="tab" data-period="month">Este mês</button>
          </div>
        </div>
        <div class="toolbar">
          <label style="margin:0;display:flex;align-items:center;gap:6px">
            <span>De</span>
            <input id="financeFrom" type="date" style="width:auto">
          </label>
          <label style="margin:0;display:flex;align-items:center;gap:6px">
            <span>Até</span>
            <input id="financeTo" type="date" style="width:auto">
          </label>
          <button id="applyFinanceBtn" type="button">Aplicar</button>
          <button id="refreshFinanceBtn" type="button" class="secondary">Atualizar</button>
        </div>
        <div class="finance-cards" id="financeCards"></div>
        <div class="card">
          <h2>Faturamento por dia</h2>
          <div id="financeDaily"></div>
        </div>
        <div class="card">
          <h2>Vendas por produto</h2>
          <div id="financeProducts"></div>
        </div>
        <div id="financeError" class="error"></div>
      </div>
    </div>
  </div>

  <script>
    const TOKEN_KEY = "td_admin_token";
    let currentStatus = "active";
    let currentSection = "orders";
    let ordersTimer = null;
    let categoryList = [];

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
    const financeView = document.getElementById("financeView");
    const settingsView = document.getElementById("settingsView");
    const usersView = document.getElementById("usersView");
    const usersList = document.getElementById("usersList");
    const usersError = document.getElementById("usersError");
    const userFormCard = document.getElementById("userFormCard");
    const userForm = document.getElementById("userForm");
    const userFormTitle = document.getElementById("userFormTitle");
    const userIdInput = document.getElementById("userId");
    const userNameInput = document.getElementById("userName");
    const userEmailInput = document.getElementById("userEmail");
    const userRoleInput = document.getElementById("userRole");
    const userActiveInput = document.getElementById("userActive");
    const userPasswordInput = document.getElementById("userPassword");
    const userPasswordLabel = document.getElementById("userPasswordLabel");
    const userFormError = document.getElementById("userFormError");
    const emailInput = document.getElementById("email");
    const userSaveBtn = document.getElementById("saveUserBtn");
    let currentUser = null;
    const settingsForm = document.getElementById("settingsForm");
    const settingsFee = document.getElementById("settingsFee");
    const settingsOpen = document.getElementById("settingsOpen");
    const settingsNotice = document.getElementById("settingsNotice");
    const settingsError = document.getElementById("settingsError");
    const orderSearchInput = document.getElementById("orderSearch");
    const orderFromInput = document.getElementById("orderFrom");
    const orderToInput = document.getElementById("orderTo");
    const clearOrderFiltersBtn = document.getElementById("clearOrderFiltersBtn");
    const financeFromInput = document.getElementById("financeFrom");
    const financeToInput = document.getElementById("financeTo");
    const financeCardsEl = document.getElementById("financeCards");
    const financeDailyEl = document.getElementById("financeDaily");
    const financeProductsEl = document.getElementById("financeProducts");
    const financeError = document.getElementById("financeError");
    const categoriesCard = document.getElementById("categoriesCard");
    const categoryForm = document.getElementById("categoryForm");
    const categoryFormError = document.getElementById("categoryFormError");
    const categoryIdInput = document.getElementById("categoryId");
    const categoryLabelInput = document.getElementById("categoryLabel");
    const categorySlugInput = document.getElementById("categorySlug");
    const categorySortInput = document.getElementById("categorySort");
    const categoryActiveInput = document.getElementById("categoryActive");
    const categoriesEl = document.getElementById("categories");
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
        return '<button type="button" data-id="' + order.id + '" data-status="' + action.status + '" data-current="' + order.status + '" data-total="' + order.total + '">' + action.label + '</button>';
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
          (order.refund_label ? '<strong>' + order.refund_label + '</strong><br>' : '') +
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
          body: JSON.stringify({ email: emailInput.value, password: passwordInput.value })
        });
        setToken(data.token);
        applyUser(data.user);
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
      const params = new URLSearchParams({ status: currentStatus });
      const search = orderSearchInput.value.trim();
      if (search) params.set("search", search);
      if (orderFromInput.value) params.set("from", orderFromInput.value);
      if (orderToInput.value) params.set("to", orderToInput.value);
      try {
        const data = await api("/api/admin/orders?" + params.toString());
        const orders = data.orders || [];
        if (!orders.length) {
          ordersEl.innerHTML = '<div class="empty">Nenhum pedido nesta aba.</div>';
          return;
        }
        ordersEl.innerHTML = orders.map(renderOrder).join("");
        ordersEl.querySelectorAll("button[data-status]").forEach(function(btn) {
          btn.addEventListener("click", function() {
            updateStatus(btn.dataset.id, btn.dataset.status, btn, btn.dataset);
          });
        });
      } catch (error) {
        ordersEl.innerHTML = "";
        listError.textContent = error.message;
      }
    }

    async function updateStatus(id, status, button, dataset) {
      let refund;
      if (status === "cancelled") {
        if (!confirm("Cancelar o pedido " + id + "?")) return;
        if (["paid", "preparing", "ready"].indexOf(dataset.current) !== -1) {
          refund = confirm("Estornar " + formatMoney(Number(dataset.total)) + " ao cliente via Pix?\n\nOK = estornar\nCancelar = cancelar sem estorno");
        }
      }
      button.disabled = true;
      try {
        await api("/api/admin/orders/" + encodeURIComponent(id) + "/status", {
          method: "POST",
          body: JSON.stringify({ status, refund })
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
      populateProductCategorySelect();
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
        populateProductCategorySelect(product.category);
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

    function populateProductCategorySelect(keepValue) {
      const current = keepValue !== undefined ? keepValue : productCategoryInput.value;
      productCategoryInput.innerHTML = categoryList.map(function(category) {
        const suffix = category.active ? "" : " (oculta)";
        return '<option value="' + category.slug + '">' + category.label + suffix + '</option>';
      }).join("");
      if (current && categoryList.some(function(c) { return c.slug === current; })) {
        productCategoryInput.value = current;
      } else if (categoryList.length) {
        productCategoryInput.value = categoryList[0].slug;
      }
    }

    function renderCategories() {
      if (!categoryList.length) {
        categoriesEl.innerHTML = '<div class="empty">Nenhuma categoria.</div>';
        return;
      }
      const rows = categoryList.map(function(category) {
        const status = category.active
          ? '<span class="badge available">Ativa</span>'
          : '<span class="badge hidden-product">Oculta</span>';
        return '<tr>' +
          '<td>' + category.label + '</td>' +
          '<td><code>' + category.slug + '</code></td>' +
          '<td class="num">' + category.sort_order + '</td>' +
          '<td>' + status + '</td>' +
          '<td class="num">' +
            '<button type="button" class="secondary" data-edit-category="' + category.id + '">Editar</button> ' +
            '<button type="button" class="secondary" data-delete-category="' + category.id + '">Excluir</button>' +
          '</td>' +
        '</tr>';
      }).join("");
      categoriesEl.innerHTML =
        '<table class="data"><thead><tr>' +
        '<th>Nome</th><th>Identificação</th><th class="num">Ordem</th><th>Status</th><th></th>' +
        '</tr></thead><tbody>' + rows + '</tbody></table>';
      categoriesEl.querySelectorAll("[data-edit-category]").forEach(function(btn) {
        btn.addEventListener("click", function() {
          const id = Number(btn.getAttribute("data-edit-category"));
          const category = categoryList.find(function(item) { return item.id === id; });
          if (category) showCategoryForm(category);
        });
      });
      categoriesEl.querySelectorAll("[data-delete-category]").forEach(function(btn) {
        btn.addEventListener("click", function() {
          deleteCategory(Number(btn.getAttribute("data-delete-category")));
        });
      });
    }

    function resetCategoryForm() {
      categoryIdInput.value = "";
      categoryLabelInput.value = "";
      categorySlugInput.value = "";
      categorySlugInput.disabled = false;
      categorySlugInput.required = false;
      categorySortInput.value = "0";
      categoryActiveInput.checked = true;
      categoryFormError.textContent = "";
    }

    function showCategoryForm(category) {
      categoriesCard.hidden = false;
      resetCategoryForm();
      if (category) {
        categoryIdInput.value = category.id;
        categoryLabelInput.value = category.label;
        categorySlugInput.value = category.slug;
        categorySlugInput.disabled = true;
        categorySortInput.value = category.sort_order;
        categoryActiveInput.checked = !!category.active;
      }
      categoryLabelInput.focus();
    }

    function categoryPayload() {
      const payload = {
        label: categoryLabelInput.value.trim(),
        sort_order: Number(categorySortInput.value) || 0,
        active: categoryActiveInput.checked
      };
      if (!categorySlugInput.disabled) {
        payload.slug = categorySlugInput.value.trim();
      }
      return payload;
    }

    async function saveCategory(event) {
      event.preventDefault();
      categoryFormError.textContent = "";
      const saveBtn = document.getElementById("saveCategoryBtn");
      saveBtn.disabled = true;
      try {
        const editingId = categoryIdInput.value;
        if (editingId) {
          await api("/api/admin/categories/" + encodeURIComponent(editingId), {
            method: "PUT",
            body: JSON.stringify(categoryPayload())
          });
        } else {
          await api("/api/admin/categories", {
            method: "POST",
            body: JSON.stringify(categoryPayload())
          });
        }
        resetCategoryForm();
        await loadProducts();
      } catch (error) {
        categoryFormError.textContent = error.message;
      } finally {
        saveBtn.disabled = false;
      }
    }

    async function deleteCategory(id) {
      if (!confirm("Excluir esta categoria?")) return;
      categoryFormError.textContent = "";
      try {
        await api("/api/admin/categories/" + encodeURIComponent(id), { method: "DELETE" });
        if (Number(categoryIdInput.value) === id) resetCategoryForm();
        await loadProducts();
      } catch (error) {
        categoryFormError.textContent = error.message;
      }
    }

    function applyUser(user) {
      currentUser = user;
      document.body.classList.toggle("not-owner", !(user && user.role === "dono"));
    }

    async function loadMe() {
      const data = await api("/api/admin/me");
      applyUser(data.user);
    }

    function resetUserForm() {
      userIdInput.value = "";
      userNameInput.value = "";
      userEmailInput.value = "";
      userEmailInput.disabled = false;
      userRoleInput.value = "atendente";
      userActiveInput.checked = true;
      userPasswordInput.value = "";
      userPasswordInput.required = true;
      userPasswordLabel.textContent = "SENHA INICIAL";
      userFormTitle.textContent = "Novo usuário";
      userFormError.textContent = "";
      userFormCard.hidden = true;
    }

    function openUserForm(user) {
      resetUserForm();
      userIdInput.value = String(user.id);
      userNameInput.value = user.name;
      userEmailInput.value = user.email;
      userEmailInput.disabled = true;
      userRoleInput.value = user.role;
      userActiveInput.checked = user.active;
      userPasswordInput.required = false;
      userPasswordLabel.textContent = "NOVA SENHA (OPCIONAL)";
      userFormTitle.textContent = "Editar usuário";
      userFormCard.hidden = false;
      userNameInput.focus();
    }

    function renderUserRow(user) {
      const row = document.createElement("div");
      row.className = "card product-row";
      const info = document.createElement("div");
      info.style.flex = "1";
      const title = document.createElement("div");
      title.className = "product-name";
      title.textContent = user.name + (user.role === "dono" ? " · dono" : " · atendente");
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = user.email + (user.active ? "" : " · desativado");
      info.appendChild(title);
      info.appendChild(meta);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = "Editar";
      button.addEventListener("click", function() { openUserForm(user); });
      row.appendChild(info);
      row.appendChild(button);
      return row;
    }

    async function loadUsers() {
      usersError.textContent = "";
      usersList.innerHTML = '<div class="empty">Carregando…</div>';
      try {
        const data = await api("/api/admin/users");
        usersList.innerHTML = "";
        if (!data.users.length) {
          usersList.innerHTML = '<div class="empty">Nenhum usuário.</div>';
          return;
        }
        data.users.forEach(function(user) { usersList.appendChild(renderUserRow(user)); });
      } catch (error) {
        usersList.innerHTML = "";
        usersError.textContent = error.message;
      }
    }

    async function saveUser(event) {
      event.preventDefault();
      userFormError.textContent = "";
      userSaveBtn.disabled = true;
      try {
        const editingId = userIdInput.value;
        const payload = {
          name: userNameInput.value,
          role: userRoleInput.value,
          active: userActiveInput.checked
        };
        if (editingId) {
          if (userPasswordInput.value) payload.password = userPasswordInput.value;
          await api("/api/admin/users/" + encodeURIComponent(editingId), {
            method: "PUT",
            body: JSON.stringify(payload)
          });
        } else {
          payload.email = userEmailInput.value;
          payload.password = userPasswordInput.value;
          await api("/api/admin/users", { method: "POST", body: JSON.stringify(payload) });
        }
        resetUserForm();
        await loadUsers();
      } catch (error) {
        userFormError.textContent = error.message;
      } finally {
        userSaveBtn.disabled = false;
      }
    }

    async function loadSettings() {
      settingsError.textContent = "";
      try {
        const data = await api("/api/admin/settings");
        settingsFee.value = Number(data.settings.delivery_fee).toFixed(2);
        settingsOpen.checked = data.settings.store_open;
        settingsNotice.value = data.settings.notice;
      } catch (error) {
        settingsError.textContent = error.message;
      }
    }

    async function saveSettings(event) {
      event.preventDefault();
      settingsError.textContent = "";
      const saveBtn = document.getElementById("saveSettingsBtn");
      saveBtn.disabled = true;
      try {
        await api("/api/admin/settings", {
          method: "PUT",
          body: JSON.stringify({
            delivery_fee: settingsFee.value,
            store_open: settingsOpen.checked,
            notice: settingsNotice.value
          })
        });
        await loadSettings();
      } catch (error) {
        settingsError.textContent = error.message;
      } finally {
        saveBtn.disabled = false;
      }
    }

    async function loadProducts() {
      productsError.textContent = "";
      productsEl.innerHTML = '<div class="empty">Carregando…</div>';
      try {
        const data = await api("/api/admin/products");
        categoryList = data.categories || [];
        populateProductCategorySelect();
        renderCategories();
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

    function toDateInput(date) {
      return date.getFullYear() + "-" +
        String(date.getMonth() + 1).padStart(2, "0") + "-" +
        String(date.getDate()).padStart(2, "0");
    }

    function setFinancePeriod(period) {
      const today = new Date();
      let from = new Date(today);
      if (period === "7d") {
        from.setDate(today.getDate() - 6);
      } else if (period === "month") {
        from = new Date(today.getFullYear(), today.getMonth(), 1);
      }
      financeFromInput.value = toDateInput(from);
      financeToInput.value = toDateInput(today);
    }

    function renderFinanceCards(totals) {
      const cards = [
        { label: "Faturamento", value: formatMoney(totals.revenue || 0) },
        { label: "Pedidos pagos", value: totals.orders || 0 },
        { label: "Ticket médio", value: formatMoney(totals.average_ticket || 0) },
        { label: "Taxas de entrega", value: formatMoney(totals.delivery_fees || 0) }
      ];
      financeCardsEl.innerHTML = cards.map(function(card) {
        return '<div class="finance-card"><div class="meta">' + card.label +
          '</div><div class="value">' + card.value + '</div></div>';
      }).join("");
    }

    function renderFinanceDaily(daily) {
      if (!daily.length) {
        financeDailyEl.innerHTML = '<div class="empty">Sem vendas no período.</div>';
        return;
      }
      const rows = daily.map(function(day) {
        const d = new Date(day.date + "T00:00:00");
        return '<tr><td>' + d.toLocaleDateString("pt-BR") + '</td>' +
          '<td class="num">' + day.orders + '</td>' +
          '<td class="num">' + formatMoney(day.revenue) + '</td></tr>';
      }).join("");
      financeDailyEl.innerHTML = '<table class="data"><thead><tr><th>Dia</th>' +
        '<th class="num">Pedidos</th><th class="num">Faturamento</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>';
    }

    function renderFinanceProducts(products) {
      if (!products.length) {
        financeProductsEl.innerHTML = '<div class="empty">Sem produtos vendidos no período.</div>';
        return;
      }
      const rows = products.map(function(item) {
        return '<tr><td>' + item.product_name + '</td>' +
          '<td class="num">' + item.quantity + '</td>' +
          '<td class="num">' + formatMoney(item.revenue) + '</td></tr>';
      }).join("");
      financeProductsEl.innerHTML = '<table class="data"><thead><tr><th>Produto</th>' +
        '<th class="num">Qtd</th><th class="num">Receita</th></tr></thead>' +
        '<tbody>' + rows + '</tbody></table>';
    }

    async function loadFinance() {
      financeError.textContent = "";
      financeCardsEl.innerHTML = '<div class="empty">Carregando…</div>';
      financeDailyEl.innerHTML = "";
      financeProductsEl.innerHTML = "";
      const params = new URLSearchParams();
      if (financeFromInput.value) params.set("from", financeFromInput.value);
      if (financeToInput.value) params.set("to", financeToInput.value);
      try {
        const data = await api("/api/admin/finance/report?" + params.toString());
        renderFinanceCards(data.totals || {});
        renderFinanceDaily(data.daily || []);
        renderFinanceProducts(data.by_product || []);
      } catch (error) {
        financeCardsEl.innerHTML = "";
        financeError.textContent = error.message;
      }
    }

    function showSection(section) {
      currentSection = section;
      document.querySelectorAll(".main-tab").forEach(function(el) {
        el.classList.toggle("active", el.dataset.section === section);
      });
      ordersView.hidden = section !== "orders";
      productsView.hidden = section !== "products";
      financeView.hidden = section !== "finance";
      settingsView.hidden = section !== "settings";
      usersView.hidden = section !== "users";
      if (section === "orders") {
        loadOrders();
        startOrdersTimer();
      } else if (section === "products") {
        stopOrdersTimer();
        loadProducts();
      } else if (section === "settings") {
        stopOrdersTimer();
        loadSettings();
      } else if (section === "users") {
        stopOrdersTimer();
        resetUserForm();
        loadUsers();
      } else {
        stopOrdersTimer();
        loadFinance();
      }
    }

    async function refreshCurrentSection() {
      if (currentSection === "orders") await loadOrders();
      else if (currentSection === "products") await loadProducts();
      else if (currentSection === "settings") await loadSettings();
      else if (currentSection === "users") await loadUsers();
      else await loadFinance();
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
      document.querySelectorAll("#tabs .tab").forEach(function(el) { el.classList.remove("active"); });
      tab.classList.add("active");
      currentStatus = tab.dataset.status;
      loadOrders();
    });

    document.getElementById("financePresets").addEventListener("click", function(event) {
      const tab = event.target.closest(".tab");
      if (!tab) return;
      document.querySelectorAll("#financePresets .tab").forEach(function(el) { el.classList.remove("active"); });
      tab.classList.add("active");
      setFinancePeriod(tab.dataset.period);
      loadFinance();
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
    let searchTimer = null;
    orderSearchInput.addEventListener("input", function() {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadOrders, 400);
    });
    orderSearchInput.addEventListener("keydown", function(event) {
      if (event.key === "Enter") {
        clearTimeout(searchTimer);
        loadOrders();
      }
    });
    orderFromInput.addEventListener("change", loadOrders);
    orderToInput.addEventListener("change", loadOrders);
    clearOrderFiltersBtn.addEventListener("click", function() {
      orderSearchInput.value = "";
      orderFromInput.value = "";
      orderToInput.value = "";
      loadOrders();
    });

    document.getElementById("applyFinanceBtn").addEventListener("click", loadFinance);
    document.getElementById("refreshFinanceBtn").addEventListener("click", loadFinance);

    document.getElementById("refreshProductsBtn").addEventListener("click", loadProducts);
    document.getElementById("newProductBtn").addEventListener("click", function() {
      showProductForm(null);
    });
    document.getElementById("cancelProductBtn").addEventListener("click", hideProductForm);
    document.getElementById("toggleCategoriesBtn").addEventListener("click", function() {
      categoriesCard.hidden = !categoriesCard.hidden;
      if (!categoriesCard.hidden && !categoryList.length) loadProducts();
    });
    document.getElementById("cancelCategoryBtn").addEventListener("click", function() {
      categoriesCard.hidden = true;
      resetCategoryForm();
    });
    categoryForm.addEventListener("submit", saveCategory);
    settingsForm.addEventListener("submit", saveSettings);
    userForm.addEventListener("submit", saveUser);
    document.getElementById("newUserBtn").addEventListener("click", function() {
      resetUserForm();
      userFormCard.hidden = false;
      userNameInput.focus();
    });
    document.getElementById("refreshUsersBtn").addEventListener("click", loadUsers);
    document.getElementById("cancelUserBtn").addEventListener("click", resetUserForm);
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

    setFinancePeriod("today");

    if (token()) {
      loadMe().then(showPanel).catch(showLogin);
    } else {
      showLogin();
    }
  </script>
</body>
</html>''';
