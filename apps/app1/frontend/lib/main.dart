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
import 'package:tri_docuras/screens/order_tracking_screen.dart';
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
      cart: CartController(
        deliveryFeeAmount: StoreConfigHolder.instance.config.deliveryFee,
      ),
      favorites: favorites,
      orderHistory: orderHistory,
      account: account,
    ),
  );
  await account.load();
}

/// Tela inicial: a loja. Quem chega pelo link `/pedido/TD-XXXX?t=<token>`
/// vê o acompanhamento por cima dela, e o Voltar leva à loja.
///
/// Usa `home` de propósito: com `onGenerateInitialRoutes` a loja não era
/// montada (a tela ficava vazia).
class _StartScreen extends StatefulWidget {
  const _StartScreen();

  @override
  State<_StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<_StartScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _openTrackingFromLink());
  }

  void _openTrackingFromLink() {
    if (!mounted) return;
    final segments = Uri.base.pathSegments;
    if (segments.length != 2 || segments.first != 'pedido') return;

    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OrderTrackingScreen(
          orderId: segments.last,
          trackingToken: Uri.base.queryParameters['t'],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => const HomeScreen();
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
              home: const _StartScreen(),
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
