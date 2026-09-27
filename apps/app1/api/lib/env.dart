import 'dart:io';

/// Leitura de variáveis de ambiente com ponto de injeção para testes.
///
/// `Platform.environment` é um `Map` imutável criado na inicialização do
/// processo e não pode ser substituído — apenas lido. Por isso, código que
/// depende de env (senha do painel, secret do webhook) tornava o teste
/// dependente de `-e VAR=...` na linha de comando: `dart test` puro rodava
/// com a variável ausente e o teste falhava.
///
/// Aqui a leitura passa por [Env.get], que usa [override] quando definido.
class Env {
  const Env._();

  static Map<String, String>? _overrides;

  /// Faz [get] devolver [values] no lugar do ambiente real do processo.
  /// Passe um mapa completo (não é merge) para que o teste controle também
  /// as variáveis ausentes. Usar `{}` simula "nada configurado".
  static void override(Map<String, String> values) {
    _overrides = Map<String, String>.unmodifiable(values);
  }

  /// Restaura a leitura de `Platform.environment`.
  static void reset() {
    _overrides = null;
  }

  /// Valor de [key] ou `null` se não existir (ou for vazio após `trim`).
  ///
  /// Com [override] ativo a leitura é **substituição total**: chaves ausentes
  /// no mapa retornam `null` em vez de cair no ambiente real. É o que
  /// permite simular "nada configurado" mesmo com a variável setada no
  /// processo (`dart test` com `-e APP1_ADMIN_PASSWORD=...`).
  static String? get(String key) {
    final overrides = _overrides;
    final value =
        overrides != null ? overrides[key] : Platform.environment[key];
    if (value == null) return null;
    final trimmed = value.trim();
    return trimmed.isEmpty ? null : trimmed;
  }
}
