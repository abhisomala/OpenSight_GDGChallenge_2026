/// Single-utterance client for the OpenSight backend `/ws` endpoint.
///
/// Mirrors the desktop client exactly, per CONTRACT.md:
///   * One WebSocket per utterance (§1): open → send {"text": ...} → read frames
///     until the `response` frame → close. Not a persistent connection.
///   * Outgoing query is a single JSON text frame `{"text": "<user words>"}` (§2).
///   * Incoming frames are discriminated by `type` (§3): `status`,
///     `research_status`, `browser_action`, `response`. The `response` frame is
///     the end-of-response signal — reading stops on it and its `text` is used.
///   * `status` / `research_status` are treated generically as a "working" signal;
///     no specific strings are matched (§3a/§3b).
///   * This client cannot drive a browser, so a `browser_action` (§3c) is answered
///     immediately with a stub `browser_result` (§4) so the server does not block.
///   * There is no error frame (§5): server problems arrive as a normal `response`.
///     Transport failures (cannot connect / drop mid-exchange) are handled here.
library;

import 'dart:async';
import 'dart:convert';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import 'config.dart';

/// Thrown for transport-level failures (cannot connect, or the socket closes
/// before a `response` frame arrives). Per CONTRACT.md §5 these are NOT signalled
/// by any server message — they are detected and surfaced client-side.
class EngineConnectionException implements Exception {
  EngineConnectionException(this.message);

  final String message;

  @override
  String toString() => 'EngineConnectionException: $message';
}

/// Encode the outgoing query frame. CONTRACT.md §2: `{ "text": "<words>" }`.
///
/// Pure and unit-tested: `jsonEncode` emits no extra whitespace, so this
/// byte-matches the contract's send example.
String encodeQuery(String text) => jsonEncode(<String, String>{'text': text});

/// Extract the spoken answer from a decoded `response` frame. CONTRACT.md §3d:
/// `{ "type": "response", "text": "<answer>" }`. Returns null if [frame] is not
/// a `response` frame or has no string `text`.
String? extractResponseText(Map<String, dynamic> frame) {
  if (frame['type'] != 'response') return null;
  final dynamic text = frame['text'];
  return text is String ? text : null;
}

/// Build the stub reply to a `browser_action`. CONTRACT.md §4 shape:
/// `{ "type": "browser_result", "agent": "<AGENT>", "data": {...} }`.
///
/// This client does no browser work, so `data` is the empty shape the server's
/// `_wait_for_browser_result` / `synthesize_shopping_response` can consume
/// without blocking: an empty `results` list and an empty `scraped` map. The
/// `agent` is echoed from the incoming `browser_action` so the server matches it.
String buildBrowserResultReply(Map<String, dynamic> browserAction) {
  final dynamic agent = browserAction['agent'];
  return jsonEncode(<String, dynamic>{
    'type': 'browser_result',
    'agent': agent is String ? agent : '',
    'data': <String, dynamic>{
      'results': <dynamic>[],
      'scraped': <String, dynamic>{},
    },
  });
}

/// Default read/response timeout. If the server accepts the socket but sends no
/// `response` frame (and never closes) within this window, the exchange fails as
/// a transport error rather than parking the caller forever (CONTRACT.md §5 —
/// the desktop client guarded `ws.recv()`, a guard the original port had dropped).
///
/// Set to 30s rather than the desktop client's 180s: this client only sends
/// non-browser queries (it stubs `browser_result` instead of driving a browser),
/// and those come back in seconds, so 30s is a generous ceiling. The shorter
/// bound also recovers fast enough to stay demo-usable on camera, whereas 180s
/// merely caps an infinite hang without being recoverable in any practical run.
const Duration defaultResponseTimeout = Duration(seconds: 30);

/// Opens a [WebSocketChannel] for [uri]. Injectable so tests can supply a fake
/// channel (e.g. one that never sends a `response`); defaults to
/// [WebSocketChannel.connect].
typedef ChannelConnector = WebSocketChannel Function(Uri uri);

/// Supplies the Firebase ID token to send in the auth frame, or null if there is
/// no token. Injectable so tests can simulate auth without a live Firebase.
typedef TokenProvider = Future<String?> Function();

/// Default [TokenProvider]: the current anonymous user's Firebase ID token, or
/// null if no user is signed in. Only ever called when [requireAuth] is true (or
/// a test injects `requireAuth: true`), so it never touches Firebase otherwise.
Future<String?> _firebaseIdToken() async =>
    FirebaseAuth.instance.currentUser?.getIdToken();

/// Top-level alias for the config [requireAuth] flag, so the constructor's
/// `requireAuth` parameter can default to it without name shadowing.
const bool _defaultRequireAuth = requireAuth;

/// Client for one query/response round trip against the OpenSight `/ws` endpoint.
class EngineClient {
  EngineClient({
    this.url = engineUrl,
    this.connectTimeout = const Duration(seconds: 5),
    this.responseTimeout = defaultResponseTimeout,
    ChannelConnector? connect,
    bool? requireAuth,
    TokenProvider? tokenProvider,
  })  : _connect = connect ?? WebSocketChannel.connect,
        requireAuth = requireAuth ?? _defaultRequireAuth,
        tokenProvider = tokenProvider ?? _firebaseIdToken;

  /// WebSocket URL of the backend `/ws` endpoint. Defaults to [engineUrl].
  final String url;

  /// How long to wait for the socket to connect before failing (mirrors the
  /// desktop client's `open_timeout=5` from CONTRACT.md §1).
  final Duration connectTimeout;

  /// How long to wait for the `response` frame after sending the query before
  /// failing with [EngineConnectionException] (CONTRACT.md §5 read guard).
  /// Defaults to [defaultResponseTimeout] (30s).
  final Duration responseTimeout;

  /// Factory used to open the socket; injectable for tests (see [ChannelConnector]).
  final ChannelConnector _connect;

  /// Whether to send an auth frame as the FIRST message on each connection.
  /// Defaults to the config [requireAuth] flag; injectable so tests can force it
  /// on without flipping the compile-time const.
  final bool requireAuth;

  /// Supplies the Firebase ID token for the auth frame. Defaults to the current
  /// anonymous user's token; injectable so tests can supply a fake token without
  /// a live Firebase. Only consulted when [requireAuth] is true.
  final TokenProvider tokenProvider;

  /// Open one WebSocket, send [text] as `{"text": ...}`, read frames until the
  /// `response` frame, then close, returning the response text.
  ///
  /// [onWorking] is invoked for each `status` / `research_status` frame as a
  /// generic progress signal (the decoded frame is passed through; no string
  /// matching). `browser_action` frames are answered with a stub `browser_result`.
  ///
  /// Throws [EngineConnectionException] on transport failure.
  Future<String> sendQuery(
    String text, {
    void Function(Map<String, dynamic> frame)? onWorking,
  }) async {
    final WebSocketChannel channel = _connect(Uri.parse(url));

    // Wait for the connection to be established (or fail) before sending.
    try {
      await channel.ready.timeout(connectTimeout);
    } on TimeoutException {
      await channel.sink.close();
      throw EngineConnectionException('connection to $url timed out');
    } catch (e) {
      await channel.sink.close();
      throw EngineConnectionException('could not connect to $url: $e');
    }

    final Completer<String> completer = Completer<String>();
    late final StreamSubscription<dynamic> sub;

    sub = channel.stream.listen(
      (dynamic raw) {
        Map<String, dynamic> frame;
        try {
          frame = jsonDecode(raw as String) as Map<String, dynamic>;
        } catch (_) {
          // Ignore anything that isn't a JSON object frame.
          return;
        }

        switch (frame['type']) {
          case 'response':
            // End-of-response signal: capture text and stop reading (§3d).
            if (!completer.isCompleted) {
              completer.complete(extractResponseText(frame) ?? '');
            }
            break;
          case 'browser_action':
            // Reply with a stub so the server does not block (§3c/§4).
            channel.sink.add(buildBrowserResultReply(frame));
            break;
          case 'status':
          case 'research_status':
            // Generic "working" signal — do not match specific strings (§3a/§3b).
            onWorking?.call(frame);
            break;
          default:
            // Unknown frame type — ignore.
            break;
        }
      },
      onError: (Object e) {
        if (!completer.isCompleted) {
          completer.completeError(
            EngineConnectionException('socket error during exchange: $e'),
          );
        }
      },
      onDone: () {
        // Socket closed before we saw a `response` frame — transport failure (§5).
        if (!completer.isCompleted) {
          completer.completeError(
            EngineConnectionException('connection closed before a response frame'),
          );
        }
      },
      cancelOnError: true,
    );

    // Optional auth frame (CONTRACT mirror of the server's REQUIRE_AUTH): when
    // [requireAuth] is on, this MUST be the first frame on the socket, sent
    // before the query. We do NOT wait for an ack — the server stays silent on
    // success and only closes with code 4001 on failure. If no token is
    // available we send nothing; the server will then reject the connection.
    if (requireAuth) {
      final String? token = await tokenProvider();
      if (token != null) {
        channel.sink.add(
          jsonEncode(<String, String>{'type': 'auth', 'token': token}),
        );
      }
    }

    // Send the single query frame (§2).
    channel.sink.add(encodeQuery(text));

    try {
      // Read guard (§5): a server that accepts the socket but never sends a
      // `response` (or never closes) must not park the caller forever — time out
      // and surface it as a transport failure so the controller can recover.
      return await completer.future.timeout(
        responseTimeout,
        onTimeout: () => throw EngineConnectionException(
          'no response from $url within ${responseTimeout.inSeconds}s',
        ),
      );
    } finally {
      // One-WebSocket-per-utterance: always close after the exchange (§1). On a
      // timeout this is also what closes the silent/half-open socket.
      await sub.cancel();
      await channel.sink.close();
    }
  }
}
