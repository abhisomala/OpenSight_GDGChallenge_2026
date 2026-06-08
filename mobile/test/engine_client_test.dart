// Contract tests for the OpenSight `/ws` client, pinned directly to CONTRACT.md.
//
// These exercise the pure helpers in engine_client.dart (no socket needed):
//   * encodeQuery   — the outgoing query frame (CONTRACT.md §2).
//   * extractResponseText — pulling the answer out of a `response` frame (§3d).
//   * buildBrowserResultReply — the stub reply to a `browser_action` (§3c/§4).

import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:voice_client/engine_client.dart';

/// A [WebSocketChannel] that connects fine but never delivers a frame and never
/// closes — i.e. a silent/half-open server. `noSuchMethod` covers the channel
/// members `sendQuery` doesn't touch so we don't have to implement them all.
class _SilentChannel implements WebSocketChannel {
  _SilentChannel(this.stream);

  @override
  final Stream<dynamic> stream;

  @override
  final WebSocketSink sink = _NoopSink();

  @override
  Future<void> get ready => Future<void>.value();

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      super.noSuchMethod(invocation);
}

class _NoopSink implements WebSocketSink {
  @override
  void add(dynamic data) {}

  @override
  Future<void> close([int? closeCode, String? closeReason]) async {}

  @override
  dynamic noSuchMethod(Invocation invocation) =>
      super.noSuchMethod(invocation);
}

void main() {
  group('encodeQuery (CONTRACT.md §2 — outgoing query frame)', () {
    // The §2 "Real example" query string, verbatim from CONTRACT.md.
    const String exampleQuery = 'find me wireless headphones under fifty dollars';

    test('byte-matches the contract send example', () {
      // jsonEncode emits no extra whitespace, so the wire bytes are exactly
      // a single `text` field carrying the query string.
      expect(
        encodeQuery(exampleQuery),
        '{"text":"$exampleQuery"}',
      );
    });

    test('decodes back to the single-field {text: ...} shape the server reads', () {
      // server.py reads `message.get("text", "")`; confirm that round-trips.
      final Map<String, dynamic> decoded =
          jsonDecode(encodeQuery(exampleQuery)) as Map<String, dynamic>;
      expect(decoded.keys, <String>['text']);
      expect(decoded['text'], exampleQuery);
    });
  });

  group('extractResponseText (CONTRACT.md §3d — response frame)', () {
    test('extracts text from the contract response example', () {
      // The §3d "Real example" frame, verbatim.
      const String responseJson =
          '{ "type": "response", "text": "I found a few options. The top pick '
          'is a pair of wireless headphones for \$39.99." }';
      final Map<String, dynamic> frame =
          jsonDecode(responseJson) as Map<String, dynamic>;

      expect(
        extractResponseText(frame),
        'I found a few options. The top pick is a pair of wireless headphones '
        'for \$39.99.',
      );
    });

    test('returns null for a non-response frame (e.g. a status frame)', () {
      // §3a status frame must not be mistaken for the answer.
      final Map<String, dynamic> status = jsonDecode(
        '{ "type": "status", "agent": "BRAIN", "state": "thinking", '
        '"detail": "routing" }',
      ) as Map<String, dynamic>;
      expect(extractResponseText(status), isNull);
    });
  });

  group('buildBrowserResultReply (CONTRACT.md §3c/§4 — stub browser_result)', () {
    test('echoes the agent and sends the empty data shape', () {
      // §3c SHOPPING browser_action; the client cannot drive a browser, so it
      // replies with the empty `browser_result` shape (§4) to unblock the server.
      final Map<String, dynamic> action = jsonDecode(
        '{ "type": "browser_action", "agent": "SHOPPING", '
        '"query": "wireless headphones under fifty dollars" }',
      ) as Map<String, dynamic>;

      final Map<String, dynamic> reply =
          jsonDecode(buildBrowserResultReply(action)) as Map<String, dynamic>;

      expect(reply['type'], 'browser_result');
      expect(reply['agent'], 'SHOPPING');
      expect(reply['data'], <String, dynamic>{
        'results': <dynamic>[],
        'scraped': <String, dynamic>{},
      });
    });
  });

  group('sendQuery response timeout (CONTRACT.md §5 — read guard)', () {
    test('throws EngineConnectionException when no response frame arrives', () async {
      // Channel connects but the stream never emits and never closes, modelling a
      // server that accepts the socket then goes silent. Without the read guard
      // this would hang forever; with it, it must fail as a transport error.
      final StreamController<dynamic> frames = StreamController<dynamic>();
      addTearDown(frames.close);

      final EngineClient client = EngineClient(
        connect: (Uri _) => _SilentChannel(frames.stream),
        responseTimeout: const Duration(milliseconds: 50),
      );

      await expectLater(
        client.sendQuery('hello'),
        throwsA(isA<EngineConnectionException>()),
      );
    });
  });
}
