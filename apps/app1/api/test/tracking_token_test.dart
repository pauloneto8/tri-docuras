import 'package:test/test.dart';
import 'package:tri_docuras_api/tracking_token.dart';

void main() {
  group('newTrackingToken', () {
    test('gera 32 caracteres base64url, sem padding', () {
      final token = newTrackingToken();
      expect(token, hasLength(32));
      expect(token, matches(RegExp(r'^[A-Za-z0-9_-]+$')));
    });

    test('dois tokens não repetem', () {
      expect(newTrackingToken(), isNot(newTrackingToken()));
    });
  });

  group('trackingUrl', () {
    test('monta o link público do pedido com o token', () {
      expect(
        trackingUrl('TD-0007', 'abc'),
        'https://tridocuras.com.br/pedido/TD-0007?t=abc',
      );
    });
  });

  group('trackingTokenMatches', () {
    test('aceita o token exato', () {
      expect(trackingTokenMatches('abc123', 'abc123'), isTrue);
    });

    test('recusa token diferente, de tamanho diferente ou ausente', () {
      expect(trackingTokenMatches('abc123', 'abc124'), isFalse);
      expect(trackingTokenMatches('abc123', 'abc'), isFalse);
      expect(trackingTokenMatches('abc123', null), isFalse);
    });

    test('recusa quando o pedido não tem token (pedido sem backfill)', () {
      expect(trackingTokenMatches(null, 'abc123'), isFalse);
      expect(trackingTokenMatches('', ''), isFalse);
    });
  });
}
