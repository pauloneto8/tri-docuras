import 'package:test/test.dart';
import 'package:tri_docuras_api/orders.dart';

void main() {
  group('requireAcceptedTerms', () {
    test('aceita quando o cliente marcou o aceite', () {
      expect(() => requireAcceptedTerms(true), returnsNormally);
    });

    test('recusa sem o campo, com false ou com texto no lugar de booleano', () {
      expect(
        () => requireAcceptedTerms(null),
        throwsA(isA<OrderValidationException>()),
      );
      expect(
        () => requireAcceptedTerms(false),
        throwsA(isA<OrderValidationException>()),
      );
      expect(
        () => requireAcceptedTerms('true'),
        throwsA(isA<OrderValidationException>()),
      );
    });
  });
}
