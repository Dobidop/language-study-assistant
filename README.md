# 🧠 (a very basic) LLM driven Korean Language Study Assistant

An interactive, AI-assisted Korean language learning platform that tracks your grammar progress, adapts to your mistakes, and dynamically generates exercises using LLMs (e.g., OpenAI or local models). Built for beginners who want personalized study sessions and transparent improvement tracking.

---

## ✨ Features

- 🧩 **Grammar-aware exercise generator**  
  Automatically selects grammar points based on your weaknesses and past exposure. (not great at the moment, needs improvements)

- 📊 **Smart progress tracking**  
  Tracks your session results, grammar mastery stages, and common error patterns. (just ok, needs improvements)

- 🔁 **Real-time feedback**  
  Evaluates your answers, corrects mistakes, and explains grammar concepts. (works decently well)

- 💡 **Custom vocab buckets**  
  Prioritizes new, familiar, and core vocabulary intelligently. (works ok, but planning on an Anki integration)

- 🔄 **Supports both OpenAI and local models**  
  Easily switch between GPT-4 and local LLMs like Mistral/Qwen. (seems to work well, requests to local LLMs needs some improvements)

---

## 🛠 Tech Stack

- **Backend**: Python 3.10+, Flask-style API structure
- **Frontend**: HTML/CSS + vanilla JS
- **LLM API**: OpenAI (`openai`) or local server-compatible models
- **Storage**: JSON-based profiles and session logging

---

## 🚀 Getting Started

### Windows Users: Easy Setup

1. **Clone the repo**  
   ```bash
   git clone https://github.com/Dobidop/language-study-assistant.git
   ```
2. **Run the setup batch file** 

```bash
setup.bat
```

This will:

- Create a virtual environment
- Install required dependencies (`requirements.txt`)

---

### Manual Setup (Cross-platform)

1. **Clone the repo**  
   ```bash
   git clone https://github.com/Dobidop/language-study-assistant.git
   cd language-study-assistant
   ```

2. **Create a virtual environment and activate it**  
   ```bash
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies**  
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**  
   Create a file called `api-key.env` and add your OpenAI key:

   ```
   OPENAI_API_KEY=your-api-key-here
   ```

---

## ▶️ Running the App

To start the local web app:

```bash
startWeb.bat  # Windows only
```

Or run manually with:

```bash
python app.py
```

Then open your browser and go to:  
`http://localhost:8000/`

---

## 🧪 Usage Guide

- Visit the **Dashboard** to view your session history and error stats.
- Click **Start Studying** to begin a new session.
- You'll receive dynamically generated exercises.
- Type your answer and submit it.
- You'll get:
  - Feedback (`correct/incorrect`)
  - A corrected sentence
  - Vocabulary breakdown
  - Grammar explanation

Sessions are auto-logged in the `/sessions/` folder.

---

## 📁 File Structure Overview

```text
├── app.py                  # Main server
├── setup.bat               # Easy setup for Windows
├── startWeb.bat            # Launch web interface
├── config.json             # Model preferences and defaults
├── api-key.env             # Your OpenAI API key
├── engine/                 # Core logic for grammar, evaluation, generation
├── curriculum/             # Curriculum definitions per language
├── sessions/               # Auto-logged session history
├── dashboard.html          # Dashboard UI
├── study.html              # Study session UI
├── user_profile.json       # Your learning progress
├── vocab_data.json         # Vocabulary difficulty and tags
```

---

## 🛠 Customization

### 📚 Add/Edit Grammar Curriculum

Edit `curriculum/korean.json` to change grammar point descriptions, difficulty, or learning order.

### 🔡 Add New Vocabulary

Edit `vocab_data.json` and mark vocab items as `ease = 0` (new), 1–2 (familiar), or >2.5 (core).

### 🤖 Change Language Model

Modify `config.json` to change (manually):

```json
{
  "default_provider": "openai",
  "openai_model": "gpt-4",
  "local_model": "mistral-7b-instruct",
  "local_port": 11434
}
```

Or use the dropdown settings on the dashboard to change provider and model.

---

## 🗃 Session Logging

All completed sessions are saved as JSON in the `sessions/` folder.  
Each log includes:

- Date/time
- Exercises completed
- Accuracy stats
- Error types and examples
- Grammar focus

---

## 📜 License

This project is open source under the terms of the [MIT License](./LICENSE).

---
