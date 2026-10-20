/// Variação de um produto: tamanho (escolha única) ou adicional (com preço).
class ProductOption {
  const ProductOption({
    required this.id,
    required this.kind,
    required this.label,
    this.priceDelta = 0,
  });

  factory ProductOption.fromJson(Map<String, dynamic> json) {
    return ProductOption(
      id: (json['id'] as num).toInt(),
      kind: json['kind'] as String? ?? 'addon',
      label: json['label'] as String? ?? '',
      priceDelta: (json['price_delta'] as num?)?.toDouble() ?? 0,
    );
  }

  final int id;
  final String kind;
  final String label;

  /// Acréscimo sobre o preço do produto (0 para tamanhos).
  final double priceDelta;

  bool get isSize => kind == 'size';

  /// Texto do chip; adicional com preço mostra o valor, ex.: `Sem lactose +R$3`.
  String get chipLabel =>
      priceDelta > 0 ? '$label +R\$${_formatAmount(priceDelta)}' : label;

  static String _formatAmount(double value) {
    if (value == value.roundToDouble()) return value.toStringAsFixed(0);
    return value.toStringAsFixed(2).replaceAll('.', ',');
  }
}
