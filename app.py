import os
import re
from flask import Flask, request, render_template, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from docx import Document
import PyPDF2

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql+psycopg2://rpadmin:Wissen123@myrpappserver.postgres.database.azure.com:5432/postgres?sslmode=require'   
db = SQLAlchemy(app)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Resume(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    skills = db.Column(db.Text)

with app.app_context():
    try:
        db.create_all()
        print("✅ Connected to the database and tables created.")
    except Exception as e:
        print("❌ Error connecting to the database:", e)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['pdf', 'docx']

def extract_text_from_resume(file_path):
    if file_path.endswith('.pdf'):
        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ''
            for page in reader.pages:
                text += page.extract_text() or ''
            return text
    elif file_path.endswith('.docx'):
        doc = Document(file_path)
        return '\n'.join([para.text for para in doc.paragraphs])
    return ''

def extract_name(text):
    return text.split('\n')[0].strip()

def extract_email(text):
    match = re.search(r'\b[\w.-]+?@\w+?\.\w+?\b', text)
    return match.group() if match else 'Not found'

def extract_phone(text):
    match = re.search(r'(\+?\d{1,3})?[\s-]?(\d{10})', text)
    return match.group() if match else 'Not found'

def extract_skills(text):
    return ', '.join(re.findall(r'\b(Python|Java|SQL|Excel|Flask|Machine Learning|AI|HTML|CSS|JavaScript)\b', text, re.IGNORECASE))

    return redirect(url_for('upload_resume'))


    return redirect(url_for('upload_resume'))

@app.route('/')
def home():
    return redirect(url_for('upload_resume'))

@app.route('/upload', methods=['GET', 'POST'])
def upload_resume():
    if request.method == 'POST':
        file = request.files['resume']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            extracted_text = extract_text_from_resume(file_path)
            name = extract_name(extracted_text)
            email = extract_email(extracted_text)
            phone = extract_phone(extracted_text)
            skills = extract_skills(extracted_text)

            new_resume = Resume(name=name, email=email, phone=phone, skills=skills)
            db.session.add(new_resume)
            db.session.commit()

            return f"✅ Resume saved for {name}!"
        return "❌ Invalid file format."
    return render_template('upload.html')

@app.route('/search', methods=['GET', 'POST'])
def search_resume():
    results = []
    if request.method == 'POST':
        keyword = request.form['keyword'].lower()
        results = Resume.query.filter(
            (Resume.name.ilike(f'%{keyword}%')) |
            (Resume.email.ilike(f'%{keyword}%')) |
            (Resume.phone.ilike(f'%{keyword}%')) |
            (Resume.skills.ilike(f'%{keyword}%'))
        ).all()
    return render_template('search.html', results=results)

@app.route('/edit/<int:resume_id>', methods=['GET', 'POST'])
def edit_resume(resume_id):
    resume = Resume.query.get_or_404(resume_id)
    if request.method == 'POST':
        resume.name = request.form['name']
        resume.email = request.form['email']
        resume.phone = request.form['phone']
        resume.skills = request.form['skills']
        db.session.commit()
        return redirect(url_for('search_resume'))
    return render_template('edit.html', resume=resume)

if __name__ == '__main__':
    app.run(debug=True)
