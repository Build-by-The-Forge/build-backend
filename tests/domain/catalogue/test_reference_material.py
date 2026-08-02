import pytest

from app.domain.catalogue.errors import ReferenceMaterialAlreadyArchivedError
from app.domain.catalogue.reference_material import ReferenceMaterial
from app.domain.catalogue.value_objects import (
    CourseId,
    ReferenceMaterialTitle,
    ReferenceMaterialType,
    ReferenceMaterialUrl,
)


def test_reference_material_create_is_active() -> None:
    reference = ReferenceMaterial.create(
        course_id=CourseId(""),
        title=ReferenceMaterialTitle("Pattern Recognition and Machine Learning"),
        material_type=ReferenceMaterialType.BOOK,
        url=ReferenceMaterialUrl("https://example.com/book"),
    )

    assert reference.is_active is True
    assert reference.title.value == "Pattern Recognition and Machine Learning"
    assert len(reference.pull_events()) == 1


def test_reference_material_archive_and_publish() -> None:
    reference = ReferenceMaterial.create(
        course_id=CourseId(""),
        title=ReferenceMaterialTitle("Pattern Recognition and Machine Learning"),
        material_type=ReferenceMaterialType.BOOK,
        url=ReferenceMaterialUrl("https://example.com/book"),
    )
    reference.pull_events()

    reference.archive()
    assert reference.status.value == "archived"
    assert reference.pull_events()[0].event_type == "reference_material.archived"

    reference.publish()
    assert reference.status.value == "active"
    assert reference.pull_events()[0].event_type == "reference_material.published"


def test_reference_material_archive_twice_raises() -> None:
    reference = ReferenceMaterial.create(
        course_id=CourseId(""),
        title=ReferenceMaterialTitle("Pattern Recognition and Machine Learning"),
        material_type=ReferenceMaterialType.BOOK,
        url=ReferenceMaterialUrl("https://example.com/book"),
    )
    reference.pull_events()

    reference.archive()

    with pytest.raises(ReferenceMaterialAlreadyArchivedError):
        reference.archive()
