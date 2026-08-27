import 'package:flutter_test/flutter_test.dart';
import 'package:tri_docuras/main.dart';

void main() {
  testWidgets('App inicia com wordmark Tri Doçuras', (tester) async {
    await tester.pumpWidget(const TriDocurasApp());
    await tester.pumpAndSettle();

    expect(find.text('Tri Doçuras'), findsOneWidget);
    expect(find.text('Buscar brownie...'), findsOneWidget);
  });
}
