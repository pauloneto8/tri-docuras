/// Link de acompanhamento sem login: `/pedido/TD-XXXX?t=<token>`, no mesmo
/// domínio em que o cliente está.
Uri trackingLink({required String orderId, required String trackingToken}) {
  final base = Uri.base;
  return Uri(
    scheme: base.scheme,
    host: base.host,
    port: base.hasPort ? base.port : null,
    path: '/pedido/$orderId',
    queryParameters: {'t': trackingToken},
  );
}
