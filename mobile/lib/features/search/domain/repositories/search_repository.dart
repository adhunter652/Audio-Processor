import '../entities/search_result.dart';
import '../../../../core/errors/result.dart';

abstract class SearchRepository {
  Future<Result<List<TranscriptSegment>>> searchTranscripts({
    required String query,
    int limit = 20,
    List<int>? folderIds,
  });

  Future<Result<List<MeetingHit>>> searchMeetings({
    required String query,
    int limit = 20,
    List<int>? folderIds,
  });
}
