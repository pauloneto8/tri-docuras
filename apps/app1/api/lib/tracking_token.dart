import 'dart:convert';
import 'dart:math';

/// Token que libera o acompanhamento do pedido sem login (link
/// `/pedido/TD-XXXX?t=<token>`). 24 bytes aleatórios seguros, em base64url.
String newTrackingToken() {
  final random = Random.secure();
  final bytes = List<int>.generate(24, (_) => random.nextInt(256));
  return base64UrlEncode(bytes).replaceAll('=', '');
}

/// Compara sem parar no primeiro caractere diferente, para não vazar o token
/// pelo tempo de resposta.
bool trackingTokenMatches(String? expected, String? given) {
  if (expected == null || expected.isEmpty || given == null) return false;
  if (expected.length != given.length) return false;

  var difference = 0;
  for (var i = 0; i < expected.length; i++) {
    difference |= expected.codeUnitAt(i) ^ given.codeUnitAt(i);
  }
  return difference == 0;
}
