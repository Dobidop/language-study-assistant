# Korean Language Study Assistant

**Korean Language Study Assistant** is an interactive study tool designed to help beginners learn Korean grammar and vocabulary through dynamically generated exercises, real-time feedback, and session tracking. It runs both as a command-line tool and a lightweight web app using Flask.

---

## Features
- 📚 Beginner-focused Korean grammar exercises.
- 🔍 Personalized learning with progress tracking.
- ✍️ Dynamic exercise generation using OpenAI or local LLMs.
- ✅ Instant feedback and correction suggestions.
- 📊 Session summaries and mistake tracking.
- 🖥️ Web interface with study, history, and summary pages.

---

## Tech Stack
- Python 3
- Flask
- OpenAI API or Local LLM (optional)
- Frontend: Vanilla HTML, CSS, JavaScript

---

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/korean-study-assistant.git
   cd korean-study-assistant
   ```

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure your environment:
   - Create an `.env` file (copy from `api-key.env.example`) and add your OpenAI API key if using OpenAI.
   - Example:
     ```
     OPENAI_API_KEY=your_openai_api_key_here
     ```

4. (Optional) Edit `config.json` to adjust model/provider settings.

---

## Running the App

- **Command Line Mode** (basic study session):
  ```bash
  python main.py
  ```

- **Web App Mode**:
  ```bash
  python app.py
  ```
  Then open your browser at `http://localhost:5000`

---

## Folder Structure

```
.
├── engine/            # Core logic (exercise generation, evaluation, logging)
├── sessions/          # Saved session logs
├── curriculum/        # Curriculum data for Korean
├── static/            # Frontend HTML, CSS, JavaScript files
├── user_profile.json  # Tracks user progress
├── app.py             # Flask application
├── main.py            # CLI application
├── requirements.txt   # Python dependencies
└── README.md
```

---

## Roadmap
- Add support for more languages (e.g., Japanese, Chinese).
- Expand exercise types (listening, speaking tasks).
- Integrate spaced repetition (like Anki) more tightly.
- Mobile-friendly UI improvements.

---

## License
MIT License. See `LICENSE` file.
