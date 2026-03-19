
import os
import sys
import re
import time
import json
import math
import random
import turtle
import difflib
import logging
import threading
from datetime import datetime


try:
    import pyttsx3
    import sounddevice as sd
    import soundfile as sf
    import speech_recognition as sr
    from duckduckgo_search import DDGS
except Exception as e:
    print("Missing dependency. Run:\n pip install pyttsx3 SpeechRecognition sounddevice soundfile duckduckgo-search")
    raise e


VOICE_RECORD_SECONDS = 4
LAST_SEARCH_FILE = "lexchat_env/last_search.json"
HISTORY_FILE = "lexchat_env/lexchat_history.json"
LOG_FILE = "lexchat_env/lexchat.log"
DEFAULT_VOICE_MODE = "calm"   # calm / balanced / energetic

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format="%(asctime)s %(levelname)s: %(message)s")

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def save_history(entry: dict):
    try:
        data = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        data.append(entry)
        # keep last 300
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data[-300:], f, indent=2)
    except Exception as e:
        logging.warning("save_history error: %s", e)


def init_engine(mode=DEFAULT_VOICE_MODE):
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    # choose defensively
    voice_female = 1 if len(voices) > 1 else 0
    voice_male = 0
    if mode == "calm":
        rate = 150
        vol = 0.85
        vid = voices[voice_female].id
    elif mode == "balanced":
        rate = 175
        vol = 0.95
        vid = voices[voice_male].id
    else:
        rate = 200
        vol = 1.0
        vid = voices[voice_male].id
    engine.setProperty("rate", rate)
    engine.setProperty("volume", vol)
    try:
        engine.setProperty("voice", vid)
    except Exception:
        pass
    return engine

def split_sentences(text):
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return [p.strip() for p in parts if p.strip()]

def speak_natural(engine, text, pause=0.34):
    if not text:
        return
    for p in split_sentences(text):
        engine.say(p)
        engine.runAndWait()
        time.sleep(pause)

def respond(engine, text, pause=0.34, log=True):
    print("LEXchat:", text)
    if log:
        logging.info("SPEAK: %s", text)
    speak_natural(engine, text, pause)


ENGINE = init_engine(DEFAULT_VOICE_MODE)

def set_voice_mode(mode):
    global ENGINE
    mode = mode.lower()
    if mode not in ("calm","balanced","energetic"):
        respond(ENGINE, "Voice mode not recognized. Use calm, balanced, or energetic.")
        return
    ENGINE = init_engine(mode)
    respond(ENGINE, f"Voice mode set to {mode}.")


def record_audio(filename="voice_temp.wav", duration=VOICE_RECORD_SECONDS, fs=44100):
    try:
        respond(ENGINE, f"Recording for {duration} seconds...", pause=0.12)
        recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
        sd.wait()
        sf.write(filename, recording, fs)
        respond(ENGINE, "Finished recording.", pause=0.08)
        logging.info("Saved recording to %s", filename)
        return filename
    except Exception as e:
        logging.error("record_audio error: %s", e)
        respond(ENGINE, "Recording failed. Check microphone permissions.", pause=0.1)
        return None

def recognize_file(filename="voice_temp.wav"):
    r = sr.Recognizer()
    try:
        with sr.AudioFile(filename) as source:
            audio = r.record(source)
        text = r.recognize_google(audio)
        logging.info("Recognized: %s", text)
        print("-> (speech->text):", text)
        return text.lower()
    except sr.UnknownValueError:
        respond(ENGINE, "I couldn't understand that audio.", pause=0.1)
        return ""
    except sr.RequestError:
        respond(ENGINE, "Speech service unavailable.", pause=0.1)
        return ""
    except Exception as e:
        logging.error("recognize_file error: %s", e)
        return ""


_NUMBER_WORDS = {
    **{str(i): i for i in range(0, 21)},
    "zero":0,"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,
    "ten":10,"eleven":11,"twelve":12,"thirteen":13,"fourteen":14,"fifteen":15,"sixteen":16,
    "seventeen":17,"eighteen":18,"nineteen":19,"twenty":20,
    "thirty":30,"forty":40,"fifty":50,"sixty":60,"seventy":70,"eighty":80,"ninety":90,
    "hundred":100,"thousand":1000,"million":1000000
}

def parse_number(text):
    if text is None:
        return None
    text = text.strip().lower()
    # direct numeric
    try:
        return float(text)
    except Exception:
        pass
    t = text.replace(",", "")
    tokens = re.findall(r"[a-z]+|\d+|\-|\.", t)
    if not tokens:
        return None
    total = 0
    current = 0
    for tok in tokens:
        if tok.isdigit():
            current += int(tok)
        elif tok in _NUMBER_WORDS:
            val = _NUMBER_WORDS[tok]
            if val >= 100:
                if current == 0:
                    current = 1
                current *= val
            else:
                current += val
        elif tok == "and":
            continue
        else:
            try:
                current += float(tok)
            except:
                pass
    if current != 0:
        return float(current)
    digits = re.search(r"[-+]?\d*\.?\d+", text)
    if digits:
        try:
            return float(digits.group())
        except:
            return None
    return None


def search_web(query, num_results=5):
    respond(ENGINE, f"Searching the web for {query} 🔍")
    results_list = []
    try:
       with DDGS() as ddgs:
            results = ddgs.text(query)
            count = 0
            for r in results:
                title = r.get("title","")
                link = r.get("href","")
                body = r.get("body","")
                # skip CJK
                if any('\u4e00' <= ch <= '\u9fff' for ch in (body or "")):
                    continue
                results_list.append({"title":title,"link":link,"snippet":body})
                count += 1
                if count >= num_results:
                    break
    except Exception as e:
        logging.error("search_web error: %s", e)
        respond(ENGINE, "Search failed due to an error.")
        return
    # save
    try:
        with open(LAST_SEARCH_FILE, "w", encoding="utf-8") as f:
            json.dump(results_list, f, indent=2)
    except Exception as e:
        logging.warning("could not save last search: %s", e)
    # speak short summaries
    for res in results_list:
        title = res.get("title") or "Untitled result"
        snippet = res.get("snippet") or ""
        link = res.get("link") or ""
        print("\n📰", title)
        print("🔗", link)
        print("📄", (snippet[:300] + "...") if len(snippet) > 300 else snippet)
        respond(ENGINE, title, pause=0.28)
        if snippet:
            respond(ENGINE, (snippet[:220] + ("..." if len(snippet) > 220 else "")), pause=0.18)
    respond(ENGINE, "Search results complete.")
    save_history({"type":"search","query":query,"time":now_str()})

def load_last_search():
    if os.path.exists(LAST_SEARCH_FILE):
        with open(LAST_SEARCH_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)
        respond(ENGINE, "Here are your last saved search results:")
        for r in results:
            print("\n📰", r.get("title"))
            print("🔗", r.get("link"))
            print("📄", (r.get("snippet") or "")[:300])
    else:
        respond(ENGINE, "No previous searches saved.")


def draw_flower(petals=6, size=50, color="magenta"):
    screen = turtle.Screen()
    t = turtle.Turtle()
    t.color(color)
    t.speed(6)
    for _ in range(petals):
        t.circle(size)
        t.left(360 / petals)
    screen.mainloop()

def draw_shape(shape="square", color="blue", size=100, speed=5):
    screen = turtle.Screen()
    t = turtle.Turtle()
    t.color(color)
    t.speed(speed)
    try:
        if shape == "square":
            for _ in range(4):
                t.forward(size)
                t.right(90)
        elif shape == "triangle":
            for _ in range(3):
                t.forward(size)
                t.left(120)
        elif shape == "circle":
            t.circle(size)
        elif shape == "star":
            for _ in range(5):
                t.forward(size)
                t.right(144)
        elif shape == "heart":
            t.begin_fill()
            t.color(color)
            t.left(140)
            t.forward(size)
            t.circle(-size/2,200)
            t.left(120)
            t.circle(-size/2,200)
            t.forward(size)
            t.end_fill()
        elif shape == "spiral":
            for i in range(60):
                t.forward(i * 3)
                t.right(91)
        elif shape.startswith("polygon"):
            try:
                sides = int(shape.split(":")[1])
                if sides < 3:
                    respond(ENGINE, "Polygon must have at least 3 sides.")
                else:
                    angle = 360.0 / sides
                    for _ in range(sides):
                        t.forward(size)
                        t.right(angle)
            except Exception:
                respond(ENGINE, "Invalid polygon format. Use polygon:n")
        elif shape.startswith("flower"):
            parts = shape.split(":")
            petals = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 6
            draw_flower(petals=petals, size=size//2, color=color)
            return
        else:
            respond(ENGINE, "Shape not recognized. Use square, triangle, circle, star, heart, spiral, polygon:n, flower:n")
    except Exception as e:
        logging.error("draw_shape error: %s", e)
        respond(ENGINE, "Drawing failed due to an error.")
    respond(ENGINE, "Drawing complete. Close the turtle window to continue.")
    screen.mainloop()


def generate_python(kind):
    kind = kind.lower()
    if kind == "function":
        code = ("def greet(name):\n"
                "    \"\"\"Greet someone by name.\"\"\"\n"
                "    print(f\"Hello, {name}!\")\n")
        explain = "Defines a function named greet that accepts one parameter name and prints a greeting."
    elif kind == "loop":
        code = ("for i in range(5):\n"
                "    print(i)\n")
        explain = "A for-loop printing numbers from 0 to 4."
    elif kind == "class":
        code = ("class Person:\n"
                "    def __init__(self, name):\n"
                "        self.name = name\n\n"
                "    def greet(self):\n"
                "        print(f\"Hello, {self.name}!\")\n")
        explain = "Defines a Person class with constructor and a greet method."
    elif kind == "file":
        code = ("with open('data.txt','w') as f:\n"
                "    f.write('Hello world')\n")
        explain = "Writes Hello world to a file named data.txt using a context manager."
    else:
        code = "# Unknown python snippet"
        explain = "Unknown snippet kind."
    return code, explain

def generate_html(kind):
    if kind == "basic":
        code = ("<!DOCTYPE html>\n<html>\n<head>\n  <meta charset='utf-8'>\n  <title>My Page</title>\n</head>\n<body>\n  <h1>Hello world</h1>\n</body>\n</html>\n")
        explain = "A minimal HTML page with a heading."
    elif kind == "form":
        code = ("<form action='#' method='post'>\n  <label for='name'>Name:</label>\n  <input id='name' name='name' type='text'>\n  <button type='submit'>Send</button>\n</form>\n")
        explain = "A simple HTML form for user input."
    else:
        code = "<!-- Unknown HTML snippet -->"
        explain = "Unknown HTML snippet."
    return code, explain

def generate_js(kind):
    if kind == "console":
        code = ("for (let i = 0; i < 5; i++) {\n  console.log(i);\n}\n")
        explain = "Logs numbers 0 to 4 to the browser console."
    elif kind == "alert":
        code = "alert('Hello Gabriel!');\n"
        explain = "Shows an alert popup in the browser."
    else:
        code = "// Unknown JS snippet"
        explain = "Unknown JS snippet."
    return code, explain

def generate_code(language, kind, save=False, filename=None):
    language = (language or "python").lower().strip()
    kind = (kind or "function").lower().strip()
    if language == "python":
        code, explain = generate_python(kind)
        ext = "py"
    elif language in ("html","htm"):
        code, explain = generate_html(kind)
        ext = "html"
    elif language in ("javascript","js"):
        code, explain = generate_js(kind)
        ext = "js"
    else:
        code = "// Language not supported"
        explain = "Language unsupported."
        ext = "txt"
    respond(ENGINE, "I generated the snippet and will explain it briefly.")
    print("\n--- CODE ---\n", code)
    respond(ENGINE, explain, pause=0.5)
    if save:
        if not filename:
            filename = f"snippet_{language}_{int(time.time())}.{ext}"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(code)
            respond(ENGINE, f"Saved snippet to {filename}.")
            save_history({"type":"code","lang":language,"kind":kind,"file":filename,"time":now_str()})
        except Exception as e:
            logging.error("save snippet error: %s", e)
            respond(ENGINE, "Failed to save snippet.")
    else:
        save_history({"type":"code","lang":language,"kind":kind,"time":now_str()})


def is_prime(n):
    n = int(n)
    if n <= 1: return False
    if n <= 3: return True
    if n % 2 == 0: return False
    r = int(math.sqrt(n))
    for i in range(3, r+1, 2):
        if n % i == 0:
            return False
    return True

EMOJIS = ["😄","😎","🤖","😜","🔥","💡","🎨","⚡","🌟","🧠","😂","😇","🤩","🚀","🎯","🎶","🕹️","📘","🐍","💻","🎲","💬","✨","❤️","🦾","🌈","📡","🧩","🎁","🔮"]
JOKES = [
    "Why did the computer go to the doctor? It caught a virus!",
    "Why was the math book sad? It had too many problems.",
    "Why don’t scientists trust atoms? Because they make up everything!",
    "Why did the programmer quit his job? Because he didn't get arrays.",
    "Why was the cell phone wearing glasses? It lost its contacts!",
    "Why did the AI go to school? To improve its neural network!",
    "Why did the cookie go to the hospital? Because it felt crummy!",
    "Why did the computer sneeze? It caught a flu bug!",
    "Why do programmers prefer dark mode? Because light attracts bugs!",
    "Why was the JavaScript developer sad? Because he didn't Node how to Express himself!",
    "Why did the computer break up with the internet? There was too much buffering!",
    "Why don’t robots get tired? They recharge!",
    "Why did the robot go on vacation? It needed to unwind!",
    "Why was the computer cold? It left its Windows open!",
    "Why did the AI cross the road? To optimize the other side!",
    "Why was the developer unhappy at his job? He wanted arrays!",
    "Why do computers love coffee? Because it helps them process!",
    "Why did the function stop calling itself? It had a stack overflow!",
    "Why do Python programmers wear glasses? Because they can't C!",
    "Why did the neural network go to therapy? Too many layers of problems!"
]
EMOJIS = ["😜","🔥","💡","🎨","⚡","🌟","🧠","😂","😇","🤩","🚀","🎯","🎶","🕹️","📘","🐍","💻","🎲","💬","✨","❤️","🦾","🌈","📡","🧩","🎁","🔮"]
FUN_FACTS = [
    "Honey never spoils.",
    "Octopuses have three hearts.",
    "Smiling can actually improve your mood.",
    "Bananas are berries; strawberries are not.",
    "There are more stars than grains of sand on Earth.",
    "Water can boil and freeze at once under special conditions.",
    "Wombat poop is cube-shaped.",
    "Sloths can hold their breath longer than dolphins.",
    "A day on Venus is longer than a year on Venus.",
    "Pineapples take two years to grow."
]

COMMANDS_HELP = [
    "search — search the web",
    "last search — show last search",
    "code — generate code (python/html/js) & explain",
    "draw / turtle — draw shapes (square, circle, triangle, star, heart, spiral, polygon:n, flower:n)",
    "joke — tell a joke",
    "fact — tell a fun fact",
    "time — tell current time",
    "math / calc — calculator, factorial, sqrt, prime check",
    "story — build a short story",
    "game — rock-paper-scissors",
    "lists/tuples/sets — show examples and help",
    "set voice — change voice to calm/balanced/energetic",
    "history — show recent actions",
    "help — show this list",
    "exit / quit — exit program"
]

def show_help():
    respond(ENGINE, "Here are things you can ask me. I'll also print them to console.")
    for c in COMMANDS_HELP:
        print("-", c)

INTENT_CANDIDATES = [
    "search","last search","code","draw","joke","fact","time",
    "math","story","game","help","set voice","history","lists","exit","quit"
]

def fuzzy_intent(text, cutoff=0.5):
    text = (text or "").lower().strip()
    match = difflib.get_close_matches(text, INTENT_CANDIDATES, n=1, cutoff=cutoff)
    return match[0] if match else None


def ask_input(prompt, mode="text", record_secs=VOICE_RECORD_SECONDS):
    if mode == "voice":
        filename = record_audio(duration=record_secs)
        if not filename:
            return ""
        return recognize_file(filename)
    else:
        try:
            return input(prompt)
        except KeyboardInterrupt:
            return ""


def execute_command(command, mode="text"):
    cmd = (command or "").strip().lower()
    logging.info("CMD: %s (mode=%s)", cmd, mode)
    save_history({"type":"command","cmd":cmd,"mode":mode,"time":now_str()})

    if cmd == "":
        return True


    if any(w in cmd for w in ["hello","hi","hey","good morning","good evening"]):
        respond(ENGINE, random.choice([f"Hello Gabriel {random.choice(EMOJIS)}","Hi Gabriel — ready when you are!", "Hey — what shall we do today?"]))
        return True


    if any(w in cmd for w in ["exit","quit","goodbye","bye"]):
        respond(ENGINE, "Goodbye Gabriel. Take care!", pause=0.3)
        return False


    if "help" in cmd or "commands" in cmd:
        show_help()
        return True

    if "set voice" in cmd or cmd.startswith("voice mode") or ("voice" in cmd and "set" in cmd):
        tokens = cmd.replace("set voice","").replace("voice mode","").replace("set voice to","").strip()
        if not tokens:
            respond(ENGINE, "Which mode: calm, balanced, or energetic?")
            ask = ask_input("Mode: ", mode=mode)
            tokens = ask.lower().strip()
        chosen = tokens.split()[0] if tokens else DEFAULT_VOICE_MODE
        if chosen in ("calm","balanced","energetic"):
            set_voice_mode(chosen)
        else:
            respond(ENGINE, "I only know calm, balanced, or energetic.")
        return True


    if "time" in cmd:
        t = datetime.now().strftime("%H:%M:%S")
        respond(ENGINE, f"The current time is {t} {random.choice(EMOJIS)}")
        return True


    if "history" in cmd:
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            respond(ENGINE, f"I have {len(data)} history entries. Showing last 8.")
            for item in data[-8:]:
                print(item)
        else:
            respond(ENGINE, "No history found.")
        return True


    if "joke" in cmd:
        respond(ENGINE, random.choice(JOKES) + " " + random.choice(EMOJIS))
        return True


    if "fact" in cmd:
        respond(ENGINE, random.choice(FUN_FACTS) + " " + random.choice(EMOJIS))
        return True

    if "search" in cmd:
        respond(ENGINE, "What should I search for?")
        query = ask_input("Search query: ", mode=mode)
        if query:
            search_web(query)
        return True

    if "last search" in cmd:
        load_last_search()
        return True

    if "draw" in cmd or "turtle" in cmd:
        respond(ENGINE, "Which shape would you like? (square, circle, triangle, star, heart, spiral, polygon:n, flower:n)")
        shape_resp = ask_input("Shape: ", mode=mode) or "square"
        shape = shape_resp.strip().lower()
        respond(ENGINE, "What color?")
        color = ask_input("Color: ", mode=mode) or "blue"
        respond(ENGINE, "What size? (say a number)")
        size_txt = ask_input("Size: ", mode=mode)
        size = int(parse_number(size_txt) or 100)
        respond(ENGINE, "What speed? (1 slow - 10 fast)")
        speed_txt = ask_input("Speed: ", mode=mode)
        speed = int(parse_number(speed_txt) or 5)
        respond(ENGINE, f"Okay — drawing {shape} in {color} size {size} speed {speed}.")
        t = threading.Thread(target=draw_shape, args=(shape,color,size,speed))
        t.start()
        save_history({"type":"draw","shape":shape,"color":color,"size":size,"speed":speed,"time":now_str()})
        return True


    if "code" in cmd or "generate code" in cmd:
        respond(ENGINE, "Which language? Python, HTML, or JavaScript?")
        lang = ask_input("Language: ", mode=mode) or "python"
        respond(ENGINE, "What kind of snippet? e.g., function, loop, basic, alert, class, form")
        kind = ask_input("Kind: ", mode=mode) or "function"
        respond(ENGINE, "Do you want me to save the snippet? say yes or no.")
        save_ans = ask_input("Save? (yes/no): ", mode=mode).lower()
        save_flag = save_ans.startswith("y")
        filename = None
        if save_flag:
            suggested = f"snippet_{lang}_{int(time.time())}.{ 'py' if 'py' in lang else ('html' if 'html' in lang else 'js') }"
            respond(ENGINE, f"Say filename or I will save as {suggested}.")
            fn = ask_input("Filename (or enter to accept): ", mode=mode).strip()
            filename = fn if fn else suggested
        generate_code(lang, kind, save=save_flag, filename=filename)
        return True


    if any(k in cmd for k in ["calc","calculator","math","compute","factorial","sqrt","prime"]):
        respond(ENGINE, "Math mode. Say operation: add, subtract, multiply, divide, power, factorial, sqrt, prime")
        op = ask_input("Operation: ", mode=mode).lower()
        if op in ("factorial","prime"):
            val_txt = ask_input("Number: ", mode=mode)
            val = parse_number(val_txt)
            if val is None:
                respond(ENGINE, "Couldn't parse that number.")
            else:
                if op == "factorial":
                    try:
                        res = math.factorial(int(val))
                        respond(ENGINE, f"Factorial of {int(val)} is {res}")
                    except Exception:
                        respond(ENGINE, "Failed to compute factorial.")
                else:
                    res = is_prime(int(val))
                    respond(ENGINE, f"{int(val)} is {'a prime' if res else 'not a prime'}.")
        else:
            a_txt = ask_input("First number: ", mode=mode)
            b_txt = ask_input("Second number: ", mode=mode)
            a = parse_number(a_txt); b = parse_number(b_txt)
            if a is None or b is None:
                respond(ENGINE, "Couldn't parse numbers.")
            else:
                if op in ("add","plus","+"):
                    respond(ENGINE, f"Result: {a + b}")
                elif op in ("subtract","minus","-"):
                    respond(ENGINE, f"Result: {a - b}")
                elif op in ("multiply","times","*"):
                    respond(ENGINE, f"Result: {a * b}")
                elif op in ("divide","/"):
                    if b == 0:
                        respond(ENGINE, "Cannot divide by zero.")
                    else:
                        respond(ENGINE, f"Result: {a / b}")
                elif op in ("power","pow"):
                    respond(ENGINE, f"Result: {a ** b}")
                else:
                    respond(ENGINE, "Operation not recognized.")
        return True


    if "story" in cmd:
        respond(ENGINE, "Let's make a short story! Give me a verb, a noun, and an adjective.")
        w1 = ask_input("Verb: ", mode=mode)
        w2 = ask_input("Noun: ", mode=mode)
        w3 = ask_input("Adjective: ", mode=mode)
        story = f"Once upon a time, a brave soul decided to {w1} the {w2}. Everything turned {w3 or 'strange'}, and they found something unexpected."
        respond(ENGINE, story, pause=0.6)
        save_history({"type":"story","words":[w1,w2,w3],"time":now_str()})
        return True


    if "weight" in cmd:
        wt_txt = ask_input("Enter weight: ", mode=mode)
        wt = parse_number(wt_txt)
        if wt is None:
            respond(ENGINE, "Couldn't parse weight.")
            return True
        unit = ask_input("Unit (K for kg / L for lbs): ", mode=mode).upper()
        if unit == "K":
            respond(ENGINE, f"{wt * 2.205:.2f} pounds")
        else:
            respond(ENGINE, f"{wt / 2.205:.2f} kilograms")
        return True

    if "temp" in cmd or "temperature" in cmd:
        t_txt = ask_input("Enter temperature: ", mode=mode)
        tv = parse_number(t_txt)
        if tv is None:
            respond(ENGINE, "Couldn't parse temperature.")
            return True
        unit = ask_input("Unit (C/F): ", mode=mode).upper()
        if unit == "C":
            respond(ENGINE, f"{(9*tv)/5 + 32:.1f} °F")
        else:
            respond(ENGINE, f"{(tv-32)*5/9:.1f} °C")
        return True


    if "game" in cmd or "rps" in cmd or "rock" in cmd:
        respond(ENGINE, "Let's play rock, paper, scissors! Say rock, paper, or scissors.")
        choice = ask_input("Your choice: ", mode=mode).lower()
        ai_choice = random.choice(["rock","paper","scissors"])
        respond(ENGINE, f"I choose {ai_choice}.")
        if choice == ai_choice:
            respond(ENGINE, "It's a tie!")
        elif (choice=="rock" and ai_choice=="scissors") or (choice=="paper" and ai_choice=="rock") or (choice=="scissors" and ai_choice=="paper"):
            respond(ENGINE, "You win! 🎉")
        else:
            respond(ENGINE, "I win! 😜")
        return True


    if any(k in cmd for k in ["list","tuple","set"]):
        respond(ENGINE, "Which type? list, tuple, or set?")
        typ = ask_input("Type: ", mode=mode).lower()
        if typ == "list":
            print(["apple","banana","orange","mango"])
        elif typ == "tuple":
            print(("dog","cat","bird","gorilla"))
        elif typ == "set":
            print({"toyota","bmw","rolls royce","land rover"})
        else:
            respond(ENGINE, "Unknown type.")
        return True


    fallback = fuzzy_intent(cmd, cutoff=0.45)
    if fallback:
        respond(ENGINE, f"It sounds like you meant: {fallback}. I'll try that.")
        return execute_command(fallback, mode)

    respond(ENGINE, "Sorry, I didn't quite catch that. Say 'help' to hear commands.")
    return True


def main():
    respond(ENGINE, "Welcome,  I'm, Lexchat, Say 'voice' to use voice or 'text' to type commands.")
    while True:
        mode = input("Mode (voice/text/quit): ").strip().lower()
        if mode in ("quit","exit"):
            respond(ENGINE, "Goodbye Sirs or Madams 🫣. Take care!")
            break
        if mode not in ("voice","text"):
            respond(ENGINE, "Please type 'voice' or 'text'.")
            continue

        if mode == "voice":
            filename = record_audio(duration=VOICE_RECORD_SECONDS)
            if not filename:
                continue
            cmd = recognize_file(filename)
        else:
            cmd = input("Enter command: ")

        if not cmd:
            continue
        cont = execute_command(cmd, mode=mode)
        if not cont:
            break

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        respond(ENGINE, "Interrupted. Goodbye.", pause=0.1)
        sys.exit(0)
