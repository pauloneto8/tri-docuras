class StoreCategory {
  const StoreCategory({required this.slug, required this.label});

  factory StoreCategory.fromJson(Map<String, dynamic> json) {
    return StoreCategory(
      slug: json['slug'] as String? ?? '',
      label: json['label'] as String? ?? '',
    );
  }

  final String slug;
  final String label;
}

class StoreConfig {
  const StoreConfig({
    required this.appName,
    this.storeWhatsApp,
    this.storeWhatsAppDisplay,
    this.categories = const [],
    this.deliveryFee = 6.0,
    this.storeOpen = true,
    this.notice = '',
  });

  factory StoreConfig.fromJson(Map<String, dynamic> json) {
    final rawCategories = json['categories'];
    final categories = rawCategories is List
        ? rawCategories
            .whereType<Map<String, dynamic>>()
            .map(StoreCategory.fromJson)
            .where((category) => category.slug.isNotEmpty)
            .toList()
        : const <StoreCategory>[];
    return StoreConfig(
      appName: json['app_name'] as String? ?? 'Tri Doçuras',
      storeWhatsApp: json['store_whatsapp'] as String?,
      storeWhatsAppDisplay: json['store_whatsapp_display'] as String?,
      categories: categories,
      deliveryFee: _parseMoney(json['delivery_fee']) ?? 6.0,
      storeOpen: json['store_open'] as bool? ?? true,
      notice: json['notice'] as String? ?? '',
    );
  }

  static double? _parseMoney(Object? value) => switch (value) {
        final num number => number.toDouble(),
        final String text => double.tryParse(text),
        _ => null,
      };

  final String appName;
  final String? storeWhatsApp;
  final String? storeWhatsAppDisplay;
  final List<StoreCategory> categories;

  /// Taxa de entrega configurada no painel (R$ 6,00 até a loja mudar).
  final double deliveryFee;

  /// Loja aberta para pedidos. Fechada, o servidor recusa novos pedidos.
  final bool storeOpen;

  /// Aviso exibido no app (vazio = nenhum).
  final String notice;

  String? get whatsappForLink => storeWhatsApp;
}
