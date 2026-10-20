import 'package:test/test.dart';
import 'package:tri_docuras_api/store_settings.dart';

void main() {
  group('parseStoreSettingsInput', () {
    Map<String, dynamic> valid() => {
          'delivery_fee': 6,
          'store_open': true,
          'notice': '',
        };

    test('aceita valores válidos', () {
      final settings = parseStoreSettingsInput(valid());
      expect(settings.deliveryFee, 6.0);
      expect(settings.storeOpen, isTrue);
      expect(settings.notice, '');
    });

    test('aceita taxa como texto com vírgula', () {
      final settings = parseStoreSettingsInput({
        ...valid(),
        'delivery_fee': '7,50',
      });
      expect(settings.deliveryFee, 7.5);
    });

    test('arredonda a taxa para centavos', () {
      final settings = parseStoreSettingsInput({
        ...valid(),
        'delivery_fee': 5.999,
      });
      expect(settings.deliveryFee, 6.0);
    });

    test('recusa taxa negativa ou acima do limite', () {
      expect(
        () => parseStoreSettingsInput({...valid(), 'delivery_fee': -1}),
        throwsA(isA<StoreSettingsException>()),
      );
      expect(
        () => parseStoreSettingsInput({
          ...valid(),
          'delivery_fee': maxDeliveryFee + 0.01,
        }),
        throwsA(isA<StoreSettingsException>()),
      );
    });

    test('recusa taxa que não é número', () {
      expect(
        () => parseStoreSettingsInput({...valid(), 'delivery_fee': 'grátis'}),
        throwsA(isA<StoreSettingsException>()),
      );
      expect(
        () => parseStoreSettingsInput({...valid(), 'delivery_fee': null}),
        throwsA(isA<StoreSettingsException>()),
      );
    });

    test('exige store_open booleano', () {
      final body = valid()..remove('store_open');
      expect(
        () => parseStoreSettingsInput(body),
        throwsA(isA<StoreSettingsException>()),
      );
      expect(
        () => parseStoreSettingsInput({...valid(), 'store_open': 'sim'}),
        throwsA(isA<StoreSettingsException>()),
      );
    });

    test('remove espaços do aviso e recusa aviso longo', () {
      final settings = parseStoreSettingsInput({
        ...valid(),
        'notice': '  Fechado no feriado  ',
      });
      expect(settings.notice, 'Fechado no feriado');

      expect(
        () => parseStoreSettingsInput({
          ...valid(),
          'notice': 'x' * (maxNoticeLength + 1),
        }),
        throwsA(isA<StoreSettingsException>()),
      );
    });

    test('valores padrão reproduzem a taxa de R\$ 6,00 e loja aberta', () {
      expect(StoreSettings.defaults.deliveryFee, 6.0);
      expect(StoreSettings.defaults.storeOpen, isTrue);
      expect(StoreSettings.defaults.notice, '');
    });
  });
}
