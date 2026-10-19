import 'package:tri_docuras_api/db.dart';

/// Fuso usado para agrupar faturamento por dia (igual ao dos containers).
const financeTimezone = 'America/Recife';

/// Status de pedido que contam como faturamento confirmado.
const revenueStatuses = ['paid', 'preparing', 'ready', 'completed'];

class FinanceException implements Exception {
  FinanceException(this.message);

  final String message;

  @override
  String toString() => message;
}

class DateRange {
  DateRange(this.from, this.to);

  /// Data inicial inclusiva (apenas dia/mês/ano).
  final DateTime from;

  /// Data final inclusiva (apenas dia/mês/ano).
  final DateTime to;

  String get fromIso => _isoDate(from);
  String get toIso => _isoDate(to);

  /// Limite superior exclusivo usado nas queries de timestamp.
  DateTime get toExclusive => to.add(const Duration(days: 1));
}

DateTime dateOnly(DateTime value) =>
    DateTime(value.year, value.month, value.day);

String _isoDate(DateTime value) =>
    '${value.year.toString().padLeft(4, '0')}-'
    '${value.month.toString().padLeft(2, '0')}-'
    '${value.day.toString().padLeft(2, '0')}';

DateTime? _parseDate(String? value) {
  if (value == null) return null;
  final trimmed = value.trim();
  if (trimmed.isEmpty) return null;
  final parsed = DateTime.tryParse(trimmed);
  if (parsed == null) {
    throw FinanceException('Data inválida: use o formato AAAA-MM-DD.');
  }
  return dateOnly(parsed);
}

/// Resolve o período do relatório a partir de `from`/`to` (AAAA-MM-DD).
///
/// Sem argumentos, usa o mês corrente. `from` default = início do mês de `to`.
DateRange resolveDateRange({String? from, String? to, DateTime? now}) {
  final today = dateOnly(now ?? DateTime.now());
  final parsedTo = _parseDate(to) ?? today;
  final parsedFrom =
      _parseDate(from) ?? DateTime(parsedTo.year, parsedTo.month, 1);
  if (parsedFrom.isAfter(parsedTo)) {
    throw FinanceException('A data inicial não pode ser depois da final.');
  }
  return DateRange(parsedFrom, parsedTo);
}

double averageTicket(double revenue, int orders) {
  if (orders <= 0) return 0;
  return revenue / orders;
}

Future<Map<String, Object?>> buildFinanceReport({DateRange? range}) async {
  final period = range ?? resolveDateRange();
  final connection = await getConnection();
  final params = <Object?>[revenueStatuses, period.from, period.toExclusive];

  final totalsResult = await connection.execute(
    '''
    SELECT COUNT(*),
           COALESCE(SUM(total), 0),
           COALESCE(SUM(delivery_fee), 0)
    FROM orders
    WHERE status = ANY(\$1::text[])
      AND paid_at >= \$2 AND paid_at < \$3;
    ''',
    parameters: params,
  );

  final ordersCount = totalsResult.isEmpty
      ? 0
      : (totalsResult.first[0] as num).toInt();
  final revenue = totalsResult.isEmpty
      ? 0.0
      : _toDouble(totalsResult.first[1]);
  final deliveryFees = totalsResult.isEmpty
      ? 0.0
      : _toDouble(totalsResult.first[2]);

  final dailyResult = await connection.execute(
    '''
    SELECT paid_at::date AS day, COUNT(*), COALESCE(SUM(total), 0)
    FROM orders
    WHERE status = ANY(\$1::text[])
      AND paid_at >= \$2 AND paid_at < \$3
    GROUP BY day
    ORDER BY day ASC;
    ''',
    parameters: params,
  );

  final productsResult = await connection.execute(
    '''
    SELECT oi.product_name,
           SUM(oi.quantity) AS quantity,
           COALESCE(SUM(oi.line_total), 0) AS revenue
    FROM order_items oi
    JOIN orders o ON o.id = oi.order_id
    WHERE o.status = ANY(\$1::text[])
      AND o.paid_at >= \$2 AND o.paid_at < \$3
    GROUP BY oi.product_name
    ORDER BY revenue DESC;
    ''',
    parameters: params,
  );

  final deliveryResult = await connection.execute(
    '''
    SELECT delivery_mode, COUNT(*), COALESCE(SUM(total), 0)
    FROM orders
    WHERE status = ANY(\$1::text[])
      AND paid_at >= \$2 AND paid_at < \$3
    GROUP BY delivery_mode;
    ''',
    parameters: params,
  );

  final delivery = <String, Object?>{
    'pickup': {'orders': 0, 'revenue': 0.0},
    'delivery': {'orders': 0, 'revenue': 0.0},
  };
  for (final row in deliveryResult) {
    final mode = row[0]?.toString() ?? '';
    if (!delivery.containsKey(mode)) continue;
    delivery[mode] = {
      'orders': (row[1] as num).toInt(),
      'revenue': _toDouble(row[2]),
    };
  }

  return {
    'period': {'from': period.fromIso, 'to': period.toIso},
    'totals': {
      'revenue': revenue,
      'orders': ordersCount,
      'average_ticket': averageTicket(revenue, ordersCount),
      'delivery_fees': deliveryFees,
    },
    'daily': dailyResult
        .map(
          (row) => {
            'date': _dateString(row[0]),
            'orders': (row[1] as num).toInt(),
            'revenue': _toDouble(row[2]),
          },
        )
        .toList(),
    'by_product': productsResult
        .map(
          (row) => {
            'product_name': row[0],
            'quantity': (row[1] as num).toInt(),
            'revenue': _toDouble(row[2]),
          },
        )
        .toList(),
    'by_delivery_mode': delivery,
  };
}

String _dateString(Object? value) {
  if (value is DateTime) return _isoDate(value);
  final text = value?.toString() ?? '';
  return text.length >= 10 ? text.substring(0, 10) : text;
}

double _toDouble(Object? value) => switch (value) {
      final num n => n.toDouble(),
      final String s => double.parse(s),
      _ => 0.0,
    };
