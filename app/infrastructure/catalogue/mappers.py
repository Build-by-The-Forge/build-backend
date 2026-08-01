from app.domain.catalogue.course import Course
from app.domain.catalogue.value_objects import (
    CourseCode,
    CourseCreditUnits,
    CourseId,
    CourseLevel,
    CourseSemester,
    CourseSlug,
    CourseStatus,
    CourseTitle,
    DepartmentId,
)
from app.infrastructure.db.models.catalogue import CourseModel


def course_to_model(course: Course, model: CourseModel | None = None) -> CourseModel:
    if model is None:
        model = CourseModel(id=course.id.value)

    model.department_id = course.department_id.value
    model.code = course.code.value
    model.title = course.title.value
    model.slug = course.slug.value
    model.credit_units = course.credit_units.value
    model.level = course.level.value
    model.semester = course.semester.value
    model.status = course.status.value
    model.description = course.description
    model.created_at = course.created_at
    model.updated_at = course.updated_at
    return model


def course_to_domain(model: CourseModel) -> Course:
    return Course(
        id=CourseId(model.id),
        department_id=DepartmentId(model.department_id),
        code=CourseCode(model.code),
        title=CourseTitle(model.title),
        slug=CourseSlug(model.slug),
        credit_units=CourseCreditUnits(model.credit_units),
        level=CourseLevel(model.level),
        semester=CourseSemester(model.semester),
        status=CourseStatus(model.status),
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
