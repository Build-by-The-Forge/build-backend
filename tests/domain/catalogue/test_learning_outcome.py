import pytest

from app.domain.catalogue.errors import LearningOutcomeAlreadyArchivedError
from app.domain.catalogue.learning_outcome import LearningOutcome
from app.domain.catalogue.value_objects import (
    LearningOutcomeDescription,
    LearningOutcomeSequence,
    TopicId,
)


def test_learning_outcome_create_is_active() -> None:
    lo = LearningOutcome.create(
        topic_id=TopicId(""),
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Explain gradient descent."),
    )

    assert lo.is_active is True
    assert lo.description.value == "Explain gradient descent."
    assert len(lo.pull_events()) == 1


def test_learning_outcome_archive_and_publish() -> None:
    lo = LearningOutcome.create(
        topic_id=TopicId(""),
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Explain gradient descent."),
    )
    lo.pull_events()

    lo.archive()
    assert lo.status.value == "archived"
    assert lo.pull_events()[0].event_type == "learning_outcome.archived"

    lo.publish()
    assert lo.status.value == "active"
    assert lo.pull_events()[0].event_type == "learning_outcome.published"


def test_learning_outcome_archive_twice_raises() -> None:
    lo = LearningOutcome.create(
        topic_id=TopicId(""),
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Explain gradient descent."),
    )
    lo.pull_events()

    lo.archive()

    with pytest.raises(LearningOutcomeAlreadyArchivedError):
        lo.archive()


def test_learning_outcome_update_description_emits_event() -> None:
    lo = LearningOutcome.create(
        topic_id=TopicId("topic-1"),
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Explain gradient descent."),
    )
    lo.pull_events()

    lo.update_description(LearningOutcomeDescription("Explain how gradient descent converges."))

    assert lo.description.value == "Explain how gradient descent converges."
    assert lo.pull_events()[0].event_type == "learning_outcome.updated"
