#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
test_check_private_data.py -- 100+ automated tests for the god-of-gods auditor.

Run:  python -m unittest test_check_private_data -v

Covers: target loading, every encoded variant, fuzzy regex, structural secret
patterns, byte/binary/hex scanning, steganographic carving (carved strings,
trailing-after-EOF, EXIF, LSB bit-plane), forensics, process introspection,
the LLM primary+fallback chain (mocked), repo walking, end-to-end main(), and
remote handling (mocked git).
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import types
import unittest
import urllib.error

import check_private_data as cpd

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def mkargs(**kw):
    d = dict(
        targets_file=None, target=None, no_llm=True,
        model=cpd.DEFAULT_MODEL, fallback_model=cpd.DEFAULT_FALLBACK_MODEL,
        models=[cpd.DEFAULT_MODEL, cpd.DEFAULT_FALLBACK_MODEL],
        ollama_url="http://test", max_bytes=25_000_000,
    )
    d.update(kw)
    return types.SimpleNamespace(**d)


def tlist(*pairs):
    """Build a targets list from (value, category) pairs."""
    return [{"label": v, "value": v, "category": c} for v, c in pairs]


def compiled_for(targets):
    return cpd.compile_targets(targets)


class FakeResp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener_ok(content):
    def _o(req, timeout=0):
        return FakeResp({"message": {"content": content}})
    return _o


def opener_fail(_=None):
    def _o(req, timeout=0):
        raise urllib.error.URLError("boom")
    return _o


def opener_model_aware(good_model, content):
    def _o(req, timeout=0):
        body = json.loads(req.data.decode("utf-8"))
        if body["model"] == good_model:
            return FakeResp({"message": {"content": content}})
        raise urllib.error.URLError("model not available")
    return _o


def write(path, data):
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    kw = {} if "b" in mode else {"encoding": "utf-8"}
    with open(path, mode, **kw) as fh:
        fh.write(data)


# ============================================================================
# 1. _normalize
# ============================================================================
class TestNormalize(unittest.TestCase):
    def test_lowercases(self):
        self.assertEqual(cpd._normalize("ABC"), "abc")

    def test_strips_accents(self):
        self.assertEqual(cpd._normalize("Lopez".replace("o", "ó")), "lopez")

    def test_tilde_n(self):
        self.assertEqual(cpd._normalize("Muñoz"), "munoz")

    def test_empty(self):
        self.assertEqual(cpd._normalize(""), "")

    def test_digits_unchanged(self):
        self.assertEqual(cpd._normalize("559648601"), "559648601")

    def test_mixed(self):
        self.assertEqual(cpd._normalize("Ángela L."), "angela l.")


# ============================================================================
# 2. load_targets
# ============================================================================
class TestLoadTargets(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CHECK_PRIVATE_DATA_TARGETS", None)

    def tearDown(self):
        os.environ.pop("CHECK_PRIVATE_DATA_TARGETS", None)

    def test_json_dict(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            write(p, json.dumps({"names": ["Foo", "Bar"], "phones": ["123"]}))
            ts = cpd.load_targets(mkargs(targets_file=p))
        self.assertEqual(len(ts), 3)

    def test_json_categories(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            write(p, json.dumps({"phones": ["123"]}))
            ts = cpd.load_targets(mkargs(targets_file=p))
        self.assertEqual(ts[0]["category"], "phones")

    def test_json_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            write(p, json.dumps(["a", "b"]))
            ts = cpd.load_targets(mkargs(targets_file=p))
        self.assertEqual(len(ts), 2)
        self.assertEqual(ts[0]["category"], "generic")

    def test_newline_list(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.txt")
            write(p, "one\ntwo\nthree\n")
            ts = cpd.load_targets(mkargs(targets_file=p))
        self.assertEqual(len(ts), 3)

    def test_newline_comments_skipped(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.txt")
            write(p, "# comment\nreal\n")
            ts = cpd.load_targets(mkargs(targets_file=p))
        self.assertEqual([t["value"] for t in ts], ["real"])

    def test_env(self):
        os.environ["CHECK_PRIVATE_DATA_TARGETS"] = "envval"
        ts = cpd.load_targets(mkargs())
        self.assertEqual(ts[0]["value"], "envval")

    def test_target_flag(self):
        ts = cpd.load_targets(mkargs(target=["x", "y"]))
        self.assertEqual(len(ts), 2)

    def test_dedupe(self):
        ts = cpd.load_targets(mkargs(target=["dup", "dup"]))
        self.assertEqual(len(ts), 1)

    def test_empty_none(self):
        self.assertEqual(cpd.load_targets(mkargs()), [])

    def test_merge_file_env_flag(self):
        os.environ["CHECK_PRIVATE_DATA_TARGETS"] = "envone"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.txt")
            write(p, "fileone\n")
            ts = cpd.load_targets(mkargs(targets_file=p, target=["flagone"]))
        vals = {t["value"] for t in ts}
        self.assertEqual(vals, {"fileone", "envone", "flagone"})

    def test_strips_whitespace(self):
        ts = cpd.load_targets(mkargs(target=["  spaced  "]))
        self.assertEqual(ts[0]["value"], "spaced")


# ============================================================================
# 3. byte_variants
# ============================================================================
class TestByteVariants(unittest.TestCase):
    def test_utf8_present(self):
        self.assertEqual(cpd.byte_variants("Foo")["utf-8"], b"Foo")

    def test_utf16(self):
        self.assertEqual(cpd.byte_variants("Foo")["utf-16-le"], "Foo".encode("utf-16-le"))

    def test_hex(self):
        import binascii
        self.assertEqual(cpd.byte_variants("Foo")["hex"], binascii.hexlify(b"Foo"))

    def test_base64(self):
        import base64
        self.assertEqual(cpd.byte_variants("Foo")["base64"], base64.b64encode(b"Foo"))

    def test_base32(self):
        import base64
        self.assertEqual(cpd.byte_variants("Foo")["base32"], base64.b32encode(b"Foo"))

    def test_url(self):
        self.assertEqual(cpd.byte_variants("a b")["url"], b"a%20b")

    def test_rot13(self):
        self.assertEqual(cpd.byte_variants("abc")["rot13"], b"nop")

    def test_reversed(self):
        self.assertEqual(cpd.byte_variants("abc")["reversed"], b"cba")

    def test_leet(self):
        self.assertEqual(cpd.byte_variants("aeios")["leet"], b"43105")

    def test_normalized_accented(self):
        v = "Ángela"
        self.assertEqual(cpd.byte_variants(v)["normalized"], b"angela")

    def test_dedupe_by_bytes(self):
        # for a lowercase ascii letterless-of-accents value normalized == utf-8 -> deduped
        out = cpd.byte_variants("foo")
        self.assertEqual(out["utf-8"], b"foo")
        self.assertNotIn("normalized", out)  # duplicate dropped

    def test_phone_hex(self):
        import binascii
        self.assertEqual(cpd.byte_variants("12345")["hex"], binascii.hexlify(b"12345"))

    def test_unicode_value(self):
        out = cpd.byte_variants("Münoz")
        self.assertIn("utf-8", out)
        self.assertIn("normalized", out)

    def test_all_values_bytes(self):
        for v in cpd.byte_variants("Sample123").values():
            self.assertIsInstance(v, bytes)

    def test_nonempty(self):
        self.assertTrue(len(cpd.byte_variants("x")) >= 4)


# ============================================================================
# 4. fuzzy_regex
# ============================================================================
class TestFuzzyRegex(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(cpd.fuzzy_regex("Angela").search("Angela"))

    def test_spaced(self):
        self.assertTrue(cpd.fuzzy_regex("Angela").search("a n g e l a"))

    def test_dashed(self):
        self.assertTrue(cpd.fuzzy_regex("12345").search("1-2-3-4-5"))

    def test_dotted(self):
        self.assertTrue(cpd.fuzzy_regex("12345").search("1.2.3.4.5"))

    def test_accent_insensitive(self):
        rx = cpd.fuzzy_regex("Ángela")
        self.assertTrue(rx.search(cpd._normalize("Ángela")))

    def test_case_insensitive(self):
        self.assertTrue(cpd.fuzzy_regex("foo").search("FOO"))

    def test_underscore_sep(self):
        self.assertTrue(cpd.fuzzy_regex("abc").search("a_b_c"))

    def test_no_match(self):
        self.assertIsNone(cpd.fuzzy_regex("zzzqqq").search("nothing here"))

    def test_phone_in_text(self):
        self.assertTrue(cpd.fuzzy_regex("559648601").search("call 5 5 9 6 4 8 6 0 1 now"))

    def test_empty_value_never_matches(self):
        self.assertIsNone(cpd.fuzzy_regex("   ").search("anything"))

    def test_too_far_apart_fails(self):
        # 4+ separators between chars should break the {0,3} bound
        self.assertIsNone(cpd.fuzzy_regex("ab").search("a--------b"))

    def test_returns_pattern(self):
        import re
        self.assertIsInstance(cpd.fuzzy_regex("x"), re.Pattern)


# ============================================================================
# 5. STRUCT_PATTERNS
# ============================================================================
class TestStructPatterns(unittest.TestCase):
    def hit(self, data):
        return {h["secret_type"] for h in cpd.scan_struct(data)}

    def test_rsa_private(self):
        self.assertIn("private_key_pem", self.hit(b"-----BEGIN RSA PRIVATE KEY-----"))

    def test_ec_private(self):
        self.assertIn("private_key_pem", self.hit(b"-----BEGIN EC PRIVATE KEY-----"))

    def test_plain_private(self):
        self.assertIn("private_key_pem", self.hit(b"-----BEGIN PRIVATE KEY-----"))

    def test_dsa_private(self):
        self.assertIn("private_key_pem", self.hit(b"-----BEGIN DSA PRIVATE KEY-----"))

    def test_pgp_private(self):
        self.assertIn("private_key_pem", self.hit(b"-----BEGIN PGP PRIVATE KEY-----"))

    def test_openssh(self):
        self.assertIn("ssh_private", self.hit(b"-----BEGIN OPENSSH PRIVATE KEY-----"))

    def test_certificate(self):
        self.assertIn("certificate_pem", self.hit(b"-----BEGIN CERTIFICATE-----"))

    def test_putty(self):
        self.assertIn("putty_key", self.hit(b"PuTTY-User-Key-File-2: ssh-rsa"))

    def test_kyber_plain(self):
        self.assertIn("kyber_keyword", self.hit(b"this uses KYBER keys"))

    def test_kyber_crystals(self):
        self.assertIn("kyber_keyword", self.hit(b"crystals-kyber"))

    def test_kyber_mlkem(self):
        self.assertIn("kyber_keyword", self.hit(b"ML-KEM-768"))

    def test_aws(self):
        self.assertIn("aws_access_key", self.hit(b"AKIAIOSFODNN7EXAMPLE"))

    def test_google(self):
        self.assertIn("google_api_key", self.hit(b"AIza" + b"B" * 35))

    def test_slack(self):
        self.assertIn("slack_token", self.hit(b"xoxb-1234567890-abcdef"))

    def test_bearer(self):
        self.assertIn("generic_bearer", self.hit(b"Authorization: Bearer abcdef0123456789abcdef"))

    def test_jwt(self):
        self.assertIn("jwt", self.hit(
            b"eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4"))

    def test_high_entropy(self):
        self.assertIn("high_entropy_b64", self.hit(b"A" * 80))

    def test_clean_none(self):
        self.assertEqual(self.hit(b"just normal text"), set())


# ============================================================================
# 6. scan_bytes (encoded-variant detection)
# ============================================================================
class TestScanBytes(unittest.TestCase):
    def layers_for(self, value, data, category="generic"):
        ts = tlist((value, category))
        c = compiled_for(ts)
        return {h["layer"] for h in cpd.scan_bytes(data, ts, c)}

    def test_plaintext(self):
        self.assertIn("bytes:utf-8", self.layers_for("Wonderland", b"hi Wonderland bye"))

    def test_case_insensitive_plain(self):
        self.assertIn("bytes:utf-8", self.layers_for("Wonderland", b"WONDERLAND"))

    def test_utf16(self):
        v = "Wonderland"
        self.assertIn("bytes:utf-16-le", self.layers_for(v, v.encode("utf-16-le")))

    def test_hex(self):
        import binascii
        v = "Wonderland"
        self.assertIn("bytes:hex", self.layers_for(v, binascii.hexlify(v.encode())))

    def test_base64(self):
        import base64
        v = "Wonderland"
        self.assertIn("bytes:base64", self.layers_for(v, base64.b64encode(v.encode())))

    def test_base32(self):
        import base64
        v = "Wonderland"
        self.assertIn("bytes:base32", self.layers_for(v, base64.b32encode(v.encode())))

    def test_rot13(self):
        import codecs
        v = "Wonderland"
        self.assertIn("bytes:rot13", self.layers_for(v, codecs.encode(v, "rot_13").encode()))

    def test_reversed(self):
        v = "Wonderland"
        self.assertIn("bytes:reversed", self.layers_for(v, v[::-1].encode()))

    def test_leet(self):
        v = "leetspeak"
        layers = self.layers_for(v, v.translate(cpd._LEET).encode())
        self.assertIn("bytes:leet", layers)

    def test_fuzzy(self):
        self.assertIn("fuzzy-regex", self.layers_for("12345", b"id 1 2 3 4 5 end"))

    def test_url_encoded(self):
        self.assertIn("bytes:url", self.layers_for("a b c", b"a%20b%20c"))

    def test_no_match(self):
        self.assertEqual(self.layers_for("zzzqqq", b"nothing"), set())

    def test_category_preserved(self):
        ts = tlist(("Wonderland", "names"))
        c = compiled_for(ts)
        hits = cpd.scan_bytes(b"Wonderland", ts, c)
        self.assertEqual(hits[0]["category"], "names")

    def test_offset_reported(self):
        ts = tlist(("Wonderland", "generic"))
        c = compiled_for(ts)
        hits = cpd.scan_bytes(b"xx Wonderland", ts, c)
        self.assertTrue(any(h["offset"] == 3 for h in hits if h["layer"] == "bytes:utf-8"))

    def test_multiple_targets(self):
        ts = tlist(("Alpha", "a"), ("Bravo", "b"))
        c = compiled_for(ts)
        names = {h["target"] for h in cpd.scan_bytes(b"Alpha and Bravo", ts, c)}
        self.assertEqual(names, {"Alpha", "Bravo"})


# ============================================================================
# 7. carve_strings
# ============================================================================
class TestCarveStrings(unittest.TestCase):
    def test_extracts_printable(self):
        out = cpd.carve_strings(b"\x00\x01hello\x00world\xff")
        self.assertIn(b"hello", out)
        self.assertIn(b"world", out)

    def test_min_length(self):
        out = cpd.carve_strings(b"\x00ab\x00abcd\x00")
        self.assertIn(b"abcd", out)
        self.assertNotIn(b"ab\n", out + b"\n")

    def test_binary_noise_dropped(self):
        out = cpd.carve_strings(b"\x00\x01\x02\x03")
        self.assertEqual(out, b"")

    def test_limit(self):
        data = (b"\x00abcd" * 10000)
        out = cpd.carve_strings(data, limit=5)
        self.assertEqual(out.count(b"abcd"), 5)


# ============================================================================
# 8. steg_scan
# ============================================================================
class TestStegScan(unittest.TestCase):
    def test_carved_strings_in_binary(self):
        ts = tlist(("HIDDEN", "generic"))
        c = compiled_for(ts)
        data = b"\x00\x01\x02HIDDEN\x00\x99"
        layers = {h["layer"] for h in cpd.steg_scan("x.bin", data, ts, c)}
        self.assertIn("steg:carved-strings", layers)

    def test_non_image_returns_carved_only(self):
        ts = tlist(("ZZ", "generic"))
        c = compiled_for(ts)
        hits = cpd.steg_scan("x.bin", b"binary", ts, c)
        self.assertTrue(all(h["layer"].startswith("steg:carved") for h in hits) or hits == [])

    @unittest.skipUnless(_HAS_PIL, "Pillow not installed")
    def test_trailing_after_png_eof(self):
        ts = tlist(("APPENDEDSECRET", "generic"))
        c = compiled_for(ts)
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
        data = buf.getvalue() + b"APPENDEDSECRET-payload-here-xxxxxxxx"
        layers = {h["layer"] for h in cpd.steg_scan("x.png", data, ts, c)}
        self.assertTrue("steg:trailing-after-eof" in layers or "steg:carved-strings" in layers)

    @unittest.skipUnless(_HAS_PIL, "Pillow not installed")
    def test_trailing_after_jpeg_eof(self):
        ts = tlist(("JPGSECRETPAYLOAD", "generic"))
        c = compiled_for(ts)
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="JPEG")
        data = buf.getvalue() + b"JPGSECRETPAYLOAD-xxxxxxxx"
        layers = {h["layer"] for h in cpd.steg_scan("x.jpg", data, ts, c)}
        self.assertTrue("steg:trailing-after-eof" in layers or "steg:carved-strings" in layers)

    @unittest.skipUnless(_HAS_PIL, "Pillow not installed")
    def test_lsb_bitplane(self):
        secret = b"SECRET42"
        # embed secret bits into LSBs in R,G,B,R,... order, MSB-first per byte
        bits = []
        for byte in secret:
            for j in range(8):
                bits.append((byte >> (7 - j)) & 1)
        npix = (len(bits) + 2) // 3
        pixels = []
        bi = 0
        for _ in range(max(npix, 64)):
            chan = []
            for _c in range(3):
                base = 100
                if bi < len(bits):
                    base = (base & ~1) | bits[bi]
                    bi += 1
                chan.append(base)
            pixels.append(tuple(chan))
        img = Image.new("RGB", (len(pixels), 1))
        img.putdata(pixels)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.png")
            img.save(p, format="PNG")
            data = open(p, "rb").read()
            ts = tlist(("SECRET42", "generic"))
            c = compiled_for(ts)
            layers = {h["layer"] for h in cpd.steg_scan(p, data, ts, c)}
        self.assertTrue(any(layer.startswith("steg:lsb") for layer in layers))

    @unittest.skipUnless(_HAS_PIL, "Pillow not installed")
    def test_image_without_secret_no_target_hit(self):
        ts = tlist(("NOTPRESENTXYZ", "generic"))
        c = compiled_for(ts)
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (123, 222, 99)).save(buf, format="PNG")
        hits = cpd.steg_scan("x.png", buf.getvalue(), ts, c)
        self.assertTrue(all(h.get("target") != "NOTPRESENTXYZ" for h in hits))


# ============================================================================
# 9. forensics
# ============================================================================
class TestForensics(unittest.TestCase):
    def test_femto_display(self):
        s = cpd.femto_display(1000)
        self.assertIn("fs", s)
        self.assertIn("1000 ns", s)

    def test_file_owner_string(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "x")
            self.assertIsInstance(cpd.file_owner(p), str)

    def test_file_forensics_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "hello")
            meta = cpd.file_forensics(p, d)
        for k in ("size_bytes", "owner_account", "mtime_ns", "sha256",
                  "mtime_femto", "relpath", "git"):
            self.assertIn(k, meta)

    def test_sha256_correct(self):
        import hashlib
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "hello")
            meta = cpd.file_forensics(p, d)
        self.assertEqual(meta["sha256"], hashlib.sha256(b"hello").hexdigest())

    def test_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "12345")
            self.assertEqual(cpd.file_forensics(p, d)["size_bytes"], 5)

    def test_relpath(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "x")
            self.assertEqual(cpd.file_forensics(p, d)["relpath"], "f.txt")

    def test_mtime_ns_int(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "f.txt")
            write(p, "x")
            self.assertIsInstance(cpd.file_forensics(p, d)["mtime_ns"], int)

    def test_git_blame_meta_nonrepo(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cpd.git_blame_meta(d, "nope.txt"), {})


# ============================================================================
# 10. process_forensics
# ============================================================================
class TestProcessForensics(unittest.TestCase):
    def test_pid(self):
        self.assertEqual(cpd.process_forensics()["pid"], os.getpid())

    def test_has_login(self):
        self.assertIn("login", cpd.process_forensics())

    def test_structure(self):
        info = cpd.process_forensics()
        self.assertIn("parents", info)
        self.assertIn("memory_maps", info)

    def test_no_crash(self):
        cpd.process_forensics()  # must not raise


# ============================================================================
# 11. LLM primary + fallback (mocked)
# ============================================================================
class TestLLM(unittest.TestCase):
    def setUp(self):
        self.ts = tlist(("Foo", "names"))

    def test_primary_success(self):
        r = cpd.llm_review("text", ["A", "B"], "http://x", self.ts, opener=opener_ok("LEAK: yes"))
        self.assertEqual(r["model"], "A")
        self.assertEqual(r["verdict"], "LEAK: yes")

    def test_primary_fail_fallback_success(self):
        r = cpd.llm_review("text", ["glm-5.2:cloud", "glm-5.1:cloud"],
                           "http://x", self.ts,
                           opener=opener_model_aware("glm-5.1:cloud", "CLEAN"))
        self.assertEqual(r["model"], "glm-5.1:cloud")
        self.assertEqual(r["verdict"], "CLEAN")

    def test_both_fail(self):
        r = cpd.llm_review("text", ["A", "B"], "http://x", self.ts, opener=opener_fail())
        self.assertIsNone(r["model"])
        self.assertTrue(r["verdict"].startswith("[llm-unavailable"))

    def test_empty_text(self):
        r = cpd.llm_review("   ", ["A"], "http://x", self.ts, opener=opener_ok("x"))
        self.assertIsNone(r["model"])
        self.assertEqual(r["verdict"], "")

    def test_ollama_chat_ok(self):
        out = cpd.ollama_chat("hi", "A", "http://x", self.ts, opener=opener_ok("HELLO"))
        self.assertEqual(out, "HELLO")

    def test_ollama_chat_error(self):
        out = cpd.ollama_chat("hi", "A", "http://x", self.ts, opener=opener_fail())
        self.assertTrue(out.startswith("[llm-unavailable"))

    def test_default_models(self):
        self.assertEqual(cpd.build_models(cpd.DEFAULT_MODEL, cpd.DEFAULT_FALLBACK_MODEL),
                         ["glm-5.2:cloud", "glm-5.1:cloud"])

    def test_build_models_dedupe(self):
        self.assertEqual(cpd.build_models("same", "same"), ["same"])

    def test_build_models_skip_empty(self):
        self.assertEqual(cpd.build_models("primary", ""), ["primary"])

    def test_system_prompt_mentions_categories(self):
        sp = cpd._llm_system_prompt(tlist(("x", "phones"), ("y", "names")))
        self.assertIn("phones", sp)
        self.assertIn("names", sp)

    def test_fallback_order_respected(self):
        # only the SECOND model good -> first tried and skipped
        r = cpd.llm_review("text", ["bad", "good"], "http://x", self.ts,
                           opener=opener_model_aware("good", "LEAK"))
        self.assertEqual(r["model"], "good")

    def test_api_key_header(self):
        os.environ["OLLAMA_API_KEY"] = "secret"
        captured = {}

        def cap_opener(req, timeout=0):
            captured["auth"] = req.get_header("Authorization")
            return FakeResp({"message": {"content": "ok"}})
        try:
            cpd.ollama_chat("hi", "A", "http://x", self.ts, opener=cap_opener)
        finally:
            os.environ.pop("OLLAMA_API_KEY", None)
        self.assertEqual(captured["auth"], "Bearer secret")


# ============================================================================
# 12. iter_files / repo walking
# ============================================================================
class TestIterFiles(unittest.TestCase):
    def test_yields_files(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "a.txt"), "x")
            write(os.path.join(d, "b.txt"), "y")
            self.assertEqual(len(list(cpd.iter_files(d, 10**9))), 2)

    def test_skips_skip_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, ".git"))
            write(os.path.join(d, ".git", "secret.txt"), "x")
            write(os.path.join(d, "keep.txt"), "y")
            files = [os.path.basename(p) for p in cpd.iter_files(d, 10**9)]
        self.assertEqual(files, ["keep.txt"])

    def test_size_cap(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "big.txt"), "x" * 100)
            self.assertEqual(list(cpd.iter_files(d, 10)), [])


# ============================================================================
# 13. scan_repo (end-to-end planted-secret detection -- GOD LEVEL proof)
# ============================================================================
class TestScanRepoDetection(unittest.TestCase):
    def _plant(self, d, value):
        import base64
        import binascii
        import codecs
        files = {
            "plain.txt": f"hi {value} bye".encode(),
            "utf16.bin": value.encode("utf-16-le"),
            "hex.txt": binascii.hexlify(value.encode()),
            "b64.txt": base64.b64encode(value.encode()),
            "b32.txt": base64.b32encode(value.encode()),
            "rot13.txt": codecs.encode(value, "rot_13").encode(),
            "reversed.txt": value[::-1].encode(),
            "spaced.txt": (" ".join(value)).encode(),
        }
        for name, content in files.items():
            write(os.path.join(d, name), content)
        return set(files)

    def test_detects_every_encoding(self):
        value = "Wonderland"
        with tempfile.TemporaryDirectory() as d:
            planted = self._plant(d, value)
            ts = tlist((value, "names"))
            c = compiled_for(ts)
            res = cpd.scan_repo(d, ts, c, mkargs(no_llm=True))
        flagged = {f["forensics"]["relpath"] for f in res["findings"]}
        self.assertEqual(planted, flagged,
                         f"missed: {planted - flagged}")

    def test_detects_private_key_file(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "id_rsa"), b"-----BEGIN RSA PRIVATE KEY-----\nabc\n")
            ts = tlist(("irrelevant", "generic"))
            c = compiled_for(ts)
            res = cpd.scan_repo(d, ts, c, mkargs(no_llm=True))
        self.assertEqual(len(res["findings"]), 1)
        layers = {m["layer"] for m in res["findings"][0]["matches"]}
        self.assertIn("struct:private_key_pem", layers)

    def test_detects_kyber_file(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "pq.txt"), b"using crystals-kyber for keys")
            ts = tlist(("nope", "generic"))
            c = compiled_for(ts)
            res = cpd.scan_repo(d, ts, c, mkargs(no_llm=True))
        self.assertEqual(len(res["findings"]), 1)

    def test_clean_repo_no_findings(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "ok.txt"), b"completely innocuous text")
            ts = tlist(("absent-value-xyz", "generic"))
            c = compiled_for(ts)
            res = cpd.scan_repo(d, ts, c, mkargs(no_llm=True))
        self.assertEqual(res["findings"], [])

    def test_files_scanned_count(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "a.txt"), b"x")
            write(os.path.join(d, "b.txt"), b"y")
            ts = tlist(("z", "generic"))
            res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=True))
        self.assertEqual(res["files_scanned"], 2)

    def test_finding_has_forensics(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "a.txt"), b"Wonderland")
            ts = tlist(("Wonderland", "names"))
            res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=True))
        self.assertIn("sha256", res["findings"][0]["forensics"])

    def test_llm_gated_off(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "a.txt"), b"plain")
            ts = tlist(("absent", "generic"))
            res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=True))
        self.assertEqual(res["findings"], [])

    def test_llm_flags_file_via_mock(self):
        # monkeypatch llm_review to force a LEAK verdict
        orig = cpd.llm_review
        cpd.llm_review = lambda *a, **k: {"model": "glm-5.2:cloud", "verdict": "LEAK: hidden"}
        try:
            with tempfile.TemporaryDirectory() as d:
                write(os.path.join(d, "a.txt"), b"nothing regex would catch")
                ts = tlist(("absent-xyz", "generic"))
                res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=False))
            self.assertEqual(len(res["findings"]), 1)
            self.assertEqual(res["findings"][0]["llm_model"], "glm-5.2:cloud")
        finally:
            cpd.llm_review = orig

    def test_llm_clean_no_finding(self):
        orig = cpd.llm_review
        cpd.llm_review = lambda *a, **k: {"model": "glm-5.2:cloud", "verdict": "CLEAN"}
        try:
            with tempfile.TemporaryDirectory() as d:
                write(os.path.join(d, "a.txt"), b"nothing")
                ts = tlist(("absent-xyz", "generic"))
                res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=False))
            self.assertEqual(res["findings"], [])
        finally:
            cpd.llm_review = orig

    def test_llm_unavailable_not_flagged(self):
        orig = cpd.llm_review
        cpd.llm_review = lambda *a, **k: {"model": None, "verdict": "[llm-unavailable: x]"}
        try:
            with tempfile.TemporaryDirectory() as d:
                write(os.path.join(d, "a.txt"), b"nothing")
                ts = tlist(("absent-xyz", "generic"))
                res = cpd.scan_repo(d, ts, compiled_for(ts), mkargs(no_llm=False))
            self.assertEqual(res["findings"], [])
        finally:
            cpd.llm_review = orig


# ============================================================================
# 14. main() end-to-end
# ============================================================================
class TestMain(unittest.TestCase):
    def test_no_targets_exit_2(self):
        os.environ.pop("CHECK_PRIVATE_DATA_TARGETS", None)
        with tempfile.TemporaryDirectory() as d:
            rc = cpd.main(["--local", "--repo", d, "--no-llm",
                           "--output", os.path.join(d, "r.json")])
        self.assertEqual(rc, 2)

    def test_local_clean_exit_0(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "ok.txt"), "innocuous")
            out = os.path.join(d, "r.json")
            rc = cpd.main(["--local", "--repo", d, "--no-llm",
                           "--target", "absent-value-xyz", "--output", out])
        self.assertEqual(rc, 0)

    def test_local_leak_exit_1(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "leak.txt"), "Wonderland is here")
            out = os.path.join(d, "r.json")
            rc = cpd.main(["--local", "--repo", d, "--no-llm",
                           "--target", "Wonderland", "--output", out])
        self.assertEqual(rc, 1)

    def test_report_written_valid_json(self):
        with tempfile.TemporaryDirectory() as d:
            write(os.path.join(d, "leak.txt"), "Wonderland")
            out = os.path.join(d, "r.json")
            cpd.main(["--local", "--repo", d, "--no-llm",
                      "--target", "Wonderland", "--output", out])
            with open(out, encoding="utf-8") as fh:
                report = json.load(fh)
        self.assertEqual(report["scope"], "local")
        self.assertIn("process_forensics", report)
        self.assertEqual(report["total_files_with_findings"], 1)

    def test_default_scope_is_local(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            cpd.main(["--repo", d, "--no-llm", "--target", "x", "--output", out])
            with open(out, encoding="utf-8") as fh:
                report = json.load(fh)
        self.assertEqual(report["scope"], "local")

    def test_report_records_models_when_llm_on(self):
        orig = cpd.llm_review
        cpd.llm_review = lambda *a, **k: {"model": None, "verdict": ""}
        try:
            with tempfile.TemporaryDirectory() as d:
                write(os.path.join(d, "a.txt"), "x")
                out = os.path.join(d, "r.json")
                cpd.main(["--local", "--repo", d, "--target", "x", "--output", out])
                with open(out, encoding="utf-8") as fh:
                    report = json.load(fh)
            self.assertEqual(report["llm_models"], ["glm-5.2:cloud", "glm-5.1:cloud"])
        finally:
            cpd.llm_review = orig

    def test_custom_model_flags(self):
        orig = cpd.llm_review
        cpd.llm_review = lambda *a, **k: {"model": None, "verdict": ""}
        try:
            with tempfile.TemporaryDirectory() as d:
                write(os.path.join(d, "a.txt"), "x")
                out = os.path.join(d, "r.json")
                cpd.main(["--local", "--repo", d, "--target", "x", "--output", out,
                          "--model", "m1", "--fallback-model", "m2"])
                with open(out, encoding="utf-8") as fh:
                    report = json.load(fh)
            self.assertEqual(report["llm_models"], ["m1", "m2"])
        finally:
            cpd.llm_review = orig


# ============================================================================
# 15. remote handling (mocked git)
# ============================================================================
class TestRemote(unittest.TestCase):
    def test_detect_remote_url(self):
        orig = cpd.subprocess.run

        class R:
            returncode = 0
            stdout = "https://example.com/repo.git\n"
        cpd.subprocess.run = lambda *a, **k: R()
        try:
            self.assertEqual(cpd.detect_remote_url("x"), "https://example.com/repo.git")
        finally:
            cpd.subprocess.run = orig

    def test_detect_remote_url_none(self):
        orig = cpd.subprocess.run

        class R:
            returncode = 1
            stdout = ""
        cpd.subprocess.run = lambda *a, **k: R()
        try:
            self.assertEqual(cpd.detect_remote_url("x"), "")
        finally:
            cpd.subprocess.run = orig

    def test_clone_remote_invoked(self):
        orig = cpd.subprocess.run
        called = {}

        def fake_run(cmd, *a, **k):
            called["cmd"] = cmd
            class R:
                returncode = 0
            return R()
        cpd.subprocess.run = fake_run
        try:
            cpd.clone_remote("https://x/y.git")
        finally:
            cpd.subprocess.run = orig
        self.assertIn("clone", called["cmd"])

    def test_both_mode_merges(self):
        orig_detect = cpd.detect_remote_url
        orig_clone = cpd.clone_remote
        cpd.detect_remote_url = lambda repo: "https://x/y.git"
        with tempfile.TemporaryDirectory() as remote_d:
            write(os.path.join(remote_d, "r.txt"), "Wonderland remote")
            cpd.clone_remote = lambda url: remote_d
            try:
                with tempfile.TemporaryDirectory() as local_d:
                    write(os.path.join(local_d, "l.txt"), "Wonderland local")
                    out = os.path.join(local_d, "rep.json")
                    rc = cpd.main(["--both", "--repo", local_d, "--no-llm",
                                   "--target", "Wonderland", "--output", out])
                    with open(out, encoding="utf-8") as fh:
                        report = json.load(fh)
            finally:
                cpd.detect_remote_url = orig_detect
                cpd.clone_remote = orig_clone
        modes = {s["mode"] for s in report["scans"]}
        self.assertEqual(modes, {"local", "remote"})
        self.assertEqual(rc, 1)

    def test_remote_error_captured(self):
        orig_detect = cpd.detect_remote_url
        orig_clone = cpd.clone_remote
        cpd.detect_remote_url = lambda repo: "https://x/y.git"

        def boom(url):
            raise RuntimeError("clone failed")
        cpd.clone_remote = boom
        try:
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "r.json")
                cpd.main(["--remote", "--repo", d, "--no-llm",
                          "--target", "x", "--output", out])
                with open(out, encoding="utf-8") as fh:
                    report = json.load(fh)
        finally:
            cpd.detect_remote_url = orig_detect
            cpd.clone_remote = orig_clone
        remote = [s for s in report["scans"] if s["mode"] == "remote"][0]
        self.assertIn("error", remote)


# ============================================================================
# 16. parser / misc
# ============================================================================
class TestParserMisc(unittest.TestCase):
    def test_parser_defaults(self):
        args = cpd.build_parser().parse_args([])
        self.assertEqual(args.model, "glm-5.2:cloud")
        self.assertEqual(args.fallback_model, "glm-5.1:cloud")

    def test_parser_scope_flags(self):
        args = cpd.build_parser().parse_args(["--both"])
        self.assertTrue(args.both)

    def test_parser_target_repeatable(self):
        args = cpd.build_parser().parse_args(["--target", "a", "--target", "b"])
        self.assertEqual(args.target, ["a", "b"])

    def test_compile_targets_keys(self):
        ts = tlist(("Foo", "x"), ("Bar", "y"))
        c = cpd.compile_targets(ts)
        self.assertEqual(set(c.keys()), {"Foo", "Bar"})

    def test_compile_targets_has_variants_and_fuzzy(self):
        c = cpd.compile_targets(tlist(("Foo", "x")))
        self.assertIn("variants", c["Foo"])
        self.assertIn("fuzzy", c["Foo"])

    def test_skip_dirs_constant(self):
        self.assertIn(".git", cpd.SKIP_DIRS)

    def test_text_review_ext(self):
        self.assertIn(".py", cpd.TEXT_REVIEW_EXT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
