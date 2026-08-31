import 'package:flutter/material.dart';
import 'package:tri_docuras/cart/cart_controller.dart';
import 'package:tri_docuras/cart/cart_scope.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/screens/home_screen.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/theme/app_theme.dart';

void main() {
  runApp(TriDocurasApp(cart: CartController()));
}

class TriDocurasApp extends StatelessWidget {
  const TriDocurasApp({super.key, required this.cart});

  final CartController cart;

  @override
  Widget build(BuildContext context) {
    return CartScope(
      notifier: cart,
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
    );
  }
}
