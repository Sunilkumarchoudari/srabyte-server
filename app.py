from flask import Flask, request, jsonify, send_from_directory
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from flask_cors import CORS
from pymongo import MongoClient
from datetime import datetime, timedelta
from dotenv import load_dotenv
import uuid
import yaml
import traceback

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

# CORS configuration
CORS(app, supports_credentials=True, origins=['http://127.0.0.1:*', 'http://localhost:*'])

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
try:
    client = MongoClient(MONGO_URI)
    db = client['srabyt']  # Updated to match your database name
    otp_collection = db['otps']
    print("Connected to MongoDB successfully")
except Exception as e:
    print(f"Failed to connect to MongoDB: {e}")
    raise e

# Email configuration
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')

# Validate email credentials
if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
    print(f"Error: Missing email credentials - EMAIL_ADDRESS={EMAIL_ADDRESS}, EMAIL_PASSWORD={'set' if EMAIL_PASSWORD else 'not set'}")
    raise ValueError("EMAIL_ADDRESS and EMAIL_PASSWORD must be set in .env file")

def generate_otp(length=6):
    """Generate a random OTP of specified length."""
    return ''.join(random.choices(string.digits, k=length))

def send_email(to_email, subject, email_body, attachment=None):
    """Send an email with optional attachment."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(email_body, 'html'))

        if attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={attachment.filename}'
            )
            msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        print(f"Email sent successfully to {to_email}")
        return True
    except Exception as e:
        print(f"Error sending email to {to_email}: {str(e)}")
        traceback.print_exc()
        return False

@app.route('/')
def serve_index():
    """Serve the index.html file."""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        print(f"Error serving index.html: {e}")
        return jsonify({'error': 'File not found'}), 404

@app.route('/assets/<path:path>')
def serve_assets(path):
    """Serve static assets."""
    try:
        return send_from_directory('assets', path)
    except Exception as e:
        print(f"Error serving asset {path}: {e}")
        return jsonify({'error': 'Asset not found'}), 404

@app.route('/favicon.ico')
def serve_favicon():
    """Serve favicon to suppress 404 errors."""
    try:
        return send_from_directory('.', 'favicon.ico', mimetype='image/x-icon')
    except FileNotFoundError:
        print("Warning: favicon.ico not found")
        return '', 204

@app.route('/projects', methods=['GET'])
def get_projects():
    """Read and parse projects from projects.md."""
    try:
        with open('projects.md', 'r') as file:
            content = file.read()
        
        # Split content by YAML front matter delimiter (---)
        project_sections = content.split('---')[1:]  # Skip initial empty section
        projects = []
        
        for section in project_sections:
            if section.strip():
                try:
                    # Parse YAML front matter
                    project_data = yaml.safe_load(section.strip())
                    projects.append({
                        'title': project_data.get('title', ''),
                        'shortDescription': project_data.get('shortDescription', ''),
                        'fullDescription': project_data.get('fullDescription', ''),
                        'technologies': project_data.get('technologies', []),
                        'domains': project_data.get('domains', []),
                        'icon': project_data.get('icon', 'fas fa-project-diagram')
                    })
                except yaml.YAMLError as e:
                    print(f"Error parsing project in projects.md: {e}")
                    continue
        
        if not projects:
            print("Warning: No projects parsed from projects.md")
            return jsonify({'error': 'No projects found'}), 404
        
        print(f"Loaded {len(projects)} projects from projects.md")
        return jsonify({'projects': projects})
    except FileNotFoundError:
        print("Error: projects.md file not found")
        return jsonify({'error': 'Projects file not found'}), 404
    except Exception as e:
        print(f"Error reading projects.md: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Server error'}), 500

@app.route('/test-otp', methods=['GET'])
def test_otp():
    """Test endpoint to store a sample OTP in MongoDB."""
    try:
        otp = '123456'
        form_data = {'email': 'test@example.com', 'fullName': 'Test User'}
        otp_id = str(uuid.uuid4())
        otp_collection.insert_one({
            'otp_id': otp_id,
            'email': form_data['email'],
            'otp': otp,
            'form_data': form_data,
            'created_at': datetime.utcnow()
        })
        print(f"Test OTP stored: otp_id={otp_id}, otp={otp}, form_data={form_data}")
        return jsonify({'message': 'Test OTP set to 123456', 'otp_id': otp_id})
    except Exception as e:
        print(f"Error in test_otp: {e}")
        return jsonify({'error': 'Failed to generate test OTP'}), 500

@app.route('/send-otp', methods=['POST'])
def send_otp():
    """Generate and store OTP in MongoDB, then send it via email."""
    if request.method != 'POST':
        print(f"Warning: Invalid method {request.method} for /send-otp")
        return jsonify({'error': 'Method not allowed'}), 405

    try:
        data = request.json
        if not data:
            print("Error: No JSON data received")
            return jsonify({'error': 'No data received'}), 400

        email = data.get('email')
        project_title = data.get('projectTitle', 'General Project Request')
        
        if not email:
            print("Error: Email is missing")
            return jsonify({'error': 'Email is required'}), 400

        # Generate OTP and unique OTP ID
        otp = generate_otp()
        otp_id = str(uuid.uuid4())

        # Store OTP and form data in MongoDB
        otp_collection.insert_one({
            'otp_id': otp_id,
            'email': email,
            'otp': otp,
            'form_data': data,
            'created_at': datetime.utcnow()
        })
        print(f"OTP stored: otp_id={otp_id}, otp={otp}, email={email}, form_data={data}")

        # Send OTP email
        email_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #fff; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #007BFF; text-align: center; }}
                .otp {{ font-size: 24px; font-weight: bold; color: #28a745; text-align: center; margin: 20px 0; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #777; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Your OTP for Project Quote</h1>
                <p>Your One-Time Password (OTP) for the project <strong>{project_title}</strong> is:</p>
                <p class="otp">{otp}</p>
                <p>Please use this OTP to verify your request. This OTP is valid for 10 minutes.</p>
                <div class="footer">This email was sent from SraByte. Please do not reply directly to this email.</div>
            </div>
        </body>
        </html>
        """

        success = send_email(email, 'SraByte OTP Verification', email_body)
        if success:
            return jsonify({'message': 'OTP sent successfully', 'otp_id': otp_id})
        else:
            try:
                otp_collection.delete_one({'otp_id': otp_id})  # Clean up on email failure
                print(f"Cleaned up OTP on email failure: otp_id={otp_id}")
            except Exception as e:
                print(f"Error cleaning up OTP: {e}")
            return jsonify({'error': 'Failed to send OTP'}), 500
    except Exception as e:
        print(f"Error in send_otp: {e}")
        traceback.print_exc()
        return jsonify({'error': 'Server error'}), 500

@app.route('/verify-otp', methods=['POST'])
def verify_otp():
    """Verify OTP by checking MongoDB and send project quote email if valid."""
    try:
        data = request.json
        if not data:
            print("Error: No JSON data received")
            return jsonify({'error': 'No data received'}), 400
        
        otp = data.get('otp')
        otp_id = data.get('otp_id')
        
        if not otp or not otp_id:
            print(f"Error: Missing OTP or OTP ID - otp={otp}, otp_id={otp_id}")
            return jsonify({'error': 'OTP and OTP ID are required'}), 400

        # Query MongoDB for OTP
        otp_doc = otp_collection.find_one({'otp_id': otp_id, 'otp': otp})
        if not otp_doc:
            print(f"Error: Invalid OTP or OTP ID - otp_id={otp_id}, otp={otp}")
            return jsonify({'error': 'Invalid OTP or OTP ID'}), 400

        # Check if OTP is expired (10 minutes)
        created_at = otp_doc['created_at']
        if datetime.utcnow() > created_at + timedelta(minutes=10):
            print(f"Error: OTP expired - otp_id={otp_id}, created_at={created_at}")
            try:
                otp_collection.delete_one({'otp_id': otp_id})  # Clean up expired OTP
                print(f"Cleaned up expired OTP: otp_id={otp_id}")
            except Exception as e:
                print(f"Error cleaning up expired OTP: {e}")
            return jsonify({'error': 'OTP has expired. Please request a new OTP.'}), 400

        # OTP is valid; proceed with sending project quote email
        form_data = otp_doc['form_data']
        project_title = form_data.get('projectTitle', 'General Project Request')
        
        email_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #f4f4f4; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #fff; border-radius: 8px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
                h1 {{ color: #007BFF; text-align: center; }}
                .field {{ margin: 10px 0; }}
                .field-label {{ font-weight: bold; color: #555; }}
                .field-value {{ margin-left: 10px; }}
                .footer {{ text-align: center; margin-top: 20px; font-size: 12px; color: #777; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Project Quote Request</h1>
                <p>A new request for the project <strong>{project_title}</strong> has been submitted.</p>
                <div class="field"><span class="field-label">Full Name:</span> <span class="field-value">{form_data.get('fullName', '')}</span></div>
                <div class="field"><span class="field-label">College/Company:</span> <span class="field-value">{form_data.get('collegeOrCompany', '')}</span></div>
                <div class="field"><span class="field-label">Branch/Position:</span> <span class="field-value">{form_data.get('branchOrPosition', '')}</span></div>
                <div class="field"><span class="field-label">Address:</span> <span class="field-value">{form_data.get('address', '')}</span></div>
                <div class="field"><span class="field-label">Email:</span> <span class="field-value">{form_data.get('email', '')}</span></div>
                <div class="field"><span class="field-label">Contact Number:</span> <span class="field-value">{form_data.get('contactNumber', '')}</span></div>
                <div class="field"><span class="field-label">Gender:</span> <span class="field-value">{form_data.get('gender', '')}</span></div>
                {f'<div class="field"><span class="field-label">Project Domain:</span> <span class="field-value">{form_data.get("projectDomain", "")}</span></div>' if form_data.get('projectDomain') else ''}
                <div class="field"><span class="field-label">Project Requirements:</span> <span class="field-value">{form_data.get('projectRequirements', '')}</span></div>
                <div class="field"><span class="field-label">Estimated Completion Date:</span> <span class="field-value">{form_data.get('estimatedCompletionDate', '')}</span></div>
                {f'<div class="field"><span class="field-label">Abstract:</span> <span class="field-value">{form_data.get("abstract", "")}</span></div>' if form_data.get('abstract') else ''}
                <div class="footer">This email was generated automatically. Please do not reply directly to this email.</div>
            </div>
        </body>
        </html>
        """

        attachment = None
        if 'abstract' in form_data and form_data['abstract']:
            # Simulate file attachment (requires file upload handling)
            pass

        success = send_email(EMAIL_ADDRESS, f'Project Quote Request: {project_title}', email_body, attachment)
        if success:
            try:
                otp_collection.delete_one({'otp_id': otp_id})  # Clean up after successful verification
                print(f"OTP verified and deleted: otp_id={otp_id}")
            except Exception as e:
                print(f"Error cleaning up OTP: {e}")
            return jsonify({'message': 'Request sent successfully'})
        else:
            print(f"Error: Failed to send project quote email - otp_id={otp_id}")
            return jsonify({'error': 'Failed to send request'}), 500
    except Exception as e:
        print(f"Error in verify_otp: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': 'Server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=True)