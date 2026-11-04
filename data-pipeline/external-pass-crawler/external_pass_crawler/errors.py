class CrawlerError(Exception):
    code = "CRAWLER_ERROR"


class ContractError(CrawlerError):
    code = "BE_CONTRACT_MISMATCH"


class AccessRestricted(CrawlerError):
    code = "ACCESS_RESTRICTED"


class FetchError(CrawlerError):
    code = "FETCH_FAILED"


class ParseError(CrawlerError):
    code = "HTML_LAYOUT_CHANGED"


class IdentityConflict(CrawlerError):
    code = "SOURCE_COMPANY_CONFLICT"


class StaleTask(CrawlerError):
    code = "STALE_TASK"
