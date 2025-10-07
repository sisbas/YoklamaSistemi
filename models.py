"""Database models for the attendance tracking system.

This module defines all persistent entities used by the application. SQLAlchemy
is used as the ORM layer. The models include:

* :class:`ClassRoom` – represents a named classroom or cohort.
* :class:`Student` – represents a student belonging to a classroom.
* :class:`LessonSchedule` – represents the number of lessons a classroom has
  on a given day of the week.
* :class:`Attendance` – stores attendance records for students. Each record
  captures the class, student, date, lesson number, status and an optional
  note. A unique constraint across ``classroom_id``, ``student_id``, ``date``
  and ``lesson_no`` ensures that no duplicate attendance is recorded for
  a given student in a single lesson:contentReference[oaicite:2]{index=2}.
"""

from datetime import date
from flask_sqlalchemy import SQLAlchemy


# Instantiate the SQLAlchemy extension. This instance will be initialised
# with the Flask application in ``app.py`` via ``db.init_app(app)``.
db = SQLAlchemy()


class ClassRoom(db.Model):
    """Represents a classroom or cohort.

    Each classroom has a unique name. A classroom can have many students,
    schedules and attendance records associated with it. Relationships are
    defined with ``lazy=True`` so that related objects are loaded only when
    accessed.
    """

    __tablename__ = 'classroom'

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(50), unique=True, nullable=False)

    # Relationships
    students = db.relationship('Student', backref='classroom', lazy=True)
    schedules = db.relationship('LessonSchedule', backref='classroom', lazy=True)
    attendance_records = db.relationship('Attendance', backref='classroom', lazy=True)

    def __repr__(self) -> str:
        return f"<ClassRoom {self.name}>"


class Student(db.Model):
    """Represents a student.

    Students belong to exactly one classroom. The ``attendance_records``
    relationship provides access to all attendance entries for a student.
    """

    __tablename__ = 'student'

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(100), nullable=False)
    classroom_id: int = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)

    # Relationship to attendance
    attendance_records = db.relationship('Attendance', backref='student', lazy=True)

    def __repr__(self) -> str:
        return f"<Student {self.name}>"


class LessonSchedule(db.Model):
    """Represents the number of lessons a classroom has on a specific day.

    For example, a classroom might have 6 lessons on Monday and 4 lessons on
    Thursday. The combination of ``classroom_id`` and ``day_of_week`` is
    unique, enforced via a table-level :class:`~sqlalchemy.schema.UniqueConstraint`
    so that each classroom has at most one schedule entry per weekday
    :contentReference[oaicite:3]{index=3}.
    """

    __tablename__ = 'lesson_schedule'

    id: int = db.Column(db.Integer, primary_key=True)
    classroom_id: int = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    day_of_week: int = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    lessons_count: int = db.Column(db.Integer, nullable=False)

    __table_args__ = (db.UniqueConstraint('classroom_id', 'day_of_week', name='uix_schedule_class_day'),)

    def __repr__(self) -> str:
        return (f"<LessonSchedule class={self.classroom_id} day={self.day_of_week} "
                f"count={self.lessons_count}>")


class Attendance(db.Model):
    """Represents a single attendance record for a student.

    Each record captures the date, lesson number and status for a student in a
    given classroom. The unique constraint ensures a student cannot have
    multiple records for the same class/date/lesson combination:contentReference[oaicite:4]{index=4}.
    """

    __tablename__ = 'attendance'

    id: int = db.Column(db.Integer, primary_key=True)
    classroom_id: int = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    student_id: int = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date: date = db.Column(db.Date, nullable=False)
    lesson_no: int = db.Column(db.Integer, nullable=False)
    status: str = db.Column(db.String(20), nullable=False)  # geldi, gelmedi, mazeretli, izinli
    note: str = db.Column(db.String(255), nullable=True)

    __table_args__ = (db.UniqueConstraint('classroom_id', 'student_id', 'date', 'lesson_no',
                                          name='uix_attendance_unique'),)

    def __repr__(self) -> str:
        return (f"<Attendance class={self.classroom_id} student={self.student_id} "
                f"date={self.date} lesson={self.lesson_no} status={self.status}>")
