# Tests for translator.py. Run:  python3 test_translator.py
# No internet needed: Google's HTTP endpoint is replaced by a fake that "translates" by tagging the text.
import io, json, os, sys, time, unittest, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translator as tr


class FakeResponse(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeGoogle:
    """Pretends to be translate.googleapis.com. 'Translates' English into '<target>:' + text."""
    def __init__(self, delay=0.0, fail=None):
        self.delay, self.fail, self.calls, self.sizes = delay, fail, 0, []

    def __call__(self, request, timeout=None):
        self.calls += 1
        if self.fail:
            raise self.fail
        form = urllib.parse.parse_qs(request.data.decode("utf-8"))
        text, target = form["q"][0], form["tl"][0]
        self.sizes.append(len(text))
        time.sleep(self.delay)
        source = "es" if text.lower().startswith(("hola", "buenos")) else "en"
        out = text if source == target.split("-")[0] else f"[{target}] {text}"
        return FakeResponse(json.dumps([[[out, text, None, None, 1]], None, source]).encode("utf-8"))


def install(fake):
    urllib.request.urlopen = fake


class Tests(unittest.TestCase):
    def setUp(self):
        self.real = urllib.request.urlopen

    def tearDown(self):
        urllib.request.urlopen = self.real

    def test_english_to_spanish(self):
        install(FakeGoogle())
        out = tr.MessageTranslator().translate("How are you today?", "es")
        self.assertEqual(out, {"text": "[es] How are you today?"})

    def test_already_in_target_language_shows_nothing(self):
        install(FakeGoogle())
        self.assertIsNone(tr.MessageTranslator().translate("hola amigo", "es"))

    def test_links_and_mentions_survive(self):
        install(FakeGoogle())
        out = tr.MessageTranslator().translate("hey @bob see https://x.com/a?b=1 :smile:", "fr")
        for bit in ("@bob", "https://x.com/a?b=1", ":smile:"):
            self.assertIn(bit, out["text"])

    def test_nothing_to_translate(self):
        install(FakeGoogle())
        t = tr.MessageTranslator()
        for s in ("", "   ", "12345 !!!", "https://example.com", "@bob"):
            self.assertIsNone(t.translate(s, "es"))

    def test_any_length(self):
        fake = FakeGoogle()
        install(fake)
        text = "\n".join(f"Line number {i}. It has two sentences here!" for i in range(2000))   # ~90,000 chars
        out = tr.MessageTranslator().translate(text, "es")["text"]
        self.assertTrue(all(n <= tr.MAX_CHUNK for n in fake.sizes))
        self.assertGreater(len(fake.sizes), 10)
        self.assertEqual(out.count("Line number"), 2000)                     # nothing dropped
        self.assertEqual(out.count("\n"), 1999)                              # line breaks kept
        self.assertIn("Line number 1999", out)

    def test_one_huge_word_run(self):
        install(FakeGoogle())
        out = tr.MessageTranslator().translate("a" * 20000, "es")["text"]
        self.assertEqual(out.count("a"), 20000)

    def test_chunks_rejoin_exactly(self):
        text = ("Sentence one. " * 700) + "\n\n" + ("Another line!\n" * 500)
        self.assertEqual("".join(tr._chunks(text)), text)

    def test_parallel_is_fast(self):
        install(FakeGoogle(delay=0.3))
        t = tr.MessageTranslator()
        done, start = [], time.time()
        for i in range(6):
            t.translate_async(f"message number {i}", "es", lambda r, e: done.append((r, e)))
        while len(done) < 6 and time.time() - start < 5:
            time.sleep(0.01)
        self.assertEqual(len(done), 6)
        self.assertLess(time.time() - start, 0.9)                           # 6 x 0.3s would be 1.8s one-at-a-time
        self.assertTrue(all(e is None and r for r, e in done))

    def test_long_message_pieces_run_together(self):
        install(FakeGoogle(delay=0.3))
        text = ("Hello there my friend. " * 200)                           # ~4,600 chars -> 2 pieces
        text = text * 4                                                      # 4 pieces
        start = time.time()
        tr.MessageTranslator().translate(text, "es")
        self.assertLess(time.time() - start, 0.9)

    def test_cache(self):
        fake = FakeGoogle()
        install(fake)
        t = tr.MessageTranslator()
        t.translate("same text", "es"); t.translate("same text", "es")
        self.assertEqual(fake.calls, 1)

    def test_offline_gives_clear_error_and_is_not_cached(self):
        install(FakeGoogle(fail=urllib.error.URLError("no network")))
        t = tr.MessageTranslator()
        with self.assertRaises(Exception) as cm:
            t.translate("hello", "es")
        self.assertIn("internet", tr.friendly_error(cm.exception).lower())
        install(FakeGoogle())                                                # network is back
        self.assertEqual(t.translate("hello", "es"), {"text": "[es] hello"})

    def test_rate_limit_pauses_then_reports(self):
        err = urllib.error.HTTPError("u", 429, "Too Many", {}, None)
        install(FakeGoogle(fail=err))
        t = tr.MessageTranslator(cooldown=60)
        with self.assertRaises(Exception):
            t.translate("hello", "es")
        self.assertGreater(t.seconds_blocked(), 0)

    def test_falls_back_to_offline_pack(self):
        install(FakeGoogle(fail=urllib.error.URLError("down")))
        auto = tr.AutoBackend()

        class FakeArgos:
            def installed(self): return {"es": 1, "en": 1}
            def translate(self, text, target): return "OFFLINE " + text
        auto._argos, auto._argos_tried = FakeArgos(), True
        self.assertEqual(auto.translate("hello", "es"), "OFFLINE hello")
        with self.assertRaises(Exception):                                   # no pack for German -> real error
            auto.translate("hello", "de")

    def test_codes(self):
        self.assertEqual(tr.normalize_target("he"), "iw")
        self.assertEqual(tr.normalize_target("zh"), "zh-CN")
        self.assertEqual(tr.lang_base("zh-CN"), "zh")
        self.assertEqual(tr.lang_base("iw"), "he")


if __name__ == "__main__":
    unittest.main(verbosity=2)
