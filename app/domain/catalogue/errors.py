class CatalogueParentArchivedError(Exception):
    """Something new can't join a course or topic that's archived."""


class CourseAlreadyArchivedError(Exception):
    pass


class CurriculumVersionAlreadyArchivedError(Exception):
    pass


class TopicAlreadyArchivedError(Exception):
    pass


class LearningOutcomeAlreadyArchivedError(Exception):
    pass


class ReferenceMaterialAlreadyArchivedError(Exception):
    pass
