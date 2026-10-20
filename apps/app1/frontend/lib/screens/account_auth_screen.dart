import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/checkout/checkout_validators.dart';
import 'package:tri_docuras/checkout/whatsapp_input_formatter.dart';
import 'package:tri_docuras/legal/legal_consent.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_text_field.dart';

const _minPasswordLength = 8;
final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Entrar ou criar conta. Ao dar certo, fecha a tela e a sessão já está ativa.
class AccountAuthScreen extends StatefulWidget {
  const AccountAuthScreen({super.key});

  @override
  State<AccountAuthScreen> createState() => _AccountAuthScreenState();
}

class _AccountAuthScreenState extends State<AccountAuthScreen> {
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();
  final _whatsappController = TextEditingController();

  bool _registerMode = true;
  bool _submitted = false;
  bool _submitting = false;
  bool _acceptedTerms = false;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    _whatsappController.dispose();
    super.dispose();
  }

  String? get _emailError {
    if (!_submitted && _emailController.text.isEmpty) return null;
    return _emailPattern.hasMatch(_emailController.text.trim())
        ? null
        : 'Informe um e-mail válido.';
  }

  String? get _passwordError {
    if (!_submitted && _passwordController.text.isEmpty) return null;
    if (!_registerMode) {
      return _passwordController.text.isEmpty ? 'Informe sua senha.' : null;
    }
    return _passwordController.text.length < _minPasswordLength
        ? 'A senha precisa ter pelo menos $_minPasswordLength caracteres.'
        : null;
  }

  String? get _nameError {
    if (!_registerMode) return null;
    if (!_submitted && _nameController.text.isEmpty) return null;
    return CheckoutValidators.validateName(_nameController.text);
  }

  String? get _whatsappError {
    if (!_registerMode) return null;
    if (!_submitted && _whatsappController.text.isEmpty) return null;
    return CheckoutValidators.validateWhatsApp(_whatsappController.text);
  }

  bool get _isValid {
    final emailOk = _emailPattern.hasMatch(_emailController.text.trim());
    final passwordOk = _registerMode
        ? _passwordController.text.length >= _minPasswordLength
        : _passwordController.text.isNotEmpty;
    final registerOk = !_registerMode ||
        (CheckoutValidators.isNameValid(_nameController.text) &&
            CheckoutValidators.isWhatsAppValid(_whatsappController.text) &&
            _acceptedTerms);
    return emailOk && passwordOk && registerOk;
  }

  void _toggleMode() {
    setState(() {
      _registerMode = !_registerMode;
      _submitted = false;
    });
  }

  Future<void> _submit() async {
    setState(() => _submitted = true);
    if (!_isValid || _submitting) return;

    setState(() => _submitting = true);
    final account = AccountScope.of(context);
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    try {
      if (_registerMode) {
        await account.register(
          email: email,
          password: password,
          name: CheckoutValidators.sanitizeName(_nameController.text),
          whatsapp: CheckoutValidators.digitsOnly(_whatsappController.text),
        );
      } else {
        await account.login(email: email, password: password);
      }
      if (!mounted) return;
      Navigator.of(context).pop();
    } on ApiException catch (error) {
      _showError(error.message);
    } catch (_) {
      _showError('Não foi possível entrar agora. Tente de novo.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  void _showError(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.dark,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.cream,
      appBar: AppBar(
        backgroundColor: AppColors.cream,
        elevation: 0,
        foregroundColor: AppColors.dark,
        title: Text(_registerMode ? 'Criar conta' : 'Entrar'),
      ),
      body: SafeArea(
        child: AutofillGroup(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  _registerMode
                      ? 'Suas compras, endereços e pedidos ficam salvos na sua conta.'
                      : 'Entre para acompanhar seus pedidos e comprar.',
                  style: GoogleFonts.poppins(
                    fontSize: 14,
                    color: AppColors.brown,
                    height: 1.4,
                  ),
                ),
                const SizedBox(height: 20),
                if (_registerMode) ...[
                  _Label('NOME COMPLETO'),
                  const SizedBox(height: 8),
                  TdTextField(
                    controller: _nameController,
                    hintText: 'Seu nome completo',
                    errorText: _nameError,
                    textInputAction: TextInputAction.next,
                    autofillHints: const [AutofillHints.name],
                    maxLength: CheckoutValidators.nameMaxLength,
                    onChanged: (_) => setState(() {}),
                  ),
                  const SizedBox(height: 16),
                  _Label('WHATSAPP'),
                  const SizedBox(height: 8),
                  TdTextField(
                    controller: _whatsappController,
                    hintText: '(11) 91234-5678',
                    errorText: _whatsappError,
                    keyboardType: TextInputType.phone,
                    textInputAction: TextInputAction.next,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      WhatsAppInputFormatter(),
                    ],
                    onChanged: (_) => setState(() {}),
                  ),
                  const SizedBox(height: 16),
                ],
                _Label('E-MAIL'),
                const SizedBox(height: 8),
                TdTextField(
                  controller: _emailController,
                  hintText: 'voce@exemplo.com',
                  errorText: _emailError,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.email],
                  onChanged: (_) => setState(() {}),
                ),
                const SizedBox(height: 16),
                _Label('SENHA'),
                const SizedBox(height: 8),
                TdTextField(
                  controller: _passwordController,
                  hintText: _registerMode
                      ? 'Mínimo de $_minPasswordLength caracteres'
                      : 'Sua senha',
                  errorText: _passwordError,
                  obscureText: true,
                  textInputAction: TextInputAction.done,
                  autofillHints: const [AutofillHints.password],
                  onChanged: (_) => setState(() {}),
                ),
                if (_registerMode) ...[
                  const SizedBox(height: 16),
                  LegalConsent(
                    value: _acceptedTerms,
                    onChanged: _submitting
                        ? null
                        : (value) => setState(() => _acceptedTerms = value),
                  ),
                ],
                const SizedBox(height: 24),
                TdButton(
                  label: _submitting
                      ? 'Aguarde…'
                      : (_registerMode ? 'Criar conta' : 'Entrar'),
                  variant: _isValid && !_submitting
                      ? TdButtonVariant.primary
                      : TdButtonVariant.disabled,
                  onPressed: _submitting ? null : _submit,
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: _submitting ? null : _toggleMode,
                  child: Text(
                    _registerMode
                        ? 'Já tenho conta: entrar'
                        : 'Não tenho conta: criar agora',
                    style: GoogleFonts.poppins(
                      fontSize: 14,
                      color: AppColors.pinkDeep,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                if (!_registerMode) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Esqueceu a senha? Por enquanto, fale com a loja pelo WhatsApp.',
                    textAlign: TextAlign.center,
                    style: GoogleFonts.poppins(
                      fontSize: 13,
                      color: AppColors.brown,
                      height: 1.4,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Label extends StatelessWidget {
  const _Label(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.labelSmall?.copyWith(letterSpacing: 0.8),
    );
  }
}
