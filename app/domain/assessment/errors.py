class QuestionAlreadyArchivedError(Exception):
    pass


class AttemptExpiredError(Exception):
    pass


class AttemptAlreadySubmittedError(Exception):
    pass


class AttemptLimitReachedError(Exception):
    pass


class AttemptPolicyLockedError(Exception):
    pass


class QuestionOptionAlreadyArchivedError(Exception):
    pass


class AssessmentAlreadyArchivedError(Exception):
    pass
