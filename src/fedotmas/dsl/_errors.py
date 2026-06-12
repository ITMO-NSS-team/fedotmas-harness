"""Internal: the error contract — every failure stage speaks (path, message, expected)."""

from __future__ import annotations

from pydantic import BaseModel, ValidationError


class Issue(BaseModel):
    """One failure: a dotted path into the document, what went wrong, what was expected."""

    path: str
    message: str
    expected: str | None = None


class ManifestError(Exception):
    """The single failure mode of parse, merge, and compile: the full list of issues."""

    def __init__(self, issues: list[Issue]) -> None:
        self.issues = issues
        super().__init__("\n".join(_render(i) for i in issues))


def _render(issue: Issue) -> str:
    tail = f" (expected {issue.expected})" if issue.expected else ""
    return f"{issue.path}: {issue.message}{tail}"


def _from_validation_error(err: ValidationError) -> ManifestError:
    # Union tags are "~"-marked in _manifest; dropping them leaves the document path.
    issues = [
        Issue(
            path=".".join(
                str(part) for part in e["loc"] if not str(part).startswith("~")
            )
            or "<document>",
            message=e["msg"],
            expected=e["type"],
        )
        for e in err.errors()
    ]
    return ManifestError(issues)
