from enum import StrEnum


class Role(StrEnum):
    OPERATOR = 'operator'
    REVIEWER = 'reviewer'
    VIEWER = 'viewer'


class Status(StrEnum):
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETE = 'complete'
    FAILED = 'failed'


class LotStatus(StrEnum):
    ACTIVE = 'active'
    SEALED = 'sealed'


class ProductionKind(StrEnum):
    SEMI = 'semi'
    DISH = 'dish'


class ProductionStatus(StrEnum):
    PRODUCED = 'produced'
    SERVED = 'served'
