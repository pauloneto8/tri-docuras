import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/orders/order_history_controller.dart';
import 'package:tri_docuras/orders/order_history_entry.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('remember adiciona pedido no topo', () async {
    final history = OrderHistoryController();
    await history.remember(id: 'TD-0001', total: 24.0);
    await history.remember(id: 'TD-0002', total: 36.0);

    expect(history.entries.first.id, 'TD-0002');
    expect(history.entries.length, 2);
  });

  test('remember atualiza pedido existente', () async {
    final history = OrderHistoryController();
    await history.remember(id: 'TD-0001', total: 24.0);
    await history.remember(id: 'TD-0001', total: 30.0);

    expect(history.entries.length, 1);
    expect(history.entries.first.total, 30.0);
  });

  test('remove apaga pedido', () async {
    final history = OrderHistoryController(
      seed: [
        OrderHistoryEntry(
          id: 'TD-0001',
          total: 24,
          createdAt: DateTime(2026),
        ),
      ],
    );
    await history.remove('TD-0001');
    expect(history.isEmpty, isTrue);
  });
}
