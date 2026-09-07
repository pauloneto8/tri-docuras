import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:tri_docuras/favorites/favorites_controller.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('toggle adiciona e remove favorito', () async {
    final favorites = FavoritesController();
    expect(favorites.isFavorite(4), isFalse);

    await favorites.toggle(4);
    expect(favorites.isFavorite(4), isTrue);
    expect(favorites.count, 1);

    await favorites.toggle(4);
    expect(favorites.isFavorite(4), isFalse);
    expect(favorites.count, 0);
  });

  test('remove só notifica quando havia item', () async {
    final favorites = FavoritesController(seed: {4});
    await favorites.remove(99);
    expect(favorites.count, 1);
    await favorites.remove(4);
    expect(favorites.count, 0);
  });
}
