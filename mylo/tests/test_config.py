"""Unit tests for Mylo configuration loading and validation."""

from __future__ import annotations

import unittest

from mylo.config import ConfigError, MyloConfig, _load_env_file, load_config


class LoadConfigTests(unittest.TestCase):
    def test_overrides_win_and_ids_parse_to_ints(self) -> None:
        cfg = load_config(
            overrides={
                "DISCORD_API_KEY": "  tok  ",
                "ERROR_CHANNEL": "100",
                "SUMMARY_CHANNEL": "200",
                "DISCORD_DEV_GUILD_ID": "300",
                "DISCORD_OWNER_IDS": "1, 2 ,3",
            }
        )
        self.assertEqual(cfg.token, "tok")
        self.assertEqual(cfg.error_channel_id, 100)
        self.assertEqual(cfg.summary_channel_id, 200)
        self.assertEqual(cfg.dev_guild_id, 300)
        self.assertEqual(cfg.owner_ids, frozenset({1, 2, 3}))
        self.assertTrue(cfg.reporting_enabled)
        self.assertTrue(cfg.is_dev)

    def test_absent_optionals_are_none_and_reporting_disabled(self) -> None:
        cfg = load_config(overrides={"DISCORD_API_KEY": "", "ERROR_CHANNEL": ""})
        self.assertEqual(cfg.token, "")
        self.assertIsNone(cfg.error_channel_id)
        self.assertFalse(cfg.reporting_enabled)
        self.assertFalse(cfg.is_dev)

    def test_non_numeric_channel_id_raises(self) -> None:
        with self.assertRaises(ConfigError):
            load_config(overrides={"ERROR_CHANNEL": "not-a-number"})

    def test_require_bot_raises_without_token(self) -> None:
        cfg = MyloConfig(token="", error_channel_id=1)
        with self.assertRaises(ConfigError):
            cfg.require_bot()

    def test_require_bot_runs_without_an_error_channel(self) -> None:
        """The channel is optional: without it, reports go to the log only."""
        cfg = MyloConfig(token="tok", error_channel_id=None)
        self.assertIs(cfg.require_bot(), cfg)

    def test_the_bot_exits_cleanly_without_a_token(self) -> None:
        """No token is "stay off", not a crash a service manager would loop on."""
        from unittest import mock

        from mylo.bot import __main__ as entry

        with mock.patch.object(entry, "load_config", lambda: MyloConfig(token="", error_channel_id=None)):
            with self.assertRaises(SystemExit) as exited:
                entry.main()
        self.assertEqual(exited.exception.code, 0)

    def test_require_bot_returns_self_when_complete(self) -> None:
        cfg = MyloConfig(token="tok", error_channel_id=1)
        self.assertIs(cfg.require_bot(), cfg)


class EnvFileParserTests(unittest.TestCase):
    def test_parses_pairs_ignoring_comments_and_quotes(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env-mylo"
            path.write_text(
                "# a comment\n"
                'DISCORD_API_KEY="abc"\n'
                "\n"
                "ERROR_CHANNEL = 55 \n"
                "MALFORMED_NO_EQUALS\n",
                encoding="utf-8",
            )
            values = _load_env_file(path)
        self.assertEqual(values["DISCORD_API_KEY"], "abc")
        self.assertEqual(values["ERROR_CHANNEL"], "55")
        self.assertNotIn("MALFORMED_NO_EQUALS", values)

    def test_missing_file_yields_empty_mapping(self) -> None:
        from pathlib import Path

        self.assertEqual(_load_env_file(Path("/no/such/.env-mylo")), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
