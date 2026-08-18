# Academic Catalogue Specification

This document defines the academic data model for BUILD v0.4.0 and beyond.
It is designed to support canonical curriculum data, shared course architecture, elective tracking, prerequisites, topic-based learning, and future AI-driven features.

## 1. Guiding principles

- Model the university curriculum as a real academic catalogue, not just application entities.
- Keep the canonical source of truth aligned with NUC CCMAS and FUTA curriculum structure.
- Support curriculum versioning so students keep the correct syllabus for their year of admission.
- Separate course ownership from programme consumption.
- Support shared courses, electives, prerequisites, and topic-based materials.
- Make the graph explicit for AI and analytics.

## 2. Core entities

### 2.1 University

The highest-level tenant is a University.
This is the root of the academic platform and may support multiple institutions in the future.

Fields:
- `id`
- `name`
- `slug`
- `status`
- `created_at`
- `updated_at`

### 2.2 Faculty

A faculty owns departments.

Fields:
- `id`
- `tenant_id`
- `name`
- `slug`
- `status`
- `created_at`
- `updated_at`

### 2.3 Department

A department owns courses and belongs to a faculty.

Fields:
- `id`
- `tenant_id`
- `faculty_id`
- `name`
- `slug`
- `code`
- `status`
- `created_at`
- `updated_at`

### 2.4 Programme

A programme is a degree track consumed by students.
It is tied to a faculty, department, and curriculum versioning.

Fields:
- `id`
- `tenant_id`
- `faculty_id`
- `department_id`
- `name`
- `slug`
- `code`
- `duration_years`
- `status`
- `created_at`
- `updated_at`

## 3. Curriculum versioning

### 3.1 CurriculumVersion

A curriculum version captures a programme-specific syllabus for a defined period.

Fields:
- `id`
- `programme_id`
- `name`
- `version`
- `effective_session_id`
- `expires_session_id`
- `status`
- `created_at`
- `updated_at`

Rules:
- A programme can have multiple curriculum versions.
- Students are assigned a curriculum version on admission.
- Future changes create a new version instead of mutating the old one.

## 4. Academic catalogue entities

### 4.1 Course

A course is a reusable academic unit.
Courses are owned by a department and shared across programmes.

Fields:
- `id`
- `tenant_id`
- `department_id` (owner)
- `code`
- `title`
- `credits`
- `contact_hours`
- `course_type` (core, elective, required_elective, restricted_elective)
- `status`
- `created_at`
- `updated_at`

### 4.2 ProgrammeCourse

A join table representing which curriculum version consumes which courses.

Fields:
- `id`
- `curriculum_version_id`
- `course_id`
- `sequence`
- `year_level`
- `semester_number`
- `course_category` (core, elective, required_elective, restricted_elective)
- `status`
- `created_at`
- `updated_at`

### 4.3 CoursePrerequisite

A self-referential relationship between courses.

Fields:
- `id`
- `course_id`
- `prerequisite_course_id`
- `required_type` (prerequisite, co_requisite)
- `status`
- `created_at`
- `updated_at`

### 4.4 LearningOutcome

Learning outcomes are course-specific goals.

Fields:
- `id`
- `course_id`
- `sequence`
- `description`
- `status`
- `created_at`
- `updated_at`

## 5. Topic-based learning model

### 5.1 Topic

Topics belong to courses and are the unit for questions and materials.

Fields:
- `id`
- `course_id`
- `title`
- `description`
- `level`
- `status`
- `created_at`
- `updated_at`

### 5.2 Subtopic

Subtopics are nested under topics for finer structure.

Fields:
- `id`
- `topic_id`
- `title`
- `description`
- `status`
- `created_at`
- `updated_at`

### 5.3 CourseMaterial

Materials are attached to topics or subtopics, not directly to courses.

Fields:
- `id`
- `topic_id`
- `material_type` (slide, video, pdf, flashcard, exercise)
- `title`
- `url`
- `metadata`
- `status`
- `created_at`
- `updated_at`

### 5.4 QuestionBank

A question bank is topic-first.
Questions belong to topics or subtopics and are used for CBT, practice, and analytics.

Fields:
- `id`
- `topic_id`
- `question_text`
- `question_type` (mcq, written, true_false)
- `difficulty`
- `status`
- `created_at`
- `updated_at`

### 5.5 QuestionOption

Options for MCQ-style questions.

Fields:
- `id`
- `question_id`
- `option_text`
- `is_correct`
- `explanation`
- `status`
- `created_at`
- `updated_at`

## 6. Feature relationships

### 6.1 Course ownership vs consumption

- `Department owns Course`
- `Programme consumes Course` through `ProgrammeCourse`
- Shared courses are represented once and reused by many programmes.

### 6.2 Elective modelling

Elective classification is stored on the curriculum/course relationship, not as a free-text field.
This supports:
- `core`
- `elective`
- `required_elective`
- `restricted_elective`

### 6.3 Curriculum versioning and admission

Students should be assigned a curriculum version on admission.
That mapping is the key to versioned course delivery.

### 6.4 AI-friendly graph

This structure supports queries such as:
- all prerequisites for CSC401
- topics needed for a given course
- questions aligned to topic learning outcomes
- shared courses across programmes

## 7. Next implementation scope for v0.4.0

1. Add the `Academic Catalogue` bounded context.
2. Implement the entities above in domain and infrastructure layers.
3. Create Alembic migrations for catalogue tables.
4. Add seed scaffolding for sample curriculum data.
5. Keep identity and tenant core stable while the catalogue is built.

## 8. Notes

- AI should remain a separate service layer on top of this graph.
- The backend should own business rules; intelligence should be applied by the AI service.
- This document is the source of truth for the next structural release.
