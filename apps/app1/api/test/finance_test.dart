import 'package:test/test.dart';
import 'package:tri_docuras_api/finance.dart';

void main() {
  group('ratio', () {
    test('divide e arredonda em 4 casas', () {
      expect(ratio(1, 3), 0.3333);
      expect(ratio(2, 4), 0.5);
    });

    test('sem total devolve 0 em vez de dividir por zero', () {
      expect(ratio(0, 0), 0);
      expect(ratio(3, 0), 0);
    });
  });

  group('resolveDateRange', () {
    final now = DateTime(2026, 10, 19);

    test('sem argumentos usa o mês corrente', () {
      final range = resolveDateRange(now: now);
      expect(range.fromIso, '2026-10-01');
      expect(range.toIso, '2026-10-19');
    });

    test('aceita from e to explícitos', () {
      final range =
          resolveDateRange(from: '2026-09-01', to: '2026-09-30', now: now);
      expect(range.fromIso, '2026-09-01');
      expect(range.toIso, '2026-09-30');
      expect(range.toExclusive, DateTime(2026, 10, 1));
    });

    test('to sem from usa o início do mês de to', () {
      final range = resolveDateRange(to: '2026-08-20', now: now);
      expect(range.fromIso, '2026-08-01');
      expect(range.toIso, '2026-08-20');
    });

    test('from depois de to lança exceção', () {
      expect(
        () => resolveDateRange(from: '2026-10-10', to: '2026-10-01', now: now),
        throwsA(isA<FinanceException>()),
      );
    });

    test('data inválida lança exceção', () {
      expect(
        () => resolveDateRange(from: 'ontem', now: now),
        throwsA(isA<FinanceException>()),
      );
    });
  });

  group('averageTicket', () {
    test('divide faturamento pelo número de pedidos', () {
      expect(averageTicket(120, 5), 24);
    });

    test('sem pedidos retorna zero', () {
      expect(averageTicket(0, 0), 0);
    });
  });

  group('revenueStatuses', () {
    test('exclui pending_payment e cancelled', () {
      expect(revenueStatuses, isNot(contains('pending_payment')));
      expect(revenueStatuses, isNot(contains('cancelled')));
    });
  });
}
