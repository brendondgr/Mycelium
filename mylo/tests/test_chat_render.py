"""chat_render: how an answer looks in Discord. Pure functions, no Discord."""

from __future__ import annotations

import unittest

from mylo.bot import chat_render as render


class SplitTests(unittest.TestCase):
    def test_short_text_is_one_chunk(self) -> None:
        self.assertEqual(
            render.split("Hello.\n\nTwo paragraphs."), ["Hello.\n\nTwo paragraphs."]
        )

    def test_every_chunk_is_under_the_limit_and_splits_on_paragraphs(self) -> None:
        paras = [f"Paragraph {i} " + "word " * 120 for i in range(12)]
        chunks = render.split("\n\n".join(paras))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLess(len(chunk), render.LIMIT)
            self.assertTrue(chunk.startswith("Paragraph"))

    def test_a_code_fence_is_never_left_open(self) -> None:
        code = "\n".join(f"x = {i}  # " + "c" * 60 for i in range(80))
        text = "Here is the code:\n\n```python\n" + code + "\n```\n\nDone."
        chunks = render.split(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLess(len(chunk), render.LIMIT)
            self.assertEqual(chunk.count("```") % 2, 0, chunk[:80])
        # the reopened fence keeps its language
        self.assertTrue(chunks[1].startswith("```python"))
        # no blank lines were inserted into the code
        self.assertNotIn("\n\nx = ", "".join(chunks))

    def test_one_enormous_line_is_cut(self) -> None:
        chunks = render.split("a" * 5000)
        self.assertTrue(all(len(c) < render.LIMIT for c in chunks))
        self.assertEqual("".join(chunks), "a" * 5000)


class MentionTests(unittest.TestCase):
    def test_model_output_cannot_ping(self) -> None:
        text = render.neutralise("Hi <@123> and <@!456>, <@&789>, @everyone and @here")
        self.assertNotIn("<@", text)
        self.assertNotIn("@everyone", text)
        self.assertNotIn("@here", text)

    def test_the_question_loses_the_mention_that_addressed_it(self) -> None:
        self.assertEqual(
            render.strip_mention("<@999> what is due?", bot_id=999), "what is due?"
        )
        self.assertEqual(
            render.strip_mention("<@&5> hi", bot_id=999, role_ids=[5]), "hi"
        )

    def test_the_slow_answer_ping_is_the_askers_only(self) -> None:
        self.assertEqual(render.slow_answer_prefix("111"), "<@111> ")
        with self.assertRaises(ValueError):
            render.slow_answer_prefix("<@&1>")


class SourcesAndModelTests(unittest.TestCase):
    def test_a_citation_is_a_link_where_it_stands(self) -> None:
        sources = [
            {"n": 1, "title": "[grant] Ocean call", "url": "https://x.org/a"},
            {"n": 2, "title": "A lab", "url": ""},
        ]
        text = "Due Friday (**#1**), says #2. See `#1` and issue#1.\n```\n#1\n```"
        out = render.link_citations(text, sources)
        self.assertIn("(**[#1](<https://x.org/a>)**), says #2.", out)
        self.assertIn("`#1` and issue#1.", out)  # code and words are left alone
        self.assertIn("```\n#1\n```", out)
        self.assertEqual(out.count("https://x.org/a"), 1)

    def test_only_sources_without_a_link_are_listed(self) -> None:
        block = render.sources_block(
            [
                {"n": 1, "title": "[grant] Ocean call", "url": "https://x.org/a"},
                {"n": 2, "title": "A lab", "url": ""},
                {"n": 3, "title": "x" * 200, "url": "javascript:alert(1)"},
            ]
        )
        self.assertEqual(block.split("\n")[0], "-# #2 A lab")
        self.assertNotIn("Ocean call", block)
        self.assertNotIn("javascript", block)
        self.assertLessEqual(len(block.split("\n")[1]), 100)

    def test_links_follow_the_answer_only_when_mylo_asks(self) -> None:
        sources = [{"n": 1, "title": "[paper] Cell maps", "url": "https://x.org/a"}]
        plain = render.answer_chunks("Read #1 first.", sources, None, first=False)
        self.assertEqual(plain, ["Read [#1](<https://x.org/a>) first."])
        asked = render.answer_chunks(
            "Read #1 first.\n\n[[links]]", sources, None, first=False
        )
        self.assertEqual(
            asked,
            [
                "Read [#1](<https://x.org/a>) first.",
                "**Links**\n- [Cell maps](<https://x.org/a>)",
            ],
        )

    def test_the_model_line(self) -> None:
        local = {"name": "qwen", "label": "Qwen", "location": "local"}
        self.assertEqual(render.model_line(local, first=True), "")
        self.assertEqual(render.model_line(local, first=False), "")
        cloud = {"name": "c", "label": "Cloud model", "location": "cloud"}
        self.assertIn("in the cloud", render.model_line(cloud, first=False))
        self.assertEqual(render.model_line(None, first=True), "")

    def test_answer_chunks_carry_sources_and_model_on_the_last(self) -> None:
        chunks = render.answer_chunks(
            "It is due Friday (#1).",
            [{"n": 1, "title": "Call", "url": "https://x.org"}],
            {"label": "Qwen", "location": "cloud"},
            first=True,
        )
        self.assertEqual(len(chunks), 1)
        self.assertIn("It is due Friday ([#1](<https://x.org>)).", chunks[0])
        self.assertNotIn("Sources", chunks[0])
        self.assertIn("-# Qwen", chunks[0])


class StatusTests(unittest.TestCase):
    def test_activity_becomes_a_status_line_never_thinking_text(self) -> None:
        self.assertEqual(
            render.status_line({"type": "activity", "payload": {"state": "thinking"}}),
            render.THINKING,
        )
        line = render.status_line(
            {
                "type": "activity",
                "payload": {"state": "running", "label": "Reading the call"},
            }
        )
        self.assertEqual(line, "*Reading the call…*")
        self.assertEqual(render.status_line({"type": "assistant"}), "")
        self.assertEqual(render.status_line({"type": "queued"}), render.QUEUED)

    def test_edits_are_throttled(self) -> None:
        now = [0.0]
        throttle = render.Throttle(clock=lambda: now[0])
        self.assertTrue(throttle.ready())
        now[0] = 1.0
        self.assertFalse(throttle.ready())
        now[0] = 1.6
        self.assertTrue(throttle.ready())


if __name__ == "__main__":
    unittest.main()
