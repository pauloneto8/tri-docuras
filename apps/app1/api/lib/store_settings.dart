import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/db.dart';

/// Taxa de entrega usada enquanto a loja não tiver outro valor salvo.
/// Os padrões reproduzem o comportamento de antes desta tabela existir.
const defaultDeliveryFee = 6.0;
const maxDeliveryFee = 100.0;
const maxNoticeLength = 300;

class StoreSettingsException implements Exception {
  StoreSettingsException(this.message);

  final String message;

  @override
  String toString() => message;
}

class StoreSettings {
  const StoreSettings({
    required this.deliveryFee,
    required this.storeOpen,
    required this.notice,
  });

  static const defaults = StoreSettings(
    deliveryFee: defaultDeliveryFee,
    storeOpen: true,
    notice: '',
  );

  final double deliveryFee;
  final bool storeOpen;
  final String notice;

  Map<String, Object?> toJson() => {
        'delivery_fee': deliveryFee,
        'store_open': storeOpen,
        'notice': notice,
      };
}

/// Valida o corpo do PUT de configurações. Os três campos são obrigatórios:
/// o painel sempre envia o formulário inteiro.
StoreSettings parseStoreSettingsInput(Map<String, dynamic> body) {
  final fee = _parseMoney(body['delivery_fee']);
  if (fee == null || fee < 0 || fee > maxDeliveryFee) {
    throw StoreSettingsException(
      'Taxa de entrega inválida (use um valor entre 0 e ${maxDeliveryFee.toStringAsFixed(2)}).',
    );
  }

  final storeOpen = body['store_open'];
  if (storeOpen is! bool) {
    throw StoreSettingsException('Informe se a loja está aberta.');
  }

  final notice = body['notice']?.toString().trim() ?? '';
  if (notice.length > maxNoticeLength) {
    throw StoreSettingsException(
      'Aviso muito longo (máx. $maxNoticeLength caracteres).',
    );
  }

  return StoreSettings(
    deliveryFee: double.parse(fee.toStringAsFixed(2)),
    storeOpen: storeOpen,
    notice: notice,
  );
}

double? _parseMoney(Object? value) {
  return switch (value) {
    final num number => number.toDouble(),
    final String text => double.tryParse(text.trim().replaceAll(',', '.')),
    _ => null,
  };
}

Future<void> ensureStoreSettingsSchema(Connection connection) async {
  await connection.execute('''
    CREATE TABLE IF NOT EXISTS store_settings (
      id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
      delivery_fee NUMERIC(10, 2) NOT NULL DEFAULT 6.00,
      store_open BOOLEAN NOT NULL DEFAULT TRUE,
      notice TEXT NOT NULL DEFAULT '',
      updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  ''');
  await connection.execute('''
    INSERT INTO store_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
  ''');
}

Future<StoreSettings> getStoreSettings() async {
  final connection = await getConnection();
  final result = await connection.execute('''
    SELECT delivery_fee, store_open, notice
    FROM store_settings
    WHERE id = 1;
  ''');
  if (result.isEmpty) return StoreSettings.defaults;

  final row = result.first;
  return StoreSettings(
    deliveryFee: _toDouble(row[0]),
    storeOpen: row[1]! as bool,
    notice: row[2]! as String,
  );
}

Future<StoreSettings> updateStoreSettings(StoreSettings settings) async {
  final connection = await getConnection();
  await connection.execute(
    '''
      UPDATE store_settings
      SET delivery_fee = \$1, store_open = \$2, notice = \$3, updated_at = NOW()
      WHERE id = 1;
    ''',
    parameters: [settings.deliveryFee, settings.storeOpen, settings.notice],
  );
  return getStoreSettings();
}

double _toDouble(Object? value) => switch (value) {
      final num number => number.toDouble(),
      final String text => double.parse(text),
      _ => throw StateError('delivery_fee inválido: $value'),
    };
