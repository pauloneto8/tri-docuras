import 'package:flutter/material.dart';
import 'package:tri_docuras/config.dart';
import 'package:tri_docuras/screens/home_screen.dart';
import 'package:tri_docuras/theme/app_theme.dart';

void main() {
  runApp(const TriDocurasApp());
}

class TriDocurasApp extends StatelessWidget {
  const TriDocurasApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: AppConfig.appName,
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      home: const HomeScreen(),
    );
  }
}
