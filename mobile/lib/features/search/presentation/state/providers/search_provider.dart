import 'package:flutter/foundation.dart';

import '../../../domain/entities/search_result.dart';
import '../../../domain/repositories/search_repository.dart';
import 'package:mobile/core/errors/result.dart';

class SearchProvider extends ChangeNotifier {
  SearchProvider(this._repository);

  final SearchRepository _repository;

  List<TranscriptSegment> _transcriptResults = [];
  List<MeetingHit> _meetingResults = [];
  bool _isLoading = false;
  String? _errorMessage;

  List<TranscriptSegment> get transcriptResults => List.unmodifiable(_transcriptResults);
  List<MeetingHit> get meetingResults => List.unmodifiable(_meetingResults);
  bool get isLoading => _isLoading;
  String? get errorMessage => _errorMessage;

  Future<void> search(String query) async {
    if (query.trim().isEmpty) {
      _transcriptResults = [];
      _meetingResults = [];
      _errorMessage = null;
      notifyListeners();
      return;
    }
    _isLoading = true;
    _errorMessage = null;
    notifyListeners();

    final q = query.trim();
    final transcriptResult = await _repository.searchTranscripts(query: q);
    final meetingResult = await _repository.searchMeetings(query: q);

    _transcriptResults = transcriptResult.valueOrNull ?? [];
    _meetingResults = meetingResult.valueOrNull ?? [];

    if (transcriptResult.isError && transcriptResult.failureOrNull != null) {
      _errorMessage = transcriptResult.failureOrNull!.message;
    } else if (meetingResult.isError && meetingResult.failureOrNull != null) {
      _errorMessage = meetingResult.failureOrNull!.message;
    }

    _isLoading = false;
    notifyListeners();
  }

  void clearError() {
    _errorMessage = null;
    notifyListeners();
  }
}
