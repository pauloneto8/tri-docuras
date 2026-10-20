import 'package:flutter/material.dart';
import 'package:tri_docuras/account/account_controller.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';
import 'package:tri_docuras/favorites/favorites_scope.dart';
import 'package:tri_docuras/orders/order_history_controller.dart';
import 'package:tri_docuras/orders/order_history_scope.dart';
import 'package:tri_docuras/screens/home_screen.dart';
import 'package:tri_docuras/store_config_holder.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await StoreConfigHolder.instance.load();

  final favorites = FavoritesController();
  final orderHistory = OrderHistoryController();
  final account = AccountController(
    onSessionChanged: () {
      favorites.load(force: true);
      orderHistory.load();
    },
  );

  runApp(
    TriDocurasApp(
      cart: CartController(),
      favorites: favorites,
      orderHistory: orderHistory,
      account: account,
    ),
  );
  await account.load();
}

class TriDocurasApp extends StatelessWidget {
  const TriDocurasApp({
    super.key,
    required this.cart,
    required this.favorites,
    required this.orderHistory,
    required this.account,
  });

  final CartController cart;
  final FavoritesController favorites;
  final OrderHistoryController orderHistory;
  final AccountController account;

  @override
  Widget build(BuildContext context) {
    return CartScope(
      notifier: cart,
      child: FavoritesScope(
        notifier: favorites,
        child: OrderHistoryScope(
          notifier: orderHistory,
          child: AccountScope(
            notifier: account,
            child: MaterialApp(
              title: AppConfig.appName,
              debugShowCheckedModeBanner: false,
              theme: AppTheme.light,
              home: const HomeScreen(),
              builder: (context, child) {
                return ColoredBox(
                  color: AppColors.cream,
                  child: Scaffold(
                    backgroundColor: AppColors.cream,
                    body: child,
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
  }
}
