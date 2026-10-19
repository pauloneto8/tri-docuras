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
    );
  }

  final String appName;
  final String? storeWhatsApp;
  final String? storeWhatsAppDisplay;
  final List<StoreCategory> categories;

  String? get whatsappForLink => storeWhatsApp;
}
