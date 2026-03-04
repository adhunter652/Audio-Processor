import 'dart:developer' as dev;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../../core/errors/error_handler.dart';
import '../../../../core/errors/result.dart';
import '../../domain/repositories/auth_repository.dart';

class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  'Audio Search',
                  style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Sign in to search transcripts and meetings',
                  style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 48),
                _SignInButton(
                  onSignIn: () => _signInWithGoogle(context),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _signInWithGoogle(BuildContext context) async {
    dev.log('LoginScreen: Sign in with Google tapped', name: 'LoginScreen');
    final repo = context.read<AuthRepository>();
    final result = await repo.signInWithGoogle();
    if (!context.mounted) return;
    if (result.isError && result.failureOrNull != null) {
      final msg = ErrorHandler.message(result.failureOrNull!);
      dev.log('LoginScreen: sign-in failed: $msg', name: 'LoginScreen');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg)),
      );
    } else {
      dev.log('LoginScreen: sign-in succeeded', name: 'LoginScreen');
    }
  }
}

class _SignInButton extends StatefulWidget {
  const _SignInButton({required this.onSignIn});

  final Future<void> Function() onSignIn;

  @override
  State<_SignInButton> createState() => _SignInButtonState();
}

class _SignInButtonState extends State<_SignInButton> {
  bool _loading = false;

  @override
  Widget build(BuildContext context) {
    return FilledButton.icon(
      onPressed: _loading
          ? null
          : () async {
              setState(() => _loading = true);
              await widget.onSignIn();
              if (mounted) setState(() => _loading = false);
            },
      icon: _loading
          ? const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.login),
      label: Text(_loading ? 'Signing in…' : 'Sign in with Google'),
      style: FilledButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      ),
    );
  }
}
