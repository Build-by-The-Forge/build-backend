import pytest

from app.domain.catalogue.errors import TopicAlreadyArchivedError
from app.domain.catalogue.topic import Topic
from app.domain.catalogue.value_objects import (
    CourseId,
    TopicDescription,
    TopicId,
    TopicLevel,
    TopicSlug,
    TopicTitle,
)


def test_topic_create_is_active() -> None:
    topic = Topic.create(
        course_id=CourseId(""),
        title=TopicTitle("Linear Regression"),
        slug=TopicSlug("linear-regression"),
        description=TopicDescription("Introduction to linear regression."),
        level=TopicLevel.PRIMARY,
    )

    assert topic.is_active is True
    assert topic.title.value == "Linear Regression"
    assert len(topic.pull_events()) == 1


def test_topic_archive_and_publish() -> None:
    topic = Topic.create(
        course_id=CourseId(""),
        title=TopicTitle("Linear Regression"),
        slug=TopicSlug("linear-regression"),
        description=TopicDescription("Introduction to linear regression."),
    )
    topic.pull_events()

    topic.archive()
    assert topic.status.value == "archived"
    assert topic.pull_events()[0].event_type == "topic.archived"

    topic.publish()
    assert topic.status.value == "active"
    assert topic.pull_events()[0].event_type == "topic.published"


def test_topic_archive_twice_raises() -> None:
    topic = Topic.create(
        course_id=CourseId(""),
        title=TopicTitle("Linear Regression"),
        slug=TopicSlug("linear-regression"),
        description=TopicDescription("Introduction to linear regression."),
    )
    topic.pull_events()

    topic.archive()

    with pytest.raises(TopicAlreadyArchivedError):
        topic.archive()


def test_topic_add_learning_outcome_emits_event() -> None:
    topic = Topic.create(
        course_id=CourseId(""),
        title=TopicTitle("Linear Regression"),
        slug=TopicSlug("linear-regression"),
        description=TopicDescription("Introduction to linear regression."),
    )
    topic.pull_events()

    from app.domain.catalogue.learning_outcome import LearningOutcome
    from app.domain.catalogue.value_objects import LearningOutcomeDescription, LearningOutcomeSequence

    lo = LearningOutcome.create(
        topic_id=topic.id,
        sequence=LearningOutcomeSequence(1),
        description=LearningOutcomeDescription("Understand the regression line."),
    )

    topic.add_learning_outcome(lo)
    events = topic.pull_events()

    assert events[0].event_type == "topic.learning_outcome_added"
    assert events[0].payload["learning_outcome_id"] == lo.id.value
