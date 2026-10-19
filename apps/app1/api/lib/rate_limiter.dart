import 'package:dart_frog/dart_frog.dart';

/// Limite de tentativas por chave dentro de uma janela deslizante.
/// Em memória: basta para uma única instância da API.
class RateLimiter {
  RateLimiter({required this.maxHits, required this.window});

  final int maxHits;
  final Duration window;
  final Map<String, List<DateTime>> _hits = {};

  /// Registra uma tentativa de [key] e devolve `true` se ela ainda cabe no
  /// limite. Tentativas bloqueadas não estendem o bloqueio.
  bool allow(String key, DateTime now) {
    _hits.removeWhere((_, times) => times.every((t) => now.difference(t) >= window));
    final times = _hits.putIfAbsent(key, () => []);
    times.removeWhere((t) => now.difference(t) >= window);
    if (times.length >= maxHits) return false;
    times.add(now);
    return true;
  }

  /// Segundos até a tentativa mais antiga sair da janela (para `Retry-After`).
  int retryAfterSeconds(String key, DateTime now) {
    final times = _hits[key];
    if (times == null || times.isEmpty) return 0;
    final wait = window - now.difference(times.first);
    return wait.isNegative ? 0 : wait.inSeconds + 1;
  }
}

/// IP do cliente. O Caddy fica na frente e define `X-Forwarded-For`; vale a
/// última entrada (a que o proxy acrescentou), que o cliente não controla.
String clientIp(RequestContext context) {
  final forwarded = context.request.headers['x-forwarded-for'];
  if (forwarded != null) {
    final last = forwarded.split(',').last.trim();
    if (last.isNotEmpty) return last;
  }
  return context.request.connectionInfo.remoteAddress.address;
}

/// Resposta 429 padrão, ou `null` se [key] ainda pode prosseguir.
Response? rateLimitResponse(RateLimiter limiter, String key) {
  final now = DateTime.now();
  if (limiter.allow(key, now)) return null;
  return Response.json(
    statusCode: 429,
    headers: {'Retry-After': '${limiter.retryAfterSeconds(key, now)}'},
    body: {'error': 'Muitas tentativas. Aguarde um pouco e tente de novo.'},
  );
}

final loginLimiter =
    RateLimiter(maxHits: 5, window: const Duration(minutes: 15));
final orderCreateLimiter =
    RateLimiter(maxHits: 10, window: const Duration(hours: 1));
final pixCreateLimiter =
    RateLimiter(maxHits: 10, window: const Duration(hours: 1));
