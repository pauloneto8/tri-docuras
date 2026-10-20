import 'package:test/test.dart';
import 'package:tri_docuras_api/customers.dart';

void main() {
  Map<String, dynamic> valid() => {
        'email': 'Maria@Exemplo.com',
        'password': 'senha-boa-1',
        'name': '  Maria   Souza ',
        'whatsapp': '(81) 99691-8192',
      };

  group('parseCustomerInput', () {
    test('normaliza e aceita dados válidos', () {
      final input = parseCustomerInput(valid());
      expect(input.email, 'maria@exemplo.com');
      expect(input.name, 'Maria Souza');
      expect(input.whatsapp, '81996918192');
    });

    test('recusa e-mail inválido', () {
      expect(
        () => parseCustomerInput(valid()..['email'] = 'nao-e-email'),
        throwsA(isA<CustomerException>()),
      );
    });

    test('recusa senha curta com a mensagem da regra', () {
      expect(
        () => parseCustomerInput(valid()..['password'] = 'curta'),
        throwsA(
          isA<CustomerException>().having(
            (e) => e.message,
            'message',
            contains('8 caracteres'),
          ),
        ),
      );
    });

    test('recusa nome de uma palavra e WhatsApp fora de 11 dígitos', () {
      expect(
        () => parseCustomerInput(valid()..['name'] = 'M'),
        throwsA(isA<CustomerException>()),
      );
      expect(
        () => parseCustomerInput(valid()..['whatsapp'] = '8199'),
        throwsA(isA<CustomerException>()),
      );
    });
  });

  group('parseCustomerAddresses', () {
    test('sem endereços devolve lista vazia', () {
      expect(parseCustomerAddresses(null), isEmpty);
    });

    test('mais de 5 endereços é recusado', () {
      final six = List.generate(
        6,
        (_) => {'street': 'Rua A', 'number': '1', 'neighborhood': 'Centro'},
      );
      expect(
        () => parseCustomerAddresses(six),
        throwsA(isA<CustomerException>()),
      );
    });

    test('endereço sem número ou bairro é recusado', () {
      expect(
        () => parseCustomerAddresses([
          {'street': 'Rua A', 'number': '', 'neighborhood': 'Centro'},
        ]),
        throwsA(isA<CustomerException>()),
      );
    });

    test('rótulo vazio vira "Endereço"', () {
      final list = parseCustomerAddresses([
        {'street': 'Rua A', 'number': '10', 'neighborhood': 'Centro'},
      ]);
      expect(list.single.label, 'Endereço');
      expect(list.single.complement, isNull);
    });
  });
}
