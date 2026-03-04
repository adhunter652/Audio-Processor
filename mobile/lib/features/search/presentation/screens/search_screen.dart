import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../../core/errors/error_handler.dart';
import '../../../auth/domain/repositories/auth_repository.dart';
import '../../domain/entities/search_result.dart';
import '../state/providers/search_provider.dart';

class SearchScreen extends StatefulWidget {
  const SearchScreen({super.key});

  @override
  State<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends State<SearchScreen> {
  final _controller = TextEditingController();
  final _focusNode = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Search'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () async {
              await context.read<AuthRepository>().signOut();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: SearchBar(
              controller: _controller,
              focusNode: _focusNode,
              hintText: 'Search transcripts and meetings…',
              onSubmitted: (value) => context.read<SearchProvider>().search(value),
              trailing: [
                IconButton(
                  icon: const Icon(Icons.search),
                  onPressed: () => context.read<SearchProvider>().search(_controller.text),
                ),
              ],
            ),
          ),
          Expanded(
            child: Consumer<SearchProvider>(
              builder: (context, provider, _) {
                if (provider.errorMessage != null) {
                  return _ErrorView(
                    message: provider.errorMessage!,
                    onRetry: () => provider.search(_controller.text),
                    onDismiss: provider.clearError,
                  );
                }
                if (provider.isLoading) {
                  return const Center(child: CircularProgressIndicator());
                }
                final hasTranscripts = provider.transcriptResults.isNotEmpty;
                final hasMeetings = provider.meetingResults.isNotEmpty;
                if (!hasTranscripts && !hasMeetings && _controller.text.trim().isNotEmpty) {
                  return Center(
                    child: Text(
                      'No results',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  );
                }
                if (!hasTranscripts && !hasMeetings) {
                  return Center(
                    child: Text(
                      'Enter a search term above',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                            color: Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  );
                }
                return ListView(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  children: [
                    if (hasTranscripts) ...[
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(
                          'Transcripts',
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                color: Theme.of(context).colorScheme.primary,
                              ),
                        ),
                      ),
                      ...provider.transcriptResults.map((s) => _TranscriptCard(segment: s)),
                      const SizedBox(height: 24),
                    ],
                    if (hasMeetings) ...[
                      Padding(
                        padding: const EdgeInsets.only(bottom: 8),
                        child: Text(
                          'Meetings',
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                color: Theme.of(context).colorScheme.primary,
                              ),
                        ),
                      ),
                      ...provider.meetingResults.map((m) => _MeetingCard(hit: m)),
                    ],
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({
    required this.message,
    required this.onRetry,
    required this.onDismiss,
  });

  final String message;
  final VoidCallback onRetry;
  final VoidCallback onDismiss;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.error_outline, size: 48, color: Theme.of(context).colorScheme.error),
            const SizedBox(height: 16),
            Text(
              ErrorHandler.message(message),
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyLarge,
            ),
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: onDismiss,
              child: const Text('Dismiss'),
            ),
          ],
        ),
      ),
    );
  }
}

class _TranscriptCard extends StatelessWidget {
  const _TranscriptCard({required this.segment});

  final TranscriptSegment segment;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              segment.text,
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 8),
            Text(
              '${segment.originalFilename} · ${_formatTime(segment.start)} – ${_formatTime(segment.end)}',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatTime(double seconds) {
    final m = (seconds / 60).floor();
    final s = (seconds % 60).floor();
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }
}

class _MeetingCard extends StatelessWidget {
  const _MeetingCard({required this.hit});

  final MeetingHit hit;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              hit.mainTopic.isNotEmpty ? hit.mainTopic : '(No topic)',
              style: Theme.of(context).textTheme.titleSmall,
            ),
            if (hit.originalFilename.isNotEmpty) ...[
              const SizedBox(height: 4),
              Text(
                hit.originalFilename,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
