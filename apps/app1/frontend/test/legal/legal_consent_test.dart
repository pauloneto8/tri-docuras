import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/legal/legal_consent.dart';

void main() {
  testWidgets('marcar a caixa avisa a tela com true', (tester) async {
    bool? checked;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) => LegalConsent(
              value: checked ?? false,
              onChanged: (value) => setState(() => checked = value),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.byType(Checkbox));
    await tester.pump();

    expect(checked, isTrue);
    expect(find.text('Ler os termos'), findsOneWidget);
    expect(find.text('Ler a privacidade'), findsOneWidget);
  });

  testWidgets('com onChanged nulo a caixa fica desabilitada', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: LegalConsent(value: false, onChanged: null)),
      ),
    );

    final checkbox = tester.widget<Checkbox>(find.byType(Checkbox));
    expect(checkbox.onChanged, isNull);
  });
}
