# Smart Quiz Platform - Documentation

This document provides a comprehensive overview of the **Smart Quiz Platform**, detailing its Frontend, Backend, API connections, and step-by-step instructions for local setup and deployment.

---

## 📂 Project Structure

```
project 1/
│
├── backend/
│   ├── app.py              # Main Flask Server & API routes
│   ├── requirements.txt    # Python Dependencies
│   ├── data.json           # Local JSON Database (Users & History)
│   └── .env                # Environment Variables (API Keys)
│
├── frontend/
│   ├── index.html          # Landing / Welcome Page
│   ├── login.html          # User Login Page
│   ├── register.html       # User Registration Page
│   ├── dashboard.html      # Main Quiz Dashboard Workspace
│   ├── profile.html        # User Profile, History & Badges Page
│   ├── style.css           # Global Premium CSS Stylesheet
│   └── app.js              # Client-Side Application Logic
│
└── README.md               # Documentation File (This File)
```

---

## 🎨 Frontend Architecture

The frontend is built using **HTML5, CSS3 (Vanilla), and JavaScript (ES6)** with a modern, glassmorphism-inspired dark/light design.

### Key Pages:
1. **Welcome Page (`index.html`)**: Simple, minimal hero page introducing the platform.
2. **Authentication (`login.html` & `register.html`)**: Clean forms to log in and sign up. Saves user session details to browser `localStorage`.
3. **Dashboard (`dashboard.html`)**: The core interactive page. Features:
   * **Browse Mode**: Start instant default quizzes in various categories (HTML, CSS, JS, Python, AI, Space, History, Sports, GK).
   * **Custom Mode (Topic-based)**: Generate quizzes on any custom topic.
   * **Custom Mode (File-upload)**: Upload a **PDF** or **TXT** document to generate questions directly from its text content.
   * **Language Selection**: Generate quizzes in **English, Gujarati, or Hindi**.
   * **Timer**: 30-second countdown timer per question.
   * **Text-to-Speech (TTS)**: Reads out questions using the browser speech synthesis engine.
   * **Leaderboard View**: Shows latest scores from the local database.
   * **Certificate Generation**: Uses HTML5 `<canvas>` to draw and download a customized completion certificate.
4. **Profile View (`profile.html`)**: Displays user statistics (Total quizzes taken, average score, highest score), chronological history, and unlocks **Achievements/Badges** (e.g., First Step, Quiz Master, Perfectionist).

---

## ⚙️ Backend Architecture

The backend is built with **Flask** in Python and serves both static frontend assets and REST API endpoints.

### Key Backend Features:
* **Hybrid Quiz Generation**:
  * **AI Live Mode**: If a `GEMINI_API_KEY` is provided, it connects to Google Gemini (using `google-generativeai`) to generate customized, structured JSON questions, options, correct answers, and explanations.
  * **Document AI Mode**: Extracts text from PDF files (using `pypdf`) or TXT files and asks Gemini to formulate a quiz based *only* on the text contents.
  * **Dynamic Mock Fallback**: If no API key is provided, or the API fails:
    * For documents, it extracts sentences and dynamically negates them or blanks words to create Fill-in-the-blank and True/False questions offline.
    * For topics, it pulls structured questions from a pre-defined multi-lingual offline database built directly inside `app.py`.
* **Lightweight DB**: Uses `data.json` to store registered usernames, passwords, and quiz logs.

---

## 🔌 API Connection (Frontend & Backend Integration)

The frontend `app.js` communicates with the backend `app.py` using standard asynchronous `fetch()` requests. The base URL is automatically resolved in `app.js` via `window.location.origin`.

### Available API Endpoints:

#### 1. Generate Quiz
* **Endpoint**: `POST /api/generate-quiz`
* **Content-Type**: `multipart/form-data`
* **Parameters**:
  * `topic` (string) - Topic name or uploaded filename.
  * `difficulty` (string) - `easy` | `medium` | `hard`
  * `count` (integer) - Number of questions requested.
  * `language` (string) - `English` | `Gujarati` | `Hindi`
  * `quiz_type` (string) - `mcq` | `true_false` | `mixed`
  * `file` (file, optional) - PDF or TXT file object.
* **Response**:
  ```json
  {
    "success": true,
    "mode": "gemini" | "mock" | "document_fallback",
    "questions": [
      {
        "question": "What is the capital of India?",
        "options": ["Delhi", "Mumbai", "Kolkata", "Chennai"],
        "correct_answer": "Delhi",
        "explanation": "Delhi is the capital territory of India."
      }
    ],
    "message": "Optional status message..."
  }
  ```

#### 2. Save Gemini API Key
* **Endpoint**: `POST /api/save-key`
* **Request Payload** (`application/json`):
  ```json
  {
    "api_key": "YOUR_GEMINI_API_KEY_HERE"
  }
  ```
  *(Send `{"api_key": "disconnect"}` to clear key and return to Mock Mode)*
* **Response**:
  ```json
  {
    "success": true,
    "message": "API Key saved successfully!"
  }
  ```

#### 3. User Registration
* **Endpoint**: `POST /api/register`
* **Request Payload** (`application/json`):
  ```json
  {
    "username": "john_doe",
    "email": "john@example.com",
    "password": "secure_password"
  }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "message": "Registration successful!"
  }
  ```

#### 4. User Login
* **Endpoint**: `POST /api/login`
* **Request Payload** (`application/json`):
  ```json
  {
    "username": "john_doe",
    "password": "secure_password"
  }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "user": {
      "username": "john_doe",
      "email": "john@example.com"
    }
  }
  ```

#### 5. Fetch User Profile & Stats
* **Endpoint**: `GET /api/get-profile?username=john_doe`
* **Response**:
  ```json
  {
    "success": true,
    "data": {
      "profile": {
        "username": "john_doe",
        "email": "john@example.com",
        "date_created": "2026-07-20T05:35:48Z"
      },
      "stats": {
        "total_quizzes": 5,
        "avg_score": 3.8,
        "highest_score": 5
      },
      "badges": [
        { "name": "First Step", "desc": "Completed your first quiz", "icon": "🎓", "unlocked": true }
      ],
      "history": [
        { "category": "HTML Quiz", "score": 4, "time_taken": "0:45", "date_created": "..." }
      ]
    }
  }
  ```

#### 6. Save Quiz Score
* **Endpoint**: `POST /api/save-score`
* **Request Payload** (`application/json`):
  ```json
  {
    "username": "john_doe",
    "category": "Science Quiz",
    "score": 4,
    "time_taken": "0:52"
  }
  ```
* **Response**:
  ```json
  {
    "success": true,
    "message": "Score saved successfully!"
  }
  ```

---

## 🚀 Setup & Local Deployment Guide

Follow these steps to run the application locally on your computer:

### Prerequisite
Make sure you have **Python 3.8+** installed.

### Step 1: Navigate to the Backend directory
Open your terminal/command prompt and navigate to the project directory:
```bash
cd "k:\internship doc\project 1\backend"
```

### Step 2: Create a Virtual Environment (Recommended)
Creating an isolated virtual environment prevents library conflicts:
```bash
python -m venv .venv
```
Activate it:
* **Windows (PowerShell)**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
* **Windows (Command Prompt)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```
* **macOS / Linux**:
  ```bash
  source .venv/bin/activate
  ```

### Step 3: Install Dependencies
Install all required libraries using pip:
```bash
pip install -r requirements.txt
```

### Step 4: Configure Gemini API Key
To use the AI generation features:
1. Open the [backend/.env](file:///k:/internship%20doc/project%201/backend/.env) file.
2. Get a free API Key from [Google AI Studio](https://aistudio.google.com/).
3. Add your key into the file:
   ```env
   GEMINI_API_KEY=your_actual_api_key_here
   ```
*(Note: If you leave this blank, the app will run in **Mock Quiz Mode** using built-in questions and local offline files parsing).*

### Step 5: Start the Flask Server
Run the Flask server:
```bash
python app.py
```
By default, the server will start on **`http://localhost:5000`**.

### Step 6: Access the App
Open your web browser and go to:
👉 **`http://localhost:5000`**

The Flask backend is configured to automatically serve the frontend files (HTML/CSS/JS) directly from the `frontend/` directory.

---

## 🌐 Production Deployment

To deploy this project to hosting services:

### Option A: Render / Heroku / Railway (PaaS)
1. Push your code to a Git repository (e.g., GitHub).
2. Create a new Web Service on the deployment platform.
3. Configure the build commands:
   * **Build Command**: `pip install -r backend/requirements.txt`
   * **Start Command**: `gunicorn --directory backend app:app` (Make sure to install `gunicorn` package or run standard python start command).
4. Set Environment Variables on the provider's dashboard:
   * `GEMINI_API_KEY` = `your_gemini_api_key`
   * `PORT` = `8080` (or as required by the host)

### Option B: Local Network Hosting
If you want to access the app from your mobile phone or other devices on the same Wi-Fi:
1. Run python app.py.
2. Find your local IP Address (run `ipconfig` in cmd).
3. Open `http://<YOUR_LOCAL_IP>:5000` on your mobile browser.
