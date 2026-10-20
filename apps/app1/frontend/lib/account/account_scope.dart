import 'package:flutter/material.dart';
import 'package:tri_docuras/account/account_controller.dart';

class AccountScope extends InheritedNotifier<AccountController> {
  const AccountScope({
    super.key,
    required AccountController super.notifier,
    required super.child,
  });

  static AccountController of(BuildContext context) {
    final scope = context.dependOnInheritedWidgetOfExactType<AccountScope>();
    assert(scope != null, 'AccountScope not found in widget tree');
    return scope!.notifier!;
  }
}
