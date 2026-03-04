/// Single transcript segment from search.
class TranscriptSegment {
  final String text;
  final String jobId;
  final double start;
  final double end;
  final String originalFilename;
  final double distance;

  const TranscriptSegment({
    required this.text,
    required this.jobId,
    required this.start,
    required this.end,
    required this.originalFilename,
    required this.distance,
  });
}

/// Single meeting hit from search.
class MeetingHit {
  final String jobId;
  final String originalFilename;
  final String mainTopic;
  final String document;
  final double distance;

  const MeetingHit({
    required this.jobId,
    required this.originalFilename,
    required this.mainTopic,
    required this.document,
    required this.distance,
  });
}
