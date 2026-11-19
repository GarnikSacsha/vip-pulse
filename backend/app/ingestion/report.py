"""Import report: what was read, what was kept, and why anything was dropped."""

from enum import StrEnum

from pydantic import BaseModel, Field


class IssueLevel(StrEnum):
    WARNING = "warning"  # value was normalized or a duplicate was dropped; data kept
    ERROR = "error"  # record could not be used and was skipped


class IngestIssue(BaseModel):
    level: IssueLevel
    source: str  # "players" | "dialogs"
    ref: str  # row number or record id, so a human can find it in the file
    reason: str


class ImportReport(BaseModel):
    adapter: str
    players_read: int = 0
    players_kept: int = 0
    conversations_read: int = 0
    conversations_kept: int = 0
    messages_kept: int = 0
    issues: list[IngestIssue] = Field(default_factory=list)

    @property
    def errors(self) -> list[IngestIssue]:
        return [i for i in self.issues if i.level == IssueLevel.ERROR]

    @property
    def warnings(self) -> list[IngestIssue]:
        return [i for i in self.issues if i.level == IssueLevel.WARNING]
