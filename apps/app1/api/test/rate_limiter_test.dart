import 'package:test/test.dart';
import 'package:tri_docuras_api/rate_limiter.dart';

void main() {
  final t0 = DateTime(2026, 10, 19, 12);

  test('bloqueia a partir da tentativa seguinte ao limite', () {
    final l = RateLimiter(maxHits: 5, window: const Duration(minutes: 15));
    for (var i = 0; i < 5; i++) {
      expect(l.allow('1.1.1.1', t0), isTrue);
    }
    expect(l.allow('1.1.1.1', t0), isFalse);
  });

  test('chaves diferentes são independentes', () {
    final l = RateLimiter(maxHits: 1, window: const Duration(minutes: 15));
    expect(l.allow('a', t0), isTrue);
    expect(l.allow('b', t0), isTrue);
    expect(l.allow('a', t0), isFalse);
  });

  test('libera depois da janela', () {
    final l = RateLimiter(maxHits: 1, window: const Duration(minutes: 15));
    expect(l.allow('a', t0), isTrue);
    expect(l.allow('a', t0.add(const Duration(minutes: 14))), isFalse);
    expect(l.allow('a', t0.add(const Duration(minutes: 15))), isTrue);
  });

  test('tentativa bloqueada não estende o bloqueio', () {
    final l = RateLimiter(maxHits: 1, window: const Duration(minutes: 15));
    l.allow('a', t0);
    l.allow('a', t0.add(const Duration(minutes: 10)));
    expect(l.allow('a', t0.add(const Duration(minutes: 16))), isTrue);
  });

  test('retryAfterSeconds conta até a tentativa mais antiga expirar', () {
    final l = RateLimiter(maxHits: 1, window: const Duration(minutes: 15));
    l.allow('a', t0);
    expect(l.retryAfterSeconds('a', t0.add(const Duration(minutes: 10))), 301);
    expect(l.retryAfterSeconds('zzz', t0), 0);
  });
}
