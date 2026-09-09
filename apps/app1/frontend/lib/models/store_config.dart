class StoreConfig {
  const StoreConfig({
    required this.appName,
    this.storeWhatsApp,
    this.storeWhatsAppDisplay,
  });

  factory StoreConfig.fromJson(Map<String, dynamic> json) {
    return StoreConfig(
      appName: json['app_name'] as String? ?? 'Tri Doçuras',
      storeWhatsApp: json['store_whatsapp'] as String?,
      storeWhatsAppDisplay: json['store_whatsapp_display'] as String?,
    );
  }

  final String appName;
  final String? storeWhatsApp;
  final String? storeWhatsAppDisplay;

  String? get whatsappForLink => storeWhatsApp;
}
