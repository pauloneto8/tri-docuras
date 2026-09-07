import 'package:flutter/material.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';

class FavoritesScope extends InheritedNotifier<FavoritesController> {
  const FavoritesScope({
    super.key,
    required FavoritesController super.notifier,
    required super.child,
  });

  static FavoritesController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<FavoritesScope>();
    assert(scope != null, 'FavoritesScope not found in widget tree');
    return scope!.notifier!;
  }
}
