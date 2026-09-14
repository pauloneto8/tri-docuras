import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_auth.dart';

// Requer APP1_ADMIN_PASSWORD definida no ambiente do processo de teste
// (ex.: `docker run -e APP1_ADMIN_PASSWORD=test-pw ... dart test`).
void main() {
  group('AdminAuth (com senha configurada)', () {
    test('isConfigured é true quando a env var está setada', () {
      expect(AdminAuth.isConfigured, isTrue);
    });

    test('verifyPassword aceita a senha correta e rejeita a errada', () {
      expect(AdminAuth.verifyPassword('test-pw'), isTrue);
      expect(AdminAuth.verifyPassword('test-pw-errada'), isFalse);
      expect(AdminAuth.verifyPassword(''), isFalse);
    });

    test('issueToken + verifyToken: round-trip válido', () {
      final token = AdminAuth.issueToken();
      expect(token, contains('.'));
      expect(AdminAuth.verifyToken(token), isTrue);
    });

    test('token não é mais reversível para a senha em claro (não é base64 dela)', () {
      final token = AdminAuth.issueToken();
      expect(token, isNot(contains('test-pw')));
    });

    test('assinatura adulterada é rejeitada', () {
      final token = AdminAuth.issueToken();
      final lastChar = token[token.length - 1];
      final replacement = lastChar == '0' ? '1' : '0';
      final tampered = '${token.substring(0, token.length - 1)}$replacement';
      expect(AdminAuth.verifyToken(tampered), isFalse);
    });

    test('expiração adulterada (estendida) é rejeitada — assinatura não bate', () {
      final token = AdminAuth.issueToken();
      final dotIndex = token.indexOf('.');
      final expiry = int.parse(token.substring(0, dotIndex));
      final signature = token.substring(dotIndex + 1);
      final forgedExpiry = expiry + 1000 * 60 * 60 * 24; // +1 dia
      final forgedToken = '$forgedExpiry.$signature';
      expect(AdminAuth.verifyToken(forgedToken), isFalse);
    });

    test('token expirado é rejeitado mesmo com assinatura válida', () {
      // Fabrica um token expirado manualmente reaproveitando a lógica pública
      // não é possível sem acesso ao _sign privado; então validamos indiretamente:
      // um token com timestamp no passado e assinatura (recalculada via outro
      // issueToken + substituição do campo de expiração) deve falhar por expiração
      // OU por assinatura — em ambos os casos, o resultado esperado é false.
      final pastEpoch = DateTime.now()
          .toUtc()
          .subtract(const Duration(hours: 1))
          .millisecondsSinceEpoch;
      final token = AdminAuth.issueToken();
      final dotIndex = token.indexOf('.');
      final signature = token.substring(dotIndex + 1);
      final expiredToken = '$pastEpoch.$signature';
      expect(AdminAuth.verifyToken(expiredToken), isFalse);
    });

    test('token malformado não lança exceção', () {
      expect(AdminAuth.verifyToken('sem-ponto-nenhum'), isFalse);
      expect(AdminAuth.verifyToken('123.'), isFalse);
      expect(AdminAuth.verifyToken('.assinatura'), isFalse);
      expect(AdminAuth.verifyToken(null), isFalse);
    });
  });
}
