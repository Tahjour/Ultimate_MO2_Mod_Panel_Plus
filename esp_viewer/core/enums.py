from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

class ConflictStatus(Enum):
    NOT_DEFINED = "ctNotDefined"
    IDENTICAL_TO_MASTER = "ctIdenticalToMaster"
    ONLY_ONE = "ctOnlyOne"
    HIDDEN_BY_MOD_GROUP = "ctHiddenByModGroup"
    MASTER = "ctMaster"
    CONFLICT_BENIGN = "ctConflictBenign"
    OVERRIDE = "ctOverride"
    IDENTICAL_TO_MASTER_WINS_CONFLICT = "ctIdenticalToMasterWinsConflict"
    CONFLICT_LOSES = "ctConflictLoses"
    CONFLICT_CRITICAL = "ctConflictCritical"

def is_conflict_status(status: ConflictStatus) -> bool:
    return status in {
        ConflictStatus.CONFLICT_BENIGN,
        ConflictStatus.OVERRIDE,
        ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT,
        ConflictStatus.CONFLICT_LOSES,
        ConflictStatus.CONFLICT_CRITICAL,
    }

def is_winning_status(status: ConflictStatus) -> bool:
    return status in {
        ConflictStatus.CONFLICT_BENIGN,
        ConflictStatus.OVERRIDE,
        ConflictStatus.IDENTICAL_TO_MASTER_WINS_CONFLICT,
        ConflictStatus.CONFLICT_CRITICAL,
    }

def is_losing_status(status: ConflictStatus) -> bool:
    return status == ConflictStatus.CONFLICT_LOSES

@dataclass(frozen=True)
class RecordConflict:
    status: ConflictStatus
    field_statuses: Dict[Tuple[str, int], ConflictStatus]
    winning_plugin: Optional[str]
    chain_length: int
    is_deleted: bool
    is_injected: bool
    chain_plugins: Tuple[str, ...]
