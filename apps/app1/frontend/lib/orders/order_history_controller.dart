import 'package:flutter/foundation.dart';
import 'package:tri_docuras/account/auth_token.dart';
import 'package:tri_docuras/orders/order_history_entry.dart';
import 'package:tri_docuras/services/api_service.dart';

/// Histórico de pedidos do cliente logado, vindo da API. Sem conta, fica
/// vazio. Pedido criado nesta sessão entra na lista em memória até a
/// próxima atualização.
class OrderHistoryController extends ChangeNotifier {
  OrderHistoryController({
    List<OrderHistoryEntry>? seed,
    ApiService? api,
  })  : _entries = [...?seed],
        _api = api ?? ApiService();

  final List<OrderHistoryEntry> _entries;
  final ApiService _api;
  bool _loaded = false;

  List<OrderHistoryEntry> get entries => List.unmodifiable(_entries);
  bool get isLoaded => _loaded;
  bool get isEmpty => _entries.isEmpty;

  Future<void> load() async {
    if (AuthToken.value == null) {
      _entries.clear();
    } else {
      try {
        final orders = await _api.fetchMyOrders();
        _entries
          ..clear()
          ..addAll(orders.map(_entryFromTracking));
      } catch (_) {
        // Sem rede ou sessão recusada: mantém a lista atual.
      }
    }
    _loaded = true;
    notifyListeners();
  }

  void remember({
    required String id,
    required double total,
    String deliveryMode = 'pickup',
    DateTime? createdAt,
  }) {
    _entries.removeWhere((entry) => entry.id == id);
    _entries.insert(
      0,
      OrderHistoryEntry(
        id: id,
        total: total,
        createdAt: createdAt ?? DateTime.now(),
        deliveryMode: deliveryMode,
      ),
    );
    notifyListeners();
  }

  /// Tira o pedido da lista desta sessão. Não apaga nada no servidor.
  void remove(String id) {
    final index = _entries.indexWhere((entry) => entry.id == id);
    if (index < 0) return;
    _entries.removeAt(index);
    notifyListeners();
  }

  void clear() {
    if (_entries.isEmpty) return;
    _entries.clear();
    notifyListeners();
  }

  OrderHistoryEntry _entryFromTracking(Map<String, dynamic> tracking) {
    final order = tracking['order'] as Map<String, dynamic>;
    return OrderHistoryEntry(
      id: order['id'] as String,
      total: (order['total'] as num).toDouble(),
      createdAt: DateTime.parse(order['created_at'] as String).toLocal(),
      deliveryMode: order['delivery_mode'] as String? ?? 'pickup',
    );
  }
}
