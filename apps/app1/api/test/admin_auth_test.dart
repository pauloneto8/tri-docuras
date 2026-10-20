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
      final claims = AdminAuth.verifyToken(AdminAuth.issueToken());
      expect(claims, isNotNull);
      expect(claims!.userId, 0);
      expect(claims.sessionVersion, 0);
    });

    test('token carrega usuário e versão de sessão', () {
      final claims = AdminAuth.verifyToken(
        AdminAuth.issueToken(userId: 7, sessionVersion: 3),
      );
      expect(claims!.userId, 7);
      expect(claims.sessionVersion, 3);
    });

    test('token não contém a senha em claro', () {
      expect(AdminAuth.issueToken(), isNot(contains(_password)));
    });

    test('assinatura adulterada é rejeitada', () {
      final token = AdminAuth.issueToken();
      final lastChar = token[token.length - 1];
      final replacement = lastChar == '0' ? '1' : '0';
      final tampered = '${token.substring(0, token.length - 1)}$replacement';
      expect(AdminAuth.verifyToken(tampered), isNull);
    });

    test('trocar o id do usuário no token é rejeitado', () {
      final parts = AdminAuth.issueToken(userId: 7).split('.');
      final forged = ['8', parts[1], parts[2], parts[3]].join('.');
      expect(AdminAuth.verifyToken(forged), isNull);
    });

    test('expiração estendida é rejeitada (assinatura não bate)', () {
      final parts = AdminAuth.issueToken().split('.');
      final forgedExpiry = int.parse(parts[2]) + 1000 * 60 * 60 * 24;
      final forged = [parts[0], parts[1], '$forgedExpiry', parts[3]].join('.');
      expect(AdminAuth.verifyToken(forged), isNull);
    });

    test('token expirado é rejeitado', () {
      final pastEpoch = DateTime.now()
          .toUtc()
          .subtract(const Duration(hours: 1))
          .millisecondsSinceEpoch;
      final parts = AdminAuth.issueToken().split('.');
      final expired = [parts[0], parts[1], '$pastEpoch', parts[3]].join('.');
      expect(AdminAuth.verifyToken(expired), isNull);
    });

    test('token malformado não lança exceção', () {
      expect(AdminAuth.verifyToken('sem-pontos'), isNull);
      expect(AdminAuth.verifyToken('1.2.3'), isNull);
      expect(AdminAuth.verifyToken('a.b.c.d'), isNull);
      expect(AdminAuth.verifyToken(null), isNull);
    });

    test('token emitido com outra senha não é aceito', () {
      final token = AdminAuth.issueToken();
      Env.override({'APP1_ADMIN_PASSWORD': 'outra-senha'});
      expect(AdminAuth.verifyToken(token), isNull);
    });
  });

  group('AdminAuth (APP1_ADMIN_SECRET separada da senha)', () {
    setUp(() => Env.override({
          'APP1_ADMIN_PASSWORD': _password,
          'APP1_ADMIN_SECRET': 'chave-propria-do-token',
        }));
    tearDown(Env.reset);

    test('token verifica com a chave própria', () {
      expect(AdminAuth.verifyToken(AdminAuth.issueToken()), isNotNull);
    });

    test('trocar a senha não invalida tokens assinados pela chave própria', () {
      final token = AdminAuth.issueToken();
      Env.override({
        'APP1_ADMIN_PASSWORD': 'senha-nova',
        'APP1_ADMIN_SECRET': 'chave-propria-do-token',
      });
      expect(AdminAuth.verifyToken(token), isNotNull);
    });

    test('token não verifica quando a chave muda', () {
      final token = AdminAuth.issueToken();
      Env.override({
        'APP1_ADMIN_PASSWORD': _password,
        'APP1_ADMIN_SECRET': 'outra-chave',
      });
      expect(AdminAuth.verifyToken(token), isNull);
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
      expect(AdminAuth.verifyToken('0.0.9999999999999.abc'), isNull);
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
