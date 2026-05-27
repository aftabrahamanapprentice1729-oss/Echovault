# Echovault

Echovault is a Python web application featuring automated AI data labeling and Progressive Web App (PWA) capabilities. 

**Live Demo:** [https://echovault-1729.onrender.com](https://echovault-1729.onrender.com)

## Project Structure

- `app.py`: Main web server and application routing.
- `ai_labeler.py`: Core logic for data processing and AI label assignment.
- `index.html`: Primary frontend interface.
- `echovault.db`: Lightweight SQLite database for data persistence.
- `sw.js` & `manifest.json`: Service worker and web manifest enabling PWA functionality.
- `requirements.txt`: Python environment dependencies.
- `cookies.txt`: Cookie storage and authentication handling. *(Note: Ensure this is added to `.gitignore` if it contains live session data).*

## Local Development

### Prerequisites

- Python 3.8+

### Installation

1. Clone the repository:

```bash
git clone https://github.com/aftabrahamanapprentice1729-oss/Echovault.git
cd Echovault
```

2. Create and activate a virtual environment:

```bash
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Start the server:

```bash
python app.py
```

The application will be accessible via your local host network (typically `http://localhost:5000` or `http://127.0.0.1:8000`).

## Deployment Notes (Render)

Because the live application is hosted on Render, please note that the local SQLite database (`echovault.db`) will behave ephemerally on Render's standard web service tier. Any data written to the database during runtime will be reset upon the next deployment or server restart unless a Render Persistent Disk is attached and configured in the application path.

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to modify to ensure it aligns with the project goals.

## License

MIT
