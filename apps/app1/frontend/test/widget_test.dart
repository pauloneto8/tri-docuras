import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';
import 'package:tri_docuras/main.dart';
import 'package:tri_docuras/orders/order_history_controller.dart';

void main() {
  testWidgets('App inicia com wordmark Tri Doçuras', (tester) async {
    await tester.pumpWidget(
      TriDocurasApp(
        cart: CartController(),
        favorites: FavoritesController(),
        orderHistory: OrderHistoryController(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Tri Doçuras'), findsOneWidget);
    expect(find.text('Buscar brownie...'), findsOneWidget);
  });
}
