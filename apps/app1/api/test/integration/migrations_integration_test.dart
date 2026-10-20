// Integração: precisa de DATABASE_URL (ver stock_integration_test.dart).
import 'dart:io';

import 'package:test/test.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/migrations.dart';

final _skip = (Platform.environment['DATABASE_URL'] ?? '').isEmpty
    ? 'defina DATABASE_URL para rodar os testes de integração'
    : null;

// Versões altas, para não conflitar com as migrações reais do app.
const _okVersion = 9001;
const _failVersion = 9002;

void main() {
  group('runMigrations com Postgres real', skip: _skip, () {
    late Future<void> Function() cleanup;

    setUp(() async {
      final connection = await getConnection();
      await runMigrations(connection, const []); // garante schema_migrations
      await connection.execute(
        'DROP TABLE IF EXISTS migracao_teste_ok, migracao_teste_falha;',
      );
      await connection.execute(
        'DELETE FROM schema_migrations WHERE version >= 9000;',
      );
      cleanup = () async {
        await connection.execute(
          'DROP TABLE IF EXISTS migracao_teste_ok, migracao_teste_falha;',
        );
        await connection.execute(
          'DELETE FROM schema_migrations WHERE version >= 9000;',
        );
      };
    });

    tearDown(() async => cleanup());

    test('aplica a migração uma vez e não a repete', () async {
      final connection = await getConnection();
      final migrations = [
        Migration(
          version: _okVersion,
          name: 'cria tabela de teste',
          apply: (tx) async {
            await tx.execute('CREATE TABLE migracao_teste_ok (id INT);');
          },
        ),
      ];

      await runMigrations(connection, migrations);
      // Se fosse reaplicada, o CREATE TABLE falharia: a segunda execução
      // precisa passar em silêncio.
      await runMigrations(connection, migrations);

      final rows = await connection.execute(
        r'SELECT COUNT(*) FROM schema_migrations WHERE version = $1;',
        parameters: [_okVersion],
      );
      expect((rows.first.first as num).toInt(), 1);
    });

    test('falha desfaz a transação e não registra a versão', () async {
      final connection = await getConnection();
      final migrations = [
        Migration(
          version: _failVersion,
          name: 'falha de propósito',
          apply: (tx) async {
            await tx.execute('CREATE TABLE migracao_teste_falha (id INT);');
            throw StateError('falha de teste');
          },
        ),
      ];

      await expectLater(
        runMigrations(connection, migrations),
        throwsA(isA<StateError>()),
      );

      final table = await connection.execute(
        "SELECT to_regclass('migracao_teste_falha') IS NULL;",
      );
      expect(table.first.first, isTrue);

      final rows = await connection.execute(
        r'SELECT COUNT(*) FROM schema_migrations WHERE version = $1;',
        parameters: [_failVersion],
      );
      expect((rows.first.first as num).toInt(), 0);
    });
  });
}
