import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_orders.dart';
import 'package:tri_docuras_api/order_tracking.dart';

void main() {
  expiredStatusTests();
  group('statusLabel', () {
    test('labels em português', () {
      expect(statusLabel('paid', 'pickup'), 'Pago — na fila');
      expect(statusLabel('ready', 'pickup'), 'Pronto para retirada');
      expect(statusLabel('ready', 'delivery'), 'Pronto para entrega');
      expect(statusLabel('completed', 'delivery'), 'Entregue');
      expect(statusLabel('cancelled', 'delivery'), 'Cancelado');
    });
  });

  group('nextActionsFor', () {
    test('paid pode ir para preparo ou pronto', () {
      final actions = nextActionsFor('paid', 'pickup');
      expect(actions.map((a) => a['status']), contains('preparing'));
      expect(actions.map((a) => a['status']), contains('ready'));
    });

    test('ready pode concluir ou cancelar', () {
      final actions = nextActionsFor('ready', 'delivery');
      expect(actions.map((a) => a['status']), contains('completed'));
      expect(actions.map((a) => a['status']), contains('cancelled'));
    });

    test('pending_payment só pode cancelar', () {
      final actions = nextActionsFor('pending_payment', 'pickup');
      expect(actions, hasLength(1));
      expect(actions.first['status'], 'cancelled');
    });

    test('completed não tem ações', () {
      expect(nextActionsFor('completed', 'pickup'), isEmpty);
    });

    test('cancelled não tem ações', () {
      expect(nextActionsFor('cancelled', 'pickup'), isEmpty);
    });
  });

  group('actionLabel', () {
    test('retirada vs entrega', () {
      expect(actionLabel('completed', 'pickup'), 'Confirmar retirada');
      expect(actionLabel('completed', 'delivery'), 'Confirmar entrega');
      expect(actionLabel('cancelled', 'pickup'), 'Cancelar pedido');
    });
  });

  group('adminAllStatuses', () {
    test('inclui cancelled', () {
      expect(adminAllStatuses, contains('cancelled'));
    });
  });
}

void expiredStatusTests() {
  group('status expired', () {
    test('rótulo e sem ações', () {
      expect(statusLabel('expired', 'pickup'), 'Expirado');
      expect(nextActionsFor('expired', 'pickup'), isEmpty);
    });
    test('timeline do cliente mostra pedido expirado', () {
      final t = buildCustomerTimeline('expired', 'pickup');
      expect(t.last['key'], 'expired');
      expect(t.last['current'], isTrue);
    });
  });
}
