import os
import re
from flask import Flask, request, render_template, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from docx import Document
import PyPDF2
from unidecode import unidecode
import spacy
import datetime # Keep this for the context processor, even if uploaded_at is removed

# --- Flask App Initialization ---
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_dev')
app.config['UPLOAD_FOLDER'] = 'uploads'

# DATABASE_URI: IMPORTANT - Use environment variable for production!
# For GitHub Codespaces, set 'DATABASE_URL' as a Codespace Secret.
# For Azure App Service, set 'DATABASE_URL' as an Application Setting.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL',
    'postgresql+psycopg2://rpadmin:Wissen123@myrpappserver.postgres.database.azure.com:5432/postgres?sslmode=require')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Load spaCy model only once
nlp = None
try:
    nlp = spacy.load("en_core_web_sm")
    print("✅ spaCy model 'en_core_web_sm' loaded successfully.")
except OSError:
    print("❌ spaCy model 'en_core_web_sm' not found. Please run: python -m spacy download en_core_web_sm")

# Load skills from skills.txt
SKILLS_FILE = 'skills.txt'
COMMON_SKILLS = set()
def load_skills_from_file(filepath):
    skills_set = set()
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                skill = line.strip()
                if skill:
                    skills_set.add(skill.lower())
        print(f"✅ Loaded {len(skills_set)} skills from {filepath}")
    except FileNotFoundError:
        print(f"❌ Skills file not found: {filepath}. Using a limited default set.")
        skills_set = {'python', 'java', 'sql', 'excel', 'flask', 'machine learning', 'ai', 'html', 'css', 'javascript'}
    return skills_set

COMMON_SKILLS = load_skills_from_file(SKILLS_FILE)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# --- Database Model ---
class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False) # Email as unique identifier
    phone = db.Column(db.String(50))
    skills = db.Column(db.Text)
    # The 'uploaded_at' column is removed here.

    def __repr__(self):
        return f'<Resume {self.name} - {self.email}>'

# Create database tables if they don't exist
with app.app_context():
    try:
        db.create_all()
        print("✅ Connected to the database and tables created/verified.")
    except Exception as e:
        print(f"❌ Error connecting to the database or creating tables: {e}")

# --- Context Processor for global variables in templates ---
@app.context_processor
def inject_now():
    """Injects the current datetime object into all templates."""
    return {'now': datetime.datetime.now()}

# --- Helper Functions for File Handling (No change needed here) ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'docx']

def extract_text_from_resume(file_path):
    text = ''
    try:
        if file_path.endswith('.pdf'):
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ''
        elif file_path.endswith('.docx'):
            doc = Document(file_path)
            text = '\n'.join([para.text for para in doc.paragraphs])
    except Exception as e:
        print(f"Error extracting text from {file_path}: {e}")
        text = ''
    return unidecode(text)

def extract_name(text):
    if nlp:
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                if len(ent.text.split()) >= 2 and len(ent.text) > 5:
                    return ent.text.strip()
        lines = text.strip().split('\n')
        for line in lines[:3]:
            if len(line.strip().split()) >= 2 and len(line.strip()) > 5:
                if not re.search(r'^(resume|curriculum vitae|cv|contact|summary)', line.strip(), re.IGNORECASE):
                    return line.strip()
    else:
        lines = text.strip().split('\n')
        for line in lines[:3]:
            if len(line.strip().split()) >= 2 and len(line.strip()) > 5:
                if not re.search(r'^(resume|curriculum vitae|cv|contact|summary)', line.strip(), re.IGNORECASE):
                    return line.strip()
    return 'Name not found'

def extract_email(text):
    match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    return match.group() if match else 'Email not found'

def extract_phone(text):
    phone_patterns = [
        r'\b(?:\+?\d{1,3}[-.●\s]?)?\(?\d{3}\)?[-.●\s]?\d{3}[-.●\s]?\d{4}\b',
        r'\b(?:\+\d{1,3}[-.●\s]?)?\d{10,14}\b',
        r'\b0\d{3}[-.●\s]?\d{3}[-.●\s]?\d{4}\b'
    ]
    found_numbers = []
    for pattern in phone_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            cleaned_number = re.sub(r'[\s\-().●]', '', match)
            if 7 <= len(cleaned_number) <= 15:
                found_numbers.append(cleaned_number)
    return found_numbers[0] if found_numbers else 'Phone not found'

def extract_skills(text):
    found_skills = set()
    lower_text = text.lower()
    for skill in COMMON_SKILLS:
        pattern = r'\b' + re.escape(skill) + r'\b'
        if re.search(pattern, lower_text):
            found_skills.add(skill.title())
    return ', '.join(sorted(list(found_skills))) if found_skills else 'Skills not found'

# --- Flask Routes ---

@app.route('/')
def home():
    return redirect(url_for('upload_resume'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_resume():
    if request.method == 'POST':
        if 'resume' not in request.files or request.files['resume'].filename == '':
            flash("No file selected for upload.", 'error')
            return redirect(request.url)

        file = request.files['resume']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            try:
                file.save(file_path)

                extracted_text = extract_text_from_resume(file_path)
                if not extracted_text:
                    flash(f"❌ Failed to extract text from {filename}. File might be corrupted or empty.", 'error')
                    return redirect(request.url)

                name = extract_name(extracted_text)
                email = extract_email(extracted_text)
                phone = extract_phone(extracted_text)
                skills = extract_skills(extracted_text)

                if email == 'Email not found' or name == 'Name not found':
                    flash(f"❌ Resume processing failed: Could not extract email or name. Please ensure the resume is clear.", 'error')
                    return redirect(request.url)

                # --- Duplicate Handling / Upsert Logic (Primary unique key: email) ---
                existing_resume = Resume.query.filter_by(email=email).first()

                if existing_resume:
                    # Update existing record
                    existing_resume.name = name
                    existing_resume.phone = phone
                    existing_resume.skills = skills
                    # Removed: existing_resume.uploaded_at = db.func.now()
                    db.session.commit()
                    flash(f"✅ Resume for {name} ({email}) updated successfully!", 'success')
                else:
                    # Create a new record
                    new_resume = Resume(name=name, email=email, phone=phone, skills=skills)
                    db.session.add(new_resume)
                    db.session.commit()
                    flash(f"✅ New resume for {name} ({email}) saved successfully!", 'success')

                return redirect(url_for('search'))
            except Exception as e:
                flash(f"An error occurred during file processing or saving: {e}", 'error')
                print(f"Error in upload_resume: {e}")
                return redirect(request.url)
        else:
            flash("❌ Invalid file format. Only PDF and DOCX are allowed.", 'error')
            return redirect(request.url)

    return render_template('upload.html')

@app.route('/search', methods=['GET'])
def search():
    search_query = request.args.get('query', '').strip()
    resumes = []

    if search_query:
        query = Resume.query

        # Split the query into individual search terms
        search_terms = [term.strip() for term in search_query.split(',') if term.strip()]

        if search_terms:
            # Build a more complex query that searches across multiple fields
            for term in search_terms:
                query = query.filter(db.or_(
                    Resume.skills.ilike(f'%{term}%'),  # Search in skills
                    Resume.name.ilike(f'%{term}%'),    # Search in name
                    Resume.email.ilike(f'%{term}%'),   # Search in email
                    Resume.phone.ilike(f'%{term}%')    # Search in phone
                ))
            resumes = query.all()
        else:
            resumes = Resume.query.all()
    else:
        resumes = Resume.query.all()

    return render_template('search.html', resumes=resumes, search_query=search_query)


@app.route('/edit/<int:resume_id>', methods=['GET', 'POST'])
def edit_resume(resume_id):
    resume = db.session.get(Resume, resume_id)
    if not resume:
        flash("Resume not found.", 'error')
        return redirect(url_for('search'))

    if request.method == 'POST':
        resume.name = request.form['name']
        resume.email = request.form['email']
        resume.phone = request.form['phone']
        resume.skills = request.form['skills']
        db.session.commit()
        flash(f"Resume for {resume.name} updated successfully!", 'success')
        return redirect(url_for('search'))
    return render_template('edit.html', resume=resume)

@app.route('/delete/<int:resume_id>', methods=['POST'])
def delete_resume(resume_id):
    resume = db.session.get(Resume, resume_id)
    if resume:
        db.session.delete(resume)
        db.session.commit()
        flash(f"Candidate '{resume.name}' ({resume.email}) deleted successfully.", 'success')
    else:
        flash("Resume not found.", 'error')
    return redirect(url_for('search'))

# Removed: The entire @app.route('/delete_duplicates', ...) block was here.

if __name__ == '__main__':
    app.run(debug=True)