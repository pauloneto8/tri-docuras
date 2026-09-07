import 'package:test/test.dart';
import 'package:tri_docuras_api/mercado_pago_client.dart';

void main() {
  group('mercadoPagoStatusIsPaid', () {
    test('approved é pago', () {
      expect(mercadoPagoStatusIsPaid('approved'), isTrue);
    });

    test('pending não é pago', () {
      expect(mercadoPagoStatusIsPaid('pending'), isFalse);
    });
  });
}
