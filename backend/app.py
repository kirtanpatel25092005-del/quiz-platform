import os
import json
import logging
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
from pypdf import PdfReader

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, static_folder='../frontend', static_url_path='')
# Enable CORS
CORS(app)

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    r.headers['Cache-Control'] = 'public, max-age=0'
    return r

# Configure Google Gemini API
API_KEY = os.getenv("GEMINI_API_KEY")
is_gemini_configured = False

if API_KEY and API_KEY != "your_gemini_api_key_here" and len(API_KEY.strip()) > 10:
    try:
        genai.configure(api_key=API_KEY)
        is_gemini_configured = True
        logging.info("Google Gemini API successfully configured.")
    except Exception as e:
        logging.error(f"Error configuring Gemini API: {e}")
else:
    logging.warning("GEMINI_API_KEY is not configured or is using default placeholder. Using Mock Quiz Mode.")

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/dashboard')
def serve_dashboard():
    return app.send_static_file('dashboard.html')

# PDF Text Extractor Helper
def extract_text_from_pdf(file_stream):
    try:
        reader = PdfReader(file_stream)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text.strip()
    except Exception as e:
        logging.error(f"Error reading PDF file: {e}")
        return ""

# TXT Text Extractor Helper
def extract_text_from_txt(file_stream):
    try:
        return file_stream.read().decode('utf-8', errors='ignore').strip()
    except Exception as e:
        logging.error(f"Error reading TXT file: {e}")
        return ""

# Dynamic mock quiz generation from uploaded document text when Gemini is offline
def generate_mock_quiz_from_text(source_text, count, quiz_type, language):
    import re
    import random
    
    # Split text into sentences (supports English and Hindi punctuation including danda)
    sentences = re.split(r'[.!?।\n]\s*', source_text)
    clean_sentences = []
    for s in sentences:
        s_clean = s.strip()
        # Filter for reasonable sentence sizes
        if 20 < len(s_clean) < 300:
            clean_sentences.append(s_clean)
            
    # Remove duplicates
    clean_sentences = list(dict.fromkeys(clean_sentences))
    
    # Localization for options/explanations
    local_labels = {
        "english": {"true": "True", "false": "False", "based_on": "Based on the uploaded document: "},
        "hindi": {"true": "सत्य", "false": "असत्य", "based_on": "दस्तावेज़ के अनुसार: "}
    }
    lang_lower = language.lower()
    labels = local_labels.get(lang_lower, local_labels["english"])
    
    questions = []
    
    # If we have sentences, generate questions from them
    if clean_sentences:
        random.shuffle(clean_sentences)
        
        # Iterate and generate questions (multiple passes if count > len(clean_sentences))
        max_attempts = count * 3
        attempt = 0
        sen_idx = 0
        
        while len(questions) < count and attempt < max_attempts:
            attempt += 1
            sen = clean_sentences[sen_idx % len(clean_sentences)]
            sen_idx += 1
            
            current_type = quiz_type
            if quiz_type == "mixed":
                current_type = random.choice(["mcq", "true_false"])
                
            if current_type == "true_false":
                # Generate True/False
                is_true = random.choice([True, False])
                if is_true:
                    q_text = sen
                    correct = labels["true"]
                    explanation = labels["based_on"] + f"'{sen}'"
                else:
                    negations = {
                        "english": ["It is not true that ", "False that: "],
                        "hindi": ["यह सत्य नहीं है कि ", "यह कथन असत्य है कि "]
                    }
                    neg_prefix = random.choice(negations.get(lang_lower, negations["english"]))
                    q_text = neg_prefix + sen[0].lower() + sen[1:] if lang_lower == "english" else neg_prefix + sen
                    correct = labels["false"]
                    explanation = labels["based_on"] + ("यह कथन बदल दिया गया है।" if lang_lower == "hindi" else "The statement has been negated.")
                    
                questions.append({
                    "question": q_text,
                    "options": [labels["true"], labels["false"]],
                    "correct_answer": correct,
                    "explanation": explanation
                })
                
            else:
                # Generate MCQ: find a suitable word to blank out (supports Devanagari and Latin letters)
                if lang_lower == "hindi":
                    words = [w.strip() for w in re.findall(r'[\u0900-\u097F\w]{3,18}', sen) if len(w.strip()) >= 3]
                else:
                    words = re.findall(r'\b\w{4,18}\b', sen)

                if not words:
                    questions.append({
                        "question": sen,
                        "options": [labels["true"], labels["false"]],
                        "correct_answer": labels["true"],
                        "explanation": labels["based_on"] + f"'{sen}'"
                    })
                    continue
                    
                target_word = random.choice(words)
                q_text = sen.replace(target_word, "_______", 1)
                
                # Find distractors from the source text
                if lang_lower == "hindi":
                    all_words = list(set([w.strip() for w in re.findall(r'[\u0900-\u097F\w]{3,18}', source_text) if len(w.strip()) >= 3 and w.strip().lower() != target_word.lower()]))
                else:
                    all_words = list(set([w for w in re.findall(r'\b\w{4,18}\b', source_text) if w.lower() != target_word.lower()]))
                
                if len(all_words) < 3:
                    default_distractors = ["विकल्प 1", "विकल्प 2", "विकल्प 3"] if lang_lower == "hindi" else ["Option A", "Option B", "Option C"]
                    distractors = default_distractors[:3]
                else:
                    distractors = random.sample(all_words, min(3, len(all_words)))
                    
                options = distractors + [target_word]
                random.shuffle(options)
                
                explanation_str = labels["based_on"] + (f"रिक्त स्थान में सही शब्द '{target_word}' आता है: '{sen}'" if lang_lower == "hindi" else f"The blank word is '{target_word}' to complete: '{sen}'.")
                questions.append({
                    "question": q_text,
                    "options": options,
                    "correct_answer": target_word,
                    "explanation": explanation_str
                })

    # If still fewer than count, supplement with topic mock questions so count is always fulfilled
    if len(questions) < count:
        needed = count - len(questions)
        supplements = get_mock_quiz("ai" if "ai" in source_text.lower() else "gk", "medium", needed, language, quiz_type)
        for sq in supplements:
            questions.append(sq)
            if len(questions) >= count:
                break
                
    return questions[:count]

# Fallback Mock Quiz Data Generator supporting multi-language and quiz types
def get_mock_quiz(topic, difficulty, count, language, quiz_type):
    lang_lower = language.lower()
    type_lower = quiz_type.lower()
    topic_lower = topic.lower()
    
    # Simple localization dictionary
    local_labels = {
        "english": {"true": "True", "false": "False", "exp": "Explanation"},
        "hindi": {"true": "सत्य", "false": "असत्य", "exp": "स्पष्टीकरण"}
    }
    labels = local_labels.get(lang_lower, local_labels["english"])
    
    # Identify Topic Category
    if "html" in topic_lower or "एचटीएमएल" in topic_lower:
        topic_cat = "html"
    elif "css" in topic_lower or "सीएसएस" in topic_lower:
        topic_cat = "css"
    elif "javascript" in topic_lower or "js" in topic_lower or "जावास्क्रिप्ट" in topic_lower:
        topic_cat = "javascript"
    elif "python" in topic_lower or "py" in topic_lower or "पायथन" in topic_lower:
        topic_cat = "python"
    elif "cricket" in topic_lower or "क्रिकेट" in topic_lower:
        topic_cat = "cricket"
    elif "sport" in topic_lower or "game" in topic_lower or "play" in topic_lower or "ball" in topic_lower or "foot" in topic_lower or "soccer" in topic_lower or "खेल" in topic_lower:
        topic_cat = "sports"
    elif "general" in topic_lower or "knowledge" in topic_lower or "gk" in topic_lower or "सामान्य" in topic_lower or "सामान्य ज्ञान" in topic_lower:
        topic_cat = "gk"
    elif "tech" in topic_lower or "computer" in topic_lower or "कंप्यूटर" in topic_lower or "तकीनीकी" in topic_lower or "तकनीक" in topic_lower:
        topic_cat = "tech"
    elif "ai" in topic_lower or "generative" in topic_lower or "llm" in topic_lower or "gpt" in topic_lower or "एआई" in topic_lower:
        topic_cat = "ai"
    elif "space" in topic_lower or "astronomy" in topic_lower or "universe" in topic_lower or "अंतरिक्ष" in topic_lower or "ब्रह्मांड" in topic_lower:
        topic_cat = "space"
    elif "history" in topic_lower or "india" in topic_lower or "war" in topic_lower or "king" in topic_lower or "इतिहास" in topic_lower or "भारत" in topic_lower:
        topic_cat = "history"
    else:
        topic_cat = "gk"
        
    # Question database mapping (tagged with difficulty)
    database = {
        "english": {
            "html": {
                "true_false": [
                    {"question": "HTML is a programming language.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "HTML is a markup language used for structuring web content, not a programming language.", "difficulty": "easy"},
                    {"question": "HTML stands for Hyper Text Markup Language.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "HTML is the standard abbreviation for Hyper Text Markup Language.", "difficulty": "easy"},
                    {"question": "The <img> tag in HTML requires a closing </img> tag.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "The <img> tag is an empty/self-closing element.", "difficulty": "medium"},
                    {"question": "HTML5 is the latest major revision of the HTML standard.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "HTML5 is the current standard major version for HTML.", "difficulty": "medium"},
                    {"question": "The <canvas> element has built-in drawing abilities of its own.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "The <canvas> element requires JavaScript to actually draw graphics.", "difficulty": "hard"},
                    {"question": "In HTML5, SVG elements can be embedded directly without any plugins.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Correct, inline SVG is fully supported in HTML5.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Which HTML element is used for the largest heading?", "options": ["<h6>", "<heading>", "<h1>", "<head>"], "correct_answer": "<h1>", "explanation": "<h1> defines the largest heading.", "difficulty": "easy"},
                    {"question": "Which HTML tag is used to create a hyperlink?", "options": ["<link>", "<a>", "<href>", "<src>"], "correct_answer": "<a>", "explanation": "The anchor tag <a> is used to define hyperlinks.", "difficulty": "easy"},
                    {"question": "What is the correct HTML element for inserting a line break?", "options": ["<lb>", "<br>", "<break>", "<line>"], "correct_answer": "<br>", "explanation": "<br> is used to insert a single line break.", "difficulty": "medium"},
                    {"question": "Which attribute is used to define inline styles in HTML?", "options": ["class", "font", "styles", "style"], "correct_answer": "style", "explanation": "The style attribute allows inline CSS declaration.", "difficulty": "medium"},
                    {"question": "Which HTML5 element is used to display measurements within a known range?", "options": ["<meter>", "<progress>", "<range>", "<gauge>"], "correct_answer": "<meter>", "explanation": "The <meter> element displays scalar measurements within a known range.", "difficulty": "hard"},
                    {"question": "In HTML5, which attribute specifies that an input field must be filled out before submitting?", "options": ["validate", "required", "placeholder", "mandatory"], "correct_answer": "required", "explanation": "The required attribute specifies that the input cannot be left empty.", "difficulty": "hard"}
                ]
            },
            "css": {
                "true_false": [
                    {"question": "CSS stands for Cascading Style Sheets.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "CSS stands for Cascading Style Sheets.", "difficulty": "easy"},
                    {"question": "In CSS, a class selector starts with a dot (.) character.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Class selectors are written with a dot prefix.", "difficulty": "easy"},
                    {"question": "Inline styles override external stylesheet styles.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Inline styles have higher specificity.", "difficulty": "medium"},
                    {"question": "The default value of the position property is relative.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "The default value of position is static.", "difficulty": "medium"},
                    {"question": "The box-sizing property with 'border-box' includes padding and border in the element's total width and height.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, border-box includes padding and borders in the size calculation.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "What does CSS stand for?", "options": ["Cascading Style Sheets", "Computer Style Sheets", "Creative Style Sheets", "Colorful Style Sheets"], "correct_answer": "Cascading Style Sheets", "explanation": "CSS stands for Cascading Style Sheets.", "difficulty": "easy"},
                    {"question": "Which CSS property is used to change the text color of an element?", "options": ["text-color", "fgcolor", "color", "font-color"], "correct_answer": "color", "explanation": "The color property sets the text color.", "difficulty": "easy"},
                    {"question": "Which CSS property controls the text size?", "options": ["text-size", "font-style", "font-size", "size"], "correct_answer": "font-size", "explanation": "The font-size property is used to configure text size.", "difficulty": "medium"},
                    {"question": "How do you select an element with ID 'header' in CSS?", "options": [".header", "#header", "header", "*header"], "correct_answer": "#header", "explanation": "IDs are selected in CSS using the hash (#) symbol.", "difficulty": "medium"},
                    {"question": "Which value of the display property makes an element behave like a grid container?", "options": ["flex", "grid", "block", "table"], "correct_answer": "grid", "explanation": "display: grid initializes a grid formatting context.", "difficulty": "hard"},
                    {"question": "What is the correct CSS declaration to center-align a block-level element horizontally?", "options": ["align: center;", "text-align: center;", "margin: 0 auto;", "padding: 0 auto;"], "correct_answer": "margin: 0 auto;", "explanation": "Setting margins to auto centers a block element within its container.", "difficulty": "hard"}
                ]
            },
            "javascript": {
                "true_false": [
                    {"question": "JavaScript is case-sensitive.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, JavaScript distinguishes between uppercase and lowercase.", "difficulty": "easy"},
                    {"question": "JSON stands for JavaScript Object Notation.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "JSON is JavaScript Object Notation.", "difficulty": "easy"},
                    {"question": "JavaScript is a multi-threaded language by default.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "JavaScript is single-threaded, using an event loop.", "difficulty": "medium"},
                    {"question": "typeof null in JavaScript returns 'object'.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "This is a long-standing legacy bug/behavior in JS.", "difficulty": "medium"},
                    {"question": "The const keyword prevents array elements from being mutated.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "const prevents variable reassignment, but arrays can still be mutated.", "difficulty": "hard"},
                    {"question": "JavaScript event propagation has two phases: Capturing and Bubbling.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, events propagate down (capturing) and then bubble up (bubbling).", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "How do you write 'Hello World' in an alert box?", "options": ["msg('Hello World');", "alertBox('Hello World');", "alert('Hello World');", "console.log('Hello World');"], "correct_answer": "alert('Hello World');", "explanation": "The alert() method displays an alert box.", "difficulty": "easy"},
                    {"question": "Which keyword is used to declare a variable in JavaScript?", "options": ["var", "string", "declare", "int"], "correct_answer": "var", "explanation": "var, let, and const are used to declare variables.", "difficulty": "easy"},
                    {"question": "Which keyword is used to declare a block-scoped variable in JavaScript?", "options": ["var", "let", "define", "const-var"], "correct_answer": "let", "explanation": "let and const declare block-scoped variables.", "difficulty": "medium"},
                    {"question": "Which operator is used to check both value and type equality in JavaScript?", "options": ["==", "=", "===", "!=="], "correct_answer": "===", "explanation": "The strict equality operator === compares both values and types.", "difficulty": "medium"},
                    {"question": "What is the output of 'typeof []' in JavaScript?", "options": ["'array'", "'object'", "'list'", "'undefined'"], "correct_answer": "'object'", "explanation": "Arrays are special objects in JS, so typeof returns 'object'.", "difficulty": "hard"},
                    {"question": "Which method is used to serialize a JavaScript object into a JSON string?", "options": ["JSON.parse()", "JSON.stringify()", "Object.toJSON()", "JSON.serialize()"], "correct_answer": "JSON.stringify()", "explanation": "JSON.stringify() converts a JavaScript value to a JSON string.", "difficulty": "hard"}
                ]
            },
            "sports": {
                "true_false": [
                    {"question": "A standard soccer match consists of two halves of 45 minutes each.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, soccer has two standard 45-minute halves.", "difficulty": "easy"},
                    {"question": "The Olympic Games are held every two years.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "The Summer and Winter Olympics are held every four years.", "difficulty": "easy"},
                    {"question": "In tennis, a score of 40-40 is called Deuce.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "A tie of 40-40 in tennis is named Deuce.", "difficulty": "medium"},
                    {"question": "Basketball was originally invented in Canada.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "It was invented in Springfield, Massachusetts, USA.", "difficulty": "medium"},
                    {"question": "A decathlon consists of exactly 10 track and field events.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "A decathlon consists of ten events.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "How many players are on the field for a single team in standard soccer?", "options": ["9", "10", "11", "12"], "correct_answer": "11", "explanation": "A team consists of 11 players including the goalkeeper.", "difficulty": "easy"},
                    {"question": "In which sport would you use a shuttlecock?", "options": ["Tennis", "Badminton", "Table Tennis", "Squash"], "correct_answer": "Badminton", "explanation": "A shuttlecock is used in Badminton.", "difficulty": "easy"},
                    {"question": "Which country won the FIFA World Cup in 2022?", "options": ["France", "Brazil", "Argentina", "Croatia"], "correct_answer": "Argentina", "explanation": "Argentina defeated France in the finals.", "difficulty": "medium"},
                    {"question": "How long is a standard marathon race?", "options": ["21.1 km", "42.195 km", "50 km", "10 km"], "correct_answer": "42.195 km", "explanation": "The official marathon distance is 42.195 kilometers.", "difficulty": "medium"},
                    {"question": "Who holds the world record for the 100m sprint in athletics?", "options": ["Carl Lewis", "Usain Bolt", "Tyson Gay", "Yohan Blake"], "correct_answer": "Usain Bolt", "explanation": "Usain Bolt set the 100m world record at 9.58 seconds in 2009.", "difficulty": "hard"}
                ]
            },
            "cricket": {
                "true_false": [
                    {"question": "A standard cricket match is played with 11 players in each team.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, each team consists of 11 players on the field.", "difficulty": "easy"},
                    {"question": "The ICC Cricket World Cup (ODI) is held every four years.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, the ODI World Cup takes place once every four years.", "difficulty": "medium"},
                    {"question": "In test cricket, a bowler can bowl an unlimited number of overs in an innings.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Correct, there is no limit to the number of overs a bowler can bowl in test cricket.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "How many runs is a 'century' in cricket?", "options": ["50", "100", "150", "200"], "correct_answer": "100", "explanation": "A century refers to a batsman scoring 100 runs in a single innings.", "difficulty": "easy"},
                    {"question": "Who is widely referred to as the 'Master Blaster' of cricket?", "options": ["Sachin Tendulkar", "MS Dhoni", "Virat Kohli", "Kapil Dev"], "correct_answer": "Sachin Tendulkar", "explanation": "Sachin Tendulkar is known as the Master Blaster due to his legendary batting.", "difficulty": "easy"},
                    {"question": "Which country won the inaugural ICC T20 World Cup in 2007?", "options": ["Pakistan", "India", "Australia", "West Indies"], "correct_answer": "India", "explanation": "India won the first T20 World Cup under MS Dhoni's captaincy by defeating Pakistan in the finals.", "difficulty": "medium"},
                    {"question": "Which bowler has taken the most wickets in Test cricket history?", "options": ["Shane Warne", "Muttiah Muralitharan", "Anil Kumble", "James Anderson"], "correct_answer": "Muttiah Muralitharan", "explanation": "Muttiah Muralitharan holds the record with 800 Test wickets.", "difficulty": "hard"}
                ]
            },
            "gk": {
                "true_false": [
                    {"question": "Light travels faster than sound.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Light travels at 300,000 km/s, while sound travels at 343 m/s in air.", "difficulty": "easy"},
                    {"question": "Mount Everest is the tallest mountain in the world above sea level.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Mount Everest is the highest mountain peak above sea level.", "difficulty": "easy"},
                    {"question": "Sound travels faster in water than in air.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Sound travels faster in water because water is denser.", "difficulty": "medium"},
                    {"question": "The Great Wall of China is easily visible from the Moon with the naked eye.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "It cannot be seen without magnification from the Moon.", "difficulty": "medium"},
                    {"question": "The Sahara Desert is the largest desert on Earth.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "The Antarctic Desert is the largest desert on Earth, followed by the Arctic Desert.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "What is the capital city of France?", "options": ["London", "Berlin", "Paris", "Rome"], "correct_answer": "Paris", "explanation": "Paris is the capital of France.", "difficulty": "easy"},
                    {"question": "Which planet is known as the Red Planet?", "options": ["Venus", "Mars", "Jupiter", "Saturn"], "correct_answer": "Mars", "explanation": "Mars has iron oxide on its surface, giving it a reddish appearance.", "difficulty": "easy"},
                    {"question": "What is the largest ocean on Earth?", "options": ["Atlantic Ocean", "Indian Ocean", "Pacific Ocean", "Arctic Ocean"], "correct_answer": "Pacific Ocean", "explanation": "The Pacific Ocean is the largest ocean basin.", "difficulty": "medium"},
                    {"question": "Who wrote the play 'Romeo and Juliet'?", "options": ["Charles Dickens", "William Shakespeare", "Mark Twain", "Leo Tolstoy"], "correct_answer": "William Shakespeare", "explanation": "William Shakespeare wrote Romeo and Juliet.", "difficulty": "medium"},
                    {"question": "Which element has the atomic number 1 in the periodic table?", "options": ["Helium", "Hydrogen", "Oxygen", "Carbon"], "correct_answer": "Hydrogen", "explanation": "Hydrogen is the first element with atomic number 1.", "difficulty": "hard"}
                ]
            },
            "tech": {
                "true_false": [
                    {"question": "Linux is an open-source operating system.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Linux is famous for being open-source.", "difficulty": "easy"},
                    {"question": "RAM is a volatile memory that loses its contents when powered off.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "RAM requires electricity to store data.", "difficulty": "easy"},
                    {"question": "A Kilobyte consists of exactly 1000 bytes.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "In computing, 1 Kilobyte is equal to 1024 bytes.", "difficulty": "medium"},
                    {"question": "The first computer mouse was made of wood.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Doug Engelbart created the first mouse prototype out of wood in 1964.", "difficulty": "medium"},
                    {"question": "Symmetric key cryptography uses two different keys for encryption and decryption.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Symmetric cryptography uses the same key for both encryption and decryption.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Which company developed the Windows operating system?", "options": ["Apple", "Google", "Microsoft", "IBM"], "correct_answer": "Microsoft", "explanation": "Microsoft released Windows in 1985.", "difficulty": "easy"},
                    {"question": "What does CPU stand for?", "options": ["Computer Processing Unit", "Central Processing Unit", "Core Power Utility", "Central Printing Union"], "correct_answer": "Central Processing Unit", "explanation": "CPU stands for Central Processing Unit.", "difficulty": "easy"},
                    {"question": "What is the main circuit board of a computer called?", "options": ["CPU", "Motherboard", "Sound Card", "RAM Card"], "correct_answer": "Motherboard", "explanation": "The motherboard holds and connects all internal components.", "difficulty": "medium"},
                    {"question": "Which protocol is the secure version of HTTP?", "options": ["FTP", "HTTPS", "SMTP", "SSH"], "correct_answer": "HTTPS", "explanation": "HTTPS adds SSL/TLS encryption.", "difficulty": "medium"},
                    {"question": "What is the standard port number for the HTTP protocol?", "options": ["21", "80", "443", "8080"], "correct_answer": "80", "explanation": "HTTP default port is 80. HTTPS default port is 443.", "difficulty": "hard"}
                ]
            },
            "python": {
                "true_false": [
                    {"question": "Python is an interpreted language.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Python code is executed line-by-line by an interpreter.", "difficulty": "easy"},
                    {"question": "The 'def' keyword is used to declare a function in Python.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "def introduces a function definition.", "difficulty": "easy"},
                    {"question": "Lists in Python are immutable.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Lists are mutable (can be changed). Tuples are immutable.", "difficulty": "medium"},
                    {"question": "Variable names in Python can start with a number.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Variables cannot begin with digits.", "difficulty": "medium"},
                    {"question": "Python multiple inheritance resolves methods using Method Resolution Order (MRO).", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Yes, Python uses C3 linearization to resolve MRO.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Which keyword is used to define a function in Python?", "options": ["function", "define", "def", "func"], "correct_answer": "def", "explanation": "def is the keyword to start a function definition.", "difficulty": "easy"},
                    {"question": "Which function displays output to the screen?", "options": ["echo()", "printf()", "print()", "show()"], "correct_answer": "print()", "explanation": "print() prints a line of text.", "difficulty": "easy"},
                    {"question": "What data structure uses curly braces {} and stores key-value pairs?", "options": ["List", "Dictionary", "Tuple", "Set"], "correct_answer": "Dictionary", "explanation": "Dictionaries store key-value pairs.", "difficulty": "medium"},
                    {"question": "What is the output of len([1, 2, 3])?", "options": ["2", "3", "4", "Error"], "correct_answer": "3", "explanation": "The len() function returns the number of elements in the list.", "difficulty": "medium"},
                    {"question": "What is the correct syntax to slice a list 'my_list' from index 2 to 5 (exclusive)?", "options": ["my_list[2-5]", "my_list[2:5]", "my_list[2::5]", "my_list(2:5)"], "correct_answer": "my_list[2:5]", "explanation": "List slicing syntax is list[start:stop].", "difficulty": "hard"}
                ]
            },
            "ai": {
                "true_false": [
                    {"question": "Generative AI can create entirely new content like text, images, and music.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Generative AI models are designed to generate new original output.", "difficulty": "easy"},
                    {"question": "LLM stands for Large Language Model.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "LLM is the standard abbreviation for Large Language Model.", "difficulty": "easy"},
                    {"question": "GPT models are developed using recurrent neural networks (RNNs) as their primary architecture.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "GPT models are built on the Transformer architecture.", "difficulty": "medium"},
                    {"question": "A temperature parameter of 0 makes the LLM response more deterministic.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Lower temperature values result in less random, more predictable completions.", "difficulty": "medium"},
                    {"question": "Tokens in LLMs are always whole words.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Tokens can be sub-words, individual characters, or parts of words.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "What does GPT stand for in Generative AI?", "options": ["General Purpose Text", "Generative Pre-trained Transformer", "Global Processing Token", "Graphical Pattern Tool"], "correct_answer": "Generative Pre-trained Transformer", "explanation": "GPT stands for Generative Pre-trained Transformer.", "difficulty": "easy"},
                    {"question": "Which architecture is the foundation of modern Large Language Models?", "options": ["CNN", "RNN", "Transformer", "LSTM"], "correct_answer": "Transformer", "explanation": "The Transformer architecture, introduced in 2017, is the foundation of LLMs.", "difficulty": "easy"},
                    {"question": "What is it called when an AI model confidently generates incorrect or fabricated information?", "options": ["Dreaming", "Hallucination", "Drifting", "Blinking"], "correct_answer": "Hallucination", "explanation": "AI generation of incorrect info is termed hallucination.", "difficulty": "medium"},
                    {"question": "Which parameter controls the randomness of an LLM's output?", "options": ["Tokens", "Top-k", "Temperature", "Max Length"], "correct_answer": "Temperature", "explanation": "Temperature adjusts the probability distribution of predicted tokens.", "difficulty": "medium"},
                    {"question": "What training step comes after pre-training to align LLMs with human instructions?", "options": ["Tokenization", "Fine-tuning / RLHF", "Quantization", "Vectorization"], "correct_answer": "Fine-tuning / RLHF", "explanation": "Instruction fine-tuning and Reinforcement Learning from Human Feedback (RLHF) align the pre-trained model.", "difficulty": "hard"}
                ]
            },
            "space": {
                "true_false": [
                    {"question": "The sun is a star.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "The Sun is a yellow dwarf star at the center of our solar system.", "difficulty": "easy"},
                    {"question": "Mars is known as the Red Planet.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Mars appears red due to iron oxide (rust) on its surface.", "difficulty": "easy"},
                    {"question": "The Earth is the largest planet in our solar system.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Jupiter is the largest planet.", "difficulty": "medium"},
                    {"question": "Light takes about 8 minutes to travel from the Sun to Earth.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Light travels at 300,000 km/s and takes around 8 minutes to cross the distance to Earth.", "difficulty": "medium"},
                    {"question": "A light-year is a unit of time.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "A light-year is a unit of distance, not time.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Which is the hottest planet in our solar system?", "options": ["Mercury", "Venus", "Mars", "Jupiter"], "correct_answer": "Venus", "explanation": "Venus has a thick greenhouse atmosphere that traps heat, making it hotter than Mercury.", "difficulty": "easy"},
                    {"question": "Which planet is famous for its beautiful rings?", "options": ["Neptune", "Uranus", "Saturn", "Mars"], "correct_answer": "Saturn", "explanation": "Saturn is well-known for its extensive ring system.", "difficulty": "easy"},
                    {"question": "What is the name of our galaxy?", "options": ["Andromeda", "Milky Way", "Triangulum", "Sombrero"], "correct_answer": "Milky Way", "explanation": "We reside in the Milky Way galaxy.", "difficulty": "medium"},
                    {"question": "Which is the closest star to Earth after the Sun?", "options": ["Sirius", "Proxima Centauri", "Betelgeuse", "Polaris"], "correct_answer": "Proxima Centauri", "explanation": "Proxima Centauri is the closest star at 4.24 light-years.", "difficulty": "medium"},
                    {"question": "What is the boundary surrounding a black hole from which nothing can escape?", "options": ["Singularity", "Event Horizon", "Accretion Disk", "Wormhole"], "correct_answer": "Event Horizon", "explanation": "The Event Horizon is the point of no return for matter and light.", "difficulty": "hard"}
                ]
            },
            "history": {
                "true_false": [
                    {"question": "Mahatma Gandhi led the Salt March in 1930.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "The Dandi march (Salt Satyagraha) occurred in March-April 1930.", "difficulty": "easy"},
                    {"question": "The Taj Mahal was built by Emperor Akbar.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Taj Mahal was built by Shah Jahan.", "difficulty": "easy"},
                    {"question": "India gained independence from British rule in 1947.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "Independence Day is celebrated on 15 August 1947.", "difficulty": "medium"},
                    {"question": "Ashoka was a famous ruler of the Gupta Empire.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Ashoka was a ruler of the Maurya Empire.", "difficulty": "medium"},
                    {"question": "The Battle of Plassey took place in 1757.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "The battle occurred in June 1757, laying foundations for British rule.", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Who was the first Prime Minister of independent India?", "options": ["Mahatma Gandhi", "Jawaharlal Nehru", "Sardar Patel", "Dr. B.R. Ambedkar"], "correct_answer": "Jawaharlal Nehru", "explanation": "Jawaharlal Nehru took office on August 15, 1947.", "difficulty": "easy"},
                    {"question": "Which Mughal Emperor built the Taj Mahal?", "options": ["Akbar", "Jahangir", "Shah Jahan", "Aurangzeb"], "correct_answer": "Shah Jahan", "explanation": "Shah Jahan commissioned it in memory of his wife Mumtaz Mahal.", "difficulty": "easy"},
                    {"question": "Who was the founder of the Maurya Empire?", "options": ["Chandragupta Maurya", "Ashoka", "Samudragupta", "Harsha"], "correct_answer": "Chandragupta Maurya", "explanation": "Chandragupta Maurya founded the empire with Chanakya's guidance.", "difficulty": "medium"},
                    {"question": "Which freedom fighter is known as the 'Iron Man of India'?", "options": ["Subhas Chandra Bose", "Sardar Vallabhbhai Patel", "Bhagat Singh", "Lala Lajpat Rai"], "correct_answer": "Sardar Vallabhbhai Patel", "explanation": "Sardar Patel is known as the Iron Man for his role in integrating princely states.", "difficulty": "medium"},
                    {"question": "In which year did the First War of Indian Independence (Sepoy Mutiny) occur?", "options": ["1857", "1757", "1919", "1942"], "correct_answer": "1857", "explanation": "The rebellion began in Meerut in 1857.", "difficulty": "hard"}
                ]
            }
        },
        "hindi": {
            "html": {
                "true_false": [
                    {"question": "HTML एक प्रोग्रामिंग भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "HTML एक मार्कअप भाषा है जो वेब पेज की संरचना बनाती है, प्रोग्रामिंग भाषा नहीं।", "difficulty": "easy"},
                    {"question": "HTML का पूर्ण रूप Hyper Text Markup Language है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "HTML का सही और पूर्ण नाम Hyper Text Markup Language है।", "difficulty": "easy"},
                    {"question": "<img> टैग को क्लोजिंग </img> टैग की आवश्यकता होती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "<img> टैग एक सेल्फ-क्लोजिंग (एम्प्टी) टैग है।", "difficulty": "medium"},
                    {"question": "HTML5 वेब मानकों का सबसे नवीनतम संस्करण है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "HTML5 वर्तमान में आधिकारिक वेब मानक का मुख्य संस्करण है।", "difficulty": "medium"},
                    {"question": "HTML दस्तावेज़ में मुख्य सामग्री <body> टैग के अंदर लिखी जाती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "ब्राउज़र पर दिखने वाली सभी सामग्री <body> टैग में होती है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "HTML का पूर्ण रूप क्या है?", "options": ["Hyper Text Markup Language", "High Text Markup Language", "Hyper Text Media Language", "None of these"], "correct_answer": "Hyper Text Markup Language", "explanation": "HTML का अर्थ Hyper Text Markup Language है।", "difficulty": "easy"},
                    {"question": "HTML में सबसे बड़ा हेडिंग टैग कौन सा है?", "options": ["<h1>", "<h6>", "<head>", "<heading>"], "correct_answer": "<h1>", "explanation": "HTML में <h1> सबसे बड़ा और <h6> सबसे छोटा हेडिंग टैग है।", "difficulty": "easy"},
                    {"question": "वेब पेज पर हाइपरलिंक बनाने के लिए किस टैग का उपयोग किया जाता है?", "options": ["<a>", "<link>", "<href>", "<nav>"], "correct_answer": "<a>", "explanation": "एंकर टैग <a> का उपयोग हाइपरलिंक बनाने के लिए किया जाता है।", "difficulty": "medium"},
                    {"question": "HTML में लाइन ब्रेक देने के लिए किस टैग का उपयोग होता है?", "options": ["<br>", "<lb>", "<break>", "<hr>"], "correct_answer": "<br>", "explanation": "<br> टैग टेक्स्ट में नई लाइन जोड़ने के लिए उपयोग किया जाता है।", "difficulty": "medium"},
                    {"question": "HTML में ड्रॉपडाउन मेनू बनाने के लिए किस टैग का उपयोग किया जाता है?", "options": ["<select>", "<dropdown>", "<list>", "<input>"], "correct_answer": "<select>", "explanation": "<select> टैग और <option> का उपयोग ड्रॉपडाउन सूची बनाने में होता है।", "difficulty": "hard"}
                ]
            },
            "css": {
                "true_false": [
                    {"question": "CSS का उपयोग वेब पेज को स्टाइल और डिज़ाइन करने के लिए किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, CSS (Cascading Style Sheets) का मुख्य काम पेज को सुंदर और व्यवस्थित बनाना है।", "difficulty": "easy"},
                    {"question": "इनलाइन CSS की प्राथमिकता एक्सटर्नल CSS से अधिक होती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, इनलाइन स्टाइल सबसे विशिष्ट होने के कारण प्राथमिकता में ऊपर रहता है।", "difficulty": "easy"},
                    {"question": "CSS में क्लास सेलेक्टर को हैश (#) चिह्न से दर्शाया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "क्लास सेलेक्टर को डॉट (.) से और ID सेलेक्टर को हैश (#) से दर्शाते हैं।", "difficulty": "medium"},
                    {"question": "Flexbox लेआउट 1-डायमेंशनल लेआउट सिस्टम है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "फ्लेक्सबॉक्स एक समय में एक दिशा (पंक्ति या स्तंभ) में काम करता है।", "difficulty": "medium"},
                    {"question": "CSS Grid का उपयोग केवल 1-डायमेंशनल लेआउट बनाने के लिए किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "CSS Grid एक 2-डायमेंशनल (पंक्ति और स्तंभ दोनों) लेआउट सिस्टम है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "CSS का पूर्ण रूप क्या है?", "options": ["Cascading Style Sheets", "Computer Style Sheets", "Creative Style Sheets", "Colorful Style Sheets"], "correct_answer": "Cascading Style Sheets", "explanation": "CSS का अर्थ Cascading Style Sheets है।", "difficulty": "easy"},
                    {"question": "टेक्स्ट का रंग बदलने के लिए किस CSS प्रॉपर्टी का उपयोग किया जाता है?", "options": ["color", "font-color", "text-color", "background-color"], "correct_answer": "color", "explanation": "टेक्स्ट के फ़ॉन्ट रंग को बदलने के लिए 'color' प्रॉपर्टी का उपयोग होता है।", "difficulty": "easy"},
                    {"question": "CSS में ID सेलेक्टर का चयन करने के लिए किस चिह्न का उपयोग होता है?", "options": ["#", ".", "*", "@"], "correct_answer": "#", "explanation": "ID सेलेक्टर के लिए # (हैश) चिह्न का उपयोग किया जाता है।", "difficulty": "medium"},
                    {"question": "तत्व के चारों ओर बाहरी खाली जगह (outer spacing) जोड़ने के लिए क्या उपयोग होता है?", "options": ["margin", "padding", "border", "gap"], "correct_answer": "margin", "explanation": "मार्जिन बॉर्डर के बाहर खाली जगह जोड़ता है, जबकि पैडिंग बॉर्डर के अंदर।", "difficulty": "medium"},
                    {"question": "तत्वों के स्टैकिंग ऑर्डर (आगे-पीछे का स्तर) को नियंत्रित करने के लिए किस प्रॉपर्टी का उपयोग होता है?", "options": ["z-index", "stack-order", "position-index", "display-order"], "correct_answer": "z-index", "explanation": "z-index प्रॉपर्टी तय करती है कि कौन सा एलिमेंट स्क्रीन पर ऊपर दिखेगा।", "difficulty": "hard"}
                ]
            },
            "javascript": {
                "true_false": [
                    {"question": "जावास्क्रिप्ट एक केस-सेंसिटिव भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, जावास्क्रिप्ट में 'myVar' और 'myvar' दो अलग-अलग वेरिएबल माने जाते हैं।", "difficulty": "easy"},
                    {"question": "जावास्क्रिप्ट केवल ब्राउज़र पर चल सकती है, सर्वर पर नहीं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Node.js की मदद से जावास्क्रिप्ट सर्वर साइड पर भी आसानी से चलती है।", "difficulty": "easy"},
                    {"question": "=== ऑपरेटर वैल्यू और डेटा टाइप दोनों की समानता की जाँच करता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "=== सख्त समानता ऑपरेटर है जो टाइप और वैल्यू दोनों की जाँच करता है।", "difficulty": "medium"},
                    {"question": "जावास्क्रिप्ट और जावा दोनों एक ही प्रोग्रामिंग भाषा हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "जावा और जावास्क्रिप्ट दोनों पूरी तरह से अलग-अलग भाषाएं हैं।", "difficulty": "medium"},
                    {"question": "जावास्क्रिप्ट सिंगल-थ्रेडेड प्रोग्रामिंग भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "जावास्क्रिप्ट सिंगल थ्रेडेड है और इवेंट लूप की मदद से एसिंक्रोनस काम करती है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "जावास्क्रिप्ट में ब्लॉक-स्कोप वेरिएबल घोषित करने के लिए कौन सा कीवर्ड उपयुक्त है?", "options": ["let", "var", "function", "define"], "correct_answer": "let", "explanation": "let और const ब्लॉक-स्कोप होते हैं, जबकि var फंक्शन-स्कोप होता है।", "difficulty": "easy"},
                    {"question": "जावास्क्रिप्ट में कंसोल पर संदेश प्रिंट करने के लिए क्या उपयोग होता है?", "options": ["console.log()", "print()", "system.out.print()", "echo()"], "correct_answer": "console.log()", "explanation": "ब्राउज़र या नोड कंसोल पर आउटपुट देखने के लिए console.log() का उपयोग होता है।", "difficulty": "easy"},
                    {"question": "जावास्क्रिप्ट में किसी वेरिएबल का प्रकार (Data Type) जानने के लिए किस ऑपरेटर का उपयोग होता है?", "options": ["typeof", "type", "instanceof", "checkType"], "correct_answer": "typeof", "explanation": "typeof ऑपरेटर किसी वेरिएबल का डेटा टाइप बताता है।", "difficulty": "medium"},
                    {"question": "जावास्क्रिप्ट में ऐरे (Array) की लंबाई जानने के लिए किस प्रॉपर्टी का उपयोग किया जाता है?", "options": ["length", "size", "count", "len"], "correct_answer": "length", "explanation": "array.length से ऐरे में मौजूद तत्वों की कुल संख्या मिलती है।", "difficulty": "medium"},
                    {"question": "जावास्क्रिप्ट में कौन सा फंक्शन स्ट्रिंग को पूर्णांक (Integer) में बदलता है?", "options": ["parseInt()", "toInteger()", "Number.integer()", "castInt()"], "correct_answer": "parseInt()", "explanation": "parseInt() स्ट्रिंग को पार्स करके इंटीजर नंबर लौटाता है।", "difficulty": "hard"}
                ]
            },
            "python": {
                "true_false": [
                    {"question": "Python एक इंटरप्रिटेड (Interpreted) भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, पायथन कोड लाइन-दर-लाइन इंटरप्रिटर द्वारा निष्पादित होता है।", "difficulty": "easy"},
                    {"question": "Python में कोड ब्लॉक दर्शाने के लिए इंडेंटेशन (स्पेसिंग) अनिवार्य है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "पायथन में घुंघराले ब्रैकेट {} की जगह इंडेंटेशन का उपयोग किया जाता है।", "difficulty": "easy"},
                    {"question": "Python में टपल (Tuple) को परिभाषित करने के बाद बदला (Mutable) जा सकता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "टपल इम्यूटेबल (अपरिवर्तनीय) होते हैं, इन्हें बदला नहीं जा सकता।", "difficulty": "medium"},
                    {"question": "Python में फंक्शन बनाने के लिए 'function' कीवर्ड का उपयोग किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "पायथन में फंक्शन को 'def' कीवर्ड से परिभाषित किया जाता है।", "difficulty": "medium"},
                    {"question": "Python बहु-विरासत (Multiple Inheritance) का समर्थन करती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, एक पायथन क्लास एक से अधिक बेस क्लास से इनहेरिट कर सकती है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "Python में स्क्रीन पर आउटपुट प्रिंट करने के लिए किस फंक्शन का उपयोग किया जाता है?", "options": ["print()", "echo()", "printf()", "console.log()"], "correct_answer": "print()", "explanation": "पायथन में संदेश प्रदर्शित करने के लिए print() फंक्शन का उपयोग होता है।", "difficulty": "easy"},
                    {"question": "Python में सिंगल लाइन कमेंट लिखने के लिए किस प्रतीक का उपयोग किया जाता है?", "options": ["#", "//", "/* */", "<!-- -->"], "correct_answer": "#", "explanation": "पायथन में सिंगल लाइन कमेंट के लिए # प्रतीक का उपयोग होता है।", "difficulty": "easy"},
                    {"question": "Python में लिस्ट (List) बनाने के लिए किस ब्रैकेट का उपयोग होता है?", "options": ["[] (Square Brackets)", "() (Parentheses)", "{} (Curly Braces)", "<> (Angle Brackets)"], "correct_answer": "[] (Square Brackets)", "explanation": "लिस्ट के लिए चौकोर ब्रैकेट [] और टपल के लिए गोल ब्रैकेट () का उपयोग होता है।", "difficulty": "medium"},
                    {"question": "Python में डिक्शनरी में 'key-value' जोड़े होते हैं। इसे किस ब्रैकेट से बनाया जाता है?", "options": ["{}", "[]", "()", "||"], "correct_answer": "{}", "explanation": "डिक्शनरी और सेट को कर्ली ब्रेसेस {} से परिभाषित किया जाता है।", "difficulty": "medium"},
                    {"question": "Python में फाइल को सुरक्षित रूप से खोलने और स्वतः बंद करने के लिए किस स्टेटमेंट का उपयोग होता है?", "options": ["with open()", "try open()", "file.auto()", "open.close()"], "correct_answer": "with open()", "explanation": "with स्टेटमेंट संदर्भ प्रबंधक के रूप में फाइल को काम खत्म होने पर स्वतः बंद कर देता है।", "difficulty": "hard"}
                ]
            },
            "ai": {
                "true_false": [
                    {"question": "LLM का पूर्ण रूप Large Language Model है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, LLM का पूर्ण रूप Large Language Model होता है।", "difficulty": "easy"},
                    {"question": "आर्टिफिशियल न्यूरल नेटवर्क मानव मस्तिष्क की कार्यप्रणाली से प्रेरित हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, कृत्रिम न्यूरॉन्स मानव दिमाग के जैविक न्यूरॉन्स के मॉडल पर आधारित हैं।", "difficulty": "easy"},
                    {"question": "Generative AI नए प्रकार का टेक्स्ट, चित्र और कोड उत्पन्न कर सकता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, जनरेटिव एआई मॉडल नया और मौलिक कंटेंट बनाने के लिए प्रशिक्षित होते हैं।", "difficulty": "easy"},
                    {"question": "पर्यवेक्षित शिक्षण (Supervised Learning) में डेटा बिना किसी लेबल के होता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "पर्यवेक्षित शिक्षण में लेबल किए गए डेटा (इनपुट और सही आउटपुट) की आवश्यकता होती है।", "difficulty": "medium"},
                    {"question": "डीप लर्निंग (Deep Learning) मशीन लर्निंग का ही एक उपसमूह (Subset) है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "AI के अंदर ML आता है, और ML के अंदर Deep Learning आता है।", "difficulty": "medium"},
                    {"question": "मशीन लर्निंग मॉडल का प्रशिक्षण केवल CPU पर ही संभव है, GPU पर नहीं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "GPU और TPU बड़े मॉडलों के समानांतर प्रशिक्षण के लिए सबसे अधिक उपयोग किए जाते हैं।", "difficulty": "medium"},
                    {"question": "NLP का पूर्ण रूप Natural Language Processing है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, NLP कंप्यूटर को मानव भाषा समझने और प्रोसेस करने में सक्षम बनाता है।", "difficulty": "easy"},
                    {"question": "Transformer आर्किटेक्चर को सबसे पहले 2017 में 'Attention Is All You Need' पेपर में पेश किया गया था।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, गूगल के शोधकर्ताओं ने 2017 में ट्रांसफॉर्मर आर्किटेक्चर पेश किया था।", "difficulty": "hard"},
                    {"question": "Overfitting तब होती है जब मॉडल ट्रेनिंग डेटा पर बहुत अच्छा और नए डेटा पर खराब प्रदर्शन करता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, ओवरफिटिंग में मॉडल ट्रेनिंग डेटा को रट लेता है जिससे वह नए डेटा पर असफल होता है।", "difficulty": "hard"},
                    {"question": "कंप्यूटर विज़न में ऑब्जेक्ट डिटेक्शन के लिए YOLO (You Only Look Once) एक प्रसिद्ध मॉडल है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, YOLO रियल-टाइम ऑब्जेक्ट डिटेक्शन के लिए अत्यधिक लोकप्रिय है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "AI का पूर्ण रूप क्या है?", "options": ["Artificial Intelligence", "Active Intelligence", "Automated Information", "Advanced Integration"], "correct_answer": "Artificial Intelligence", "explanation": "AI का पूरा नाम Artificial Intelligence (कृत्रिम बुद्धिमत्ता) है।", "difficulty": "easy"},
                    {"question": "आधुनिक Large Language Models (LLMs) की मुख्य नींव कौन सा आर्किटेक्चर है?", "options": ["Transformer", "CNN", "RNN", "Decision Trees"], "correct_answer": "Transformer", "explanation": "ट्रांसफॉर्मर आर्किटेक्चर और 'Self-Attention' मेकैनिज्म आधुनिक LLMs का आधार है।", "difficulty": "easy"},
                    {"question": "ChatGPT को किस कंपनी ने विकसित किया है?", "options": ["OpenAI", "Google", "Microsoft", "Meta"], "correct_answer": "OpenAI", "explanation": "ChatGPT को OpenAI कंपनी द्वारा विकसित किया गया है।", "difficulty": "easy"},
                    {"question": "कंप्यूटर विज़न में छवियों के वर्गीकरण के लिए सबसे लोकप्रिय न्यूरल नेटवर्क कौन सा है?", "options": ["CNN", "RNN", "ANN", "KNN"], "correct_answer": "CNN", "explanation": "कन्वोल्यूशनल न्यूरल नेटवर्क (CNN) इमेज और वीडियो प्रोसेसिंग के लिए प्रसिद्ध है।", "difficulty": "medium"},
                    {"question": "जब AI मॉडल आत्मविश्वास के साथ गलत या मनगढ़ंत जानकारी देता है, तो इसे क्या कहा जाता है?", "options": ["Hallucination", "Overfitting", "Drifting", "Gradient Descent"], "correct_answer": "Hallucination", "explanation": "एआई द्वारा गलत तथ्य प्रस्तुत करने को Hallucination कहा जाता है।", "difficulty": "medium"},
                    {"question": "Reinforcement Learning में एजेंट पर्यावरण से सीखने के लिए किस पर निर्भर करता है?", "options": ["पुरस्कार और दंड (Rewards & Penalties)", "लेबल किए गए चित्र", "SQL क्वेरी", "मैन्युअल कोडिंग"], "correct_answer": "पुरस्कार और दंड (Rewards & Penalties)", "explanation": "सुदृढ़ीकरण शिक्षण में एजेंट सही कदम पर रिवॉर्ड और गलत कदम पर पेनाल्टी से सीखता है।", "difficulty": "medium"},
                    {"question": "Python में मशीन लर्निंग और डीप लर्निंग के लिए सबसे लोकप्रिय लाइब्रेरी कौन सी है?", "options": ["PyTorch / TensorFlow", "Tkinter", "Flask", "BeautifulSoup"], "correct_answer": "PyTorch / TensorFlow", "explanation": "PyTorch और TensorFlow डीप लर्निंग मॉडल बनाने के प्रमुख फ्रेमवर्क हैं।", "difficulty": "medium"},
                    {"question": "AI मॉडल में प्रॉम्ट को बेहतर बनाकर सटीक उत्तर प्राप्त करने की कला को क्या कहते हैं?", "options": ["Prompt Engineering", "Feature Scaling", "Data Normalization", "Web Scraping"], "correct_answer": "Prompt Engineering", "explanation": "प्रॉम्प्ट इंजीनियरिंग एआई से सर्वश्रेष्ठ परिणाम प्राप्त करने के लिए निर्देश तैयार करने की कला है।", "difficulty": "easy"},
                    {"question": "Google द्वारा विकसित प्रमुख AI मॉडल परिवार का नाम क्या है?", "options": ["Gemini", "Claude", "LLaMA", "DeepSeek"], "correct_answer": "Gemini", "explanation": "Gemini गूगल का अत्याधुनिक मल्टीमॉडल AI मॉडल परिवार है।", "difficulty": "easy"},
                    {"question": "न्यूरल नेटवर्क में वेट्स (Weights) को अपडेट करने के लिए कौन सा ऑप्टिमाइज़र सबसे व्यापक रूप से उपयोग होता है?", "options": ["Adam", "Linear Search", "Bubble Sort", "Dijkstra"], "correct_answer": "Adam", "explanation": "Adam (Adaptive Moment Estimation) ग्रेडिएंट आधारित सबसे लोकप्रिय ऑप्टिमाइज़र है।", "difficulty": "hard"},
                    {"question": "RAG का पूर्ण रूप AI और LLM शब्दावली में क्या है?", "options": ["Retrieval-Augmented Generation", "Random Auto Generator", "Recursive Action Graph", "Rapid Analysis Grid"], "correct_answer": "Retrieval-Augmented Generation", "explanation": "RAG बाहरी डेटाबेस से प्रासंगिक जानकारी खोजकर LLM को सटीक उत्तर देने में सक्षम बनाता है।", "difficulty": "hard"},
                    {"question": "मशीन लर्निंग मॉडल में 'Epoch' शब्द का क्या अर्थ है?", "options": ["पूरे ट्रेनिंग डेटासेट का एक पूरा चक्कर", "एक समय में प्रोसेस होने वाले डेटा का आकार", "लर्निंग रेट का मान", "एरर का प्रतिशत"], "correct_answer": "पूरे ट्रेनिंग डेटासेट का एक पूरा चक्कर", "explanation": "एक Epoch का अर्थ है जब पूरा डेटासेट एक बार न्यूरल नेटवर्क से आगे और पीछे गुजरता है।", "difficulty": "hard"}
                ]
            },
            "tech": {
                "true_false": [
                    {"question": "RAM एक वोलाटाइल (अस्थायी) मेमोरी है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, कंप्यूटर बंद होते ही RAM में मौजूद सारा डेटा नष्ट हो जाता है।", "difficulty": "easy"},
                    {"question": "SSD, पारंपरिक HDD की तुलना में बहुत तेज़ गति प्रदान करती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, सॉलिड स्टेट ड्राइव (SSD) में कोई मूविंग पार्ट नहीं होता और यह तेज़ होती है।", "difficulty": "easy"},
                    {"question": "ऑपरेटिंग सिस्टम एक एप्लिकेशन सॉफ्टवेयर का उदाहरण है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "ऑपरेटिंग सिस्टम एक 'सिस्टम सॉफ्टवेयर' है, एप्लिकेशन सॉफ्टवेयर नहीं।", "difficulty": "medium"},
                    {"question": "HTTPS में 'S' का अर्थ 'Secure' (सुरक्षित) होता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "HTTPS का मतलब Hypertext Transfer Protocol Secure है।", "difficulty": "medium"},
                    {"question": "IPv6 पता 128 बिट्स लंबा होता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "IPv4 32 बिट्स का होता है जबकि IPv6 128 बिट्स का होता है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "कंप्यूटर का 'मस्तिष्क' (Brain) किसे कहा जाता है?", "options": ["CPU", "RAM", "Hard Disk", "Monitor"], "correct_answer": "CPU", "explanation": "सेंट्रल प्रोसेसिंग यूनिट (CPU) को कंप्यूटर का दिमाग कहा जाता है।", "difficulty": "easy"},
                    {"question": "कंप्यूटर का मुख्य सर्किट बोर्ड कौन सा है जिससे सभी घटक जुड़ते हैं?", "options": ["Motherboard", "Graphic Card", "Hard Drive", "Power Supply"], "correct_answer": "Motherboard", "explanation": "मदरबोर्ड मुख्य बोर्ड है जो सीपीयू, रैम और अन्य हिस्सों को जोड़ता है।", "difficulty": "easy"},
                    {"question": "इंटरनेट पर सुरक्षित डेटा संचार के लिए किस प्रोटोकॉल का उपयोग किया जाता है?", "options": ["HTTPS", "FTP", "SMTP", "Telnet"], "correct_answer": "HTTPS", "explanation": "HTTPS एन्क्रिप्शन का उपयोग करके सुरक्षित ब्राउज़िंग सुनिश्चित करता है।", "difficulty": "medium"},
                    {"question": "कंप्यूटर डेटा की सबसे छोटी इकाई कौन सी है?", "options": ["Bit", "Byte", "Kilobyte", "Nibble"], "correct_answer": "Bit", "explanation": "एक बिट (0 या 1) कंप्यूटर डेटा की सबसे छोटी इकाई है। 8 बिट = 1 बाइट।", "difficulty": "medium"},
                    {"question": "DNS का पूर्ण रूप क्या है?", "options": ["Domain Name System", "Dynamic Network Service", "Digital Name Server", "Data Node Security"], "correct_answer": "Domain Name System", "explanation": "DNS डोमेन नाम को IP पते में अनुवादित करता है।", "difficulty": "hard"}
                ]
            },
            "cricket": {
                "true_false": [
                    {"question": "वनडे क्रिकेट विश्व कप हर चार साल में आयोजित किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, ICC पुरुष क्रिकेट विश्व कप प्रत्येक चार वर्ष में होता है।", "difficulty": "easy"},
                    {"question": "टी20 मैच में प्रत्येक टीम को अधिकतम 20 ओवर खेलने को मिलते हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, टी20 का अर्थ ही बीस-बीस ओवरों का मैच होता है।", "difficulty": "easy"},
                    {"question": "क्रिकेट में LBW का पूर्ण रूप 'Leg Before Wicket' है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, जब गेंद विकेट के आगे पैर पर लगती है तो LBW आउट दिया जाता है।", "difficulty": "medium"},
                    {"question": "भारत ने अपना पहला क्रिकेट विश्व कप 2011 में जीता था।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "भारत ने पहला विश्व कप 1983 में कपिल देव की कप्तानी में जीता था।", "difficulty": "medium"},
                    {"question": "टेस्ट क्रिकेट में फॉलो-ऑन देने के लिए पहली पारी में कम से कम 200 रनों की बढ़त आवश्यक है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "5 दिवसीय टेस्ट में 200 रन या अधिक की बढ़त पर फॉलो-ऑन दिया जा सकता है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "क्रिकेट में 'शतक' का क्या अर्थ है?", "options": ["100 रन", "50 रन", "150 रन", "200 रन"], "correct_answer": "100 रन", "explanation": "क्रिकेट में किसी बल्लेबाज द्वारा 100 रन बनाना शतक कहलाता है।", "difficulty": "easy"},
                    {"question": "क्रिकेट के एक ओवर में कितनी वैध गेंदें फेंकी जाती हैं?", "options": ["6", "5", "8", "4"], "correct_answer": "6", "explanation": "एक मानक क्रिकेट ओवर में 6 वैध गेंदें होती हैं।", "difficulty": "easy"},
                    {"question": "2023 आईसीसी पुरुष क्रिकेट विश्व कप का खिताब किस देश ने जीता?", "options": ["ऑस्ट्रेलिया", "भारत", "इंग्लैंड", "दक्षिण अफ्रीका"], "correct_answer": "ऑस्ट्रेलिया", "explanation": "ऑस्ट्रेलिया ने 2023 के फाइनल में भारत को हराकर विश्व कप जीता था।", "difficulty": "medium"},
                    {"question": "विश्व क्रिकेट में 'क्रिकेट का भगवान' किसे कहा जाता है?", "options": ["सचिन तेंदुलकर", "विराट कोहली", "एमएस धोनी", "कपिल देव"], "correct_answer": "सचिन तेंदुलकर", "explanation": "सचिन तेंदुलकर को उनके असाधारण रिकॉर्ड के लिए यह उपाधि दी गई है।", "difficulty": "medium"},
                    {"question": "क्रिकेट की वैश्विक सर्वोच्च नियामक संस्था कौन सी है?", "options": ["ICC", "BCCI", "FIFA", "IOC"], "correct_answer": "ICC", "explanation": "इंटरनेशनल क्रिकेट काउंसिल (ICC) क्रिकेट की शीर्ष संस्था है।", "difficulty": "hard"}
                ]
            },
            "sports": {
                "true_false": [
                    {"question": "फुटबॉल की एक टीम में मैदान पर 11 खिलाड़ी होते हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, प्रत्येक फुटबॉल टीम में मैदान पर 11 खिलाड़ी खेलते हैं।", "difficulty": "easy"},
                    {"question": "ग्रीष्मकालीन ओलंपिक खेल प्रत्येक 4 वर्ष में आयोजित किए जाते हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, ओलंपिक खेल चार वर्ष के अंतराल पर आयोजित होते हैं।", "difficulty": "easy"},
                    {"question": "नीरज चोपड़ा बैडमिंटन खेल से संबंधित हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "नीरज चोपड़ा भाला फेंक (Javelin Throw) के ओलंपिक स्वर्ण पदक विजेता हैं।", "difficulty": "medium"},
                    {"question": "टेनिस में स्कोर '0' को 'Love' कहा जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, टेनिस स्कोरिंग प्रणाली में शून्य स्कोर को Love कहा जाता है।", "difficulty": "medium"},
                    {"question": "शतरंज की बिसात पर कुल 64 वर्ग (खानें) होते हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "शतरंज बोर्ड 8x8 ग्रिड का होता है जिसमें कुल 64 सफेद और काले वर्ग होते हैं।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "2022 फीफा फुटबॉल विश्व कप की विजेता टीम कौन सी थी?", "options": ["आर्जेन्टीना", "फ्रांस", "ब्राजील", "क्रोएशिया"], "correct_answer": "आर्जेन्टीना", "explanation": "लियोनेल मेस्सी की कप्तानी में आर्जेन्टीना ने विश्व कप जीता था।", "difficulty": "easy"},
                    {"question": "भारत का राष्ट्रीय खेल पारंपरिक रूप से किसे माना जाता है?", "options": ["हॉकी", "क्रिकेट", "कबड्डी", "फुटबॉल"], "correct_answer": "हॉकी", "explanation": "भारत में फील्ड हॉकी को पारंपरिक रूप से राष्ट्रीय खेल का दर्जा दिया जाता है।", "difficulty": "easy"},
                    {"question": "एक मानक मैराथन दौड़ की कुल दूरी कितनी होती है?", "options": ["42.195 किमी", "21.1 किमी", "50 किमी", "10 किमी"], "correct_answer": "42.195 किमी", "explanation": "मैराथन की आधिकारिक दूरी 42.195 किलोमीटर (26.2 मील) होती है।", "difficulty": "medium"},
                    {"question": "बास्केटबॉल मैच में कोर्ट पर प्रत्येक टीम के कितने खिलाड़ी खेलते हैं?", "options": ["5", "6", "7", "11"], "correct_answer": "5", "explanation": "बास्केटबॉल में दोनों टीमों से 5-5 खिलाड़ी कोर्ट पर खेलते हैं।", "difficulty": "medium"},
                    {"question": "ओलंपिक ध्वज में कितने छल्ले (Rings) होते हैं?", "options": ["5", "4", "6", "7"], "correct_answer": "5", "explanation": "ये 5 छल्ले दुनिया के पांच महाद्वीपों के मिलन का प्रतीक हैं।", "difficulty": "hard"}
                ]
            },
            "gk": {
                "true_false": [
                    {"question": "माउंट एवरेस्ट दुनिया की सबसे ऊंची पर्वत चोटी है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, माउंट एवरेस्ट (8848.86 मीटर) दुनिया का सबसे ऊंचा शिखर है।", "difficulty": "easy"},
                    {"question": "भारत 15 अगस्त 1947 को ब्रिटिश शासन से स्वतंत्र हुआ था।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, 15 अगस्त को भारत अपना स्वतंत्रता दिवस मनाता है।", "difficulty": "easy"},
                    {"question": "क्षेत्रफल की दृष्टि से भारत दुनिया का सबसे बड़ा देश है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "क्षेत्रफल में रूस दुनिया का सबसे बड़ा देश है, भारत सातवें स्थान पर है।", "difficulty": "medium"},
                    {"question": "भारतीय संविधान के मुख्य निर्माता डॉ. बी.आर. अंबेडकर थे।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "डॉ. अंबेडकर संविधान सभा की प्रारूप समिति के अध्यक्ष थे।", "difficulty": "medium"},
                    {"question": "विश्व का सबसे बड़ा महासागर प्रशांत महासागर है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "प्रशांत महासागर पृथ्वी का सबसे विशाल और गहरा महासागर है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "भारत की राजधानी क्या है?", "options": ["नई दिल्ली", "मुंबई", "कोलकाता", "चेन्नई"], "correct_answer": "नई दिल्ली", "explanation": "नई दिल्ली भारत की आधिकारिक राजधानी है।", "difficulty": "easy"},
                    {"question": "भारत की राष्ट्रीय नदी कौन सी है?", "options": ["गंगा", "यमुना", "ब्रह्मपुत्र", "गोदावरी"], "correct_answer": "गंगा", "explanation": "गंगा भारत की राष्ट्रीय नदी और सबसे पवित्र मानी जाने वाली नदी है।", "difficulty": "easy"},
                    {"question": "विश्व का सबसे बड़ा महाद्वीप कौन सा है?", "options": ["एशिया", "अफ्रीका", "यूरोप", "उत्तरी अमेरिका"], "correct_answer": "एशिया", "explanation": "एशिया क्षेत्रफल और जनसंख्या दोनों में विश्व का सबसे बड़ा महाद्वीप है।", "difficulty": "medium"},
                    {"question": "भारत के राष्ट्रगान 'जन गण मन' के रचयिता कौन हैं?", "options": ["रवींद्रनाथ टैगोर", "बंकिम चंद्र चट्टोपाध्याय", "सरोजिनी नायडू", "सुभाष चंद्र बोस"], "correct_answer": "रवींद्रनाथ टैगोर", "explanation": "रवींद्रनाथ टैगोर ने भारत का राष्ट्रगान रचा था।", "difficulty": "medium"},
                    {"question": "संयुक्त राष्ट्र (UN) का मुख्यालय कहाँ स्थित है?", "options": ["न्यूयॉर्क", "जिनेवा", "लंदन", "पेरिस"], "correct_answer": "न्यूयॉर्क", "explanation": "संयुक्त राष्ट्र का मुख्य मुख्यालय न्यूयॉर्क शहर (USA) में स्थित है।", "difficulty": "hard"}
                ]
            },
            "space": {
                "true_false": [
                    {"question": "सूर्य हमारे सौरमंडल के केंद्र में स्थित एक तारा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, सूर्य एक मध्यम आकार का पीला तारा है जो सौरमंडल का केंद्र है।", "difficulty": "easy"},
                    {"question": "पृथ्वी सूर्य के चारों ओर एक चक्कर लगभग 365 दिन में पूरा करती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, पृथ्वी की एक परिक्रमा में लगभग 365.25 दिन लगते हैं।", "difficulty": "easy"},
                    {"question": "चंद्रमा का अपना स्वयं का प्रकाश होता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "चंद्रमा सूर्य के प्रकाश को परावर्तित करके चमकता है।", "difficulty": "medium"},
                    {"question": "शुक्र (Venus) हमारे सौरमंडल का सबसे गर्म ग्रह है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "घने कार्बन डाइऑक्साइड वातावरण के कारण शुक्र सबसे गर्म ग्रह है।", "difficulty": "medium"},
                    {"question": "प्रकाश की गति अंतरिक्ष में लगभग 3,00,000 किलोमीटर प्रति सेकंड होती है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, प्रकाश की गति लगभग 299,792 किमी/सेकंड होती है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "हमारे सौरमंडल का सबसे बड़ा ग्रह कौन सा है?", "options": ["बृहस्पति (Jupiter)", "शनि (Saturn)", "पृथ्वी (Earth)", "मंगल (Mars)"], "correct_answer": "बृहस्पति (Jupiter)", "explanation": "बृहस्पति सौरमंडल का सबसे विशाल और भारी ग्रह है।", "difficulty": "easy"},
                    {"question": "'लाल ग्रह' (Red Planet) के नाम से किस ग्रह को जाना जाता है?", "options": ["मंगल (Mars)", "बुध (Mercury)", "शुक्र (Venus)", "बृहस्पति (Jupiter)"], "correct_answer": "मंगल (Mars)", "explanation": "आयरन ऑक्साइड की उपस्थिति के कारण मंगल लाल दिखाई देता है।", "difficulty": "easy"},
                    {"question": "चंद्रमा की सतह पर कदम रखने वाले पहले मानव कौन थे?", "options": ["नील आर्मस्ट्रांग", "यूरी गगारिन", "बज़ एल्ड्रिन", "राकेश शर्मा"], "correct_answer": "नील आर्मस्ट्रांग", "explanation": "नील आर्मस्ट्रांग ने 1969 में अपोलो 11 मिशन के दौरान कदम रखा था।", "difficulty": "medium"},
                    {"question": "भारतीय अंतरिक्ष अनुसंधान संगठन (ISRO) का मुख्यालय कहाँ स्थित है?", "options": ["बेंगलुरु", "नई दिल्ली", "मुंबई", "श्रीहरिकोटा"], "correct_answer": "बेंगलुरु", "explanation": "इसरो का मुख्य प्रशासनिक मुख्यालय बेंगलुरु में स्थित है।", "difficulty": "medium"},
                    {"question": "हमारी अपनी आकाशगंगा का क्या नाम है?", "options": ["मिल्की वे (दुग्ध मेखला)", "एंड्रोमेडा", "व्हर्लपूल", "सोम्ब्रेरो"], "correct_answer": "मिल्की वे (दुग्ध मेखला)", "explanation": "हमारा सौरमंडल मिल्की वे (Milky Way) आकाशगंगा में स्थित है।", "difficulty": "hard"}
                ]
            },
            "history": {
                "true_false": [
                    {"question": "भारत ने 15 अगस्त 1947 को स्वतंत्रता प्राप्त की थी।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, भारत को 15 अगस्त 1947 को ब्रिटिश हुकूमत से आजादी मिली थी।", "difficulty": "easy"},
                    {"question": "सम्राट अशोक मौर्य वंश के महान शासक थे।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, सम्राट अशोक बिंदुसार के पुत्र और मौर्य वंश के सम्राट थे।", "difficulty": "easy"},
                    {"question": "प्लासी का ऐतिहासिक युद्ध 1757 में लड़ा गया था।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, रॉबर्ट क्लाइव और सिराजुद्दौला के बीच जून 1757 में प्लासी का युद्ध हुआ था।", "difficulty": "medium"},
                    {"question": "महात्मा गांधी ने दांडी नमक सत्याग्रह यात्रा 1942 में की थी।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "दांडी यात्रा 1930 में हुई थी, जबकि 1942 में भारत छोड़ो आंदोलन हुआ था।", "difficulty": "medium"},
                    {"question": "सिंधु घाटी सभ्यता एक कांस्य युगीन (Bronze Age) सभ्यता थी।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, हड़प्पा और सिंधु सभ्यता कांस्य युग की प्रमुख सभ्यताओं में गिनी जाती है।", "difficulty": "hard"}
                ],
                "mcq": [
                    {"question": "भारत के 'लौह पुरुष' (Iron Man) के रूप में किसे जाना जाता है?", "options": ["सरदार वल्लभभाई पटेल", "महात्मा गांधी", "जवाहरलाल नेहरू", "सुभाष चंद्र बोस"], "correct_answer": "सरदार वल्लभभाई पटेल", "explanation": "रियासतों के एकीकरण में महत्वपूर्ण भूमिका के कारण उन्हें लौह पुरुष कहा जाता है।", "difficulty": "easy"},
                    {"question": "स्वतंत्र भारत के प्रथम प्रधानमंत्री कौन थे?", "options": ["पंडित जवाहरलाल नेहरू", "डॉ. राजेंद्र प्रसाद", "सरदार पटेल", "लाल बहादुर शास्त्री"], "correct_answer": "पंडित जवाहरलाल नेहरू", "explanation": "पंडित जवाहरलाल नेहरू ने 15 अगस्त 1947 को प्रथम प्रधानमंत्री का पद संभाला था।", "difficulty": "easy"},
                    {"question": "आगरा में प्रसिद्ध ताजमहल का निर्माण किस मुगल बादशाह ने करवाया था?", "options": ["शाहजहाँ", "अकबर", "जहाँगीर", "बाबर"], "correct_answer": "शाहजहाँ", "explanation": "शाहजहाँ ने अपनी बेगम मुमताज महल की याद में ताजमहल बनवाया था।", "difficulty": "medium"},
                    {"question": "1857 का प्रथम भारतीय स्वतंत्रता संग्राम कहाँ से शुरू हुआ था?", "options": ["मेरठ", "झाँसी", "दिल्ली", "कानपुर"], "correct_answer": "मेरठ", "explanation": "10 मई 1857 को मेरठ छावनी से सिपाहियों ने विद्रोह शुरू किया था।", "difficulty": "medium"},
                    {"question": "मौर्य साम्राज्य की नींव चाणक्य की सहायता से किसने रखी थी?", "options": ["चंद्रगुप्त मौर्य", "अशोक", "बिंदुसार", "हर्षवर्धन"], "correct_answer": "चंद्रगुप्त मौर्य", "explanation": "चंद्रगुप्त मौर्य ने चाणक्य के मार्गदर्शन में मौर्य वंश स्थापित किया था।", "difficulty": "hard"}
                ]
            }
        }
    }
    
    # Get questions based on Language -> Topic -> Type
    lang_db = database.get(lang_lower, database["english"])
    topic_db = lang_db.get(topic_cat, lang_db.get("python", list(lang_db.values())[0]))
    
    if type_lower == "mixed":
        import random
        questions_list = topic_db.get("true_false", []) + topic_db.get("mcq", [])
        random.shuffle(questions_list)
    else:
        questions_list = topic_db.get(type_lower, topic_db.get("mcq", []))
    
    # Filter questions by difficulty
    difficulty_lower = difficulty.lower().strip()
    selected_questions = [q for q in questions_list if q.get("difficulty", "medium") == difficulty_lower]
    
    # If we need more unique questions, add questions of other difficulties from the same category
    if len(selected_questions) < count:
        other_difficulties = ["easy", "medium", "hard"]
        if difficulty_lower in other_difficulties:
            other_difficulties.remove(difficulty_lower)
        for diff in other_difficulties:
            extra = [q for q in questions_list if q.get("difficulty", "medium") == diff]
            for q in extra:
                if q not in selected_questions:
                    selected_questions.append(q)
                    if len(selected_questions) >= count:
                        break
            if len(selected_questions) >= count:
                break
                
    # If we still need more unique questions, pull from 'gk' (General Knowledge) category of the SAME language
    if len(selected_questions) < count:
        gk_db = lang_db.get("gk", {})
        if type_lower == "mixed":
            gk_questions = gk_db.get("true_false", []) + gk_db.get("mcq", [])
        else:
            gk_questions = gk_db.get(type_lower, gk_db.get("mcq", []))
            
        for q in gk_questions:
            if q not in selected_questions:
                selected_questions.append(q)
                if len(selected_questions) >= count:
                    break

    # If still not enough, fall back strictly within the SAME language first
    if len(selected_questions) < count:
        for cat_name, cat_data in lang_db.items():
            pool = cat_data.get(type_lower, cat_data.get("mcq", [])) if type_lower != "mixed" else (cat_data.get("true_false", []) + cat_data.get("mcq", []))
            for q in pool:
                if q not in selected_questions:
                    selected_questions.append(q)
                    if len(selected_questions) >= count:
                        break
            if len(selected_questions) >= count:
                break

    # Construct the final list. Cycle existing selected questions if needed
    output_questions = []
    if selected_questions:
        for i in range(count):
            output_questions.append(selected_questions[i % len(selected_questions)])
    else:
        fallback_pool = lang_db.get("gk", {}).get("mcq", database["english"]["python"]["mcq"])
        output_questions = [fallback_pool[i % len(fallback_pool)] for i in range(count)]
        
    return output_questions

def robust_json_extract_and_parse(raw_text):
    """
    Extracts and parses JSON from LLM output (Gemini / Groq / OpenAI),
    handling markdown fences, unescaped quotes, smart quotes, and partial outputs.
    """
    import json
    import re
    
    if not raw_text or not isinstance(raw_text, str):
        return []
        
    cleaned = raw_text.strip()
    
    # Strip markdown code blocks if present
    if cleaned.startswith("```"):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()
    
    # Replace smart quotes that break JSON parsing
    cleaned = cleaned.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    
    # Try standard json parse first
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["questions", "quiz", "data", "items", "results", "questions_list"]:
                if key in data and isinstance(data[key], list):
                    return data[key]
            # If dict itself has question key
            if "question" in data:
                return [data]
    except Exception:
        pass
        
    # Attempt to extract JSON array substring
    array_match = re.search(r'\[\s*\{.*\}\s*\]', cleaned, re.DOTALL)
    if array_match:
        try:
            data = json.loads(array_match.group(0))
            if isinstance(data, list):
                return data
        except Exception:
            pass

    # Attempt to extract JSON object substring with questions
    obj_match = re.search(r'\{\s*"questions"\s*:\s*\[.*\]\s*\}', cleaned, re.DOTALL)
    if obj_match:
        try:
            data = json.loads(obj_match.group(0))
            if isinstance(data, dict) and "questions" in data and isinstance(data["questions"], list):
                return data["questions"]
        except Exception:
            pass

    # Regex extraction of individual question objects as fallback
    extracted_qs = []
    # Match patterns like {"question": "...", ...}
    pattern = re.compile(r'\{\s*"question"\s*:\s*"(?:\\.|[^"\\])*"(?:[^{}]|"(?:\\.|[^"\\])*")*\}', re.DOTALL)
    matches = pattern.findall(cleaned)
    for m in matches:
        try:
            item = json.loads(m)
            if isinstance(item, dict) and "question" in item:
                extracted_qs.append(item)
        except Exception:
            # Try cleaning trailing commas
            m_fixed = re.sub(r',\s*([\}\]])', r'\1', m)
            try:
                item = json.loads(m_fixed)
                if isinstance(item, dict) and "question" in item:
                    extracted_qs.append(item)
            except Exception:
                continue

    return extracted_qs

def sanitize_and_validate_questions(questions, language="English", quiz_type="mcq", target_count=5, topic="General Knowledge", difficulty="medium"):
    """
    Sanitizes questions returned by AI models or mock generators:
    - Strips option markers like 'A. ', 'B) ', '1. ', 'क. ', '१. '
    - Normalizes dict / list option formats
    - Resolves single letter/index correct_answers ('A', 'B', '1', 'क', '१') to actual option strings
    - Ensures correct_answer strictly matches an item in options
    - Normalizes True/False options and answers to exact language labels
    - Guarantees full target_count questions by supplementing if needed
    """
    import re
    if not questions or not isinstance(questions, list):
        questions = []
    
    is_hindi = language.lower() == "hindi"
    t_label = "सत्य" if is_hindi else "True"
    f_label = "असत्य" if is_hindi else "False"
    
    letter_map = {
        "a": 0, "b": 1, "c": 2, "d": 3, "e": 4,
        "1": 0, "2": 1, "3": 2, "4": 3, "5": 4,
        "१": 0, "२": 1, "३": 2, "४": 3, "५": 4,
        "क": 0, "ख": 1, "ग": 2, "घ": 3, "ङ": 4,
        "(a)": 0, "(b)": 1, "(c)": 2, "(d)": 3,
        "(1)": 0, "(2)": 1, "(3)": 2, "(4)": 3,
        "(१)": 0, "(२)": 1, "(३)": 2, "(४)": 3,
        "(क)": 0, "(ख)": 1, "(ग)": 2, "(घ)": 3,
        "option a": 0, "option b": 1, "option c": 2, "option d": 3,
        "option 1": 0, "option 2": 1, "option 3": 2, "option 4": 3,
        "option १": 0, "option २": 1, "option ३": 2, "option ४": 3,
        "विकल्प a": 0, "विकल्प b": 1, "विकल्प c": 2, "विकल्प d": 3,
        "विकल्प 1": 0, "विकल्प 2": 1, "विकल्प 3": 2, "विकल्प 4": 3,
        "विकल्प १": 0, "विकल्प २": 1, "विकल्प ३": 2, "विकल्प ४": 3,
        "विकल्प क": 0, "विकल्प ख": 1, "विकल्प ग": 2, "विकल्प घ": 3,
        "उत्तर a": 0, "उत्तर b": 1, "उत्तर c": 2, "उत्तर d": 3,
        "उत्तर 1": 0, "उत्तर 2": 1, "उत्तर 3": 2, "उत्तर 4": 3,
        "उत्तर १": 0, "उत्तर २": 1, "उत्तर ३": 2, "उत्तर ४": 3,
        "उत्तर क": 0, "उत्तर ख": 1, "उत्तर ग": 2, "उत्तर घ": 3,
    }

    clean_questions = []
    for item in questions:
        if not isinstance(item, dict):
            continue
        q_text = str(item.get("question", "")).strip()
        raw_options = item.get("options", [])
        
        # Handle options if provided as a dict (e.g. {"A": "...", "B": "..."})
        if isinstance(raw_options, dict):
            raw_options = list(raw_options.values())
        elif isinstance(raw_options, list):
            # Handle list of dicts: [{"text": "..."}, ...]
            parsed_opts = []
            for ro in raw_options:
                if isinstance(ro, dict):
                    parsed_opts.append(ro.get("text", ro.get("option", str(ro))))
                else:
                    parsed_opts.append(str(ro))
            raw_options = parsed_opts
            
        raw_correct = str(item.get("correct_answer", "")).strip()
        raw_explanation = str(item.get("explanation", "")).strip()
        diff = item.get("difficulty", difficulty or "medium")

        if not q_text:
            continue

        # Clean options: remove prefixes like "A. ", "A) ", "(A) ", "1. ", "क. ", "१. ", "विकल्प 1: "
        prefix_pattern = r'^(?:(?:[\(\[]?[A-Ea-e1-5क-ङ१-५][\.\)\-\]:]|\([A-Ea-e1-5क-ङ१-५]\)|\[[A-Ea-e1-5क-ङ१-५]\])\s*|\b(?:option|विकल्प|उत्तर)\s+[A-Ea-e1-5क-ङ१-५]?\s*[:\.\-]?\s*)'
        cleaned_opts = []
        if isinstance(raw_options, list):
            for opt in raw_options:
                s_opt = str(opt).strip()
                s_opt_clean = re.sub(prefix_pattern, '', s_opt, flags=re.IGNORECASE).strip()
                cleaned_opts.append(s_opt_clean if s_opt_clean else s_opt)

        # Detect question type (True/False vs MCQ)
        is_tf = (quiz_type == "true_false") or len(cleaned_opts) == 2

        if is_tf:
            # Normalize True/False options and correct_answer
            cleaned_opts = [t_label, f_label]
            lower_correct = raw_correct.lower().strip()
            if any(w in lower_correct for w in ["true", "सत्य", "सही", "सच्चा", "satya", "sahi"]):
                raw_correct = t_label
            elif any(w in lower_correct for w in ["false", "असत्य", "गलत", "झूठा", "asatya", "galat"]):
                raw_correct = f_label
            else:
                raw_correct = t_label
        else:
            # Ensure at least 4 options for MCQ
            if len(cleaned_opts) < 4:
                default_distractors = ["विकल्प A", "विकल्प B", "विकल्प C", "विकल्प D"] if is_hindi else ["Option A", "Option B", "Option C", "Option D"]
                for d in default_distractors:
                    if d not in cleaned_opts and len(cleaned_opts) < 4:
                        cleaned_opts.append(d)
                        
            # Handle correct_answer mapping for MCQ
            clean_correct_lookup = re.sub(r'[\.\)\-\]:\s]', '', raw_correct).strip().lower()
            if clean_correct_lookup in letter_map and letter_map[clean_correct_lookup] < len(cleaned_opts):
                raw_correct = cleaned_opts[letter_map[clean_correct_lookup]]
            else:
                # Strip prefix from correct_answer if present
                clean_ans = re.sub(prefix_pattern, '', raw_correct, flags=re.IGNORECASE).strip()
                # Try exact match with cleaned_opts
                matched = False
                for opt in cleaned_opts:
                    if opt.lower() == clean_ans.lower() or opt.lower() == raw_correct.lower():
                        raw_correct = opt
                        matched = True
                        break
                if not matched:
                    # Substring match
                    for opt in cleaned_opts:
                        if clean_ans and (clean_ans.lower() in opt.lower() or opt.lower() in clean_ans.lower()):
                            raw_correct = opt
                            matched = True
                            break
                if not matched:
                    raw_correct = cleaned_opts[0] if cleaned_opts else "Unknown"

        # Ensure explanation is valid
        if not raw_explanation:
            raw_explanation = f"सही उत्तर '{raw_correct}' है।" if is_hindi else f"The correct answer is '{raw_correct}'."

        clean_questions.append({
            "question": q_text,
            "options": cleaned_opts,
            "correct_answer": raw_correct,
            "explanation": raw_explanation,
            "difficulty": diff
        })

    # If we have fewer than target_count, supplement from mock database so user ALWAYS gets requested count (e.g. 10)
    if len(clean_questions) < target_count:
        needed = target_count - len(clean_questions)
        supplements = get_mock_quiz(topic, difficulty, needed * 2, language, quiz_type)
        existing_texts = set(q["question"].strip().lower() for q in clean_questions)
        for sq in supplements:
            if sq["question"].strip().lower() not in existing_texts:
                clean_questions.append(sq)
                existing_texts.add(sq["question"].strip().lower())
                if len(clean_questions) >= target_count:
                    break
        # If still short, cycle existing questions
        idx = 0
        while len(clean_questions) < target_count and len(clean_questions) > 0:
            clean_questions.append(clean_questions[idx % len(clean_questions)])
            idx += 1

    return clean_questions[:target_count]

def generate_quiz_via_groq(topic, difficulty, count, language, quiz_type, source_text):
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here" or len(GROQ_API_KEY.strip()) < 10:
        return None
        
    type_instruction = ""
    if quiz_type == "true_false":
        t_label = "True"
        f_label = "False"
        if language.lower() == "hindi":
            t_label = "सत्य"
            f_label = "असत्य"
        type_instruction = f'Questions MUST be True/False statement style, and the options list MUST consist of exactly these two elements: ["{t_label}", "{f_label}"].'
    elif quiz_type == "mcq":
        type_instruction = "Questions MUST be multiple-choice question style, with exactly 4 options."
    else: # Mixed
        type_instruction = 'Questions can be a mix of MCQ (4 options) and True/False (2 options).'

    prompt = f"""
    You are a professional quiz maker and expert educator. Generate a custom quiz.
    The quiz MUST have exactly {count} distinct questions at a "{difficulty}" difficulty level.
    
    Language constraints:
    - The entire JSON payload (including question text, option choices, and explanations) MUST be written in "{language}". Do not translate technical keywords if they are commonly understood in English (e.g., variable names, functions like print()), but write the description and options in the chosen language "{language}".
    
    Question formats:
    - {type_instruction}
    
    STRICT Rules for options and correct_answer:
    - "options": Must be a JSON array of strings containing ONLY the answer choices. DO NOT include prefixes like "A.", "B.", "1.", "क.", "१." inside the option strings. Example: ["विकल्प 1", "विकल्प 2", "विकल्प 3", "विकल्प 4"].
    - "correct_answer": MUST be the exact matching string from the "options" array. NEVER return "A", "B", "C", "D" or an index.
    
    Output Format:
    You must return a valid JSON object containing a single key "questions" which is a list of exactly {count} question objects.
    Example schema:
    {{
      "questions": [
        {{
          "question": "The question text in {language}?",
          "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
          "correct_answer": "Option 1",
          "explanation": "A short, helpful explanation of why this answer is correct in {language}."
        }}
      ]
    }}
    """

    if source_text:
        prompt += f"""
        Source text constraints:
        - You MUST generate these {count} questions based ONLY on the contents of the text provided below.
        - Do not use external knowledge or invent facts outside this text:
        ---
        {source_text[:12000]}
        ---
        """
    else:
        prompt += f"""
        Topic constraint:
        - The quiz topic is: "{topic}".
        """

    # Active and verified models on Groq
    models_to_try = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b-32768",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]
    import urllib.request
    import urllib.error
    import json

    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3,
            "max_tokens": 8192
        }
        try:
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/chat/completions",
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY.strip()}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode('utf-8'))
                content = res_data['choices'][0]['message']['content'].strip()
                raw_qs = robust_json_extract_and_parse(content)
                if raw_qs:
                    sanitized = sanitize_and_validate_questions(raw_qs, language, quiz_type, count, topic=topic, difficulty=difficulty)
                    if sanitized and len(sanitized) >= count:
                        return sanitized[:count]
                    elif sanitized:
                        return sanitized
        except Exception as e:
            logging.warning(f"Groq generation failed with model {model}: {e}")
            continue
            
    return None

@app.route('/api/status', methods=['GET'])
def get_status():
    global is_gemini_configured
    API_KEY = os.getenv("GEMINI_API_KEY")
    if API_KEY and API_KEY != "your_gemini_api_key_here" and len(API_KEY.strip()) > 10:
        try:
            genai.configure(api_key=API_KEY)
            is_gemini_configured = True
        except:
            is_gemini_configured = False
    else:
        is_gemini_configured = False
        
    GROQ_KEY = os.getenv("GROQ_API_KEY")
    is_groq_configured = GROQ_KEY and GROQ_KEY != "your_groq_api_key_here" and len(GROQ_KEY.strip()) > 10
            
    if is_groq_configured:
        mode_str = "Groq Llama-3 AI Mode"
    elif is_gemini_configured:
        mode_str = "Gemini AI Mode"
    else:
        mode_str = "Mock Quiz Mode (API Key Missing)"
        
    return jsonify({
        "status": "online",
        "gemini_connected": is_gemini_configured,
        "groq_connected": bool(is_groq_configured),
        "mode": mode_str
    })

@app.route('/api/generate-quiz', methods=['POST'])
def generate_quiz():
    global is_gemini_configured
    
    # Read parameters (handle both JSON and Multipart FormData for file uploads)
    is_multipart = request.content_type and request.content_type.startswith('multipart/form-data')
    
    if is_multipart:
        topic = request.form.get("topic", "General Knowledge").strip()
        difficulty = request.form.get("difficulty", "medium").strip()
        count = int(request.form.get("count", 5))
        language = request.form.get("language", "English").strip()
        quiz_type = request.form.get("quiz_type", "mcq").strip()
        
        uploaded_file = request.files.get("file")
        source_text = ""
        
        if uploaded_file and uploaded_file.filename != '':
            filename = uploaded_file.filename.lower()
            if filename.endswith('.pdf'):
                source_text = extract_text_from_pdf(uploaded_file)
                logging.info(f"Extracted {len(source_text)} chars from uploaded PDF: {uploaded_file.filename}")
            elif filename.endswith('.txt'):
                source_text = extract_text_from_txt(uploaded_file)
                logging.info(f"Extracted {len(source_text)} chars from uploaded TXT: {uploaded_file.filename}")
    else:
        # JSON Request
        data = request.json or {}
        topic = data.get("topic", "General Knowledge").strip()
        difficulty = data.get("difficulty", "medium").strip()
        count = int(data.get("count", 5))
        language = data.get("language", "English").strip()
        quiz_type = data.get("quiz_type", "mcq").strip()
        source_text = ""

    if not topic:
        topic = "General Knowledge"
        
    logging.info(f"Generating quiz: Language={language}, Type={quiz_type}, Difficulty={difficulty}, Count={count}, File-uploaded={bool(source_text)}")

    # Try Groq first if configured
    groq_questions = generate_quiz_via_groq(topic, difficulty, count, language, quiz_type, source_text)
    if groq_questions and len(groq_questions) >= count:
        logging.info(f"Quiz successfully generated using Groq API (Llama 3) in {language}.")
        return jsonify({
             "success": True,
             "mode": "groq",
             "questions": groq_questions[:count]
        })

    # Prompt Engineering for Google Gemini
    if is_gemini_configured:
        try:
            # Customizing options based on quiz type and language
            type_instruction = ""
            if quiz_type == "true_false":
                t_label = "True"
                f_label = "False"
                if language.lower() == "hindi":
                    t_label = "सत्य"
                    f_label = "असत्य"
                type_instruction = f'Questions MUST be True/False statement style, and the options list MUST consist of exactly these two elements: ["{t_label}", "{f_label}"].'
            elif quiz_type == "mcq":
                type_instruction = "Questions MUST be multiple-choice question style, with exactly 4 options."
            else: # Mixed
                type_instruction = 'Questions can be a mix of MCQ (4 options) and True/False (2 options).'

            prompt = f"""
            You are a professional quiz maker and expert educator. Generate a custom quiz.
            The quiz MUST have exactly {count} questions at a "{difficulty}" difficulty level.
            
            Language constraints:
            - The entire JSON payload (including question text, option choices, and explanations) MUST be written in "{language}". Do not translate technical keywords if they are commonly understood in English (e.g., variable names, functions like print()), but write the description and options in the chosen language "{language}".
            
            Question formats:
            - {type_instruction}
            
            JSON Escaping Rule:
            - CRITICAL: You must escape all inner double quotes inside the string values using a backslash (\\\"). Do not use unescaped raw double quotes inside strings.
            
            Output Format:
            You must return a valid JSON array of exactly {count} objects or a JSON object with a "questions" list key.
            Each object in the array must follow this schema:
            {{
              "question": "The question text in {language}?",
              "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
              "correct_answer": "Option 1",
              "explanation": "A short, helpful explanation in {language}."
            }}
            """

            if source_text:
                prompt += f"""
                Source text constraints:
                - You MUST generate these {count} questions based ONLY on the contents of the text provided below:
                ---
                {source_text[:12000]}
                ---
                """
            else:
                prompt += f"""
                Topic constraint:
                - The quiz topic is: "{topic}".
                """

            # Call Gemini
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.3,
                    "max_output_tokens": 8192
                }
            )
            
            raw_text = response.text.strip() if response and response.text else ""
            quiz_data = robust_json_extract_and_parse(raw_text)
            
            if quiz_data and len(quiz_data) > 0:
                sanitized_gemini = sanitize_and_validate_questions(quiz_data, language, quiz_type, count, topic=topic, difficulty=difficulty)
                if sanitized_gemini:
                    logging.info(f"Quiz successfully generated using Gemini API in {language}.")
                    return jsonify({
                         "success": True,
                         "mode": "gemini",
                         "questions": sanitized_gemini[:count]
                    })
            else:
                logging.error("Gemini response was empty or could not be parsed. Falling back to mock data.")
        except Exception as e:
            logging.error(f"Error during Gemini generation: {e}. Falling back to mock data.")
            
    # Mock Fallback
    mock_questions = []
    mode = "mock"
    msg = f"Showing mock quiz data because Gemini API Key is not set or failed. Language: {language}, Type: {quiz_type}."
    
    if source_text:
        mock_questions = generate_mock_quiz_from_text(source_text, count, quiz_type, language)
        if mock_questions:
            mode = "document_fallback"
            msg = "Generated mock quiz dynamically from the uploaded document text."
            
    if not mock_questions:
        mock_questions = get_mock_quiz(topic, difficulty, count, language, quiz_type)
        
    sanitized_mock = sanitize_and_validate_questions(mock_questions, language, quiz_type, count, topic=topic, difficulty=difficulty)
    return jsonify({
        "success": True,
        "mode": mode,
        "questions": sanitized_mock[:count] if sanitized_mock else mock_questions[:count],
        "message": msg
    })

@app.route('/api/save-key', methods=['POST'])
def save_key():
    global is_gemini_configured
    data = request.json or {}
    key = data.get("api_key", "").strip()
    
    if not key or key.lower() == "disconnect":
        is_gemini_configured = False
        os.environ["GEMINI_API_KEY"] = "your_gemini_api_key_here"
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        try:
            with open(env_path, 'w') as f:
                f.write("GEMINI_API_KEY=your_gemini_api_key_here\n")
            logging.info("Gemini API Key cleared via Settings API endpoint.")
            return jsonify({
                "success": True, 
                "message": "API Key cleared successfully! Using Mock Quiz Mode."
            })
        except Exception as e:
            logging.error(f"Error clearing key: {e}")
            return jsonify({"success": False, "message": f"Failed to clear API key: {str(e)}"})
        
    try:
        # Configure Gemini in memory
        genai.configure(api_key=key)
        is_gemini_configured = True
        
        # Save key to .env file dynamically
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        with open(env_path, 'w') as f:
            f.write(f"GEMINI_API_KEY={key}\n")
            
        # Overwrite current env variable
        os.environ["GEMINI_API_KEY"] = key
        
        logging.info("Gemini API Key successfully updated via Settings API endpoint.")
        return jsonify({
            "success": True, 
            "message": "API Key saved successfully! Live AI Mode is now active."
        })
    except Exception as e:
        is_gemini_configured = False
        logging.error(f"Error configuring key dynamically: {e}")
        return jsonify({
            "success": False, 
            "message": f"Failed to configure API key: {str(e)}"
        })

# Configure MongoDB Cloud Database
MONGO_URI = os.getenv("MONGO_URI", "").strip()
mongo_client = None
mongo_db = None
is_mongo_active = False

if MONGO_URI:
    try:
        from pymongo import MongoClient
        mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Verify connection
        mongo_client.admin.command('ping')
        mongo_db = mongo_client['quiz_platform']
        is_mongo_active = True
        logging.info("Successfully connected to MongoDB Cloud Database!")
    except Exception as e:
        logging.error(f"Failed to connect to MongoDB Cloud Database: {e}. Falling back to local data.json.")
        is_mongo_active = False

# User Auth and Profile Database APIs
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')



def load_data():
    if is_mongo_active and mongo_db is not None:
        try:
            users_doc = mongo_db.users.find({}, {'_id': 0})
            users_dict = {}
            for u in users_doc:
                if "username" in u:
                    users_dict[u["username"]] = u

            history_doc = list(mongo_db.history.find({}, {'_id': 0}).sort("date_created", -1))
            return {"users": users_dict, "history": history_doc}
        except Exception as e:
            logging.error(f"Error loading data from MongoDB: {e}")

    # Fallback to JSON file
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "history": []}
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        logging.error(f"Error loading database file: {e}")
        return {"users": {}, "history": []}

def save_data(data):
    if is_mongo_active and mongo_db is not None:
        try:
            # Sync users to MongoDB
            for username, user_info in data.get("users", {}).items():
                mongo_db.users.update_one(
                    {"username": username},
                    {"$set": user_info},
                    upsert=True
                )
            
            # Sync history items (remove deleted, insert new)
            mongo_db.history.delete_many({})
            if data.get("history"):
                mongo_db.history.insert_many(data.get("history"))
        except Exception as e:
            logging.error(f"Error saving data to MongoDB: {e}")

    # Local file save (always write to local data.json for permanent local backup)
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logging.error(f"Error saving database file: {e}")


@app.route('/api/admin-data', methods=['GET'])
def api_admin_data():
    secret = request.args.get("secret", "")
    if secret != "kirtan":
        return jsonify({"success": False, "message": "Unauthorized"}), 401
    db = load_data()
    return jsonify(db)

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        return jsonify({"success": False, "message": "All fields are required."})

    if not email.lower().endswith("@gmail.com"):
        return jsonify({"success": False, "message": "Invalid Email"})

    if len(password) < 6:
        return jsonify({"success": False, "message": "Password must be at least 6 characters long."})

    if not re.search(r'[A-Z]', password):
        return jsonify({"success": False, "message": "Password must contain at least one capital letter."})

    if not re.search(r'[0-9]', password):
        return jsonify({"success": False, "message": "Password must contain at least one number."})

    if not re.search(r'[^A-Za-z0-9]', password):
        return jsonify({"success": False, "message": "Password must contain at least one symbol (e.g. @, #, $, !)."})

    db = load_data()
    if username in db["users"]:
        return jsonify({"success": False, "message": "Username already exists."})

    import datetime
    db["users"][username] = {
        "username": username,
        "email": email,
        "password": password,
        "date_created": datetime.datetime.utcnow().isoformat() + "Z"
    }
    save_data(db)
    return jsonify({"success": True, "message": "Registration successful!"})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"success": False, "message": "Username and password are required."})

    db = load_data()
    user = db["users"].get(username)
    if not user or user["password"] != password:
        return jsonify({"success": False, "message": "Invalid username or password."})

    return jsonify({
        "success": True,
        "user": {
            "username": user["username"],
            "email": user["email"]
        }
    })

@app.route('/api/get-profile', methods=['GET'])
def api_get_profile():
    username = request.args.get("username", "").strip().lower()
    if not username:
        return jsonify({"success": False, "message": "Username is required."})

    db = load_data()
    user = db["users"].get(username)
    if not user:
        return jsonify({"success": False, "message": "User not found."})

    # Get history
    user_history = [h for h in db["history"] if h["username"] == username]
    
    # Calculate stats
    total_quizzes = len(user_history)
    avg_score = 0
    highest_score = 0
    if total_quizzes > 0:
        total_score = sum(h["score"] for h in user_history)
        avg_score = round(total_score / total_quizzes, 1)
        highest_score = max(h["score"] for h in user_history)

    # Calculate achievements badges (6 total badges)
    badges = [
        {"name": "First Step", "desc": "Completed your first quiz", "icon": "🎓", "unlocked": total_quizzes >= 1},
        {"name": "Quiz Master", "desc": "Completed 5 quizzes", "icon": "🏆", "unlocked": total_quizzes >= 5},
        {"name": "Perfectionist", "desc": "Scored 5/5 on any quiz", "icon": "💎", "unlocked": highest_score >= 5},
        {"name": "Smart Brain", "desc": "Scored 4/5 or higher on any quiz", "icon": "💡", "unlocked": highest_score >= 4},
        {"name": "Language Learner", "desc": "Took a quiz in English or Hindi", "icon": "🌐", "unlocked": total_quizzes >= 1},
        {"name": "Dedicated", "desc": "Completed 10 quizzes", "icon": "🔥", "unlocked": total_quizzes >= 10}
    ]

    return jsonify({
        "success": True,
        "data": {
            "profile": {
                "username": user["username"],
                "email": user["email"],
                "date_created": user["date_created"]
            },
            "stats": {
                "total_quizzes": total_quizzes,
                "avg_score": avg_score,
                "highest_score": highest_score
            },
            "badges": badges,
            "history": user_history
        }
    })

@app.route('/api/save-score', methods=['POST'])
def api_save_score():
    data = request.json or {}
    username = data.get("username", "").strip().lower()
    category = data.get("category", "").strip()
    score = int(data.get("score", 0))
    total_questions = int(data.get("total_questions", 5))
    time_taken = data.get("time_taken", "0:00")

    if not username:
        return jsonify({"success": False, "message": "Username is required."})

    db = load_data()
    if "users" not in db:
        db["users"] = {}
    if "history" not in db:
        db["history"] = []

    # Case-insensitive user lookup
    matched_user = None
    for u in db["users"]:
        if u.lower() == username.lower():
            matched_user = u
            break
            
    if not matched_user:
        matched_user = username
        db["users"][username] = {
            "username": username,
            "email": f"{username}@guest.com",
            "password": "",
            "date_created": datetime.datetime.utcnow().isoformat() + "Z"
        }
    username = matched_user

    import datetime
    db["history"].insert(0, {
        "username": username,
        "category": category,
        "score": score,
        "total_questions": total_questions,
        "time_taken": time_taken,
        "date_created": datetime.datetime.utcnow().isoformat() + "Z"
    })
    save_data(db)
    return jsonify({"success": True, "message": "Score saved successfully!"})

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    db = load_data()
    history = db.get("history", [])
    
    def parse_time_to_seconds(time_str):
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            return 999999
        except:
            return 999999
            
    # Filter out entries without a username
    valid_history = [h for h in history if h.get("username")]

    # Sort all entries by accuracy (percentage) descending, then by time ascending
    sorted_candidates = sorted(
        valid_history, 
        key=lambda h: (-(int(h.get("score", 0)) / max(int(h.get("total_questions", 5)), 1)), parse_time_to_seconds(h.get("time_taken", "0:00")), h.get("date_created", ""))
    )
    
    # Return top 20 attempts (all users, all quizzes)
    top_attempts = sorted_candidates[:20]
    
    return jsonify({
        "success": True,
        "leaderboard": top_attempts
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
