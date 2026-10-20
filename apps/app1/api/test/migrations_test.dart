import 'package:test/test.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/migrations.dart';

Migration _migration(int version) => Migration(
      version: version,
      name: 'm$version',
      apply: (_) async {},
    );

void main() {
  group('validateMigrations', () {
    test('aceita versões únicas e positivas', () {
      expect(() => validateMigrations([_migration(1), _migration(2)]),
          returnsNormally);
    });

    test('recusa versão repetida', () {
      expect(
        () => validateMigrations([_migration(3), _migration(3)]),
        throwsArgumentError,
      );
    });

    test('recusa versão zero ou negativa', () {
      expect(() => validateMigrations([_migration(0)]), throwsArgumentError);
      expect(() => validateMigrations([_migration(-1)]), throwsArgumentError);
    });
  });

  test('a lista de migrações do app é válida', () {
    expect(() => validateMigrations(appMigrations), returnsNormally);
    expect(appMigrations.first.version, 1);
  });
}
