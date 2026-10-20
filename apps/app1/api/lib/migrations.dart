import 'package:postgres/postgres.dart';

/// Uma mudança de schema, numerada. Cada uma roda uma vez, na própria
/// transação, e fica registrada em `schema_migrations`.
class Migration {
  const Migration({
    required this.version,
    required this.name,
    required this.apply,
  });

  final int version;
  final String name;
  final Future<void> Function(Session tx) apply;
}

/// Recusa versões repetidas: duas migrações com o mesmo número não sabem qual
/// das duas foi aplicada.
void validateMigrations(List<Migration> migrations) {
  final seen = <int>{};
  for (final migration in migrations) {
    if (migration.version <= 0) {
      throw ArgumentError('Versão de migração inválida: ${migration.version}');
    }
    if (!seen.add(migration.version)) {
      throw ArgumentError('Versão de migração repetida: ${migration.version}');
    }
  }
}

/// Aplica, em ordem, as migrações que ainda não estão em `schema_migrations`.
/// Se uma falhar, a transação dela é desfeita e a execução para ali.
Future<void> runMigrations(
  Connection db,
  List<Migration> migrations,
) async {
  validateMigrations(migrations);
  await db.execute('''
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version INTEGER PRIMARY KEY,
      name VARCHAR(100) NOT NULL,
      applied_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  ''');

  final appliedRows = await db.execute('SELECT version FROM schema_migrations;');
  final applied = {for (final row in appliedRows) (row[0] as num).toInt()};

  final ordered = [...migrations]
    ..sort((a, b) => a.version.compareTo(b.version));
  for (final migration in ordered) {
    if (applied.contains(migration.version)) continue;
    await db.runTx((tx) async {
      await migration.apply(tx);
      await tx.execute(
        r'INSERT INTO schema_migrations (version, name) VALUES ($1, $2);',
        parameters: [migration.version, migration.name],
      );
    });
  }
}
