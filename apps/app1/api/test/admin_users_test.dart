import 'package:test/test.dart';
import 'package:tri_docuras_api/admin_users.dart';

void main() {
  group('parseAdminUserInput', () {
    Map<String, dynamic> valid() => {
          'name': 'Ana',
          'email': 'Ana@Loja.com ',
          'role': 'atendente',
          'password': 'senha-forte',
        };

    test('normaliza e-mail na criação', () {
      final input = parseAdminUserInput(valid(), isCreate: true);
      expect(input.email, 'ana@loja.com');
      expect(input.name, 'Ana');
      expect(input.role, 'atendente');
      expect(input.active, isTrue);
    });

    test('recusa e-mail inválido na criação', () {
      expect(
        () => parseAdminUserInput({...valid(), 'email': 'sem-arroba'},
            isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
    });

    test('ignora e-mail na edição', () {
      final input = parseAdminUserInput(
        {...valid(), 'email': 'nao-valido'},
        isCreate: false,
      );
      expect(input.role, 'atendente');
    });

    test('recusa papel desconhecido', () {
      expect(
        () => parseAdminUserInput({...valid(), 'role': 'admin'},
            isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
    });

    test('exige senha inicial na criação, mas não na edição', () {
      final body = valid()..remove('password');
      expect(
        () => parseAdminUserInput(body, isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
      final edit = parseAdminUserInput(body, isCreate: false);
      expect(edit.password, isNull);
    });

    test('recusa senha curta ou longa demais', () {
      expect(
        () => parseAdminUserInput({...valid(), 'password': 'curta'},
            isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
      expect(
        () => parseAdminUserInput(
          {...valid(), 'password': 'x' * 73},
          isCreate: true,
        ),
        throwsA(isA<AdminUserException>()),
      );
    });

    test('recusa nome curto', () {
      expect(
        () => parseAdminUserInput({...valid(), 'name': 'A'}, isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
    });

    test('recusa campo ativo que não é booleano', () {
      expect(
        () => parseAdminUserInput({...valid(), 'active': 'sim'},
            isCreate: true),
        throwsA(isA<AdminUserException>()),
      );
    });
  });
}
