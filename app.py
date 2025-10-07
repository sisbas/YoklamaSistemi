"""Flask application providing the attendance API and web interface.

This module wires together the configuration, database models and route
definitions. It exposes both a JSON API for programmatic use and a simple
HTML/JavaScript front‑end for human users.

Endpoints:

* ``GET /api/classes`` – return a list of available classes.
* ``GET /api/students?classroom_id=`` – return students in the specified class.
* ``GET /api/schedule?classroom_id=...&date=YYYY-MM-DD`` – return the number of
  lessons scheduled for the given class on the given date (based on day
  of week).
* ``GET /api/attendance?classroom_id=...&date=YYYY-MM-DD`` – return attendance
  records for the given class and date.
* ``POST /api/attendance/bulk`` – add attendance records in bulk. If records
  already exist for the given class/date/lesson number combination a 409
  Conflict response is returned.
* ``PUT /api/attendance/bulk`` – update or insert attendance records in bulk.

The front‑end is served from ``/`` and uses JavaScript to call these APIs.

"""

from __future__ import annotations

import os
from datetime import datetime, date

from flask import Flask, jsonify, request, render_template
from werkzeug.exceptions import Conflict, NotFound, BadRequest

from sqlalchemy.exc import OperationalError, SQLAlchemyError

from config import Config
from models import db, ClassRoom, Student, LessonSchedule, Attendance


def create_app() -> Flask:
    """Application factory used by both the server and tests.

    Using an application factory allows configuration to be customised for
    different environments (development, testing, production). Here the
    default configuration comes from :class:`config.Config` and tables are
    created automatically on the first request if they do not exist.
    """
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)
    db.init_app(app)

    @app.before_first_request
    def create_tables() -> None:
        """Ensure all tables exist before handling the first request."""
        try:
            db.create_all()
        except SQLAlchemyError as exc:
            # When the database is temporarily unavailable (e.g. during Heroku
            # maintenance) the application should continue starting up instead
            # of crashing. The health check endpoint will surface the failure.
            app.logger.warning("Database unavailable during table creation: %s", exc)

    @app.route('/')
    def index() -> str:
        """Serve the single page front‑end."""
        return render_template('index.html')

    @app.route('/health')
    def healthcheck():
        """Lightweight endpoint used by Heroku router health checks."""
        return jsonify({'status': 'ok'}), 200

    # API: list of classes
    @app.route('/api/classes', methods=['GET'])
    def api_get_classes():
        classes = ClassRoom.query.order_by(ClassRoom.name).all()
        return jsonify([{'id': c.id, 'name': c.name} for c in classes])

    # API: students for a class
    @app.route('/api/students', methods=['GET'])
    def api_get_students():
        classroom_id = request.args.get('classroom_id', type=int)
        if not classroom_id:
            raise BadRequest('Missing classroom_id parameter')
        cls = ClassRoom.query.get_or_404(classroom_id)
        students = Student.query.filter_by(classroom_id=classroom_id).order_by(Student.name).all()
        return jsonify([{'id': s.id, 'name': s.name} for s in students])

    # API: get schedule (number of lessons) for a class on a given date
    @app.route('/api/schedule', methods=['GET'])
    def api_get_schedule():
        classroom_id = request.args.get('classroom_id', type=int)
        if not classroom_id:
            raise BadRequest('Missing classroom_id parameter')
        # Accept either a date or a day-of-week integer
        date_str = request.args.get('date')
        day_param = request.args.get('day', type=int)
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                raise BadRequest('Invalid date format, must be YYYY-MM-DD')
            day_of_week = dt.weekday()  # Monday=0
        elif day_param is not None:
            if not (0 <= day_param <= 6):
                raise BadRequest('day must be between 0 (Mon) and 6 (Sun)')
            day_of_week = day_param
        else:
            # Default to today
            day_of_week = date.today().weekday()

        sched = LessonSchedule.query.filter_by(classroom_id=classroom_id,
                                               day_of_week=day_of_week).first()
        lessons = sched.lessons_count if sched else 0
        return jsonify({'classroom_id': classroom_id, 'day_of_week': day_of_week, 'lessons': lessons})

    # API: get attendance for a class on a given date (optionally for a single lesson)
    @app.route('/api/attendance', methods=['GET'])
    def api_get_attendance():
        classroom_id = request.args.get('classroom_id', type=int)
        date_str = request.args.get('date')
        lesson_no = request.args.get('lesson_no', type=int)
        if not classroom_id or not date_str:
            raise BadRequest('Missing classroom_id or date parameter')
        try:
            attend_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            raise BadRequest('Invalid date format, must be YYYY-MM-DD')

        query = Attendance.query.filter_by(classroom_id=classroom_id, date=attend_date)
        if lesson_no:
            query = query.filter_by(lesson_no=lesson_no)
        records = query.all()
        result = []
        for rec in records:
            result.append({
                'student_id': rec.student_id,
                'student_name': rec.student.name,
                'lesson_no': rec.lesson_no,
                'status': rec.status,
                'note': rec.note
            })
        return jsonify(result)

    # API: bulk insert attendance
    @app.route('/api/attendance/bulk', methods=['POST'])
    def api_post_attendance_bulk():
        data = request.get_json(silent=True)
        if not data:
            raise BadRequest('Missing JSON payload')
        classroom_id = data.get('classroom_id')
        date_str = data.get('date')
        lesson_no = data.get('lesson_no')
        records = data.get('records', [])
        if not classroom_id or not date_str or not lesson_no:
            raise BadRequest('classroom_id, date and lesson_no are required')
        try:
            attend_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            raise BadRequest('Invalid date format, must be YYYY-MM-DD')
        # Check if attendance already exists for this class/date/lesson_no
        existing = Attendance.query.filter_by(classroom_id=classroom_id,
                                              date=attend_date,
                                              lesson_no=lesson_no).first()
        if existing:
            # Conflict: records already present
            raise Conflict('Attendance already exists for this class/date/lesson number')

        # Insert each record
        for rec in records:
            student_id = rec.get('student_id')
            status = rec.get('status')
            note = rec.get('note')
            if not student_id or not status:
                continue  # skip invalid entries
            attendance = Attendance(
                classroom_id=classroom_id,
                student_id=student_id,
                date=attend_date,
                lesson_no=lesson_no,
                status=status,
                note=note
            )
            db.session.add(attendance)
        db.session.commit()
        return jsonify({'message': 'Attendance created successfully'}), 201

    # API: bulk update/create attendance
    @app.route('/api/attendance/bulk', methods=['PUT'])
    def api_put_attendance_bulk():
        data = request.get_json(silent=True)
        if not data:
            raise BadRequest('Missing JSON payload')
        classroom_id = data.get('classroom_id')
        date_str = data.get('date')
        lesson_no = data.get('lesson_no')
        records = data.get('records', [])
        if not classroom_id or not date_str or not lesson_no:
            raise BadRequest('classroom_id, date and lesson_no are required')
        try:
            attend_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            raise BadRequest('Invalid date format, must be YYYY-MM-DD')

        for rec in records:
            student_id = rec.get('student_id')
            status = rec.get('status')
            note = rec.get('note')
            if not student_id or not status:
                continue
            attendance = Attendance.query.filter_by(
                classroom_id=classroom_id,
                student_id=student_id,
                date=attend_date,
                lesson_no=lesson_no
            ).first()
            if attendance:
                # Update existing record
                attendance.status = status
                attendance.note = note
            else:
                # Create new record
                attendance = Attendance(
                    classroom_id=classroom_id,
                    student_id=student_id,
                    date=attend_date,
                    lesson_no=lesson_no,
                    status=status,
                    note=note
                )
                db.session.add(attendance)
        db.session.commit()
        return jsonify({'message': 'Attendance updated successfully'})

    # Generic error handlers to return JSON responses for API errors
    @app.errorhandler(BadRequest)
    @app.errorhandler(NotFound)
    @app.errorhandler(Conflict)
    def handle_error(error):
        response = jsonify({'error': error.description})
        response.status_code = error.code if isinstance(error, (BadRequest, NotFound, Conflict)) else 500
        return response

    def handle_db_error(error):
        app.logger.error("Database operation failed: %s", error)
        return jsonify({'error': 'Database temporarily unavailable'}), 503

    app.register_error_handler(OperationalError, handle_db_error)
    app.register_error_handler(SQLAlchemyError, handle_db_error)

    return app


app = create_app()

if __name__ == '__main__':
    # When run directly, start the development server. Gunicorn will be used
    # in production as per the Procfile recommendation:contentReference[oaicite:5]{index=5}.
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
