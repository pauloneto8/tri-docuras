import 'package:test/test.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/env.dart';

void main() {
  final now = DateTime.utc(2026, 10, 20, 12);

  setUp(() => Env.override({'APP1_CUSTOMER_SECRET': 'segredo-de-teste'}));
  tearDown(Env.reset);

  group('passwordProblem', () {
    test('menos de 8 caracteres é recusado', () {
      expect(CustomerAuth.passwordProblem('1234567'), isNotNull);
    });

    test('8 caracteres é aceito', () {
      expect(CustomerAuth.passwordProblem('12345678'), isNull);
    });

    test('mais de 72 bytes é recusado (bcrypt truncaria em silêncio)', () {
      expect(CustomerAuth.passwordProblem('a' * 73), isNotNull);
      expect(CustomerAuth.passwordProblem('a' * 72), isNull);
    });

    test('acentos contam em bytes, não em caracteres', () {
      // 37 caracteres "ç" = 74 bytes em UTF-8.
      expect(CustomerAuth.passwordProblem('ç' * 37), isNotNull);
    });
  });

  group('normalizeEmail', () {
    test('minúsculas e sem espaços', () {
      expect(CustomerAuth.normalizeEmail('  Maria@Exemplo.COM '),
          'maria@exemplo.com');
    });

    test('recusa formatos inválidos', () {
      for (final bad in ['', 'sem-arroba', 'a@b', 'a b@c.com', 'a@@b.com']) {
        expect(CustomerAuth.normalizeEmail(bad), isNull, reason: bad);
      }
    });
  });

  group('hash de senha', () {
    test('verifica a senha certa e recusa a errada', () {
      final hash = CustomerAuth.hashPassword('senha-boa-1', rounds: 4);
      expect(CustomerAuth.verifyPassword('senha-boa-1', hash), isTrue);
      expect(CustomerAuth.verifyPassword('senha-ruim-1', hash), isFalse);
    });

    test('o hash não contém a senha e muda a cada geração (sal)', () {
      final a = CustomerAuth.hashPassword('mesma-senha', rounds: 4);
      final b = CustomerAuth.hashPassword('mesma-senha', rounds: 4);
      expect(a.contains('mesma-senha'), isFalse);
      expect(a, isNot(b));
    });

    test('hash inválido não derruba, só recusa', () {
      expect(CustomerAuth.verifyPassword('qualquer', 'lixo'), isFalse);
    });
  });

  group('token', () {
    test('ida e volta preserva o cliente e a versão da sessão', () {
      final token = CustomerAuth.issueToken(
        customerId: 42,
        sessionVersion: 3,
        now: now,
      );
      final session = CustomerAuth.parseToken(token, now);
      expect(session?.customerId, 42);
      expect(session?.sessionVersion, 3);
    });

    test('expira depois de 30 dias', () {
      final token = CustomerAuth.issueToken(
        customerId: 1,
        sessionVersion: 0,
        now: now,
      );
      expect(
        CustomerAuth.parseToken(
          token,
          now.add(CustomerAuth.tokenTtl - const Duration(minutes: 1)),
        ),
        isNotNull,
      );
      expect(
        CustomerAuth.parseToken(
          token,
          now.add(CustomerAuth.tokenTtl + const Duration(minutes: 1)),
        ),
        isNull,
      );
    });

    test('adulterar o id ou a versão invalida a assinatura', () {
      final token = CustomerAuth.issueToken(
        customerId: 1,
        sessionVersion: 0,
        now: now,
      );
      final parts = token.split('.');
      final forgedId = '2.${parts[1]}.${parts[2]}.${parts[3]}';
      final forgedVersion = '${parts[0]}.9.${parts[2]}.${parts[3]}';
      expect(CustomerAuth.parseToken(forgedId, now), isNull);
      expect(CustomerAuth.parseToken(forgedVersion, now), isNull);
    });

    test('token emitido com outra chave não vale', () {
      final token = CustomerAuth.issueToken(
        customerId: 1,
        sessionVersion: 0,
        now: now,
      );
      Env.override({'APP1_CUSTOMER_SECRET': 'outra-chave'});
      expect(CustomerAuth.parseToken(token, now), isNull);
    });

    test('sem chave configurada não emite nem valida', () {
      Env.override({});
      expect(CustomerAuth.isConfigured, isFalse);
      expect(
        () => CustomerAuth.issueToken(
          customerId: 1,
          sessionVersion: 0,
          now: now,
        ),
        throwsStateError,
      );
      expect(CustomerAuth.parseToken('1.0.9999999999999.x', now), isNull);
    });

    test('token de formato errado é recusado', () {
      for (final bad in [null, '', 'abc', '1.2.3', '1.2.3.4.5']) {
        expect(CustomerAuth.parseToken(bad, now), isNull, reason: '$bad');
      }
    });

    test('bearerToken extrai só o valor do cabeçalho Bearer', () {
      expect(CustomerAuth.bearerToken('Bearer abc.def'), 'abc.def');
      expect(CustomerAuth.bearerToken('Basic abc'), isNull);
      expect(CustomerAuth.bearerToken('Bearer '), isNull);
      expect(CustomerAuth.bearerToken(null), isNull);
    });
  });

  group('canAccessOrder', () {
    test('pedido sem conta não é público, nem com sessão', () {
      expect(
        canAccessOrder(orderCustomerId: null, sessionCustomerId: null),
        isFalse,
      );
      expect(
        canAccessOrder(orderCustomerId: null, sessionCustomerId: 7),
        isFalse,
      );
    });

    test('pedido com conta só para o próprio dono', () {
      expect(
        canAccessOrder(orderCustomerId: 7, sessionCustomerId: 7),
        isTrue,
      );
      expect(
        canAccessOrder(orderCustomerId: 7, sessionCustomerId: 8),
        isFalse,
      );
      expect(
        canAccessOrder(orderCustomerId: 7, sessionCustomerId: null),
        isFalse,
      );
    });
  });
}
