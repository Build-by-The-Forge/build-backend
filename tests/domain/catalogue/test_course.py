import pytest

from app.domain.catalogue.course import Course
from app.domain.catalogue.errors import CourseAlreadyArchivedError
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseTitle,
    DepartmentId,
    TopicSlug,
    TopicTitle,
)


def test_course_create_is_active_by_default() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )

    assert course.is_active is True
    assert course.status.value == "active"
    assert course.created_at <= course.updated_at
    assert len(course.pull_events()) == 1


def test_course_archive_and_publish() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )
    course.pull_events()

    course.archive()
    assert course.status.value == "archived"
    assert course.is_active is False
    assert course.pull_events()[0].event_type == "course.archived"

    course.publish()
    assert course.status.value == "active"
    assert course.is_active is True
    assert course.pull_events()[0].event_type == "course.published"


def test_course_archive_twice_raises() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )
    course.pull_events()

    course.archive()

    with pytest.raises(CourseAlreadyArchivedError):
        course.archive()


def test_course_update_details_emits_event() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )
    course.pull_events()

    course.update_details(CourseTitle("Updated Course Title"), "Updated description")

    assert course.title.value == "Updated Course Title"
    assert course.description == "Updated description"
    assert course.pull_events()[0].event_type == "course.updated"


def test_course_add_topic_references_event() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )
    course.pull_events()

    from app.domain.catalogue.topic import Topic
    from app.domain.catalogue.value_objects import TopicSlug, TopicTitle

    topic = Topic.create(
        course_id=course.id,
        title=TopicTitle("Data Structures"),
        slug=TopicSlug("data-structures"),
    )

    course.add_topic(topic)
    events = course.pull_events()
    assert events[0].event_type == "course.topic_added"
    assert events[0].payload["topic_id"] == topic.id.value


def test_course_rejects_topic_from_another_course() -> None:
    course = Course.create(
        department_id=DepartmentId(""),
        code=CourseCode("CSC101"),
        title=CourseTitle("Introduction to Computer Science"),
        slug=CourseSlug("introduction-to-computer-science"),
        credit_units=CourseCreditUnits(3),
        level=CourseLevel(100),
        semester=CourseSemester(1),
    )
    from app.domain.catalogue.topic import Topic

    topic = Topic.create(
        course_id=CourseId("other-course"),
        title=TopicTitle("Unused Topic"),
        slug=TopicSlug("unused-topic"),
    )

    with pytest.raises(ValueError, match="course_id"):
        course.add_topic(topic)
