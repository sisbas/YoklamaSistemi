"""Seed the database with initial data.

This script populates the database with classrooms, students and lesson
schedules. It can be run locally before the first launch of the app. When
deployed on Heroku the database is initially empty; you can run this script
manually or adapt it to run as part of a release command.

Usage:
    python seed.py

"""

from datetime import datetime
from typing import Dict

from flask import current_app

from config import Config
from models import db, ClassRoom, Student, LessonSchedule
from flask import Flask


def create_app() -> Flask:
    """Create a standalone Flask application for seeding.

    We avoid importing the main app here to keep the seeding process
    independent of the API routes and front-end code.
    """
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    return app


def seed_data() -> None:
    """Insert initial classrooms, lesson schedules and sample students."""
    # Define class names according to the specification
    class_names = [
        'TYT Sınıfı',
        '9. Sınıf',
        '10. Sınıf',
        '11 Say 1', '11 Say 2', '11 Ea 1', '11 Ea 2',
        '12 Say 1', '12 Say 2', '12 Say 3',
        '12 Ea 1', '12 Ea 2', '12 Ea 3',
        'Mezun Ea 1', 'Mezun Ea 2', 'Mezun Ea 3',
        'Mezun Say 1', 'Mezun Say 2', 'Mezun Say 3'
    ]

    # Drop and recreate tables. In production you might prefer Alembic
    # migrations instead of dropping the entire database.
    db.drop_all()
    db.create_all()

    classrooms: Dict[str, ClassRoom] = {}
    # Create classrooms
    for name in class_names:
        cls = ClassRoom(name=name)
        db.session.add(cls)
        classrooms[name] = cls
    db.session.commit()

    # Define lesson schedule templates. Day numbers: 0=Mon .. 6=Sun.
    schedule_templates = {
        'Mezun': {0: 6, 1: 6, 3: 6, 4: 6},          # Monday, Tuesday, Thursday, Friday: 6 lessons
        '12': {1: 4, 3: 4, 5: 6, 6: 6},             # Tuesday, Thursday: 4; Saturday, Sunday: 6
        '10': {1: 4, 3: 4},                         # Tuesday, Thursday: 4
        '9': {5: 4, 6: 4},                          # Saturday, Sunday: 4
        'TYT': {5: 6, 6: 4}                         # Saturday: 6; Sunday: 4
    }

    # Apply schedules to classrooms based on their prefix
    for name, cls in classrooms.items():
        template = None
        if name.startswith('Mezun'):
            template = schedule_templates['Mezun']
        elif name.startswith('12'):
            template = schedule_templates['12']
        elif name.startswith('10'):
            template = schedule_templates['10']
        elif name.startswith('9'):
            template = schedule_templates['9']
        elif name.startswith('TYT'):
            template = schedule_templates['TYT']
        # 11th grade schedules are not specified; leave without entries.
        if template:
            for day, count in template.items():
                sched = LessonSchedule(classroom_id=cls.id, day_of_week=day, lessons_count=count)
                db.session.add(sched)
    db.session.commit()

    # Insert sample students: create a few placeholder students per class
    for cls in classrooms.values():
        for i in range(1, 6):  # 5 students per class
            student_name = f"Öğrenci {i}"
            student = Student(name=student_name, classroom_id=cls.id)
            db.session.add(student)
    db.session.commit()

    print('Database seeded successfully.')


def main() -> None:
    app = create_app()
    with app.app_context():
        seed_data()


if __name__ == '__main__':
    main()
