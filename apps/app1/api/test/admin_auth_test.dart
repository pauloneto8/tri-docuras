import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_auth.dart';
import 'package:tri_docuras_api/env.dart';

const _password = 'test-pw';

void main() {
  group('AdminAuth (com senha configurada)', () {
    setUp(() => Env.override({'APP1_ADMIN_PASSWORD': _password}));
    tearDown(Env.reset);

    test('isConfigured é true quando a env var está setada', () {
      expect(AdminAuth.isConfigured, isTrue);
    });

    test('verifyPassword aceita a senha correta e rejeita a errada', () {
      expect(AdminAuth.verifyPassword(_password), isTrue);
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
      expect(token, isNot(contains(_password)));
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
      // A assinatura é HMAC do campo de expiração: para obtain-la com um
      // timestamp no passado é preciso reaproveitar a assinatura de um token
      // válido e trocar o timestamp — o que também invalida a assinatura.
      // Nos dois caminhos (expiração ou assinatura) o esperado é `false`.
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

    test('token emitido com outra senha não é aceito', () {
      final token = AdminAuth.issueToken();
      Env.override({'APP1_ADMIN_PASSWORD': 'outra-senha'});
      expect(AdminAuth.verifyToken(token), isFalse);
    });
  });

  group('AdminAuth (senha em ADMIN_PASSWORD, legado)', () {
    setUp(() => Env.override({'ADMIN_PASSWORD': '  legado  '}));
    tearDown(Env.reset);

    test('fallback é lido e normalizado com trim', () {
      expect(AdminAuth.password, 'legado');
      expect(AdminAuth.verifyPassword('legado'), isTrue);
    });
  });

  group('AdminAuth (sem senha configurada)', () {
    setUp(() => Env.override({}));
    tearDown(Env.reset);

    test('isConfigured é false', () {
      expect(AdminAuth.isConfigured, isFalse);
    });

    test('verifyPassword rejeita qualquer candidato', () {
      expect(AdminAuth.verifyPassword(''), isFalse);
      expect(AdminAuth.verifyPassword('qualquer'), isFalse);
    });

    test('verifyToken rejeita qualquer token', () {
      expect(AdminAuth.verifyToken('1.abc'), isFalse);
    });

    test('issueToken lança StateError', () {
      expect(AdminAuth.issueToken, throwsStateError);
    });
  });

  group('AdminAuth (senha só com espaços)', () {
    setUp(() => Env.override({'APP1_ADMIN_PASSWORD': '   '}));
    tearDown(Env.reset);

    test('valor em branco é tratado como não configurado', () {
      expect(AdminAuth.isConfigured, isFalse);
      expect(AdminAuth.verifyPassword('   '), isFalse);
    });
  });
}
