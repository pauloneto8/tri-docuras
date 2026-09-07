import 'package:flutter/material.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';
import 'package:tri_docuras/favorites/favorites_scope.dart';
import 'package:tri_docuras/screens/home_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';

void main() {
  runApp(
    TriDocurasApp(
      cart: CartController(),
      favorites: FavoritesController(),
    ),
  );
}

class TriDocurasApp extends StatelessWidget {
  const TriDocurasApp({
    super.key,
    required this.cart,
    required this.favorites,
  });

  final CartController cart;
  final FavoritesController favorites;

  @override
  Widget build(BuildContext context) {
    return CartScope(
      notifier: cart,
      child: FavoritesScope(
        notifier: favorites,
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
    );
  }
}
