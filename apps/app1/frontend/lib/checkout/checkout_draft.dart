/// Rascunho de checkout em memória — não persistir (PII).
class CheckoutDraft {
  const CheckoutDraft({
    required this.customerName,
    required this.whatsappDigits,
    required this.total,
  });

  /// Nome já sanitizado (trim + espaços normalizados).
  final String customerName;

  /// WhatsApp só dígitos (11).
  final String whatsappDigits;

  /// Total lido do [CartController] no momento do Gerar Pix.
  final double total;

  String get formattedTotal =>
      'R\$ ${total.toStringAsFixed(2).replaceAll('.', ',')}';
}
