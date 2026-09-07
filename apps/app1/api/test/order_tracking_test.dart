import 'package:test/test.dart';
import 'package:tri_docuras_api/order_tracking.dart';

void main() {
  group('buildCustomerTimeline', () {
    test('pending_payment marca só pedido recebido como atual', () {
      final timeline = buildCustomerTimeline('pending_payment', 'pickup');
      expect(timeline.first['done'], isTrue);
      expect(timeline.first['current'], isTrue);
      expect(timeline[1]['done'], isFalse);
    });

    test('preparing marca etapas anteriores como concluídas', () {
      final timeline = buildCustomerTimeline('preparing', 'delivery');
      expect(timeline[0]['done'], isTrue);
      expect(timeline[1]['done'], isTrue);
      expect(timeline[2]['current'], isTrue);
      expect(timeline[3]['label'], 'Pronto para entrega');
    });

    test('completed marca todas as etapas', () {
      final timeline = buildCustomerTimeline('completed', 'pickup');
      expect(timeline.every((step) => step['done'] == true), isTrue);
      expect(timeline.last['current'], isTrue);
    });
  });
}
