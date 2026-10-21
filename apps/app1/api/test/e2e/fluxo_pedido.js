// Fluxo completo contra uma API no ar (cadastro, pedido, acompanhamento,
// painel, exclusão). Não roda no CI: é para conferir um ambiente de teste
// depois de um deploy, sem tocar em produção.
//
// Uso (Node 20+), com a API de teste no ar e um dono cadastrado nela:
//   BASE_URL=http://localhost:8080 ADMIN_EMAIL=... ADMIN_PASSWORD=... \
//     node test/e2e/fluxo_pedido.js
//
// Cria uma conta de teste e a exclui no fim. Os pedidos ficam no banco de
// teste. Não rode com BASE_URL de produção.
const base = process.env.BASE_URL || 'http://localhost:8080';
async function call(method, path, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const r = await fetch(base + path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  let data = null;
  try { data = await r.json(); } catch (_) {}
  return { status: r.status, data };
}
const results = [];
function check(name, ok, detail) { results.push((ok ? 'OK   ' : 'FAIL ') + name + (detail ? ' — ' + detail : '')); }
(async () => {
  const email = `e2e-${Date.now()}@test.invalid`;
  const password = 'senha-e2e-1';

  let r = await call('POST', '/api/customers', { email, password, name: 'Cliente E2E', whatsapp: '81999990000' });
  check('cadastro sem aceite recusa (400)', r.status === 400, String(r.status));
  r = await call('POST', '/api/customers', { email, password, name: 'Cliente E2E', whatsapp: '81999990000', accepted_terms: true });
  check('cadastro com aceite (201)', r.status === 201, String(r.status));
  const token = r.data && r.data.token;

  r = await call('GET', '/api/customers/me', null, token);
  check('perfil com token (200)', r.status === 200, String(r.status));

  r = await call('POST', '/api/customers/session', { email, password: 'errada-123' });
  check('login com senha errada (401)', r.status === 401, String(r.status));
  r = await call('POST', '/api/customers/session', { email, password });
  check('login com senha certa (200)', r.status === 200, String(r.status));

  r = await call('GET', '/api/products');
  const product = r.data.products.find((p) => p.available !== false);
  check('catálogo tem produto', !!product, product ? product.name : 'sem produto');

  const order = {
    customer_name: 'Cliente E2E', whatsapp: '81999990000', delivery_mode: 'pickup',
    accepted_terms: true,
    items: [{ product_id: product.id, quantity: 1, option_ids: [product.options.find((o) => o.kind === 'size').id] }],
  };
  r = await call('POST', '/api/orders', { ...order, accepted_terms: false }, token);
  check('pedido sem aceite recusa (400)', r.status === 400, String(r.status));
  r = await call('POST', '/api/orders', order);
  check('pedido sem sessão recusa (401)', r.status === 401, String(r.status));
  r = await call('POST', '/api/orders', order, token);
  check('pedido com sessão (201)', r.status === 201, String(r.status) + ' ' + JSON.stringify(r.data).slice(0, 160));
  const created = r.data && r.data.order;
  const id = created && created.id;
  const orderToken = created && created.tracking_token;

  r = await call('GET', `/api/orders/${id}/tracking`);
  check('acompanhamento sem token e sem sessão recusa (404)', r.status === 404, String(r.status));
  r = await call('GET', `/api/orders/${id}/tracking?t=errado`);
  check('acompanhamento com token errado recusa (404)', r.status === 404, String(r.status));
  r = await call('GET', `/api/orders/${id}/tracking?t=${orderToken}`);
  check('acompanhamento com token certo (200)', r.status === 200, String(r.status));

  r = await call('GET', '/api/customers/me/orders', null, token);
  check('pedido aparece no histórico da conta', r.status === 200 && JSON.stringify(r.data).includes(id), String(r.status));

  r = await call('DELETE', '/api/customers/me', { password: 'errada-123' }, token);
  check('excluir com senha errada recusa', r.status >= 400, String(r.status));
  r = await call('DELETE', '/api/customers/me', { password }, token);
  check('excluir com pedido em andamento recusa (409)', r.status === 409, String(r.status));

  r = await call('POST', '/api/admin/session', { email: process.env.ADMIN_EMAIL, password: process.env.ADMIN_PASSWORD });
  const admin = r.data && (r.data.token || r.data.session_token);
  check('login do painel (200)', r.status === 200 && !!admin, String(r.status) + ' keys=' + Object.keys(r.data || {}).join(','));
  r = await call('POST', `/api/admin/orders/${id}/status`, { status: 'cancelled', refund: false }, admin);
  check('painel cancela pedido pendente', r.status === 200, String(r.status) + ' ' + JSON.stringify(r.data).slice(0, 120));
  r = await call('GET', '/api/admin/orders?status=cancelled', null, admin);
  const adminOrder = r.data && (r.data.orders || []).find((o) => o.id === id);
  check('painel mostra vínculo com conta', !!adminOrder && adminOrder.customer_account && adminOrder.customer_account.email === email, adminOrder ? JSON.stringify(adminOrder.customer_account) : 'pedido não listado');

  r = await call('DELETE', '/api/customers/me', { password }, token);
  check('excluir conta sem pedido em andamento (200)', r.status === 200, String(r.status));
  r = await call('POST', '/api/customers/session', { email, password });
  check('login após excluir falha (401)', r.status === 401, String(r.status));
  r = await call('GET', `/api/orders/${id}/tracking?t=${orderToken}`);
  check('pedido anonimizado segue com token (200), sem nome', r.status === 200 && !JSON.stringify(r.data).includes('Cliente E2E'), String(r.status));

  console.log(results.join('\n'));
})().catch((e) => { console.error('ERRO', e); process.exit(1); });
