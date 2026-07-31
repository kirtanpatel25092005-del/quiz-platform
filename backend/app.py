import os
import json
import logging
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
    
    # Split text into sentences
    sentences = re.split(r'[.!?।]\s*', source_text)
    clean_sentences = []
    for s in sentences:
        s_clean = s.strip().replace('\n', ' ')
        # Filter for reasonable sentence sizes
        if 40 < len(s_clean) < 180:
            clean_sentences.append(s_clean)
            
    # Remove duplicates
    clean_sentences = list(dict.fromkeys(clean_sentences))
    
    # If we have very few sentences, fallback to default mock
    if len(clean_sentences) < 3:
        return None
        
    random.shuffle(clean_sentences)
    questions = []
    
    # Localization for options/explanations
    local_labels = {
        "english": {"true": "True", "false": "False", "based_on": "Based on the uploaded document: "},
        "gujarati": {"true": "સાચું", "false": "ખોટું", "based_on": "અપલોડ કરેલ દસ્તાવેજ મુજબ: "},
        "hindi": {"true": "सत्य", "false": "असत्य", "based_on": "अपलोड किए गए दस्तावेज़ के अनुसार: "}
    }
    lang_lower = language.lower()
    labels = local_labels.get(lang_lower, local_labels["english"])
    
    for sen in clean_sentences:
        if len(questions) >= count:
            break
            
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
                # Simple negation
                negations = {
                    "english": ["It is not true that ", "False that: "],
                    "gujarati": ["એવું નથી કે ", "ખોટું વિધાન છે કે "],
                    "hindi": ["यह सत्य नहीं है कि ", "गलत कथन है कि "]
                }
                neg_prefix = random.choice(negations.get(lang_lower, negations["english"]))
                q_text = neg_prefix + sen[0].lower() + sen[1:] if lang_lower == "english" else neg_prefix + sen
                correct = labels["false"]
                explanation = labels["based_on"] + f"The statement has been negated."
                
            questions.append({
                "question": q_text,
                "options": [labels["true"], labels["false"]],
                "correct_answer": correct,
                "explanation": explanation
            })
            
        else:
            # Generate MCQ: find a word to blank out
            words = re.findall(r'\b\w{5,15}\b', sen)
            if not words:
                # Fallback to T/F
                questions.append({
                    "question": sen,
                    "options": [labels["true"], labels["false"]],
                    "correct_answer": labels["true"],
                    "explanation": labels["based_on"] + f"'{sen}'"
                })
                continue
                
            target_word = random.choice(words)
            q_text = sen.replace(target_word, "_______")
            
            # Find distractors from the source text
            all_words = re.findall(r'\b\w{5,15}\b', source_text)
            all_words = list(set([w for w in all_words if w.lower() != target_word.lower()]))
            
            if len(all_words) < 3:
                distractors = ["Option A", "Option B", "Option C"]
            else:
                distractors = random.sample(all_words, min(3, len(all_words)))
                
            options = distractors + [target_word]
            random.shuffle(options)
            
            questions.append({
                "question": q_text,
                "options": options,
                "correct_answer": target_word,
                "explanation": labels["based_on"] + f"The blank word is '{target_word}' to complete: '{sen}'."
            })
            
    return questions

# Fallback Mock Quiz Data Generator supporting multi-language and quiz types
def get_mock_quiz(topic, difficulty, count, language, quiz_type):
    lang_lower = language.lower()
    type_lower = quiz_type.lower()
    topic_lower = topic.lower()
    
    # Simple localization dictionary
    local_labels = {
        "english": {"true": "True", "false": "False", "exp": "Explanation"},
        "gujarati": {"true": "સાચું", "false": "ખોટું", "exp": "સમજૂતી"},
        "hindi": {"true": "सत्य", "false": "असत्य", "exp": "स्पष्टीकरण"}
    }
    labels = local_labels.get(lang_lower, local_labels["english"])
    
    # Identify Topic Category
    if "html" in topic_lower or "એચટીએમએલ" in topic_lower or "एचटीएमएल" in topic_lower:
        topic_cat = "html"
    elif "css" in topic_lower or "સીએસએસ" in topic_lower or "सीएसएस" in topic_lower:
        topic_cat = "css"
    elif "javascript" in topic_lower or "js" in topic_lower or "જાવાસ્ક્રિપ્ટ" in topic_lower or "जावास्क्रिप्ट" in topic_lower:
        topic_cat = "javascript"
    elif "python" in topic_lower or "py" in topic_lower or "પાયથોન" in topic_lower or "पायथन" in topic_lower:
        topic_cat = "python"
    elif "cricket" in topic_lower or "ક્રિકેટ" in topic_lower or "क्रिकेट" in topic_lower:
        topic_cat = "cricket"
    elif "sport" in topic_lower or "game" in topic_lower or "play" in topic_lower or "ball" in topic_lower or "foot" in topic_lower or "soccer" in topic_lower or "રમત" in topic_lower or "રમતો" in topic_lower or "ખેલ" in topic_lower or "खेल" in topic_lower:
        topic_cat = "sports"
    elif "general" in topic_lower or "knowledge" in topic_lower or "gk" in topic_lower or "સામાન્ય" in topic_lower or "સામાન્ય જ્ઞાન" in topic_lower or "सामान्य" in topic_lower or "सामान्य ज्ञान" in topic_lower:
        topic_cat = "gk"
    elif "tech" in topic_lower or "computer" in topic_lower or "ટેકનોલોજી" in topic_lower or "કમ્પ્યુટર" in topic_lower or "कंप्यूटर" in topic_lower or "तकीनीकी" in topic_lower or "तकनीक" in topic_lower:
        topic_cat = "tech"
    elif "ai" in topic_lower or "generative" in topic_lower or "llm" in topic_lower or "gpt" in topic_lower or "એઆઈ" in topic_lower or "एआई" in topic_lower:
        topic_cat = "ai"
    elif "space" in topic_lower or "astronomy" in topic_lower or "universe" in topic_lower or "અવકાશ" in topic_lower or "બ્રહ્માંડ" in topic_lower or "अंतरिक्ष" in topic_lower or "ब्रह्मांड" in topic_lower:
        topic_cat = "space"
    elif "history" in topic_lower or "india" in topic_lower or "war" in topic_lower or "king" in topic_lower or "ઇતિહાસ" in topic_lower or "ભારત" in topic_lower or "इतिहास" in topic_lower or "भारत" in topic_lower:
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
        "gujarati": {
            "html": {
                "true_false": [
                    {"question": "HTML એ એક પ્રોગ્રામિંગ લેંગ્વેજ છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "HTML એ એક માર્કઅપ લેંગ્વેજ છે, તેમાં પ્રોગ્રામિંગ લોજિક હોતું નથી.", "difficulty": "easy"},
                    {"question": "HTML નું પૂરું નામ Hyper Text Markup Language છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "હા, HTML એટલે Hyper Text Markup Language.", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "HTML માં સૌથી મોટું હેડિંગ કયું છે?", "options": ["<h6>", "<head>", "<h1>", "<heading>"], "correct_answer": "<h1>", "explanation": "HTML માં <h1> સૌથી મોટું હેડિંગ છે.", "difficulty": "easy"}
                ]
            },
            "css": {
                "true_false": [
                    {"question": "CSS નો ઉપયોગ વેબસાઈટની ડિઝાઇન અને સ્ટ્રક્ચર બનાવવા માટે થાય છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "હા, CSS પેજને કલર અને સ્ટાઇલ આપવા માટે વપરાય છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "CSS નું પૂરું નામ શું છે?", "options": ["Computer Style Sheets", "Creative Style Sheets", "Cascading Style Sheets", "Colorful Style Sheets"], "correct_answer": "Cascading Style Sheets", "explanation": "CSS એટલે Cascading Style Sheets.", "difficulty": "easy"}
                ]
            },
            "javascript": {
                "true_false": [
                    {"question": "JavaScript કેસ-સેન્સિટિવ ભાષા છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "હા, JS કેસ સેન્સિટિવ છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "જાવાસ્ક્રિપ્ટમાં કયો કીવર્ડ વેરિએબલ ડિક્લેર કરવા માટે વપરાય છે?", "options": ["var", "let", "const", "આપેલ તમામ"], "correct_answer": "આપેલ તમામ", "explanation": "જાવાસ્ક્રિપ્ટમાં વેરિએબલ માટે var, let, અને const ત્રણેય વપરાય છે.", "difficulty": "easy"}
                ]
            },
            "sports": {
                "true_false": [
                    {"question": "ફૂટબોલની એક ટીમમાં મેદાન પર 11 ખેલાડીઓ રમે છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, ફૂટબોલની મેદાન પરની ટીમમાં 11 ખેલાડીઓ હોય છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "વર્ષ 2022 નો ફીફા વર્લ્ડ કપ કયો દેશ જીત્યો હતો?", "options": ["ફ્રાન્સ", "બ્રાઝિલ", "આર્જેન્ટિના", "પોર્ટુગલ"], "correct_answer": "આર્જેન્ટિના", "explanation": "આર્જેન્ટિનાએ 2022 નો વર્લ્ડ કપ જીત્યો હતો.", "difficulty": "easy"}
                ]
            },
            "cricket": {
                "true_false": [
                    {"question": "ક્રિકેટ મેચમાં દરેક ટીમમાં 11 ખેલાડીઓ હોય છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, દરેક ટીમમાં 11 ખેલાડીઓ રમે છે.", "difficulty": "easy"},
                    {"question": "આઈસીસી વનડે ક્રિકેટ વર્લ્ડ કપ દર ચાર વર્ષે રમાય છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, વનડે વર્લ્ડ કપ દર 4 વર્ષે એકવાર યોજાય છે.", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "ક્રિકેટમાં 'સેન્ચુરી' એટલે કેટલા રન થાય?", "options": ["50", "100", "150", "200"], "correct_answer": "100", "explanation": "સેન્ચુરી એટલે કોઈ એક બેટ્સમેન દ્વારા એક જ ઇનિંગ્સમાં કરાયેલા 100 રન.", "difficulty": "easy"},
                    {"question": "કયા ભારતીય ક્રિકેટરને 'માસ્ટર બ્લાસ્ટર' તરીકે ઓળખવામાં આવે છે?", "options": ["સચિન તેંડુલકર", "એમ એસ ધોની", "વિરાટ કોહલી", "કપિલ દેવ"], "correct_answer": "સચિન તેંડુલકર", "explanation": "સચિન તેંડુલકરને ક્રિકેટ જગતના માસ્ટર બ્લાસ્ટર તરીકે ઓળખવામાં આવે છે.", "difficulty": "easy"},
                    {"question": "વર્ષ 2007 માં રમાયેલો પ્રથમ આઈસીસી ટી20 વર્લ્ડ કપ કયો દેશ જીત્યો હતો?", "options": ["પાકિસ્તાન", "ભારત", "ઓસ્ટ્રેલિયા", "વેસ્ટ ઇન્ડીઝ"], "correct_answer": "ભારत", "explanation": "ભારતે એમ એસ ધોનીની કેપ્ટનશીપ હેઠળ પ્રથમ ટી20 વર્લ્ડ કપ જીત્યો હતો.", "difficulty": "medium"}
                ]
            },
            "gk": {
                "true_false": [
                    {"question": "નદીનું પાણી હંમેશા મીઠું હોય છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, નદીઓમાં મીઠું પાણી વહે છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "ભારત દેશનું પાટનગર કયું છે?", "options": ["મુંબઈ", "નવી દિલ્હી", "ગાંધીનગર", "કોલકાતા"], "correct_answer": "નવી દિલ્હી", "explanation": "નવી દિલ્હી એ ભારતની રાજધાની છે.", "difficulty": "easy"}
                ]
            },
            "tech": {
                "true_false": [
                    {"question": "RAM એ કાયમી સંગ્રહસ્થાન ધરાવતી મેમરી છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "RAM એ અસ્થિર (Volatile) મેમરી છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "કમ્પ્યુટરનો મગજ કોને કહેવામાં આવે છે?", "options": ["RAM", "CPU", "Hard Disk", "Monitor"], "correct_answer": "CPU", "explanation": "CPU ને કમ્પ્યુટરનું મગજ કહેવામાં આવે છે.", "difficulty": "easy"}
                ]
            },
            "python": {
                "true_false": [
                    {"question": "Python એ કમ્પાઈલ કરેલી ભાષા છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "Python એ મુખ્યત્વે ઇન્ટરપ્રિટેડ ભાષા છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "પાયથોનમાં કયો કીવર્ડ ફંક્શન બનાવવા માટે વપરાય છે?", "options": ["function", "def", "fun", "create"], "correct_answer": "def", "explanation": "def કીવર્ડનો ઉપયોગ થાય છે.", "difficulty": "easy"}
                ]
            },
            "ai": {
                "true_false": [
                    {"question": "LLM એટલે Large Language Model.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, LLM એટલે Large Language Model.", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "Generative AI નું પૂરું નામ શું છે?", "options": ["Generative Artificial Intelligence", "General AI", "Global AI", "None of these"], "correct_answer": "Generative Artificial Intelligence", "explanation": "Generative AI એટલે Generative Artificial Intelligence.", "difficulty": "easy"}
                ]
            },
            "space": {
                "true_false": [
                    {"question": "સૂર્ય એક તારો છે.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "સાચું, સૂર્ય એ આપણા સૂર્યમંડળની મધ્યમાં આવેલો તારો છે.", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "સૂર્યમંડળનો સૌથી મોટો ગ્રહ કયો છે?", "options": ["શનિ", "ગુરુ", "પૃથ્વી", "મંગળ"], "correct_answer": "ગુરુ", "explanation": "ગુરુ એ સૂર્યમંડળનો સૌથી મોટો ગ્રહ છે.", "difficulty": "easy"}
                ]
            },
            "history": {
                "true_false": [
                    {"question": "ભારત દેશ ૧૯૪૭ માં આઝાદ થયો હતો.", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "હા, ભારત ૧૫ ઓગસ્ટ ૧૯૪૭ ના રોજ સ્વતંત્ર થયો હતો.", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "ભારતના લોખંડી પુરુષ તરીકે કોણ ઓળખાય છે?", "options": ["મહાત્મા ગાંધી", "જવાહરલાલ નેહરુ", "સરદાર વલ્લભભાઈ પટેલ", "સુભાષચંદ્ર બોઝ"], "correct_answer": "સરદાર વલ્લભભાઈ પટેલ", "explanation": "સરદાર વલ્લભભાઈ પટેલને ભારતના લોખંડી પુરુષ કહેવાય છે.", "difficulty": "easy"}
                ]
            }
        },
        "hindi": {
            "html": {
                "true_false": [
                    {"question": "HTML एक प्रोग्रामिंग भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["false"], "explanation": "HTML एक मार्कअप भाषा है, न कि प्रोग्रामिंग भाषा।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "HTML का पूर्ण रूप क्या है?", "options": ["Hyper Text Markup Language", "High Text Markup Language", "Hyper Text Media Language", "None of these"], "correct_answer": "Hyper Text Markup Language", "explanation": "HTML का अर्थ Hyper Text Markup Language है।", "difficulty": "easy"}
                ]
            },
            "css": {
                "true_false": [
                    {"question": "CSS का उपयोग वेब पेज को स्टाइल करने के लिए किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, CSS पेज को डिजाइन करने के लिए उपयोग किया जाता है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "CSS का पूर्ण रूप क्या है?", "options": ["Computer Style Sheets", "Cascading Style Sheets", "Creative Style Sheets", "Colorful Style Sheets"], "correct_answer": "Cascading Style Sheets", "explanation": "CSS का अर्थ Cascading Style Sheets है।", "difficulty": "easy"}
                ]
            },
            "javascript": {
                "true_false": [
                    {"question": "जावास्क्रिप्ट एक केस-सेंसिटिव भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, जावास्क्रिप्ट केस-सेंसिटिव है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "जावास्क्रिप्ट में वेरिएबल घोषित करने के लिए किस कीवर्ड का उपयोग किया जाता है?", "options": ["var", "let", "const", "इनमें से सभी"], "correct_answer": "इनमें से सभी", "explanation": "जावास्क्रिप्ट में var, let और const तीनों का उपयोग वेरिएबल घोषित करने के लिए होता है।", "difficulty": "easy"}
                ]
            },
            "sports": {
                "true_false": [
                    {"question": "फुटबॉल की एक टीम में मैदान पर 11 खिलाड़ी होते हैं।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, प्रत्येक फुटबॉल टीम में मैदान पर 11 खिलाड़ी खेलते हैं।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "2022 फीफा विश्व कप की विजेता टीम कौन सी थी?", "options": ["आर्जेन्टीना", "फ्रांस", "ब्राजील", "क्रोएशिया"], "correct_answer": "आर्जेन्टीना", "explanation": "आर्जेन्टीना ने फाइनल में फ्रांस को हराकर कप जीता।", "difficulty": "easy"}
                ]
            },
            "cricket": {
                "true_false": [
                    {"question": "वनडे क्रिकेट विश्व कप हर चार साल में आयोजित किया जाता है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, एकदिवसीय विश्व कप प्रत्येक चार वर्ष में होता है।", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "क्रिकेट में 'शतक' का क्या अर्थ है?", "options": ["50 रन", "100 रन", "150 रन", "200 रन"], "correct_answer": "100 रन", "explanation": "क्रिकेट में एक पारी में 100 रन बनाना शतक कहलाता है।", "difficulty": "easy"}
                ]
            },
            "gk": {
                "true_false": [
                    {"question": "माउंट एवरेस्ट दुनिया की सबसे ऊंची चोटी है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, माउंट एवरेस्ट दुनिया का सबसे ऊंचा शिखर है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "भारत की राजधानी क्या है?", "options": ["मुंबई", "नई दिल्ली", "कोलकाता", "चेन्नई"], "correct_answer": "नई दिल्ली", "explanation": "नई दिल्ली भारत की राजधानी है।", "difficulty": "easy"}
                ]
            },
            "tech": {
                "true_false": [
                    {"question": "RAM एक वोलाटाइल (अस्थायी) मेमोरी है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, बिजली बंद होने पर RAM का सारा डेटा नष्ट हो जाता है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "कंप्यूटर का मुख्य बोर्ड कौन सा है?", "options": ["CPU", "Motherboard", "RAM", "Hard Disk"], "correct_answer": "Motherboard", "explanation": "मदरबोर्ड मुख्य सर्किट बोर्ड है जो सभी हिस्सों को जोड़ता है।", "difficulty": "easy"}
                ]
            },
            "python": {
                "true_false": [
                    {"question": "Python एक इंटरप्रिटेड (Interpreted) भाषा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, पायथन कोड लाइन-दर-लाइन इंटरप्रिट और रन होता है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "Python में प्रिंट करने के लिए किस फंक्शन का उपयोग किया जाता है?", "options": ["echo()", "printf()", "print()", "console.log()"], "correct_answer": "print()", "explanation": "पायथन में कंसोल पर संदेश दिखाने के लिए print() का उपयोग होता है।", "difficulty": "easy"}
                ]
            },
            "ai": {
                "true_false": [
                    {"question": "LLM का पूर्ण रूप Large Language Model है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, LLM का पूर्ण रूप Large Language Model है।", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "AI का पूर्ण रूप क्या है?", "options": ["Artificial Intelligence", "Active Intelligence", "Automated Information", "None of these"], "correct_answer": "Artificial Intelligence", "explanation": "AI का पूर्ण रूप Artificial Intelligence है।", "difficulty": "easy"}
                ]
            },
            "space": {
                "true_false": [
                    {"question": "सूर्य एक तारा है।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, सूर्य हमारे सौरमंडल के केंद्र में स्थित एक तारा है।", "difficulty": "easy"}
                ],
                "mcq": [
                    {"question": "हमारे सौरमंडल का सबसे बड़ा ग्रह कौन सा है?", "options": ["शनि", "बृहस्पति", "पृथ्वी", "मंगल"], "correct_answer": "बृहस्पति", "explanation": "बृहस्पति सौरमंडल का सबसे विशाल ग्रह है।", "difficulty": "easy"}
                ]
            },
            "history": {
                "true_false": [
                    {"question": "भारत ने वर्ष 1947 में स्वतंत्रता प्राप्त की थी।", "options": [labels["true"], labels["false"]], "correct_answer": labels["true"], "explanation": "हाँ, भारत को 15 अगस्त 1947 को आजादी मिली थी।", "difficulty": "medium"}
                ],
                "mcq": [
                    {"question": "भारत के 'लौह पुरुष' के रूप में किसे जाना जाता है?", "options": ["महात्मा गांधी", "सरदार वल्लभभाई पटेल", "जवाहरलाल नेहरू", "सुभाष चंद्र बोस"], "correct_answer": "सरदार वल्लभभाई पटेल", "explanation": "सरदार वल्लभभाई पटेल को भारत का लौह पुरुष कहा जाता है।", "difficulty": "easy"}
                ]
            }
        }
    }
    
    # Get questions based on Language -> Topic -> Type
    lang_db = database.get(lang_lower, database["english"])
    topic_db = lang_db.get(topic_cat, lang_db["python"])
    
    if type_lower == "mixed":
        import random
        questions_list = topic_db.get("true_false", []) + topic_db.get("mcq", [])
        # Shuffle the mixed pool
        random.shuffle(questions_list)
    else:
        questions_list = topic_db.get(type_lower, topic_db.get("mcq", []))
    
    # Filter questions by difficulty (start with requested difficulty)
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
                
    # If we still need more unique questions, pull from 'gk' (General Knowledge) category of the same language
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

    # If still not enough, fall back to general database defaults
    if len(selected_questions) < count:
        fallback_db = database["english"]["python"]["mcq"]
        for q in fallback_db:
            if q not in selected_questions:
                selected_questions.append(q)
                if len(selected_questions) >= count:
                    break

    # Construct the final list. Only cycle as an absolute last resort.
    output_questions = []
    if selected_questions:
        for i in range(count):
            output_questions.append(selected_questions[i % len(selected_questions)])
    else:
        output_questions = database["english"]["python"]["mcq"][:count]
        
    return output_questions

def generate_quiz_via_groq(topic, difficulty, count, language, quiz_type, source_text):
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here" or len(GROQ_API_KEY.strip()) < 10:
        return None
        
    type_instruction = ""
    if quiz_type == "true_false":
        t_label = "True"
        f_label = "False"
        if language.lower() == "gujarati":
            t_label = "સાચું"
            f_label = "ખોટું"
        elif language.lower() == "hindi":
            t_label = "सत्य"
            f_label = "असत्य"
        type_instruction = f'Questions MUST be True/False statement style, and the options list MUST consist of exactly these two elements: ["{t_label}", "{f_label}"].'
    elif quiz_type == "mcq":
        type_instruction = "Questions MUST be multiple-choice question style, with exactly 4 options."
    else: # Mixed
        type_instruction = 'Questions can be a mix of MCQ (4 options) and True/False (2 options).'

    prompt = f"""
    You are a professional quiz maker and expert educator. Generate a custom quiz.
    The quiz should have exactly {count} questions at a "{difficulty}" difficulty level.
    
    Language constraints:
    - The entire JSON payload (including question text, option choices, and explanations) MUST be written in "{language}". Do not translate technical keywords if they are commonly understood in English (e.g., variable names, functions like print()), but write the description and options in the chosen language "{language}".
    
    Question formats:
    - {type_instruction}
    
    Output Format:
    You must return a valid JSON object containing a single key "questions" which is a list of question objects.
    Example schema:
    {{
      "questions": [
        {{
          "question": "The question text in {language}?",
          "options": ["Option 1", "Option 2", ...],
          "correct_answer": "The exact string corresponding to the correct answer (must match one of the items in options exactly)",
          "explanation": "A short, helpful explanation of why this answer is correct and why the other choices are incorrect, written in {language}."
        }}
      ]
    }}
    """

    if source_text:
        prompt += f"""
        Source text constraints:
        - You MUST generate these questions based ONLY on the contents of the text provided below.
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

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 4096
    }
    
    import urllib.request
    import urllib.error
    import json
    
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
            quiz_data = json.loads(content)
            if isinstance(quiz_data, dict) and "questions" in quiz_data:
                return quiz_data["questions"]
            elif isinstance(quiz_data, list):
                return quiz_data
    except Exception as e:
        logging.error(f"Error during Groq quiz generation: {e}")
        
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
    if groq_questions:
        logging.info(f"Quiz successfully generated using Groq API (Llama 3) in {language}.")
        return jsonify({
             "success": True,
             "mode": "groq",
             "questions": groq_questions
        })

    # Prompt Engineering for Google Gemini
    if is_gemini_configured:
        try:
            # Customizing options based on quiz type and language
            type_instruction = ""
            if quiz_type == "true_false":
                t_label = "True"
                f_label = "False"
                if language.lower() == "gujarati":
                    t_label = "સાચું"
                    f_label = "ખોટું"
                elif language.lower() == "hindi":
                    t_label = "सत्य"
                    f_label = "असत्य"
                type_instruction = f'Questions MUST be True/False statement style, and the options list MUST consist of exactly these two elements: ["{t_label}", "{f_label}"].'
            elif quiz_type == "mcq":
                type_instruction = "Questions MUST be multiple-choice question style, with exactly 4 options."
            else: # Mixed
                type_instruction = 'Questions can be a mix of MCQ (4 options) and True/False (2 options).'

            prompt = f"""
            You are a professional quiz maker and expert educator. Generate a custom quiz.
            The quiz should have exactly {count} questions at a "{difficulty}" difficulty level.
            
            Language constraints:
            - The entire JSON payload (including question text, option choices, and explanations) MUST be written in "{language}". Do not translate technical keywords if they are commonly understood in English (e.g., variable names, functions like print()), but write the description and options in the chosen language "{language}".
            
            Question formats:
            - {type_instruction}
            
            JSON Escaping Rule:
            - CRITICAL: You must escape all inner double quotes inside the string values (e.g., in the question, option list items, or explanations) using a backslash (\\\"). Do not use unescaped raw double quotes inside strings, as this will break JSON parsing.
            
            Output Format:
            You must return a valid JSON array of objects. Do NOT wrap the JSON in markdown blocks (do NOT use ```json ... ```).
            Each object in the array must follow this schema:
            {{
              "question": "The question text in {language}?",
              "options": ["Option 1", "Option 2", ...],
              "correct_answer": "The exact string corresponding to the correct answer (must match one of the items in options exactly)",
              "explanation": "A short, helpful explanation of why this answer is correct and why the other choices are incorrect, written in {language}."
            }}
            """

            if source_text:
                prompt += f"""
                Source text constraints:
                - You MUST generate these questions based ONLY on the contents of the text provided below.
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
            
            # Parse JSON safely
            quiz_data = None
            raw_text = response.text.strip()
            
            # Auto-repair truncated JSON array if needed
            if raw_text.startswith("[") and not raw_text.endswith("]"):
                logging.warning("Detected truncated JSON array from Gemini. Attempting auto-repair.")
                if raw_text.endswith(","):
                    raw_text = raw_text[:-1]
                raw_text += "]"
                
            try:
                quiz_data = json.loads(raw_text)
            except json.JSONDecodeError as jde:
                logging.warning(f"Initial JSON parse failed: {jde}. Attempting robust markdown block strip.")
                # Strip markdown blocks if present
                if raw_text.startswith("```"):
                    lines = raw_text.splitlines()
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw_text = "\n".join(lines).strip()
                try:
                    quiz_data = json.loads(raw_text)
                except json.JSONDecodeError as jde2:
                    logging.error(f"Failed to parse JSON. Raw response from Gemini: {response.text}")
                    raise jde2
            
            if isinstance(quiz_data, list) and len(quiz_data) > 0:
                logging.info(f"Quiz successfully generated using Gemini API in {language}.")
                return jsonify({
                     "success": True,
                     "mode": "gemini",
                     "questions": quiz_data
                })
            else:
                logging.error("Gemini response was not a valid list. Falling back to mock data.")
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
            msg = "Generated mock quiz dynamically from the uploaded document text (Gemini API Key missing/failed)."
            
    if not mock_questions:
        mock_questions = get_mock_quiz(topic, difficulty, count, language, quiz_type)
        
    return jsonify({
        "success": True,
        "mode": mode,
        "questions": mock_questions,
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

def cleanup_old_data(data):
    import datetime
    changed = False
    now = datetime.datetime.utcnow()
    ten_days_ago = now - datetime.timedelta(days=10)

    # 1. Clean up users
    users = data.get("users", {})
    new_users = {}
    for username, user_info in users.items():
        date_str = user_info.get("date_created")
        keep = True
        if date_str:
            try:
                dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                if dt < ten_days_ago:
                    keep = False
                    changed = True
            except Exception as e:
                logging.error(f"Error parsing date_created for user {username}: {e}")
        if keep:
            new_users[username] = user_info
    
    # 2. Clean up history
    history = data.get("history", [])
    new_history = []
    for item in history:
        date_str = item.get("date_created")
        keep = True
        if date_str:
            try:
                dt = datetime.datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                if dt.tzinfo is not None:
                    dt = dt.replace(tzinfo=None)
                if dt < ten_days_ago:
                    keep = False
                    changed = True
            except Exception as e:
                logging.error(f"Error parsing date_created for history item: {e}")
        if keep:
            new_history.append(item)
            
    if changed:
        data["users"] = new_users
        data["history"] = new_history
        
    return data, changed

def load_data():
    if is_mongo_active and mongo_db is not None:
        try:
            users_doc = mongo_db.users.find({}, {'_id': 0})
            users_dict = {}
            for u in users_doc:
                if "username" in u:
                    users_dict[u["username"]] = u

            history_doc = list(mongo_db.history.find({}, {'_id': 0}).sort("date_created", -1))
            
            data = {"users": users_dict, "history": history_doc}
            cleaned_data, changed = cleanup_old_data(data)
            if changed:
                save_data(cleaned_data)
            return cleaned_data
        except Exception as e:
            logging.error(f"Error loading data from MongoDB: {e}")

    # Fallback to JSON file
    if not os.path.exists(DATA_FILE):
        return {"users": {}, "history": []}
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        cleaned_data, changed = cleanup_old_data(data)
        if changed:
            save_data(cleaned_data)
        return cleaned_data
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
            return
        except Exception as e:
            logging.error(f"Error saving data to MongoDB: {e}")

    # Local file save
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
        {"name": "Language Learner", "desc": "Took a quiz in English or Gujarati", "icon": "🌐", "unlocked": total_quizzes >= 1},
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
    if username not in db["users"]:
        return jsonify({"success": False, "message": "User not found."})

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
            
    # Keep only the best score per user (highest score, tiebreaker faster time)
    user_best = {}
    for h in history:
        user = h.get("username")
        if not user:
            continue
        score = int(h.get("score", 0))
        total = int(h.get("total_questions", 5))
        time_sec = parse_time_to_seconds(h.get("time_taken", "0:00"))
        
        if user not in user_best:
            user_best[user] = h
        else:
            best_score = int(user_best[user].get("score", 0))
            best_total = int(user_best[user].get("total_questions", 5))
            best_time_sec = parse_time_to_seconds(user_best[user].get("time_taken", "0:00"))
            # Compare by percentage for fairness
            if score / max(total, 1) > best_score / max(best_total, 1):
                user_best[user] = h
            elif score / max(total, 1) == best_score / max(best_total, 1) and time_sec < best_time_sec:
                user_best[user] = h

    # Sort by percentage descending, then time ascending
    sorted_candidates = sorted(
        user_best.values(), 
        key=lambda h: (-(int(h.get("score", 0)) / max(int(h.get("total_questions", 5)), 1)), parse_time_to_seconds(h.get("time_taken", "0:00")), h.get("date_created", ""))
    )
    
    # Return top 10
    top_attempts = sorted_candidates[:10]
    
    return jsonify({
        "success": True,
        "leaderboard": top_attempts
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
