/// Limita a reconsulta de pagamento ao Mercado Pago a uma vez por intervalo
/// por pedido. Em memória: basta para uma única instância da API.
class PaymentCheckThrottle {
  PaymentCheckThrottle({
    this.interval = const Duration(seconds: 15),
    this.retention = const Duration(hours: 1),
  });

  final Duration interval;
  final Duration retention;
  final Map<String, DateTime> _lastCheck = {};

  /// `true` se já passou [interval] desde a última consulta do pedido (e
  /// registra esta). Entradas mais antigas que [retention] são descartadas.
  bool shouldCheck(String publicId, DateTime now) {
    _lastCheck.removeWhere((_, at) => now.difference(at) > retention);
    final last = _lastCheck[publicId];
    if (last != null && now.difference(last) < interval) return false;
    _lastCheck[publicId] = now;
    return true;
  }

  int get trackedOrders => _lastCheck.length;
}
