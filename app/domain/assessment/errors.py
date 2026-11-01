from app.domain.client_safe import ClientMessage


class QuestionAlreadyArchivedError(Exception):
    pass


class AttemptExpiredError(Exception):
    pass


class AttemptAlreadySubmittedError(Exception):
    pass


class AttemptLimitReachedError(Exception):
    pass


class AttemptPolicyLockedError(ClientMessage, Exception):
    pass


class ResultNotReleasedError(Exception):
    pass


class QuestionOptionAlreadyArchivedError(Exception):
    pass


class AssessmentAlreadyArchivedError(Exception):
    pass
