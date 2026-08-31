import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/checkout/delivery_address_validators.dart';

void main() {
  group('DeliveryAddressValidators', () {
    test('aceita endereço completo válido', () {
      expect(
        DeliveryAddressValidators.isValid(
          street: 'Rua das Flores',
          number: '123',
          complement: 'Casa',
          neighborhood: 'Centro',
          reference: 'Próximo à praça',
        ),
        isTrue,
      );
    });

    test('complemento é opcional', () {
      expect(
        DeliveryAddressValidators.isValid(
          street: 'Rua A',
          number: '10',
          complement: '',
          neighborhood: 'Centro',
          reference: 'Em frente ao mercado',
        ),
        isTrue,
      );
    });

    test('rejeita rua vazia', () {
      expect(DeliveryAddressValidators.validateStreet(''), isNotNull);
    });

    test('rejeita referência curta', () {
      expect(DeliveryAddressValidators.validateReference('abc'), isNotNull);
    });

    test('buildIfValid retorna DeliveryAddress', () {
      final address = DeliveryAddressValidators.buildIfValid(
        street: 'Rua B',
        number: '45A',
        complement: '',
        neighborhood: 'Bairro Novo',
        reference: 'Casa amarela ao lado da padaria',
      );
      expect(address, isNotNull);
      expect(address!.formattedSummary, 'Rua B, 45A — Bairro Novo');
    });
  });
}
