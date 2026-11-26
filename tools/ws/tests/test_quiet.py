import unittest

import harness  # noqa: F401  (sets WS_HOME, sys.path)
from workstead.fakegh import FakeGitHub, World
from workstead.protocol import quiet


class QuietMentions(unittest.TestCase):
    """The queue never @mentions anyone: GitHub would email them for every post."""

    def test_mentions_become_code_spans(self):
        self.assertEqual(quiet("Released by @bob. #3 is open"), "Released by `@bob`. #3 is open")
        self.assertEqual(quiet("@alice-x please fix"), "`@alice-x` please fix")
        self.assertEqual(quiet("Approvals: @a, @b"), "Approvals: `@a`, `@b`")
        self.assertEqual(quiet("team @org/team-a."), "team `@org/team-a`.")

    def test_leaves_code_markers_and_addresses_alone(self):
        for text in ["mail a@b.com", "already `@bob`", "```\n@decorator\ndef f(): ...\n```",
                     "<!-- ws:expired @bob -->", "git merge @{u}", "", None]:
            self.assertEqual(quiet(text), text)

    def test_every_write_is_quiet(self):
        gh = FakeGitHub(World(), "repo-bot")
        issue = gh.create_issue("t", "for @bob", [])
        self.assertEqual(gh.get_issue(issue["number"])["body"], "for `@bob`")
        gh.edit_issue(issue["number"], body="now @carol")
        self.assertEqual(gh.get_issue(issue["number"])["body"], "now `@carol`")
        com = gh.create_comment(issue["number"], "@dave hi <!-- ws:expired @dave -->")
        self.assertEqual(com["body"], "`@dave` hi <!-- ws:expired @dave -->")
        self.assertEqual(gh.edit_comment(com["id"], "@erin")["body"], "`@erin`")


if __name__ == "__main__":
    unittest.main()
