/// Token da sessão do cliente logado, lido pelo [ApiService] em cada
/// chamada autenticada. Fica em memória: quem persiste é o
/// `AccountController`, que guarda só o token no aparelho.
class AuthToken {
  AuthToken._();

  static String? value;

  /// Chamado quando a API recusa o token (401). O `AccountController` usa
  /// para encerrar a sessão sem apagar o carrinho.
  static void Function()? onUnauthorized;
}
