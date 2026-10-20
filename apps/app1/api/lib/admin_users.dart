import 'package:postgres/postgres.dart';
import 'package:tri_docuras_api/customer_auth.dart';
import 'package:tri_docuras_api/db.dart';
import 'package:tri_docuras_api/env.dart';

const adminRoles = ['dono', 'atendente'];
const adminMinPasswordLength = 8;

class AdminUserException implements Exception {
  AdminUserException(this.message);

  final String message;

  @override
  String toString() => message;
}

class AdminUser {
  const AdminUser({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
    required this.active,
    required this.sessionVersion,
    this.passwordHash,
  });

  final int id;
  final String name;
  final String email;
  final String role;
  final bool active;
  final int sessionVersion;

  /// Só vem preenchido na consulta de login.
  final String? passwordHash;

  Map<String, Object?> toAdminJson() => {
        'id': id,
        'name': name,
        'email': email,
        'role': role,
        'active': active,
      };
}

class AdminUserInput {
  AdminUserInput({
    required this.name,
    required this.email,
    required this.role,
    required this.active,
    this.password,
  });

  final String name;
  final String email;
  final String role;
  final bool active;

  /// Obrigatória na criação; opcional na edição (vazia = manter a atual).
  final String? password;
}

final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Valida o corpo de criação ou edição. Na edição o e-mail é ignorado: ele
/// é o login e não muda.
AdminUserInput parseAdminUserInput(
  Map<String, dynamic> body, {
  required bool isCreate,
}) {
  final name = body['name']?.toString().trim() ?? '';
  if (name.length < 2) {
    throw AdminUserException('Informe o nome do usuário.');
  }
  if (name.length > 100) {
    throw AdminUserException('Nome muito longo (máx. 100 caracteres).');
  }

  final email = body['email']?.toString().trim().toLowerCase() ?? '';
  if (isCreate) {
    if (email.length > 200 || !_emailPattern.hasMatch(email)) {
      throw AdminUserException('Informe um e-mail válido.');
    }
  }

  final role = body['role']?.toString().trim() ?? '';
  if (!adminRoles.contains(role)) {
    throw AdminUserException('Papel inválido (dono ou atendente).');
  }

  final active = body['active'];
  if (active != null && active is! bool) {
    throw AdminUserException('Campo ativo inválido.');
  }

  final rawPassword = body['password']?.toString() ?? '';
  final password = rawPassword.isEmpty ? null : rawPassword;
  if (isCreate && password == null) {
    throw AdminUserException('Informe uma senha inicial.');
  }
  if (password != null) {
    if (password.length < adminMinPasswordLength) {
      throw AdminUserException(
        'A senha precisa ter pelo menos $adminMinPasswordLength caracteres.',
      );
    }
    if (password.length > 72) {
      throw AdminUserException('Senha muito longa (máx. 72 caracteres).');
    }
  }

  return AdminUserInput(
    name: name,
    email: email,
    role: role,
    active: active as bool? ?? true,
    password: password,
  );
}

Future<void> ensureAdminUsersSchema(Connection connection) async {
  await connection.execute('''
    CREATE TABLE IF NOT EXISTS admin_users (
      id SERIAL PRIMARY KEY,
      name VARCHAR(100) NOT NULL,
      email VARCHAR(200) NOT NULL UNIQUE,
      password_hash TEXT NOT NULL,
      role VARCHAR(20) NOT NULL CHECK (role IN ('dono', 'atendente')),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      session_version INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMP NOT NULL DEFAULT NOW(),
      last_login_at TIMESTAMP
    );
  ''');
}

/// Cria o dono inicial a partir de `APP1_ADMIN_EMAIL` e
/// `APP1_ADMIN_PASSWORD`, somente quando não há nenhum usuário. Depois disso
/// as variáveis não são mais usadas para login.
Future<void> bootstrapAdminUser() async {
  final email = Env.get('APP1_ADMIN_EMAIL')?.trim().toLowerCase();
  final password = Env.get('APP1_ADMIN_PASSWORD');
  if (email == null || email.isEmpty || password == null) return;
  if (await countAdminUsers() > 0) return;

  await createAdminUser(
    AdminUserInput(
      name: 'Dono',
      email: email,
      role: 'dono',
      active: true,
      password: password,
    ),
  );
}

Future<int> countAdminUsers() async {
  final connection = await getConnection();
  final result = await connection.execute('SELECT COUNT(*) FROM admin_users;');
  return result.first[0]! as int;
}

AdminUser _rowToAdminUser(ResultRow row, {bool withHash = false}) {
  return AdminUser(
    id: row[0]! as int,
    name: row[1]! as String,
    email: row[2]! as String,
    role: row[3]! as String,
    active: row[4]! as bool,
    sessionVersion: row[5]! as int,
    passwordHash: withHash ? row[6] as String? : null,
  );
}

const _adminUserColumns = '''
  id, name, email, role, active, session_version
''';

Future<AdminUser?> findAdminUserById(int id) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT $_adminUserColumns
    FROM admin_users
    WHERE id = \$1;
    ''',
    parameters: [id],
  );
  if (result.isEmpty) return null;
  return _rowToAdminUser(result.first);
}

/// Usado no login: traz o hash junto. Retorna `null` se o e-mail não existe.
Future<AdminUser?> findAdminUserByEmail(String email) async {
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    SELECT $_adminUserColumns, password_hash
    FROM admin_users
    WHERE email = \$1;
    ''',
    parameters: [email.trim().toLowerCase()],
  );
  if (result.isEmpty) return null;
  return _rowToAdminUser(result.first, withHash: true);
}

Future<void> touchAdminLogin(int id) async {
  final connection = await getConnection();
  await connection.execute(
    '''
    UPDATE admin_users SET last_login_at = NOW() WHERE id = \$1;
    ''',
    parameters: [id],
  );
}

Future<List<AdminUser>> listAdminUsers() async {
  final connection = await getConnection();
  final result = await connection.execute('''
    SELECT $_adminUserColumns
    FROM admin_users
    ORDER BY name ASC, id ASC;
  ''');
  return result.map(_rowToAdminUser).toList();
}

Future<AdminUser> createAdminUser(AdminUserInput input) async {
  final connection = await getConnection();
  final existing = await connection.execute(
    'SELECT 1 FROM admin_users WHERE email = \$1;',
    parameters: [input.email],
  );
  if (existing.isNotEmpty) {
    throw AdminUserException('Já existe um usuário com esse e-mail.');
  }

  final result = await connection.execute(
    '''
    INSERT INTO admin_users (name, email, password_hash, role, active)
    VALUES (\$1, \$2, \$3, \$4, \$5)
    RETURNING $_adminUserColumns;
    ''',
    parameters: [
      input.name,
      input.email,
      CustomerAuth.hashPassword(input.password!),
      input.role,
      input.active,
    ],
  );
  return _rowToAdminUser(result.first);
}

/// Atualiza um usuário. Quando algo que dá acesso muda (senha, papel ou
/// ativo), a versão da sessão sobe e os tokens antigos deixam de valer.
Future<AdminUser> updateAdminUser(
  int id,
  AdminUserInput input, {
  required int actingUserId,
}) async {
  final current = await findAdminUserById(id);
  if (current == null) {
    throw AdminUserException('Usuário não encontrado.');
  }
  if (id == actingUserId && (input.role != 'dono' || !input.active)) {
    throw AdminUserException(
      'Você não pode tirar o próprio papel de dono nem desativar a própria conta.',
    );
  }

  final accessChanged = input.password != null ||
      input.role != current.role ||
      input.active != current.active;
  final connection = await getConnection();
  final result = await connection.execute(
    '''
    UPDATE admin_users
    SET name = \$2,
        role = \$3,
        active = \$4,
        password_hash = COALESCE(\$5, password_hash),
        session_version = session_version + \$6
    WHERE id = \$1
    RETURNING $_adminUserColumns;
    ''',
    parameters: [
      id,
      input.name,
      input.role,
      input.active,
      input.password == null ? null : CustomerAuth.hashPassword(input.password!),
      accessChanged ? 1 : 0,
    ],
  );
  return _rowToAdminUser(result.first);
}
