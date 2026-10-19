import 'package:test/test.dart';
import 'package:tri_docuras_api/payment_check_throttle.dart';

void main() {
  final t0 = DateTime.utc(2026, 10, 19, 12);

  test('primeira chamada libera e a seguinte, dentro de 15 s, bloqueia', () {
    final throttle = PaymentCheckThrottle();
    expect(throttle.shouldCheck('TD-0001', t0), isTrue);
    expect(
      throttle.shouldCheck('TD-0001', t0.add(const Duration(seconds: 14))),
      isFalse,
    );
  });

  test('libera de novo após 15 s', () {
    final throttle = PaymentCheckThrottle();
    throttle.shouldCheck('TD-0001', t0);
    expect(
      throttle.shouldCheck('TD-0001', t0.add(const Duration(seconds: 15))),
      isTrue,
    );
  });

  test('pedidos diferentes são independentes', () {
    final throttle = PaymentCheckThrottle();
    expect(throttle.shouldCheck('TD-0001', t0), isTrue);
    expect(throttle.shouldCheck('TD-0002', t0), isTrue);
  });

  test('descarta entradas com mais de 1 h', () {
    final throttle = PaymentCheckThrottle();
    throttle.shouldCheck('TD-0001', t0);
    throttle.shouldCheck('TD-0002', t0.add(const Duration(minutes: 61)));
    expect(throttle.trackedOrders, 1);
  });
}
