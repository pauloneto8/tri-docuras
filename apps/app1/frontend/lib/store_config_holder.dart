import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/models/store_config.dart';
import 'package:tri_docuras/services/store_config_repository.dart';

class StoreConfigHolder {
  StoreConfigHolder._();

  static final StoreConfigHolder instance = StoreConfigHolder._();

  StoreConfig _config = StoreConfigFallback.fallback;

  StoreConfig get config => _config;

  String? get storeWhatsApp => _config.storeWhatsApp ?? AppConfig.storeWhatsApp;

  String get storeWhatsAppDisplay =>
      _config.storeWhatsAppDisplay ?? AppConfig.storeWhatsAppDisplay;

  Future<void> load({StoreConfigRepository? repository}) async {
    final repo = repository ?? StoreConfigRepository();
    _config = await repo.fetch();
  }

  String buildOrderWhatsAppUrl({
    required String orderId,
    required String customerName,
    required String formattedTotal,
  }) {
    final phone = storeWhatsApp;
    if (phone == null || phone.isEmpty) return '';

    final message = [
      'Olá! Acabei de pagar o pedido $orderId.',
      'Nome: $customerName',
      'Total: $formattedTotal',
      'Tri Doçuras',
    ].join('\n');

    return Uri(
      scheme: 'https',
      host: 'wa.me',
      path: phone,
      queryParameters: {'text': message},
    ).toString();
  }
}
