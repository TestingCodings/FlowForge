"""The frontend and backend agree on the capability vocabulary.

`/auth/me/` serves the caller's resolved capabilities and the frontend gates
controls on them, so there is one authority on *who holds what*. But the names
themselves still exist twice: `CAPABILITIES` in models.py, and the hand-written
`Capability` union in frontend/src/hooks/useCapabilities.ts.

Drift there fails silently in both directions. A name only the frontend knows
gates a control that can never render, because the server will never issue it.
A name only the backend knows is a capability nothing in the UI can gate. Both
look like ordinary code and neither raises anything at runtime — the page just
renders the wrong set of controls.

The old frontend test carried "user.manage", which has never been a backend
capability; the split is `user.create` and `user.assign_roles`. Nothing caught
it because nothing compared the two lists.

This lives on the Python side because it has to read a file from each, and
Python does that without putting Node types into the frontend's build.
"""
import re
from pathlib import Path

import pytest

from apps.accounts.models import CAPABILITIES

REPO_ROOT = Path(__file__).resolve().parents[3]
HOOK = REPO_ROOT / "frontend" / "src" / "hooks" / "useCapabilities.ts"


def frontend_capabilities() -> list[str]:
    source = HOOK.read_text(encoding="utf-8")
    block = re.search(r"export type Capability =(.*?);", source, re.S)
    assert block, f"Capability union not found in {HOOK}"
    # Entries carry trailing // comments explaining what they mean.
    without_comments = re.sub(r"//[^\n]*", "", block.group(1))
    return re.findall(r'"([^"]+)"', without_comments)


@pytest.mark.skipif(not HOOK.exists(), reason="frontend not present in this checkout")
class TestVocabularyMatches:
    def test_the_union_parses_to_something(self):
        """Guards the regex above: if it silently matched nothing, every
        assertion below would pass for the wrong reason."""
        assert len(frontend_capabilities()) > 15

    def test_the_frontend_invents_nothing(self):
        invented = sorted(set(frontend_capabilities()) - set(CAPABILITIES))
        assert invented == [], (
            f"{invented} appear in the Capability union but not in CAPABILITIES. "
            "A control gated on one of these can never render."
        )

    def test_the_frontend_omits_nothing(self):
        missing = sorted(set(CAPABILITIES) - set(frontend_capabilities()))
        assert missing == [], (
            f"{missing} are defined server-side but absent from the Capability "
            "union, so the UI cannot gate on them."
        )

    def test_no_duplicates_in_the_union(self):
        listed = frontend_capabilities()
        assert len(listed) == len(set(listed))
