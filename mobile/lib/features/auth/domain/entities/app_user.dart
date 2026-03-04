/// Logged-in user from Firebase/Google.
class AppUser {
  final String uid;
  final String? email;
  final String? displayName;
  final String? photoUrl;

  const AppUser({
    required this.uid,
    this.email,
    this.displayName,
    this.photoUrl,
  });
}
