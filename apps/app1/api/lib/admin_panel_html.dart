const adminPanelHtml = r'''<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Tri Doçuras — Pedidos</title>
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
    input, select, button {
      font: inherit;
      border-radius: 10px;
      border: 1px solid rgba(65,36,20,.15);
      padding: 10px 12px;
    }
    input { width: 100%; background: #fff; }
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
    .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .tab {
      background: var(--peach);
      color: var(--dark);
      border: none;
      padding: 8px 14px;
      border-radius: 999px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
    }
    .tab.active { background: var(--dark); color: #fff; }
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
    .order-head { display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
    .order-id { font-weight: 700; font-size: 1.05rem; }
    .meta { color: var(--brown); font-size: 0.9rem; line-height: 1.5; }
    .items { margin: 10px 0; padding-left: 18px; }
    .items li { margin-bottom: 4px; }
    .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    .empty { text-align: center; color: var(--brown); padding: 32px 12px; }
    .error { color: #a33; font-size: 0.9rem; margin-top: 8px; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
    a.wa { color: var(--pink); text-decoration: none; font-weight: 600; }
    @media (max-width: 600px) {
      .wrap { padding: 12px; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div id="loginView" class="login card">
      <h1>Tri Doçuras</h1>
      <p class="sub">Painel de pedidos</p>
      <label for="password">SENHA</label>
      <input id="password" type="password" autocomplete="current-password" placeholder="Senha do painel">
      <div style="height:12px"></div>
      <button id="loginBtn" type="button" style="width:100%">Entrar</button>
      <div id="loginError" class="error"></div>
    </div>

    <div id="panelView" hidden>
      <div class="topbar">
        <div>
          <h1>Pedidos</h1>
          <p class="sub">Fila da loja — atualize o status conforme prepara e entrega</p>
        </div>
        <button id="logoutBtn" type="button" class="secondary">Sair</button>
      </div>

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
  </div>

  <script>
    const TOKEN_KEY = "td_admin_token";
    let currentStatus = "active";

    const loginView = document.getElementById("loginView");
    const panelView = document.getElementById("panelView");
    const passwordInput = document.getElementById("password");
    const loginBtn = document.getElementById("loginBtn");
    const loginError = document.getElementById("loginError");
    const logoutBtn = document.getElementById("logoutBtn");
    const ordersEl = document.getElementById("orders");
    const listError = document.getElementById("listError");
    const refreshBtn = document.getElementById("refreshBtn");

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
        await loadOrders();
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

    function showLogin() {
      loginView.hidden = false;
      panelView.hidden = true;
    }

    function showPanel() {
      loginView.hidden = true;
      panelView.hidden = false;
    }

    document.getElementById("tabs").addEventListener("click", function(event) {
      const tab = event.target.closest(".tab");
      if (!tab) return;
      document.querySelectorAll(".tab").forEach(function(el) { el.classList.remove("active"); });
      tab.classList.add("active");
      currentStatus = tab.dataset.status;
      loadOrders();
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

    if (token()) {
      showPanel();
      loadOrders();
      setInterval(loadOrders, 30000);
    } else {
      showLogin();
    }
  </script>
</body>
</html>''';
