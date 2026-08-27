import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/checkout/checkout_validators.dart';

void main() {
  group('CheckoutValidators.validateName', () {
    test('aceita nome com acentos', () {
      expect(CheckoutValidators.validateName('Maria Fernandes'), isNull);
      expect(CheckoutValidators.validateName('João da Silva'), isNull);
      expect(CheckoutValidators.validateName("Ana O'Brien"), isNull);
      expect(CheckoutValidators.validateName('Maria-Clara Souza'), isNull);
    });

    test('rejeita nome curto', () {
      expect(CheckoutValidators.validateName('Ab'), isNotNull);
      expect(CheckoutValidators.validateName('  A  '), isNotNull);
    });

    test('rejeita nome vazio', () {
      expect(CheckoutValidators.validateName(''), isNotNull);
      expect(CheckoutValidators.validateName('   '), isNotNull);
    });

    test('rejeita nome longo demais', () {
      final long = 'A' * 81;
      expect(CheckoutValidators.validateName(long), isNotNull);
    });

    test('rejeita só dígitos ou pontuação', () {
      expect(CheckoutValidators.validateName('12345'), isNotNull);
      expect(CheckoutValidators.validateName('---'), isNotNull);
      expect(CheckoutValidators.validateName('Maria 123'), isNotNull);
    });

    test('sanitizeName normaliza espaços', () {
      expect(
        CheckoutValidators.sanitizeName('  Maria   Fernandes  '),
        'Maria Fernandes',
      );
    });
  });

  group('CheckoutValidators.validateWhatsApp', () {
    test('aceita celular válido com 11 dígitos', () {
      expect(CheckoutValidators.validateWhatsApp('(11) 91234-5678'), isNull);
      expect(CheckoutValidators.validateWhatsApp('11912345678'), isNull);
      expect(CheckoutValidators.validateWhatsApp('21 98765-4321'), isNull);
    });

    test('rejeita vazio', () {
      expect(CheckoutValidators.validateWhatsApp(''), isNotNull);
    });

    test('rejeita 10 dígitos (fixos)', () {
      expect(CheckoutValidators.validateWhatsApp('1133334444'), isNotNull);
    });

    test('rejeita sem nono dígito', () {
      expect(CheckoutValidators.validateWhatsApp('11333344445'), isNotNull);
    });

    test('rejeita DDD inválido', () {
      expect(CheckoutValidators.validateWhatsApp('10912345678'), isNotNull);
      expect(CheckoutValidators.validateWhatsApp('00912345678'), isNotNull);
    });

    test('rejeita sequência óbvia', () {
      expect(CheckoutValidators.validateWhatsApp('00000000000'), isNotNull);
      expect(CheckoutValidators.validateWhatsApp('11111111111'), isNotNull);
    });

    test('digitsOnly extrai apenas números', () {
      expect(
        CheckoutValidators.digitsOnly('(11) 91234-5678'),
        '11912345678',
      );
    });
  });
}
