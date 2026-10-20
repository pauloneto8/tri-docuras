import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:tri_docuras/account/account_scope.dart';
import 'package:tri_docuras/checkout/checkout_validators.dart';
import 'package:tri_docuras/checkout/delivery_address_validators.dart';
import 'package:tri_docuras/checkout/whatsapp_input_formatter.dart';
import 'package:tri_docuras/models/customer_profile.dart';
import 'package:tri_docuras/services/api_service.dart';
import 'package:tri_docuras/theme/app_colors.dart';
import 'package:tri_docuras/widgets/td_button.dart';
import 'package:tri_docuras/widgets/td_text_field.dart';

const _maxAddresses = 5;
const _minPasswordLength = 8;

/// Dados pessoais, endereços salvos e troca de senha.
class AccountEditScreen extends StatefulWidget {
  const AccountEditScreen({super.key, required this.profile});

  final CustomerProfile profile;

  @override
  State<AccountEditScreen> createState() => _AccountEditScreenState();
}

class _AccountEditScreenState extends State<AccountEditScreen> {
  late final TextEditingController _nameController;
  late final TextEditingController _whatsappController;
  final _currentPasswordController = TextEditingController();
  final _newPasswordController = TextEditingController();
  late List<CustomerAddress> _addresses;

  bool _savingProfile = false;
  bool _savingPassword = false;
  bool _nameSubmitted = false;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.profile.name);
    _whatsappController = TextEditingController(
      text: WhatsAppInputFormatter.formatDigits(widget.profile.whatsapp),
    );
    _addresses = [...widget.profile.addresses];
  }

  @override
  void dispose() {
    _nameController.dispose();
    _whatsappController.dispose();
    _currentPasswordController.dispose();
    _newPasswordController.dispose();
    super.dispose();
  }

  bool get _profileValid =>
      CheckoutValidators.isNameValid(_nameController.text) &&
      CheckoutValidators.isWhatsAppValid(_whatsappController.text);

  Future<void> _saveProfile() async {
    setState(() => _nameSubmitted = true);
    if (!_profileValid || _savingProfile) return;

    setState(() => _savingProfile = true);
    try {
      await AccountScope.of(context).saveProfile(
        name: CheckoutValidators.sanitizeName(_nameController.text),
        whatsapp: CheckoutValidators.digitsOnly(_whatsappController.text),
        addresses: _addresses,
      );
      _notify('Dados salvos.');
    } on ApiException catch (error) {
      _notify(error.message);
    } catch (_) {
      _notify('Não foi possível salvar. Tente de novo.');
    } finally {
      if (mounted) setState(() => _savingProfile = false);
    }
  }

  Future<void> _changePassword() async {
    final current = _currentPasswordController.text;
    final next = _newPasswordController.text;
    if (current.isEmpty) {
      _notify('Informe sua senha atual.');
      return;
    }
    if (next.length < _minPasswordLength) {
      _notify('A nova senha precisa ter pelo menos $_minPasswordLength caracteres.');
      return;
    }

    setState(() => _savingPassword = true);
    try {
      await AccountScope.of(context).changePassword(
        currentPassword: current,
        newPassword: next,
      );
      _currentPasswordController.clear();
      _newPasswordController.clear();
      _notify('Senha trocada. Use a nova senha no próximo login.');
    } on ApiException catch (error) {
      _notify(error.message);
    } catch (_) {
      _notify('Não foi possível trocar a senha. Tente de novo.');
    } finally {
      if (mounted) setState(() => _savingPassword = false);
    }
  }

  Future<void> _addAddress() async {
    final address = await showModalBottomSheet<CustomerAddress>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => const _AddressSheet(),
    );
    if (address == null || !mounted) return;
    setState(() => _addresses = [..._addresses, address]);
  }

  void _removeAddress(int index) {
    setState(() => _addresses = [..._addresses]..removeAt(index));
  }

  void _notify(String message) {
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
        title: const Text('Meus dados'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              _SectionTitle('DADOS PESSOAIS'),
              const SizedBox(height: 8),
              TdTextField(
                controller: _nameController,
                hintText: 'Nome completo',
                errorText: _nameSubmitted && !CheckoutValidators.isNameValid(_nameController.text)
                    ? CheckoutValidators.validateName(_nameController.text)
                    : null,
                maxLength: CheckoutValidators.nameMaxLength,
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 12),
              TdTextField(
                controller: _whatsappController,
                hintText: '(11) 91234-5678',
                keyboardType: TextInputType.phone,
                inputFormatters: [
                  FilteringTextInputFormatter.digitsOnly,
                  WhatsAppInputFormatter(),
                ],
                errorText: _nameSubmitted && !CheckoutValidators.isWhatsAppValid(_whatsappController.text)
                    ? CheckoutValidators.validateWhatsApp(_whatsappController.text)
                    : null,
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              Text(
                'E-mail: ${widget.profile.email} (não pode ser trocado por aqui)',
                style: GoogleFonts.poppins(fontSize: 12, color: AppColors.brown),
              ),
              const SizedBox(height: 24),
              _SectionTitle('ENDEREÇOS SALVOS (ATÉ $_maxAddresses)'),
              const SizedBox(height: 8),
              if (_addresses.isEmpty)
                Text(
                  'Nenhum endereço salvo ainda.',
                  style: GoogleFonts.poppins(fontSize: 14, color: AppColors.brown),
                ),
              for (var i = 0; i < _addresses.length; i++) ...[
                _AddressTile(
                  address: _addresses[i],
                  onRemove: () => _removeAddress(i),
                ),
                const SizedBox(height: 8),
              ],
              TdButton(
                label: 'Adicionar endereço',
                variant: _addresses.length < _maxAddresses
                    ? TdButtonVariant.outline
                    : TdButtonVariant.disabled,
                onPressed: _addresses.length < _maxAddresses ? _addAddress : null,
              ),
              const SizedBox(height: 16),
              TdButton(
                label: _savingProfile ? 'Salvando…' : 'Salvar dados',
                onPressed: _savingProfile ? null : _saveProfile,
              ),
              const SizedBox(height: 32),
              _SectionTitle('TROCAR SENHA'),
              const SizedBox(height: 8),
              TdTextField(
                controller: _currentPasswordController,
                hintText: 'Senha atual',
                obscureText: true,
              ),
              const SizedBox(height: 12),
              TdTextField(
                controller: _newPasswordController,
                hintText: 'Nova senha (mínimo de $_minPasswordLength caracteres)',
                obscureText: true,
              ),
              const SizedBox(height: 12),
              TdButton(
                label: _savingPassword ? 'Trocando…' : 'Trocar senha',
                variant: TdButtonVariant.outline,
                onPressed: _savingPassword ? null : _changePassword,
              ),
              const SizedBox(height: 8),
              Text(
                'Trocar a senha encerra a sessão em todos os aparelhos. Você continua logado aqui.',
                style: GoogleFonts.poppins(fontSize: 12, color: AppColors.brown, height: 1.4),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: Theme.of(context).textTheme.labelSmall?.copyWith(letterSpacing: 0.8),
    );
  }
}

class _AddressTile extends StatelessWidget {
  const _AddressTile({required this.address, required this.onRemove});

  final CustomerAddress address;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.brown.withValues(alpha: 0.12)),
      ),
      child: ListTile(
        title: Text(
          address.label,
          style: GoogleFonts.poppins(fontWeight: FontWeight.w600, color: AppColors.dark),
        ),
        subtitle: Text(
          address.summary,
          style: GoogleFonts.poppins(fontSize: 13, color: AppColors.brown),
        ),
        trailing: IconButton(
          tooltip: 'Remover endereço',
          icon: const Icon(Icons.delete_outline, color: AppColors.pinkDeep),
          onPressed: onRemove,
        ),
      ),
    );
  }
}

class _AddressSheet extends StatefulWidget {
  const _AddressSheet();

  @override
  State<_AddressSheet> createState() => _AddressSheetState();
}

class _AddressSheetState extends State<_AddressSheet> {
  final _label = TextEditingController(text: 'Casa');
  final _street = TextEditingController();
  final _number = TextEditingController();
  final _neighborhood = TextEditingController();
  final _complement = TextEditingController();
  final _reference = TextEditingController();
  bool _submitted = false;

  @override
  void dispose() {
    for (final c in [_label, _street, _number, _neighborhood, _complement, _reference]) {
      c.dispose();
    }
    super.dispose();
  }

  /// Mesmas regras do checkout: um endereço salvo precisa servir para entrega.
  String? _error(String? Function() validate) => _submitted ? validate() : null;

  void _save() {
    setState(() => _submitted = true);
    final valid = DeliveryAddressValidators.isValid(
      street: _street.text,
      number: _number.text,
      complement: _complement.text,
      neighborhood: _neighborhood.text,
      reference: _reference.text,
    );
    if (!valid) return;
    Navigator.of(context).pop(
      CustomerAddress(
        label: _label.text.trim().isEmpty ? 'Endereço' : _label.text.trim(),
        street: _street.text.trim(),
        number: _number.text.trim(),
        neighborhood: _neighborhood.text.trim(),
        complement: _complement.text.trim().isEmpty ? null : _complement.text.trim(),
        reference: _reference.text.trim().isEmpty ? null : _reference.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          16,
          20,
          16 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Novo endereço', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 12),
              TdTextField(controller: _label, hintText: 'Apelido (ex.: Casa)', maxLength: 50),
              const SizedBox(height: 8),
              TdTextField(
                controller: _street,
                hintText: 'Rua',
                errorText: _error(() => DeliveryAddressValidators.validateStreet(_street.text)),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              TdTextField(
                controller: _number,
                hintText: 'Número',
                errorText: _error(() => DeliveryAddressValidators.validateNumber(_number.text)),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              TdTextField(
                controller: _neighborhood,
                hintText: 'Bairro',
                errorText: _error(() => DeliveryAddressValidators.validateNeighborhood(_neighborhood.text)),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 8),
              TdTextField(
                controller: _complement,
                hintText: 'Complemento (opcional)',
                errorText: _error(() => DeliveryAddressValidators.validateComplement(_complement.text)),
              ),
              const SizedBox(height: 8),
              TdTextField(
                controller: _reference,
                hintText: 'Ponto de referência',
                errorText: _error(() => DeliveryAddressValidators.validateReference(_reference.text)),
                onChanged: (_) => setState(() {}),
              ),
              const SizedBox(height: 16),
              TdButton(label: 'Salvar endereço', onPressed: _save),
            ],
          ),
        ),
      ),
    );
  }
}
