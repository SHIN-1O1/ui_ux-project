from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import or_
from datetime import datetime
from .models import db, User, Doctor, Patient, Department, Appointment, Treatment
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional

bp = Blueprint('main', __name__)

# -----------------------------------------------------------
# FORMS
# -----------------------------------------------------------
class LoginForm(FlaskForm):
    username = StringField('Username or Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')


class RegisterForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired()])
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Register')


class AddDoctorForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired()])
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    department = StringField('Department', validators=[Optional()])
    specialization = StringField('Specialization', validators=[Optional()])
    submit = SubmitField('Add Doctor')


class BookAppointmentForm(FlaskForm):
    start_datetime = StringField('Start', validators=[DataRequired()])
    end_datetime = StringField('End', validators=[DataRequired()])
    reason = TextAreaField('Reason', validators=[Optional()])
    submit = SubmitField('Book Appointment')


# -----------------------------------------------------------
# HELPERS
# -----------------------------------------------------------
def parse_datetime(dt_str):
    """Convert datetime-local string to datetime object."""
    try:
        if 'T' in dt_str:
            return datetime.fromisoformat(dt_str)
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(dt_str, fmt)
            except ValueError:
                continue
    except Exception:
        return None
    return None


# -----------------------------------------------------------
# ROUTES
# -----------------------------------------------------------

@bp.route('/')
def index():
    return render_template('index.html')


# ---------------- LOGIN / LOGOUT ----------------
@bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        password = form.password.data

        try:
            user = User.query.filter(
                or_(User.username == username, User.email == username)
            ).first()

            if not user or not user.check_password(password):
                flash('Invalid username or password.', 'danger')
                return render_template('login.html', form=form)

            # For doctors, ensure they are admin-created and approved
            if user.role == 'doctor':
                doc = getattr(user, 'doctor_profile', None)
                if doc is None:
                    flash('Doctor profile not found. Contact admin.', 'danger')
                    return render_template('login.html', form=form)
                if not getattr(doc, 'is_approved', False):
                    flash('Your account is pending admin approval.', 'warning')
                    return render_template('login.html', form=form)
                if not getattr(doc, 'is_active', True):
                    flash('Your account has been deactivated. Contact admin.', 'danger')
                    return render_template('login.html', form=form)

            login_user(user)
            flash('Logged in successfully.', 'success')

            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('main.admin_dashboard'))
            elif user.role == 'doctor':
                return redirect(url_for('main.doctor_dashboard'))
            elif user.role == 'patient':
                return redirect(url_for('main.patient_dashboard'))
            return redirect(url_for('main.index'))

        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash('An unexpected error occurred. Please try again.', 'danger')
            db.session.rollback()

    return render_template('login.html', form=form)


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('main.login'))


# ---------------- PATIENT REGISTRATION ----------------
@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Only patients can register themselves."""
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip()
        password = form.password.data
        full_name = form.full_name.data.strip()

        # Ensure unique username/email
        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.', 'danger')
            return render_template('register.html', form=form)

        try:
            user = User(username=username, email=email, full_name=full_name, role='patient')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            patient = Patient(user_id=user.id)
            db.session.add(patient)
            db.session.commit()

            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('main.login'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Registration error: {e}")
            flash('An error occurred while registering. Try again.', 'danger')

    return render_template('register.html', form=form)


# ---------------- ADMIN: ADD DOCTOR ----------------
@bp.route('/admin/add_doctor', methods=['GET', 'POST'])
@login_required
def add_doctor():
    """Only admins can add new doctors."""
    if current_user.role != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('main.index'))

    form = AddDoctorForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip()
        password = form.password.data
        full_name = form.full_name.data.strip()
        department_name = form.department.data.strip() if form.department.data else None
        specialization = form.specialization.data.strip() if form.specialization.data else None

        if User.query.filter((User.username == username) | (User.email == email)).first():
            flash('Username or email already exists.', 'danger')
            return render_template('add_doctor.html', form=form)

        try:
            # Create user
            user = User(username=username, email=email, full_name=full_name, role='doctor')
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            # Get or create department
            dept = None
            if department_name:
                dept = Department.query.filter_by(name=department_name).first()
                if not dept:
                    dept = Department(name=department_name)
                    db.session.add(dept)
                    db.session.flush()

            # Create doctor profile (admin-approved)
            doctor = Doctor(
                user_id=user.id,
                department_id=dept.id if dept else None,
                specialization=specialization,
                is_active=True,
                is_approved=True
            )
            db.session.add(doctor)
            db.session.commit()

            flash('Doctor added successfully.', 'success')
            return redirect(url_for('main.admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Add doctor error: {e}")
            flash('An error occurred while adding the doctor.', 'danger')

    return render_template('add_doctor.html', form=form)


# ---------------- ADMIN DASHBOARD ----------------
@bp.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    doctors = Doctor.query.all()
    patients = Patient.query.all()
    appointments = Appointment.query.order_by(Appointment.start_datetime.desc()).all()

    return render_template(
        'admin_dashboard.html',
        doctors=doctors,
        patients=patients,
        appointments=appointments
    )


# ---------------- PATIENT DASHBOARD ----------------
@bp.route('/patient')
@login_required
def patient_dashboard():
    if current_user.role != 'patient':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    patient = current_user.patient_profile
    upcoming = Appointment.query.filter_by(patient_id=patient.id).order_by(Appointment.start_datetime).all()
    doctors = Doctor.query.filter_by(is_active=True, is_approved=True).all()
    return render_template('patient_dashboard.html', patient=patient, upcoming=upcoming, doctors=doctors)


# ---------------- BOOK APPOINTMENT ----------------
@bp.route('/patient/book/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def book_appointment(doctor_id):
    if current_user.role != 'patient':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    patient = current_user.patient_profile
    doctor = Doctor.query.get_or_404(doctor_id)
    form = BookAppointmentForm()

    if form.validate_on_submit():
        start_dt = parse_datetime(form.start_datetime.data)
        end_dt = parse_datetime(form.end_datetime.data)
        reason = form.reason.data

        if not start_dt or not end_dt or end_dt <= start_dt:
            flash('Invalid time range.', 'danger')
            return redirect(url_for('main.book_appointment', doctor_id=doctor.id))

        start_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')

        # Conflict check
        conflict = Appointment.query.filter(
            Appointment.doctor_id == doctor.id,
            Appointment.status == 'Booked',
            ~((Appointment.end_datetime <= start_str) | (Appointment.start_datetime >= end_str))
        ).first()

        if conflict:
            flash('That slot is already booked.', 'danger')
            return redirect(url_for('main.book_appointment', doctor_id=doctor.id))

        appointment = Appointment(
            patient_id=patient.id,
            doctor_id=doctor.id,
            start_datetime=start_str,
            end_datetime=end_str,
            reason=reason
        )
        db.session.add(appointment)
        db.session.commit()
        flash('Appointment booked successfully.', 'success')
        return redirect(url_for('main.patient_dashboard'))

    return render_template('book_appointment.html', doctor=doctor, form=form)


# ---------------- DOCTOR DASHBOARD ----------------
@bp.route('/doctor')
@login_required
def doctor_dashboard():
    if current_user.role != 'doctor':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    doctor = current_user.doctor_profile
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.start_datetime).all()
    return render_template('doctor_dashboard.html', doctor=doctor, appointments=appointments)


# ---------------- COMPLETE APPOINTMENT ----------------
@bp.route('/doctor/complete/<int:appointment_id>', methods=['GET', 'POST'])
@login_required
def complete_appointment(appointment_id):
    if current_user.role != 'doctor':
        flash('Access denied.', 'danger')
        return redirect(url_for('main.index'))

    appt = Appointment.query.get_or_404(appointment_id)
    if appt.doctor_id != current_user.doctor_profile.id:
        flash('You are not authorized to modify this appointment.', 'danger')
        return redirect(url_for('main.doctor_dashboard'))

    if request.method == 'POST':
        diagnosis = request.form.get('diagnosis')
        prescription = request.form.get('prescription')
        appt.status = 'Completed'
        db.session.add(Treatment(appointment_id=appt.id, diagnosis=diagnosis, prescription=prescription))
        db.session.commit()
        flash('Appointment completed and treatment saved.', 'success')
        return redirect(url_for('main.doctor_dashboard'))

    return render_template('complete_appointment.html', appointment=appt)
