import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_orders.dart';

void main() {
  group('statusLabel', () {
    test('labels em português', () {
      expect(statusLabel('paid', 'pickup'), 'Pago — na fila');
      expect(statusLabel('ready', 'pickup'), 'Pronto para retirada');
      expect(statusLabel('ready', 'delivery'), 'Pronto para entrega');
      expect(statusLabel('completed', 'delivery'), 'Entregue');
    });
  });

  group('nextActionsFor', () {
    test('paid pode ir para preparo ou pronto', () {
      final actions = nextActionsFor('paid', 'pickup');
      expect(actions.map((a) => a['status']), contains('preparing'));
      expect(actions.map((a) => a['status']), contains('ready'));
    });

    test('ready só pode concluir', () {
      final actions = nextActionsFor('ready', 'delivery');
      expect(actions, hasLength(1));
      expect(actions.first['status'], 'completed');
    });

    test('completed não tem ações', () {
      expect(nextActionsFor('completed', 'pickup'), isEmpty);
    });
  });

  group('actionLabel', () {
    test('retirada vs entrega', () {
      expect(actionLabel('completed', 'pickup'), 'Confirmar retirada');
      expect(actionLabel('completed', 'delivery'), 'Confirmar entrega');
    });
  });
}
