import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/widgets/td_load_error.dart';

void main() {
  testWidgets('mostra a mensagem e chama onRetry ao tocar em Tentar de novo',
      (tester) async {
    var retries = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: TdLoadError(onRetry: () => retries++),
        ),
      ),
    );

    expect(find.text('Não foi possível carregar os produtos.'), findsOneWidget);
    expect(retries, 0);

    await tester.tap(find.text('Tentar de novo'));
    await tester.pump();

    expect(retries, 1);
  });
}
